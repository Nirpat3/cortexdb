"""
CortexDB Core - Intelligence Layer (v6.1)

Cross-engine query routing, 5-tier read cascade with semantic caching,
write fan-out with DLQ, and query path optimization.

Built on top of PostgreSQL, Redis, and Qdrant — not a replacement for them.
For simple CRUD, use the TypeScript SDK (@cortexdb/sdk) which connects directly.

Query flow: Security -> Parser -> Router -> Cache Cascade -> Engine(s) -> Bridge -> Plasticity -> Response
"""

import asyncio
import copy
import hashlib
import json
import os
import time
import logging
from collections import OrderedDict
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum

from cortexdb.core.cache_config import SemanticCacheConfig, CollectionCacheConfig
from cortexdb.observability.tracing import trace_span

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
        import re as _re
        self._pattern_set = set(p.upper() for p in self.INJECTION_PATTERNS)
        self._blocked_set = set(b.upper() for b in self.BLOCKED_OPERATIONS)
        self._injection_re = _re.compile(
            '|'.join(_re.escape(p) for p in self._pattern_set))
        self._blocked_re = _re.compile(
            '|'.join(_re.escape(p) for p in self._blocked_set))
        self._checks_total = 0
        self._blocks_total = 0

    def assess(self, query: str, actor: str = "anonymous") -> SecurityVerdict:
        import unicodedata
        start = time.perf_counter_ns()
        self._checks_total += 1
        threats = []
        # Normalize Unicode (NFKC) and strip zero-width characters to prevent bypass
        normalized = unicodedata.normalize("NFKC", query)
        normalized = "".join(c for c in normalized if unicodedata.category(c) != "Cf")
        query_upper = normalized.upper()

        for m in self._injection_re.finditer(query_upper):
            threats.append(f"SQL_INJECTION: '{m.group()}'")

        for m in self._blocked_re.finditer(query_upper):
            threats.append(f"BLOCKED_OPERATION: '{m.group()}'")

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

    def __init__(self, engines: Dict[str, Any], tenant_isolation=None,
                 field_encryption=None, audit=None):
        self.engines = engines
        self.tenant_isolation = tenant_isolation
        self.field_encryption = field_encryption  # Optional FieldEncryption instance
        self.audit = audit  # Optional ComplianceAudit instance
        self.cache_config = SemanticCacheConfig()
        self._r0_cache: OrderedDict = OrderedDict()  # LRU cache
        self._r0_lock = asyncio.Lock()  # guards _r0_cache and _pending_queries
        self._r0_max_size = 10000
        self._r0_max_entry_bytes = 1024 * 1024  # 1MB max per entry
        self._r0_hits = 0
        self._r0_misses = 0
        self._r1_hits = 0
        self._r2_hits = 0
        self._r3_hits = 0
        self._audit_failures = 0
        # Request coalescing: prevents cache stampede when multiple concurrent
        # requests for the same query all miss R0-R2 and hit R3 (PostgreSQL).
        # Only one PG query is made; other callers await the same future.
        self._pending_queries: Dict[str, asyncio.Future] = {}

    def _query_hash(self, query: str, params: Optional[Dict] = None,
                    tenant_id: Optional[str] = None) -> str:
        key = (tenant_id or "") + ":" + query + (json.dumps(params, sort_keys=True, default=str) if params else "")
        return hashlib.sha256(key.encode()).hexdigest()[:32]

    async def read(self, query: str, params: Optional[Dict] = None,
                   hint: Optional[str] = None,
                   tenant_id: Optional[str] = None) -> QueryResult:
        start = time.perf_counter()
        qhash = self._query_hash(query, params, tenant_id)
        cache_prefix = f"tenant:{tenant_id}:" if tenant_id else ""

        # R0: Process-Local LRU Cache (lock-protected to prevent concurrent corruption)
        r0_key = f"{cache_prefix}{qhash}"
        async with self._r0_lock:
            if r0_key in self._r0_cache:
                self._r0_cache.move_to_end(r0_key)
                self._r0_hits += 1
                data = copy.deepcopy(self._r0_cache[r0_key])
                r0_hit = True
            else:
                r0_hit = False
                self._r0_misses += 1

        if r0_hit:
            result = QueryResult(data=data, tier_served=CacheTier.R0_PROCESS,
                                 engines_hit=["r0_cache"],
                                 latency_ms=(time.perf_counter() - start) * 1000, cache_hit=True)
            return self._post_read(result, query, tenant_id)

        # R1: MemoryCore / Redis
        if "memory" in self.engines:
            try:
                redis_key = f"{cache_prefix}cache:{qhash}"
                cached = await self.engines["memory"].get(redis_key)
                if cached:
                    data = json.loads(cached)
                    await self._r0_set(r0_key, data)
                    self._r1_hits += 1
                    result = QueryResult(data=data, tier_served=CacheTier.R1_MEMORY,
                                         engines_hit=["memory_core"],
                                         latency_ms=(time.perf_counter() - start) * 1000, cache_hit=True)
                    return self._post_read(result, query, tenant_id)
            except Exception as e:
                logger.warning(f"R1 error for tenant={tenant_id} qhash={qhash}: {e}")

        # R2: Semantic Cache / VectorCore (adaptive thresholds)
        if "vector" in self.engines and hint != "skip_semantic":
            try:
                collection = f"tenant_{tenant_id}_cache" if tenant_id else "response_cache"
                r2_config = self.cache_config.get_config(collection, query)
                if not r2_config.r2_enabled:
                    # Skip R2 for SQL queries — use hash-based caching only
                    pass  # fall through to R3
                else:
                    similar = await self.engines["vector"].search_similar(
                        collection=collection, query_text=query,
                        threshold=r2_config.threshold, limit=1)
                    if similar:
                        data = similar[0]["payload"]["response"]
                        _serialized = json.dumps(data, default=str)
                        await self._promote_to_r1(f"{cache_prefix}cache:{qhash}", data, serialized=_serialized)
                        await self._r0_set(r0_key, data, serialized=_serialized)
                        self._r2_hits += 1
                        result = QueryResult(data=data, tier_served=CacheTier.R2_SEMANTIC,
                                             engines_hit=["vector_core"],
                                             latency_ms=(time.perf_counter() - start) * 1000, cache_hit=True)
                        return self._post_read(result, query, tenant_id)
            except Exception as e:
                logger.warning(f"R2 error for tenant={tenant_id} qhash={qhash}: {e}")

        # R3: Persistent Store (with request coalescing to prevent cache stampede)
        if "relational" in self.engines:
            try:
                # Atomic check-and-insert under lock to prevent TOCTOU
                async with self._r0_lock:
                    if qhash in self._pending_queries:
                        existing_future = self._pending_queries[qhash]
                    else:
                        existing_future = None
                        loop = asyncio.get_running_loop()
                        future: asyncio.Future = loop.create_future()
                        self._pending_queries[qhash] = future

                if existing_future is not None:
                    # Coalesce: await the existing future instead of hitting PG again
                    data = await existing_future
                else:
                    try:
                        # CRITICAL FIX: Execute SET LOCAL and query on the SAME
                        # connection in the SAME transaction. Previously, set_rls_context()
                        # acquired its own connection, so SET LOCAL was discarded before
                        # the query ran on a different pooled connection.
                        if tenant_id and self.tenant_isolation and \
                                hasattr(self.engines["relational"], "pool"):
                            pool = self.engines["relational"].pool
                            async with pool.acquire() as conn:
                                async with conn.transaction():
                                    await self.tenant_isolation.set_rls_context(
                                        tenant_id, conn=conn)
                                    data = await conn.fetch(query, *(params or []))
                        else:
                            data = await self.engines["relational"].execute(query, params)
                        future.set_result(data)
                    except Exception as exc:
                        future.set_exception(exc)
                        raise
                    finally:
                        self._pending_queries.pop(qhash, None)

                if data is not None:
                    _serialized = json.dumps(data, default=str)
                    await self._promote_to_r1(f"{cache_prefix}cache:{qhash}", data, ttl=3600, serialized=_serialized)
                    await self._r0_set(r0_key, data, serialized=_serialized)
                    self._r3_hits += 1
                    result = QueryResult(data=data, tier_served=CacheTier.R3_PERSISTENT,
                                         engines_hit=["relational_core"],
                                         latency_ms=(time.perf_counter() - start) * 1000, cache_hit=False)
                    return self._post_read(result, query, tenant_id)
            except Exception as e:
                logger.error(f"R3 error: {e}")

        # R4: Deep Retrieval
        return QueryResult(data=None, tier_served=CacheTier.R4_DEEP,
                           engines_hit=["deep_retrieval"],
                           latency_ms=(time.perf_counter() - start) * 1000, cache_hit=False,
                           metadata={"note": "R4 deep retrieval"})

    def _post_read(self, result, query, tenant_id=None):
        """Post-read processing: decrypt encrypted fields and schedule audit logging.
        Caches store the ENCRYPTED form; decryption happens only at read time."""
        # Decrypt encrypted fields if present
        if self.field_encryption and result.data is not None:
            try:
                result.data = self._decrypt_result(result.data)
            except Exception as e:
                logger.warning(f"Decryption error on read result: {e}")

        # Audit logging (fire-and-forget via background task)
        if self.audit and result.data is not None:
            try:
                from cortexdb.compliance.audit import AuditEventType

                async def _audit_log():
                    try:
                        await self.audit.log(
                            event_type=AuditEventType.DATA_READ,
                            actor=tenant_id or "anonymous",
                            resource=query[:200],
                            action="read",
                            outcome="success",
                            tenant_id=tenant_id,
                            details={
                                "tier_served": result.tier_served.value,
                                "cache_hit": result.cache_hit,
                                "engines_hit": result.engines_hit,
                            },
                        )
                    except Exception as exc:
                        self._audit_failures += 1
                        logger.warning(f"Audit logging failed: {exc}")

                asyncio.create_task(_audit_log())
            except Exception as e:
                logger.warning(f"Audit logging error on read: {e}")

        return result

    def _decrypt_result(self, data):
        """Decrypt encrypted fields in read results. Handles single dicts and lists of dicts."""
        if isinstance(data, dict):
            has_encrypted = any(
                isinstance(v, dict) and v.get("_encrypted")
                for v in data.values()
            )
            if has_encrypted:
                return self.field_encryption.decrypt_payload(data)
        elif isinstance(data, list):
            decrypted = []
            for item in data:
                if isinstance(item, dict):
                    has_encrypted = any(
                        isinstance(v, dict) and v.get("_encrypted")
                        for v in item.values()
                    )
                    if has_encrypted:
                        decrypted.append(self.field_encryption.decrypt_payload(item))
                    else:
                        decrypted.append(item)
                else:
                    decrypted.append(item)
            return decrypted
        return data

    async def _r0_set(self, key: str, value: Any, serialized: str = None):
        """Add to R0 cache. Acquires _r0_lock internally.
        If `serialized` is provided, it is used for the size check (avoids re-serializing).
        """
        # Size guard: skip caching entries larger than 1MB
        # Perform expensive serialization and deepcopy BEFORE acquiring lock
        try:
            entry_size = len(serialized) if serialized is not None else len(json.dumps(value, default=str))
            if entry_size > self._r0_max_entry_bytes:
                return
        except (TypeError, ValueError):
            pass

        value_copy = copy.deepcopy(value)

        async with self._r0_lock:
            # LRU eviction: remove least recently used (front of OrderedDict)
            while len(self._r0_cache) >= self._r0_max_size:
                self._r0_cache.popitem(last=False)

            # Store the pre-computed copy to prevent callers from mutating cached data
            self._r0_cache[key] = value_copy

    async def invalidate_tenant_cache(self, tenant_id: str):
        """Evict all R0 cache entries for a specific tenant after writes."""
        if not tenant_id:
            return
        prefix = f"tenant:{tenant_id}:"
        async with self._r0_lock:
            keys_to_evict = [k for k in self._r0_cache if k.startswith(prefix)]
            for k in keys_to_evict:
                self._r0_cache.pop(k, None)
        if keys_to_evict:
            logger.debug("R0 cache: evicted %d entries for tenant %s", len(keys_to_evict), tenant_id)

    async def _promote_to_r1(self, key: str, data: Any, ttl: int = 3600, serialized: str = None):
        if "memory" in self.engines:
            try:
                json_str = serialized if serialized is not None else json.dumps(data, default=str)
                await self.engines["memory"].set(key, json_str, ex=ttl)
            except Exception as e:
                logger.debug(f"R1 promotion failed: {e}")

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

    MAX_PATHS = 10_000  # cap to prevent unbounded memory growth

    def __init__(self):
        self._path_strengths: Dict[str, float] = {}
        self._path_hits: Dict[str, int] = {}

    def strengthen(self, query_hash: str, engines: List[str], latency_ms: float):
        key = f"{query_hash}:{','.join(sorted(engines))}"
        self._path_strengths[key] = self._path_strengths.get(key, 1.0) + 1.0
        self._path_hits[key] = self._path_hits.get(key, 0) + 1

        # Evict weakest paths when we exceed the cap
        if len(self._path_strengths) > self.MAX_PATHS:
            self._evict_weakest()

    def _evict_weakest(self):
        """Remove the weakest 10% of paths to stay within MAX_PATHS."""
        to_remove = len(self._path_strengths) - self.MAX_PATHS + self.MAX_PATHS // 10
        weakest = sorted(self._path_strengths, key=self._path_strengths.get)[:to_remove]
        for key in weakest:
            del self._path_strengths[key]
            self._path_hits.pop(key, None)

    def decay(self, decay_rate: float = 0.1):
        for key in list(self._path_strengths.keys()):
            self._path_strengths[key] = max(0, self._path_strengths[key] - decay_rate)
            if self._path_strengths[key] <= 0:
                del self._path_strengths[key]
                self._path_hits.pop(key, None)

    @property
    def top_paths(self) -> List[Dict]:
        sorted_paths = sorted(dict(self._path_strengths).items(), key=lambda x: x[1], reverse=True)
        return [{"path": k, "strength": v, "hits": self._path_hits.get(k, 0)}
                for k, v in sorted_paths[:20]]


