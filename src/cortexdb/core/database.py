"""
CortexDB Core - The Consciousness Layer (v3.0)
Router (Thalamus) + Security (Amygdala) + Optimizer (Prefrontal Cortex)
+ Bridge (Corpus Callosum) + Parser (CortexQL) + Sleep Cycle + Embedding

Multi-tenant + Multi-agent aware.
Every query flows: Amygdala (< 1ms) -> Parser -> Router -> Cache Cascade -> Engine(s) -> Bridge -> Plasticity -> Response
"""

import asyncio
import hashlib
import json
import time
import logging
from collections import OrderedDict
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
        "DROP TABLE", "'; SELECT", "; SELECT",
        "COPY PG_", "PG_READ_FILE", "PG_SHADOW",
        "LO_IMPORT", "LO_EXPORT",
        "/**/OR/**/", "/**/AND/**/",
        "DELETE FROM", "; DROP", "; DELETE",
        "COPY ", "PG_READ_", "LO_IMPORT(",
        "PG_TABLES", "PG_CATALOG", "INFORMATION_SCHEMA",
    ]

    BLOCKED_OPERATIONS = [
        "shell_exec", "os.system", "subprocess", "eval(",
        "exec(", "import os", "__import__", "cmd.exe",
    ]

    # Tables that cannot be modified via CortexQL (append-only / immutable)
    PROTECTED_TABLES = [
        "COMPLIANCE_AUDIT_LOG", "IMMUTABLE_LEDGER", "EXPERIENCE_LEDGER",
    ]

    def __init__(self):
        self._pattern_set = set(p.upper() for p in self.INJECTION_PATTERNS)
        self._blocked_set = set(b.upper() for b in self.BLOCKED_OPERATIONS)
        self._checks_total = 0
        self._blocks_total = 0

    def assess(self, query: str, actor: str = "anonymous") -> SecurityVerdict:
        start = time.perf_counter_ns()
        self._checks_total += 1
        threats = []
        query_upper = query.upper()

        for pattern in self._pattern_set:
            if pattern in query_upper:
                threats.append(f"SQL_INJECTION: '{pattern}'")

        for blocked in self._blocked_set:
            if blocked in query_upper:
                threats.append(f"BLOCKED_OPERATION: '{blocked}'")

        # Block DML on protected (immutable/audit) tables
        for table in self.PROTECTED_TABLES:
            if table in query_upper:
                for dml in ("UPDATE ", "DELETE ", "TRUNCATE ", "ALTER ", "DROP "):
                    if dml in query_upper:
                        threats.append(f"PROTECTED_TABLE: {dml.strip()} on {table}")

        if query.count("'") > 10:
            threats.append("ANOMALY: excessive single quotes")
        if len(query) > 10000:
            threats.append("ANOMALY: query exceeds 10KB")

        if threats:
            self._blocks_total += 1

        elapsed_us = (time.perf_counter_ns() - start) / 1000
        return SecurityVerdict(
            allowed=len(threats) == 0,
            threat_score=min(1.0, len(threats) * 0.3),
            threats_detected=threats,
            latency_us=elapsed_us
        )

    @property
    def stats(self) -> Dict:
        return {"checks_total": self._checks_total, "blocks_total": self._blocks_total,
                "patterns": len(self.INJECTION_PATTERNS)}


