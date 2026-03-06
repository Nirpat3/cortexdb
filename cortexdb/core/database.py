"""
CortexDB Core - The Consciousness Layer
Router (Thalamus) + Security (Amygdala) + Optimizer (Prefrontal Cortex)

Every query flows: Amygdala (< 1ms) -> Router -> Optimizer -> Engine(s) -> Bridge -> Plasticity -> Response
"""

import asyncio
import hashlib
import json
import time
import logging
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger("cortexdb")


class CacheTier(Enum):
    R0_PROCESS = "R0"
    R1_MEMORY = "R1"
    R2_SEMANTIC = "R2"
    R3_PERSISTENT = "R3"
    R4_DEEP = "R4"


class EngineType(Enum):
    RELATIONAL = "relational"
    MEMORY = "memory"
    VECTOR = "vector"
    TEMPORAL = "temporal"
    STREAM = "stream"
    IMMUTABLE = "immutable"
    GRAPH = "graph"


@dataclass
class QueryResult:
    data: Any = None
    tier_served: CacheTier = CacheTier.R3_PERSISTENT
    engines_hit: List[str] = field(default_factory=list)
    latency_ms: float = 0
    cache_hit: bool = False
    path_strength: float = 0
    metadata: Dict = field(default_factory=dict)


@dataclass
class SecurityVerdict:
    allowed: bool = True
    threat_score: float = 0.0
    threats_detected: List[str] = field(default_factory=list)
    latency_us: float = 0


class Amygdala:
    """Security Engine - < 1ms threat detection on EVERY query."""

    INJECTION_PATTERNS = [
        "'; DROP TABLE", "1=1", "OR 1=1", "UNION SELECT",
        "'; DELETE FROM", "admin'--", "' OR ''='",
        "EXEC xp_", "EXECUTE sp_", "; SHUTDOWN",
        "INTO OUTFILE", "LOAD_FILE", "BENCHMARK(",
    ]

    BLOCKED_OPERATIONS = [
        "shell_exec", "os.system", "subprocess", "eval(",
        "exec(", "import os", "__import__", "cmd.exe",
    ]

    def __init__(self):
        self._pattern_set = set(p.upper() for p in self.INJECTION_PATTERNS)
        self._blocked_set = set(b.upper() for b in self.BLOCKED_OPERATIONS)

    def assess(self, query: str, actor: str = "anonymous") -> SecurityVerdict:
        start = time.perf_counter_ns()
        threats = []
        query_upper = query.upper()

        for pattern in self._pattern_set:
            if pattern in query_upper:
                threats.append(f"SQL_INJECTION: '{pattern}'")

        for blocked in self._blocked_set:
            if blocked in query_upper:
                threats.append(f"BLOCKED_OPERATION: '{blocked}'")

        if query.count("'") > 10:
            threats.append("ANOMALY: excessive single quotes")
        if len(query) > 10000:
            threats.append("ANOMALY: query exceeds 10KB")

        elapsed_us = (time.perf_counter_ns() - start) / 1000
        return SecurityVerdict(
            allowed=len(threats) == 0,
            threat_score=min(1.0, len(threats) * 0.3),
            threats_detected=threats,
            latency_us=elapsed_us
        )