class WriteFanOut:
    """Parallel Write Fan-Out with Transactional Outbox Pattern.

    Sync engines = ACID (executed inline).
    Async engines = persisted to PG outbox table in the SAME transaction as sync writes.
    OutboxWorker background process picks up and dispatches to async engines.

    P1 FIX: Replaced in-memory DLQ (lost on crash) with PG-backed outbox table.
    """

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

    def __init__(self, engines: Dict[str, Any], cache_invalidation=None,
                 pool=None, field_encryption=None, audit=None):
        self.engines = engines
        self.cache_invalidation = cache_invalidation
        self.pool = pool  # asyncpg pool for outbox table
        self.field_encryption = field_encryption
        self.audit = audit
        self._pending_tasks: Dict[str, asyncio.Task] = {}
        self._task_counter = 0
        self._stats = {"outbox_queued": 0, "sync_completed": 0}
        self._outbox_worker = None  # set after OutboxWorker is created

    async def write(self, data_type: str, payload: Dict, actor: str = "system",
                    tenant_id: Optional[str] = None) -> Dict:
        start = time.perf_counter()
        route = self.WRITE_ROUTES.get(data_type, self.WRITE_ROUTES["default"])
        results = {"sync": {}, "async": {}, "latency_ms": 0}

        # Encrypt sensitive fields before writing (if enabled)
        write_payload = payload
        encrypted_fields = []
        if self.field_encryption:
            try:
                write_payload = self.field_encryption.encrypt_payload(
                    dict(payload), table=data_type,
                    tenant_id=payload.get("tenant_id"))
                encrypted_fields = [
                    k for k, v in write_payload.items()
                    if isinstance(v, dict) and v.get("_encrypted")
                ]
            except Exception as e:
                logger.warning(f"Field encryption failed, writing plaintext: {e}")

        # If we have a PG pool, do sync writes + outbox inserts in ONE transaction
        if self.pool and route["async"]:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    # Sync engine writes inside transaction
                    for engine_name in route["sync"]:
                        if engine_name in self.engines:
                            try:
                                result = await self.engines[engine_name].write(
                                    data_type, write_payload, actor)
                                results["sync"][engine_name] = {"status": "success", "result": result}
                            except Exception as e:
                                results["sync"][engine_name] = {"status": "error", "error": str(e)}
                                raise

                    # Insert async engine writes into outbox (same transaction)
                    for engine_name in route["async"]:
                        if engine_name in self.engines:
                            await conn.execute("""
                                INSERT INTO write_outbox (data_type, payload, actor, target_engine, tenant_id)
                                VALUES ($1, $2::jsonb, $3, $4, $5)
                            """, data_type,
                                json.dumps(write_payload, default=str),
                                actor, engine_name, tenant_id)
                            self._stats["outbox_queued"] += 1
                            results["async"][engine_name] = {"status": "outbox_queued"}
        else:
            # Fallback: no pool or no async engines — sync writes only
            for engine_name in route["sync"]:
                if engine_name in self.engines:
                    try:
                        result = await self.engines[engine_name].write(
                            data_type, write_payload, actor)
                        results["sync"][engine_name] = {"status": "success", "result": result}
                    except Exception as e:
                        results["sync"][engine_name] = {"status": "error", "error": str(e)}
                        raise

            # Legacy in-process async for engines without outbox
            for engine_name in route["async"]:
                if engine_name in self.engines:
                    self._task_counter += 1
                    task_id = f"async-{self._task_counter}"
                    task = asyncio.create_task(
                        self._tracked_async_write(task_id, engine_name, data_type, write_payload, actor))
                    self._pending_tasks[task_id] = task

        # Periodic cleanup of completed background tasks to prevent unbounded growth
        if len(self._pending_tasks) > 100:
            self._cleanup_completed_tasks()

        results["latency_ms"] = (time.perf_counter() - start) * 1000

        # Report which fields were encrypted in the result
        if encrypted_fields:
            results["encryption"] = {
                "encrypted_fields": encrypted_fields,
            }

        # Audit log the write
        if self.audit:
            try:
                from cortexdb.compliance.audit import AuditEventType
                sync_engines = list(results.get("sync", {}).keys())
                async_engines = list(results.get("async", {}).keys())
                await self.audit.log(
                    event_type=AuditEventType.DATA_WRITE,
                    actor=actor,
                    resource=data_type,
                    action="write",
                    outcome="success",
                    tenant_id=payload.get("tenant_id"),
                    details={
                        "data_type": data_type,
                        "sync_engines": sync_engines,
                        "async_engines": async_engines,
                        "encrypted_fields": encrypted_fields,
                    },
                )
            except Exception as e:
                logger.warning(f"Audit logging error on write: {e}")

        # Invalidate caches after write (including tenant-scoped R0 eviction)
        if self.cache_invalidation:
            self._task_counter += 1
            task = asyncio.create_task(self._safe_cache_invalidation(data_type, write_payload))
            self._pending_tasks[f"cache-{self._task_counter}"] = task

        # Evict R0 entries for the affected tenant to prevent stale reads
        if tenant_id and hasattr(self, '_read_cascade') and self._read_cascade:
            await self._read_cascade.invalidate_tenant_cache(tenant_id)

        return results

    async def _tracked_async_write(self, task_id: str, engine_name: str,
                                    data_type: str, payload: Dict,
                                    actor: str, retries: int = 3):
        """Fallback async write when outbox is unavailable."""
        for attempt in range(retries):
            try:
                await self.engines[engine_name].write(data_type, payload, actor)
                return
            except Exception as e:
                if attempt < retries - 1:
                    await asyncio.sleep(0.1 * (2 ** attempt))
                else:
                    logger.error(f"Async write to {engine_name} failed after "
                                 f"{retries} retries: {e}")

    async def _safe_cache_invalidation(self, data_type: str, payload: Dict):
        try:
            await self.cache_invalidation.on_write(data_type, payload)
        except Exception as e:
            logger.warning(f"Cache invalidation failed: {e}")

    def _cleanup_completed_tasks(self):
        done = [tid for tid, task in self._pending_tasks.items() if task.done()]
        for tid in done:
            task = self._pending_tasks.pop(tid)
            if task.exception():
                logger.error(f"Background task {tid} exception: {task.exception()}")

    async def drain(self, timeout: float = 30.0):
        """Wait for pending in-process tasks + outbox to drain."""
        self._cleanup_completed_tasks()
        if self._pending_tasks:
            logger.info(f"Draining {len(self._pending_tasks)} in-process tasks...")
            pending = list(self._pending_tasks.values())
            try:
                await asyncio.wait_for(
                    asyncio.gather(*pending, return_exceptions=True), timeout=timeout)
            except asyncio.TimeoutError:
                logger.warning(f"Drain timeout: {len(self._pending_tasks)} tasks still pending")
            self._cleanup_completed_tasks()

        # Wait for outbox worker to finish processing pending entries
        if self._outbox_worker:
            await self._outbox_worker.wait_for_drain(timeout=timeout)

    @property
    def pending_count(self) -> int:
        return len(self._pending_tasks)

    @property
    def dlq(self) -> List[Dict]:
        """Dead letter queue — now backed by outbox table.
        Returns empty list for sync callers; use dlq_async() for PG-backed data."""
        return []

    async def dlq_async(self) -> List[Dict]:
        """Query dead-letter entries from the outbox table."""
        if not self.pool:
            return []
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM write_outbox WHERE status = 'dead_letter' ORDER BY id LIMIT 1000"
            )
            return [dict(row) for row in rows]

    def get_stats(self) -> Dict:
        self._cleanup_completed_tasks()
        return {
            **self._stats,
            "pending_in_process": len(self._pending_tasks),
        }

    async def get_stats_async(self) -> Dict:
        """Extended stats including outbox table counts."""
        base = self.get_stats()
        if self._outbox_worker:
            base["outbox"] = await self._outbox_worker.get_metrics()
        return base