class ReadCascade:
    """5-Tier Read Cascade: R0 -> R1 -> R2 -> R3 -> R4. Target: 75-85% cache hit rate."""

    def __init__(self, engines: Dict[str, Any], tenant_isolation=None):
        self.engines = engines
        self.tenant_isolation = tenant_isolation
        self._r0_cache: OrderedDict = OrderedDict()  # LRU cache
        self._r0_max_size = 10000
        self._r0_max_entry_bytes = 1024 * 1024  # 1MB max per entry
        self._r0_hits = 0
        self._r0_misses = 0
        self._r1_hits = 0
        self._r2_hits = 0
        self._r3_hits = 0

    def _query_hash(self, query: str, params: Optional[Dict] = None,
                    tenant_id: Optional[str] = None) -> str:
        key = (tenant_id or "") + ":" + query + (json.dumps(params, sort_keys=True) if params else "")
        return hashlib.sha256(key.encode()).hexdigest()[:32]

    async def read(self, query: str, params: Optional[Dict] = None,
                   hint: Optional[str] = None,
                   tenant_id: Optional[str] = None) -> QueryResult:
        start = time.perf_counter()
        qhash = self._query_hash(query, params, tenant_id)
        cache_prefix = f"tenant:{tenant_id}:" if tenant_id else ""

        # R0: Process-Local LRU Cache
        r0_key = f"{cache_prefix}{qhash}"
        if r0_key in self._r0_cache:
            # Move to end (most recently used) for LRU
            self._r0_cache.move_to_end(r0_key)
            self._r0_hits += 1
            return QueryResult(data=self._r0_cache[r0_key], tier_served=CacheTier.R0_PROCESS,
                               engines_hit=["r0_cache"],
                               latency_ms=(time.perf_counter() - start) * 1000, cache_hit=True)
        self._r0_misses += 1

        # R1: MemoryCore / Redis
        if "memory" in self.engines:
            try:
                redis_key = f"{cache_prefix}cache:{qhash}"
                cached = await self.engines["memory"].get(redis_key)
                if cached:
                    data = json.loads(cached)
                    self._r0_set(r0_key, data)
                    self._r1_hits += 1
                    return QueryResult(data=data, tier_served=CacheTier.R1_MEMORY,
                                       engines_hit=["memory_core"],
                                       latency_ms=(time.perf_counter() - start) * 1000, cache_hit=True)
            except Exception as e:
                logger.warning(f"R1 error: {e}")

        # R2: Semantic Cache / VectorCore
        if "vector" in self.engines and hint != "skip_semantic":
            try:
                collection = f"tenant_{tenant_id}_cache" if tenant_id else "response_cache"
                similar = await self.engines["vector"].search_similar(
                    collection=collection, query_text=query, threshold=0.95, limit=1)
                if similar:
                    data = similar[0]["payload"]["response"]
                    await self._promote_to_r1(f"{cache_prefix}cache:{qhash}", data)
                    self._r0_set(r0_key, data)
                    self._r2_hits += 1
                    return QueryResult(data=data, tier_served=CacheTier.R2_SEMANTIC,
                                       engines_hit=["vector_core"],
                                       latency_ms=(time.perf_counter() - start) * 1000, cache_hit=True)
            except Exception as e:
                logger.warning(f"R2 error: {e}")

        # R3: Persistent Store
        if "relational" in self.engines:
            try:
                # Set RLS context for tenant isolation
                if tenant_id and self.tenant_isolation:
                    await self.tenant_isolation.set_rls_context(tenant_id)
                data = await self.engines["relational"].execute(query, params)
                if data is not None:
                    await self._promote_to_r1(f"{cache_prefix}cache:{qhash}", data, ttl=3600)
                    self._r0_set(r0_key, data)
                    self._r3_hits += 1
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
        # Size guard: skip caching entries larger than 1MB
        try:
            entry_size = len(json.dumps(value, default=str))
            if entry_size > self._r0_max_entry_bytes:
                return
        except (TypeError, ValueError):
            pass

        # LRU eviction: remove least recently used (front of OrderedDict)
        while len(self._r0_cache) >= self._r0_max_size:
            self._r0_cache.popitem(last=False)  # Pop oldest/least-used

        self._r0_cache[key] = value

    async def _promote_to_r1(self, key: str, data: Any, ttl: int = 3600):
        if "memory" in self.engines:
            try:
                await self.engines["memory"].set(key, json.dumps(data, default=str), ex=ttl)
            except Exception:
                pass

    @property
    def stats(self) -> Dict:
        total = self._r0_hits + self._r0_misses
        return {"r0_size": len(self._r0_cache), "r0_hits": self._r0_hits,
                "r0_misses": self._r0_misses, "r1_hits": self._r1_hits,
                "r2_hits": self._r2_hits, "r3_hits": self._r3_hits,
                "r0_hit_rate": round(self._r0_hits / max(total, 1) * 100, 2),
                "total_queries": total}


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
    """Parallel Write Fan-Out. Sync engines = ACID. Async engines = tracked best-effort."""

    WRITE_ROUTES = {
        "payment":    {"sync": ["relational", "immutable"], "async": ["temporal", "stream", "memory"]},
        "agent":      {"sync": ["relational"], "async": ["memory", "stream"]},
        "task":       {"sync": ["relational"], "async": ["temporal", "stream"]},
        "block":      {"sync": ["relational"], "async": ["vector", "memory"]},
        "heartbeat":  {"sync": ["temporal"], "async": ["memory"]},
        "audit":      {"sync": ["immutable"], "async": ["relational"]},
        "grid_event": {"sync": ["relational"], "async": ["temporal", "stream"]},
        "experience": {"sync": ["relational"], "async": ["vector"]},
        "a2a_task":   {"sync": ["relational"], "async": ["stream"]},
        "tenant":     {"sync": ["relational", "immutable"], "async": ["stream"]},
        "default":    {"sync": ["relational"], "async": []},
    }

    MAX_PENDING_TASKS = 1000  # Backpressure limit

    def __init__(self, engines: Dict[str, Any], cache_invalidation=None):
        self.engines = engines
        self.cache_invalidation = cache_invalidation
        self._pending_tasks: Dict[str, asyncio.Task] = {}
        self._task_counter = 0
        self._failed_writes: List[Dict] = []  # Dead letter queue
        self._max_dlq = 500
        self._stats = {"async_queued": 0, "async_completed": 0, "async_failed": 0}

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

        # Async writes with tracking and backpressure
        self._cleanup_completed_tasks()

        for engine_name in route["async"]:
            if engine_name in self.engines:
                if len(self._pending_tasks) >= self.MAX_PENDING_TASKS:
                    logger.warning(f"Backpressure: {len(self._pending_tasks)} pending async writes. "
                                   f"Executing {engine_name} synchronously.")
                    try:
                        await self.engines[engine_name].write(data_type, payload, actor)
                        results["async"][engine_name] = {"status": "sync_fallback"}
                    except Exception as e:
                        results["async"][engine_name] = {"status": "error", "error": str(e)}
                else:
                    self._task_counter += 1
                    task_id = f"async-{self._task_counter}"
                    task = asyncio.create_task(
                        self._tracked_async_write(task_id, engine_name, data_type, payload, actor))
                    self._pending_tasks[task_id] = task
                    self._stats["async_queued"] += 1
                    results["async"][engine_name] = {"status": "queued", "task_id": task_id}

        results["latency_ms"] = (time.perf_counter() - start) * 1000

        # Invalidate caches after write (also tracked)
        if self.cache_invalidation:
            self._task_counter += 1
            tid = f"cache-{self._task_counter}"
            task = asyncio.create_task(self._safe_cache_invalidation(data_type, payload))
            self._pending_tasks[tid] = task

        return results

    async def _tracked_async_write(self, task_id: str, engine_name: str,
                                    data_type: str, payload: Dict,
                                    actor: str, retries: int = 3):
        """Async write with error tracking and DLQ on final failure."""
        for attempt in range(retries):
            try:
                await self.engines[engine_name].write(data_type, payload, actor)
                self._stats["async_completed"] += 1
                return
            except Exception as e:
                if attempt < retries - 1:
                    await asyncio.sleep(0.1 * (2 ** attempt))
                else:
                    self._stats["async_failed"] += 1
                    logger.error(f"Async write to {engine_name} failed after "
                                 f"{retries} retries: {e}")
                    # Add to dead letter queue
                    if len(self._failed_writes) < self._max_dlq:
                        self._failed_writes.append({
                            "task_id": task_id,
                            "engine": engine_name,
                            "data_type": data_type,
                            "error": str(e),
                            "timestamp": time.time(),
                        })

    async def _safe_cache_invalidation(self, data_type: str, payload: Dict):
        """Cache invalidation with error handling."""
        try:
            await self.cache_invalidation.on_write(data_type, payload)
        except Exception as e:
            logger.warning(f"Cache invalidation failed: {e}")

    def _cleanup_completed_tasks(self):
        """Remove completed tasks from the tracking dict."""
        done = [tid for tid, task in self._pending_tasks.items() if task.done()]
        for tid in done:
            task = self._pending_tasks.pop(tid)
            # Surface unhandled exceptions
            if task.exception():
                logger.error(f"Background task {tid} exception: {task.exception()}")

    async def drain(self, timeout: float = 30.0):
        """Wait for all pending async writes to complete (for graceful shutdown)."""
        if not self._pending_tasks:
            return
        logger.info(f"Draining {len(self._pending_tasks)} pending async writes...")
        pending = list(self._pending_tasks.values())
        try:
            await asyncio.wait_for(
                asyncio.gather(*pending, return_exceptions=True),
                timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning(f"Drain timeout: {len(self._pending_tasks)} tasks still pending")
        self._cleanup_completed_tasks()

    @property
    def pending_count(self) -> int:
        return len(self._pending_tasks)

    @property
    def dlq(self) -> List[Dict]:
        return list(self._failed_writes)

    def get_stats(self) -> Dict:
        self._cleanup_completed_tasks()
        return {
            **self._stats,
            "pending": len(self._pending_tasks),
            "dlq_size": len(self._failed_writes),
        }


class CortexDB:
    """CortexDB - The Unified Database. One class. Replaces 7 databases.

    v4.0: Petabyte-scale Citus sharding, FedRAMP/SOC2/HIPAA/PCI compliance.
    """

    def __init__(self, config: Optional[Dict] = None):
        from cortexdb import __version__
        self.config = config or self._default_config()
        self.engines: Dict[str, Any] = {}
        self.amygdala = Amygdala()
        self.plasticity = SynapticPlasticity()
        self.read_cascade: Optional[ReadCascade] = None
        self.write_fanout: Optional[WriteFanOut] = None
        self.bridge = None
        self.parser = None
        self.sleep_cycle = None
        self.cache_invalidation = None
        self.embedding = None
        self.precompute = None
        self.tenant_isolation = None
        self._connected = False
        self._query_count = 0
        self._start_time = time.time()
        self._version = __version__

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
        logger.info("CortexDB v4.0 initializing...")

        # Initialize centralized connection pool for relational engines
        from cortexdb.core.pool import ConnectionPoolManager
        self._pool_manager = ConnectionPoolManager(
            dsn=self.config.get("relational", {}).get("url")
        )
        try:
            await self._pool_manager.initialize()
            logger.info("  + Connection pool initialized")
        except Exception as e:
            logger.warning(f"  x Connection pool failed: {e}")
            self._pool_manager = None

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
                # Share the centralized pool with relational-backed engines
                if self._pool_manager and name in ("relational", "temporal", "graph"):
                    engine.shared_pool = self._pool_manager
                await engine.connect()
                self.engines[name] = engine
                logger.info(f"  + {name.upper()} Core connected")
            except Exception as e:
                logger.warning(f"  x {name.upper()} Core unavailable: {e}")

        # Initialize intelligence layer
        from cortexdb.tenant.isolation import TenantIsolation
        from cortexdb.core.bridge import BridgeEngine
        from cortexdb.core.cache_invalidation import CacheInvalidationEngine
        from cortexdb.core.parser import CortexQLParser
        from cortexdb.core.sleep_cycle import SleepCycleScheduler
        from cortexdb.core.precompute import PreComputeEngine

        self.tenant_isolation = TenantIsolation(self.engines)
        self.cache_invalidation = CacheInvalidationEngine(engines=self.engines)
        self.read_cascade = ReadCascade(self.engines, self.tenant_isolation)
        self.write_fanout = WriteFanOut(self.engines, self.cache_invalidation)
        self.bridge = BridgeEngine(self.engines)
        self.parser = CortexQLParser()
        self.precompute = PreComputeEngine(self.plasticity, self.read_cascade, self.engines)
        self.sleep_cycle = SleepCycleScheduler(
            self.engines, self.plasticity, self.read_cascade)
        self.cache_invalidation.read_cascade = self.read_cascade

        # Try loading embedding pipeline (optional)
        try:
            from cortexdb.core.embedding import EmbeddingPipeline
            self.embedding = EmbeddingPipeline()
        except Exception:
            pass

        self._connected = True
        logger.info(f"CortexDB ready - {len(self.engines)}/{len(engine_classes)} engines online")

    async def query(self, cortexql: str, params: Optional[Dict] = None,
                    hint: Optional[str] = None,
                    tenant_id: Optional[str] = None) -> QueryResult:
        if not self._connected:
            raise RuntimeError("CortexDB not connected. Call await db.connect() first.")
        self._query_count += 1

        # Amygdala security check
        verdict = self.amygdala.assess(cortexql, actor="query")
        if not verdict.allowed:
            return QueryResult(
                data={"error": "BLOCKED_BY_AMYGDALA", "threats": verdict.threats_detected},
                tier_served=CacheTier.R0_PROCESS, engines_hit=["amygdala"],
                metadata={"security_verdict": verdict.__dict__})

        # Parse query to determine routing
        if self.parser:
            parsed = self.parser.parse(cortexql)
            engine_name = parsed.engine

            # Route to specific engine for CortexQL extensions
            if parsed.query_type.value == "vector" and "vector" in self.engines:
                text = parsed.parameters.get("search_text", cortexql)
                collection = parsed.collection or "default"
                if tenant_id:
                    collection = f"tenant_{tenant_id}_{collection}"
                try:
                    data = await self.engines["vector"].search_similar(
                        collection=collection, query_text=text, limit=10)
                    result = QueryResult(data=data, tier_served=CacheTier.R3_PERSISTENT,
                                         engines_hit=["vector_core"],
                                         latency_ms=0, cache_hit=False)
                    return result
                except Exception as e:
                    logger.warning(f"VectorCore query failed: {e}")

            elif parsed.query_type.value == "graph" and "graph" in self.engines:
                try:
                    data = await self.engines["graph"].execute(cortexql, params)
                    return QueryResult(data=data, tier_served=CacheTier.R3_PERSISTENT,
                                       engines_hit=["graph_core"], cache_hit=False)
                except Exception as e:
                    logger.warning(f"GraphCore query failed: {e}")

        # Default: Read Cascade
        result = await self.read_cascade.read(cortexql, params, hint, tenant_id)
        qhash = hashlib.sha256(cortexql.encode()).hexdigest()[:16]
        self.plasticity.strengthen(qhash, result.engines_hit, result.latency_ms)
        return result

    async def write(self, data_type: str, payload: Dict,
                    actor: str = "system",
                    tenant_id: Optional[str] = None) -> Dict:
        if not self._connected:
            raise RuntimeError("CortexDB not connected.")

        # Inject tenant_id into payload for RLS
        if tenant_id:
            payload["tenant_id"] = tenant_id

        verdict = self.amygdala.assess(json.dumps(payload, default=str), actor)
        if not verdict.allowed:
            raise PermissionError(f"Write blocked by Amygdala: {verdict.threats_detected}")
        return await self.write_fanout.write(data_type, payload, actor)

    async def health(self) -> Dict:
        pool_stats = self._pool_manager.stats() if getattr(self, "_pool_manager", None) else {}
        pool_health = await self._pool_manager.health_check() if getattr(self, "_pool_manager", None) else {}
        health = {
            "status": "healthy", "version": self._version,
            "uptime_seconds": round(time.time() - self._start_time, 1),
            "queries_total": self._query_count,
            "engines": {},
            "connection_pool": {**pool_stats, "health": pool_health},
            "cache": self.read_cascade.stats if self.read_cascade else {},
            "plasticity": {"top_paths_count": len(self.plasticity.top_paths)},
            "amygdala": self.amygdala.stats,
            "bridge": self.bridge.get_stats() if self.bridge else {},
            "embedding": self.embedding.get_info() if self.embedding else {"status": "not_loaded"},
            "sleep_cycle": self.sleep_cycle.get_status() if self.sleep_cycle else {},
        }
        for name, engine in self.engines.items():
            try:
                health["engines"][name] = {"status": "healthy", **(await engine.health())}
            except Exception as e:
                health["engines"][name] = {"status": "unhealthy", "error": str(e)}
                health["status"] = "degraded"
        return health

    async def close(self):
        # Drain async writes first
        if self.write_fanout:
            await self.write_fanout.drain()

        for name, engine in self.engines.items():
            try:
                await engine.close()
            except Exception as e:
                logger.warning(f"{name} close error: {e}")

        # Close the centralized connection pool
        if getattr(self, "_pool_manager", None):
            await self._pool_manager.close()
            self._pool_manager = None

        self._connected = False
        logger.info("CortexDB shut down")