class ReadCascade:
    """5-Tier Read Cascade: R0 -> R1 -> R2 -> R3 -> R4. Target: 75-85% cache hit rate."""

    def __init__(self, engines: Dict[str, Any]):
        self.engines = engines
        self._r0_cache: Dict[str, Any] = {}
        self._r0_max_size = 10000
        self._r0_hits = 0
        self._r0_misses = 0

    def _query_hash(self, query: str, params: Optional[Dict] = None) -> str:
        key = query + (json.dumps(params, sort_keys=True) if params else "")
        return hashlib.sha256(key.encode()).hexdigest()[:32]

    async def read(self, query: str, params: Optional[Dict] = None,
                   hint: Optional[str] = None) -> QueryResult:
        start = time.perf_counter()
        qhash = self._query_hash(query, params)

        # R0: Process-Local Cache
        if qhash in self._r0_cache:
            self._r0_hits += 1
            return QueryResult(data=self._r0_cache[qhash], tier_served=CacheTier.R0_PROCESS,
                               engines_hit=["r0_cache"],
                               latency_ms=(time.perf_counter() - start) * 1000, cache_hit=True)
        self._r0_misses += 1

        # R1: MemoryCore / Redis
        if "memory" in self.engines:
            try:
                cached = await self.engines["memory"].get(f"cache:{qhash}")
                if cached:
                    data = json.loads(cached)
                    self._r0_set(qhash, data)
                    return QueryResult(data=data, tier_served=CacheTier.R1_MEMORY,
                                       engines_hit=["memory_core"],
                                       latency_ms=(time.perf_counter() - start) * 1000, cache_hit=True)
            except Exception as e:
                logger.warning(f"R1 error: {e}")

        # R2: Semantic Cache / VectorCore
        if "vector" in self.engines and hint != "skip_semantic":
            try:
                similar = await self.engines["vector"].search_similar(
                    collection="response_cache", query_text=query, threshold=0.95, limit=1)
                if similar:
                    data = similar[0]["payload"]["response"]
                    await self._promote_to_r1(qhash, data)
                    self._r0_set(qhash, data)
                    return QueryResult(data=data, tier_served=CacheTier.R2_SEMANTIC,
                                       engines_hit=["vector_core"],
                                       latency_ms=(time.perf_counter() - start) * 1000, cache_hit=True)
            except Exception as e:
                logger.warning(f"R2 error: {e}")

        # R3: Persistent Store
        if "relational" in self.engines:
            try:
                data = await self.engines["relational"].execute(query, params)
                if data is not None:
                    await self._promote_to_r1(qhash, data, ttl=3600)
                    self._r0_set(qhash, data)
                    return QueryResult(data=data, tier_served=CacheTier.R3_PERSISTENT,
                                       engines_hit=["relational_core"],
                                       latency_ms=(time.perf_counter() - start) * 1000, cache_hit=False)
            except Exception as e:
                logger.error(f"R3 error: {e}")

        # R4: Deep Retrieval
        return QueryResult(data=None, tier_served=CacheTier.R4_DEEP,
                           engines_hit=["deep_retrieval"],
                           latency_ms=(time.perf_counter() - start) * 1000, cache_hit=False,
                           metadata={"note": "R4 deep retrieval"})

    def _r0_set(self, key: str, value: Any):
        if len(self._r0_cache) >= self._r0_max_size:
            del self._r0_cache[next(iter(self._r0_cache))]
        self._r0_cache[key] = value

    async def _promote_to_r1(self, key: str, data: Any, ttl: int = 3600):
        if "memory" in self.engines:
            try:
                await self.engines["memory"].set(f"cache:{key}", json.dumps(data, default=str), ex=ttl)
            except Exception:
                pass

    @property
    def stats(self) -> Dict:
        total = self._r0_hits + self._r0_misses
        return {"r0_size": len(self._r0_cache), "r0_hits": self._r0_hits,
                "r0_misses": self._r0_misses,
                "r0_hit_rate": round(self._r0_hits / max(total, 1) * 100, 2)}


class SynapticPlasticity:
    """Query path strengthening (Basal Ganglia). Frequently used paths get faster."""

    def __init__(self):
        self._path_strengths: Dict[str, float] = {}
        self._path_hits: Dict[str, int] = {}

    def strengthen(self, query_hash: str, engines: List[str], latency_ms: float):
        key = f"{query_hash}:{','.join(sorted(engines))}"
        self._path_strengths[key] = self._path_strengths.get(key, 1.0) + 1.0
        self._path_hits[key] = self._path_hits.get(key, 0) + 1

    def decay(self, decay_rate: float = 0.1):
        for key in list(self._path_strengths.keys()):
            self._path_strengths[key] = max(0, self._path_strengths[key] - decay_rate)
            if self._path_strengths[key] <= 0:
                del self._path_strengths[key]
                self._path_hits.pop(key, None)

    @property
    def top_paths(self) -> List[Dict]:
        sorted_paths = sorted(self._path_strengths.items(), key=lambda x: x[1], reverse=True)
        return [{"path": k, "strength": v, "hits": self._path_hits.get(k, 0)}
                for k, v in sorted_paths[:20]]