class CortexDB:
    """CortexDB - AI Agent Data Infrastructure.

    Intelligence layer providing cross-engine queries, semantic caching,
    write fan-out, and agent discovery on top of PostgreSQL, Redis, and Qdrant.
    """

    def __init__(self, config: Optional[Dict] = None):
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
        self.embedding_sync = None
        self.agent_memory = None
        self.rag = None
        self.hybrid_search = None
        self.outbox_worker = None
        self.field_encryption = None
        self.compliance_audit = None
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
            "immutable": {"url": os.getenv("RELATIONAL_CORE_URL", "postgresql://cortex:cortex_secret@localhost:5432/cortexdb")},
            "graph": {"url": os.getenv("GRAPH_CORE_URL", "postgresql://cortex:cortex_secret@localhost:5432/cortexdb")},
        }

    async def connect(self):
        logger.info("CortexDB v6.1 initializing...")

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
                # ImmutableCore shares the relational pool for PG-backed ledger
                if name == "immutable" and "relational" in self.engines:
                    cfg["relational_engine"] = self.engines["relational"]
                engine = cls(cfg)
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

        # Optional field encryption (requires CORTEX_ENCRYPTION_KEY env var)
        try:
            encryption_key = os.getenv("CORTEX_ENCRYPTION_KEY", "")
            if encryption_key:
                from cortexdb.compliance.encryption import FieldEncryption, KeyManager
                key_manager = KeyManager(master_key=encryption_key)
                self.field_encryption = FieldEncryption(key_manager)
                logger.info("  + FIELD ENCRYPTION enabled")
            else:
                logger.info("  - Field encryption disabled (set CORTEX_ENCRYPTION_KEY to enable)")
        except Exception as e:
            logger.warning(f"  x FIELD ENCRYPTION unavailable: {e}")

        # Initialize compliance audit trail
        try:
            from cortexdb.compliance.audit import ComplianceAudit
            self.compliance_audit = ComplianceAudit(engines=self.engines)
            logger.info("  + COMPLIANCE AUDIT trail initialized")
        except Exception as e:
            logger.warning(f"  x COMPLIANCE AUDIT unavailable: {e}")

        # Get PG pool for outbox pattern
        pg_pool = getattr(self.engines.get("relational"), "pool", None)

        self.read_cascade = ReadCascade(self.engines, self.tenant_isolation,
                                        field_encryption=self.field_encryption,
                                        audit=self.compliance_audit)
        self.write_fanout = WriteFanOut(self.engines, self.cache_invalidation,
                                        pool=pg_pool,
                                        field_encryption=self.field_encryption,
                                        audit=self.compliance_audit)
        self.write_fanout._read_cascade = self.read_cascade
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
        except Exception as e:
            logger.warning(f"Embedding pipeline unavailable: {e}")

        # Initialize Hybrid Search
        if self.embedding:
            try:
                from cortexdb.core.hybrid_search import HybridSearch
                self.hybrid_search = HybridSearch(self.engines, self.embedding)
                logger.info("  + HYBRID SEARCH initialized (dense + sparse + re-ranking)")
            except Exception as e:
                logger.warning(f"  x HYBRID SEARCH unavailable: {e}")

        # Start Embedding Sync Pipeline (auto-refresh vectors on PG changes)
        if self.embedding and "relational" in self.engines and "vector" in self.engines:
            try:
                from cortexdb.core.embedding_sync import EmbeddingSyncPipeline
                self.embedding_sync = EmbeddingSyncPipeline(
                    engines=self.engines,
                    embedding_pipeline=self.embedding,
                )
                await self.embedding_sync.install_triggers()
                await self.embedding_sync.start()
                logger.info("  + EMBEDDING SYNC pipeline started")
            except Exception as e:
                logger.warning(f"  x EMBEDDING SYNC unavailable: {e}")

        # Start Outbox Worker (transactional outbox for crash-safe async writes)
        if pg_pool:
            try:
                from cortexdb.core.outbox_worker import OutboxWorker
                self.outbox_worker = OutboxWorker(pg_pool, self.engines)
                self.write_fanout._outbox_worker = self.outbox_worker
                await self.outbox_worker.start()
                logger.info("  + OUTBOX WORKER started (crash-safe async writes)")
            except Exception as e:
                logger.warning(f"  x OUTBOX WORKER unavailable: {e}")

        # Initialize Agent Memory Protocol
        if self.embedding:
            try:
                from cortexdb.core.agent_memory import AgentMemory
                self.agent_memory = AgentMemory(
                    engines=self.engines,
                    embedding=self.embedding,
                )
                logger.info("  + AGENT MEMORY protocol initialized")
            except Exception as e:
                logger.warning(f"  x AGENT MEMORY unavailable: {e}")

        # Initialize RAG pipeline
        if self.embedding:
            try:
                from cortexdb.core.chunking import ChunkingPipeline
                from cortexdb.core.rag import RAGPipeline
                self.rag = RAGPipeline(self.engines, self.embedding)
                logger.info("  + RAG PIPELINE initialized")
            except Exception as e:
                logger.warning(f"  x RAG PIPELINE unavailable: {e}")

        self._connected = True
        logger.info(f"CortexDB ready - {len(self.engines)}/{len(engine_classes)} engines online")

    async def query(self, cortexql: str, params: Optional[Dict] = None,
                    hint: Optional[str] = None,
                    tenant_id: Optional[str] = None) -> QueryResult:
        if not self._connected:
            raise RuntimeError("CortexDB not connected. Call await db.connect() first.")
        self._query_count += 1

        with trace_span("CortexDB.query", attributes={"tenant_id": tenant_id or ""}):
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

        with trace_span("CortexDB.write", attributes={"tenant_id": tenant_id or "", "data_type": data_type}):
            # Inject tenant_id into payload for RLS
            if tenant_id:
                payload["tenant_id"] = tenant_id

            verdict = self.amygdala.assess(json.dumps(payload, default=str), actor)
            if not verdict.allowed:
                raise PermissionError(f"Write blocked by Amygdala: {verdict.threats_detected}")
            return await self.write_fanout.write(data_type, payload, actor, tenant_id=tenant_id)

    async def health(self) -> Dict:
        health = {
            "status": "healthy", "version": "6.1.0",
            "uptime_seconds": round(time.time() - self._start_time, 1),
            "queries_total": self._query_count,
            "engines": {},
            "cache": self.read_cascade.stats if self.read_cascade else {},
            "plasticity": {"top_paths_count": len(self.plasticity.top_paths)},
            "amygdala": self.amygdala.stats,
            "bridge": self.bridge.get_stats() if self.bridge else {},
            "embedding": self.embedding.get_info() if self.embedding else {"status": "not_loaded"},
            "embedding_sync": self.embedding_sync.get_status() if self.embedding_sync else {"status": "not_loaded"},
            "sleep_cycle": self.sleep_cycle.get_status() if self.sleep_cycle else {},
            "agent_memory": self.agent_memory.get_info() if self.agent_memory else {"status": "not_loaded"},
            "rag_pipeline": self.rag.get_stats() if self.rag else {"status": "not_loaded"},
            "rag_intelligence": {
                "query_understanding": bool(self.rag and self.rag.query_understanding),
                "retrieval_feedback": bool(self.rag and self.rag.retrieval_feedback),
                "answer_grounding": bool(self.rag and self.rag.answer_grounding),
                "hierarchical_chunking": bool(self.rag and self.rag.hierarchical_chunker),
            } if self.rag else {"status": "not_loaded"},
            "hybrid_search": self.hybrid_search.get_stats() if self.hybrid_search else {"status": "not_loaded"},
            "outbox_worker": (await self.outbox_worker.get_metrics()) if self.outbox_worker else {"status": "not_loaded"},
            "encryption": self.field_encryption.get_stats() if self.field_encryption else {"status": "disabled"},
            "compliance_audit": self.compliance_audit.get_stats() if self.compliance_audit else {"status": "not_loaded"},
        }
        async def _check_engine(name, engine):
            try:
                return name, {"status": "healthy", **(await engine.health())}
            except Exception as e:
                return name, {"status": "unhealthy", "error": str(e)}

        results = await asyncio.gather(
            *[_check_engine(n, e) for n, e in self.engines.items()])
        for name, result in results:
            health["engines"][name] = result
            if result["status"] == "unhealthy":
                health["status"] = "degraded"
        return health

    async def close(self):
        # Stop outbox worker (let it finish in-flight dispatches)
        if self.outbox_worker:
            try:
                await self.outbox_worker.stop()
            except Exception as e:
                logger.warning(f"Outbox worker stop error: {e}")

        # Stop embedding sync pipeline (it holds a PG connection)
        if self.embedding_sync:
            try:
                await self.embedding_sync.stop()
            except Exception as e:
                logger.warning(f"Embedding sync stop error: {e}")

        for name, engine in self.engines.items():
            try:
                await engine.close()
            except Exception as e:
                logger.warning(f"{name} close error: {e}")
        self._connected = False
        logger.info("CortexDB shut down")