class WriteFanOut:
    """Parallel Write Fan-Out. Sync engines = ACID. Async engines = best-effort."""

    WRITE_ROUTES = {
        "payment":    {"sync": ["relational", "immutable"], "async": ["temporal", "stream", "memory"]},
        "agent":      {"sync": ["relational"], "async": ["memory", "stream"]},
        "task":       {"sync": ["relational"], "async": ["temporal", "stream"]},
        "block":      {"sync": ["relational"], "async": ["vector", "memory"]},
        "heartbeat":  {"sync": ["temporal"], "async": ["memory"]},
        "audit":      {"sync": ["immutable"], "async": ["relational"]},
        "grid_event": {"sync": ["relational"], "async": ["temporal", "stream"]},
        "experience": {"sync": ["relational"], "async": ["vector"]},
        "default":    {"sync": ["relational"], "async": []},
    }

    def __init__(self, engines: Dict[str, Any]):
        self.engines = engines

    async def write(self, data_type: str, payload: Dict, actor: str = "system") -> Dict:
        start = time.perf_counter()
        route = self.WRITE_ROUTES.get(data_type, self.WRITE_ROUTES["default"])
        results = {"sync": {}, "async": {}, "latency_ms": 0}

        for engine_name in route["sync"]:
            if engine_name in self.engines:
                try:
                    result = await self.engines[engine_name].write(data_type, payload, actor)
                    results["sync"][engine_name] = {"status": "success", "result": result}
                except Exception as e:
                    results["sync"][engine_name] = {"status": "error", "error": str(e)}
                    raise

        for engine_name in route["async"]:
            if engine_name in self.engines:
                asyncio.create_task(self._async_write(engine_name, data_type, payload, actor))
                results["async"][engine_name] = {"status": "queued"}

        results["latency_ms"] = (time.perf_counter() - start) * 1000
        return results

    async def _async_write(self, engine_name: str, data_type: str,
                           payload: Dict, actor: str, retries: int = 3):
        for attempt in range(retries):
            try:
                await self.engines[engine_name].write(data_type, payload, actor)
                return
            except Exception as e:
                if attempt < retries - 1:
                    await asyncio.sleep(0.1 * (2 ** attempt))
                else:
                    logger.error(f"Async write to {engine_name} failed after {retries} retries: {e}")


class CortexDB:
    """CortexDB - The Unified Database. One class. Replaces 7 databases."""

    def __init__(self, config: Optional[Dict] = None):
        self.config = config or self._default_config()
        self.engines: Dict[str, Any] = {}
        self.amygdala = Amygdala()
        self.plasticity = SynapticPlasticity()
        self.read_cascade: Optional[ReadCascade] = None
        self.write_fanout: Optional[WriteFanOut] = None
        self._connected = False
        self._query_count = 0
        self._start_time = time.time()

    def _default_config(self) -> Dict:
        import os
        return {
            "relational": {"url": os.getenv("RELATIONAL_CORE_URL", "postgresql://cortex:cortex_secret@localhost:5432/cortexdb")},
            "memory": {"url": os.getenv("MEMORY_CORE_URL", "redis://localhost:6379/0"),
                       "password": os.getenv("MEMORY_CORE_PASSWORD", "cortex_redis_secret")},
            "vector": {"url": os.getenv("VECTOR_CORE_URL", "http://localhost:6333")},
            "stream": {"url": os.getenv("STREAM_CORE_URL", "redis://localhost:6380/0"),
                       "password": os.getenv("STREAM_CORE_PASSWORD", "cortex_stream_secret")},
            "temporal": {"url": os.getenv("TEMPORAL_CORE_URL", "postgresql://cortex:cortex_secret@localhost:5432/cortexdb")},
            "immutable": {"path": os.getenv("IMMUTABLE_CORE_PATH", "./data/immutable")},
            "graph": {"url": os.getenv("GRAPH_CORE_URL", "postgresql://cortex:cortex_secret@localhost:5432/cortexdb")},
        }

    async def connect(self):
        logger.info("CortexDB v2.0 initializing...")

        from cortexdb.engines.relational import RelationalEngine
        from cortexdb.engines.memory import MemoryEngine
        from cortexdb.engines.vector import VectorEngine
        from cortexdb.engines.stream import StreamEngine
        from cortexdb.engines.immutable import ImmutableEngine
        from cortexdb.engines.temporal import TemporalEngine
        from cortexdb.engines.graph import GraphEngine

        engine_classes = {
            "relational": (RelationalEngine, self.config.get("relational", {})),
            "memory": (MemoryEngine, self.config.get("memory", {})),
            "vector": (VectorEngine, self.config.get("vector", {})),
            "stream": (StreamEngine, self.config.get("stream", {})),
            "immutable": (ImmutableEngine, self.config.get("immutable", {})),
            "temporal": (TemporalEngine, self.config.get("temporal", {})),
            "graph": (GraphEngine, self.config.get("graph", {})),
        }

        for name, (cls, cfg) in engine_classes.items():
            try:
                engine = cls(cfg)
                await engine.connect()
                self.engines[name] = engine
                logger.info(f"  + {name.upper()} Core connected")
            except Exception as e:
                logger.warning(f"  x {name.upper()} Core unavailable: {e}")

        self.read_cascade = ReadCascade(self.engines)
        self.write_fanout = WriteFanOut(self.engines)
        self._connected = True
        logger.info(f"CortexDB ready - {len(self.engines)}/{len(engine_classes)} engines online")

    async def query(self, cortexql: str, params: Optional[Dict] = None,
                    hint: Optional[str] = None) -> QueryResult:
        if not self._connected:
            raise RuntimeError("CortexDB not connected. Call await db.connect() first.")
        self._query_count += 1

        verdict = self.amygdala.assess(cortexql, actor="query")
        if not verdict.allowed:
            return QueryResult(
                data={"error": "BLOCKED_BY_AMYGDALA", "threats": verdict.threats_detected},
                tier_served=CacheTier.R0_PROCESS, engines_hit=["amygdala"],
                metadata={"security_verdict": verdict.__dict__})

        result = await self.read_cascade.read(cortexql, params, hint)
        qhash = hashlib.sha256(cortexql.encode()).hexdigest()[:16]
        self.plasticity.strengthen(qhash, result.engines_hit, result.latency_ms)
        return result

    async def write(self, data_type: str, payload: Dict, actor: str = "system") -> Dict:
        if not self._connected:
            raise RuntimeError("CortexDB not connected.")
        verdict = self.amygdala.assess(json.dumps(payload, default=str), actor)
        if not verdict.allowed:
            raise PermissionError(f"Write blocked by Amygdala: {verdict.threats_detected}")
        return await self.write_fanout.write(data_type, payload, actor)

    async def health(self) -> Dict:
        health = {
            "status": "healthy", "version": "2.0.0",
            "uptime_seconds": round(time.time() - self._start_time, 1),
            "queries_total": self._query_count,
            "engines": {},
            "cache": self.read_cascade.stats if self.read_cascade else {},
            "plasticity": {"top_paths_count": len(self.plasticity.top_paths)},
            "amygdala": {"status": "active", "patterns": len(Amygdala.INJECTION_PATTERNS)},
        }
        for name, engine in self.engines.items():
            try:
                health["engines"][name] = {"status": "healthy", **(await engine.health())}
            except Exception as e:
                health["engines"][name] = {"status": "unhealthy", "error": str(e)}
                health["status"] = "degraded"
        return health

    async def close(self):
        for name, engine in self.engines.items():
            try:
                await engine.close()
            except Exception as e:
                logger.warning(f"{name} close error: {e}")
        self._connected = False
        logger.info("CortexDB shut down")
