"""
CortexDB API Server v6.1
Port 5400: CortexQL API  |  Port 5401: Health  |  Port 5402: Admin

AI Agent Data Infrastructure — cross-engine queries, semantic caching, write fan-out, A2A.
For simple CRUD, use the TypeScript SDK (@cortexdb/sdk) which connects directly to PostgreSQL.
Run: uvicorn cortexdb.server:app --host 0.0.0.0 --port 5400
"""

import asyncio
import os
import re
import time
import logging
import secrets
import hashlib
from fastapi import FastAPI, HTTPException, Request, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from pydantic import BaseModel, Field
from typing import Any, Dict, Optional, List
from contextlib import asynccontextmanager

from cortexdb.core.database import CortexDB
from cortexdb.core.cache_config import CollectionCacheConfig
from cortexdb.grid import (NodeStateMachine, RepairEngine, GridGarbageCollector,
                            GridHealthScorer, GridCoroner, ResurrectionProtocol)
from cortexdb.heartbeat import HeartbeatProtocol, HealthCheckRunner
from cortexdb.heartbeat.circuit_breaker import CircuitBreakerRegistry
from cortexdb.asa import ASAEnforcer
from cortexdb.tenant.manager import TenantManager, TenantPlan
from cortexdb.tenant.middleware import TenantMiddleware, get_current_tenant
from cortexdb.rate_limit.limiter import RateLimiter
from cortexdb.rate_limit.middleware import RateLimitMiddleware
from cortexdb.observability.metrics import MetricsCollector
from cortexdb.observability.tracing import trace_span
from cortexdb.mcp.server import CortexMCPServer
from cortexdb.a2a.registry import A2ARegistry, AgentCard
from cortexdb.a2a.protocol import A2AProtocol
from cortexdb.cortexgraph.identity import IdentityResolver
from cortexdb.cortexgraph.events import EventTracker
from cortexdb.cortexgraph.relationships import RelationshipGraph
from cortexdb.cortexgraph.profiles import BehavioralProfiler
from cortexdb.cortexgraph.insights import CortexGraphInsights
from cortexdb.scale.sharding import CitusShardManager
from cortexdb.scale.replication import ReplicaRouter
from cortexdb.scale.ai_index import AIIndexManager
from cortexdb.scale.rendering import DataRenderer, RenderConfig, RenderFormat
from cortexdb.compliance.framework import ComplianceFramework, Framework
from cortexdb.compliance.encryption import FieldEncryption, KeyManager
from cortexdb.compliance.audit import ComplianceAudit, AuditEventType

if os.getenv("CORTEX_LOG_JSON", "").lower() in ("1", "true", "yes"):
    import json as _json_log

    class _JsonFormatter(logging.Formatter):
        def format(self, record):
            return _json_log.dumps({
                "ts": self.formatTime(record),
                "level": record.levelname,
                "logger": record.name,
                "msg": record.getMessage(),
            })

    _handler = logging.StreamHandler()
    _handler.setFormatter(_JsonFormatter())
    logging.basicConfig(level=logging.INFO, handlers=[_handler])
else:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger("cortexdb.server")

db: Optional[CortexDB] = None
grid_sm: Optional[NodeStateMachine] = None
repair_eng: Optional[RepairEngine] = None
ggc: Optional[GridGarbageCollector] = None
health_scorer: Optional[GridHealthScorer] = None
coroner: Optional[GridCoroner] = None
resurrection: Optional[ResurrectionProtocol] = None
heartbeat: Optional[HeartbeatProtocol] = None
circuits: Optional[CircuitBreakerRegistry] = None
health_runner: Optional[HealthCheckRunner] = None
asa: Optional[ASAEnforcer] = None
tenant_mgr: Optional[TenantManager] = None
rate_limiter: Optional[RateLimiter] = None
metrics: Optional[MetricsCollector] = None
mcp_server: Optional[CortexMCPServer] = None
a2a_registry: Optional[A2ARegistry] = None
a2a_protocol: Optional[A2AProtocol] = None
identity_resolver: Optional[IdentityResolver] = None
event_tracker: Optional[EventTracker] = None
relationship_graph: Optional[RelationshipGraph] = None
profiler: Optional[BehavioralProfiler] = None
cortexgraph: Optional[CortexGraphInsights] = None
shard_mgr: Optional[CitusShardManager] = None
replica_router: Optional[ReplicaRouter] = None
ai_index: Optional[AIIndexManager] = None
data_renderer: Optional[DataRenderer] = None
compliance: Optional[ComplianceFramework] = None
field_encryption: Optional[FieldEncryption] = None
compliance_audit: Optional[ComplianceAudit] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global db, grid_sm, repair_eng, ggc, health_scorer
    global coroner, resurrection, heartbeat, circuits, health_runner, asa
    global tenant_mgr, rate_limiter, metrics, mcp_server, a2a_registry, a2a_protocol
    global identity_resolver, event_tracker, relationship_graph, profiler, cortexgraph
    global shard_mgr, replica_router, ai_index, data_renderer
    global compliance, field_encryption, compliance_audit

    db = CortexDB()
    await db.connect()

    # Grid
    grid_sm = NodeStateMachine()
    repair_eng = RepairEngine(grid_sm)
    ggc = GridGarbageCollector(grid_sm)
    health_scorer = GridHealthScorer()
    coroner = GridCoroner()
    resurrection = ResurrectionProtocol(grid_sm)

    # Heartbeat
    heartbeat = HeartbeatProtocol()
    circuits = CircuitBreakerRegistry()
    health_runner = HealthCheckRunner(db.engines)
    asa = ASAEnforcer()

    # Multi-Tenancy
    tenant_mgr = TenantManager(db.engines)
    await tenant_mgr.load_from_db()

    # Rate Limiting
    rate_limiter = RateLimiter(db.engines.get("memory"))

    # Observability
    metrics = MetricsCollector()

    # Setup OTel tracing (optional)
    try:
        from cortexdb.observability.tracing import setup_tracing
        setup_tracing()
    except Exception as e:
        logger.warning(f"OTel tracing setup failed (non-fatal): {e}")

    # MCP Server
    mcp_server = CortexMCPServer(db)

    # A2A — pass Redis + PG pool for cross-instance state sharing
    _redis_client = db.engines["memory"].client if "memory" in db.engines else None
    _pg_pool = db.engines["relational"].pool if "relational" in db.engines else None
    a2a_registry = A2ARegistry(db.engines, redis=_redis_client)
    a2a_protocol = A2AProtocol(a2a_registry, db.engines,
                                redis=_redis_client, pool=_pg_pool)

    # CortexGraph (DOC-020)
    embedding_pipeline = db.embedding if hasattr(db, 'embedding') else None
    identity_resolver = IdentityResolver(engines=db.engines, embedding=embedding_pipeline)
    relationship_graph = RelationshipGraph(engines=db.engines)
    event_tracker = EventTracker(
        engines=db.engines, identity_resolver=identity_resolver,
        relationship_graph=relationship_graph)
    profiler = BehavioralProfiler(engines=db.engines, embedding=embedding_pipeline)
    cortexgraph = CortexGraphInsights(
        identity_resolver=identity_resolver, event_tracker=event_tracker,
        relationship_graph=relationship_graph, profiler=profiler)

    # Register CortexGraph MCP tools
    mcp_server.register_cortexgraph_tools(cortexgraph)

    # Scale: Sharding, Replication, AI Indexing, Rendering
    shard_mgr = CitusShardManager(db.engines)
    replica_router = ReplicaRouter(db.engines, redis=_redis_client)
    ai_index = AIIndexManager(db.engines)
    data_renderer = DataRenderer(db.engines)

    # Compliance: Framework, Encryption, Audit
    key_manager = KeyManager()
    field_encryption = FieldEncryption(key_manager)
    compliance = ComplianceFramework(db.engines)
    compliance_audit = ComplianceAudit(db.engines)

    await ggc.start()
    yield

    # ── Graceful shutdown with timeouts ──
    logger.info("CortexDB shutting down...")

    # 1. Drain pending async writes (30s max)
    if db and db.write_fanout:
        try:
            await asyncio.wait_for(db.write_fanout.drain(timeout=25), timeout=30)
            logger.info(f"Async writes drained. DLQ size: {len(db.write_fanout.dlq)}")
        except asyncio.TimeoutError:
            logger.warning("Write drain timeout — some async writes may be lost")

    # 2. Stop GGC (10s max)
    try:
        await asyncio.wait_for(ggc.stop(), timeout=10)
    except asyncio.TimeoutError:
        logger.warning("GGC shutdown timeout — forcing")

    # 3. Close database connections (10s max)
    try:
        await asyncio.wait_for(db.close(), timeout=10)
    except asyncio.TimeoutError:
        logger.warning("Database close timeout — connections may leak")

    logger.info("CortexDB shutdown complete")


app = FastAPI(title="CortexDB", description="Consciousness-Inspired Unified Database - Petabyte-Scale, Compliance-Certified",
              version="6.1.0", lifespan=lifespan)
_cors_origins = os.environ.get("CORTEX_CORS_ORIGINS", "http://localhost:3000,http://localhost:5400").split(",")
_cortex_env = os.environ.get("CORTEX_ENV", "development").lower()
if "*" in _cors_origins:
    if _cortex_env == "production":
        raise RuntimeError("CORS wildcard '*' is not allowed in production mode (CORTEX_ENV=production). "
                           "Set CORTEX_CORS_ORIGINS to explicit origins.")
    else:
        logging.getLogger("cortexdb.server").warning(
            "CORS wildcard '*' detected in CORTEX_CORS_ORIGINS. "
            "This is insecure and will be rejected in production mode.")
app.add_middleware(CORSMiddleware, allow_origins=_cors_origins,
                   allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
                   allow_headers=["Authorization", "Content-Type", "X-Tenant-Key", "X-Request-ID"])

MAX_REQUEST_BODY_BYTES = 10 * 1024 * 1024  # 10 MB


class _RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > MAX_REQUEST_BODY_BYTES:
                    return Response("Request body too large", status_code=413)
            except ValueError:
                return Response("Invalid Content-Length header", status_code=400)
        elif request.method in ("POST", "PUT", "PATCH"):
            # No Content-Length header (e.g. chunked encoding) — read body and check size
            body = await request.body()
            if len(body) > MAX_REQUEST_BODY_BYTES:
                return Response("Request body too large", status_code=413)
        return await call_next(request)


app.add_middleware(_RequestSizeLimitMiddleware)
# Middleware uses module-level globals so lifespan() can inject dependencies.
# Starlette middleware instances are immutable after add_middleware(), so we
# use a lambda-style wrapper that reads from the globals at request time.
_tenant_middleware_instance = None
_rate_limit_middleware_instance = None


class _LazyTenantMiddleware(TenantMiddleware):
    """Reads tenant_manager from module global, allowing lifespan() to set it."""
    def __init__(self, app):
        super().__init__(app, tenant_manager=None)

    async def dispatch(self, request, call_next):
        self.tenant_manager = tenant_mgr  # read from module global at request time
        return await super().dispatch(request, call_next)


class _LazyRateLimitMiddleware(RateLimitMiddleware):
    """Reads rate_limiter from module global, allowing lifespan() to set it."""
    def __init__(self, app):
        super().__init__(app, rate_limiter=None)

    async def dispatch(self, request, call_next):
        self.rate_limiter = rate_limiter  # read from module global at request time
        return await super().dispatch(request, call_next)


app.add_middleware(_LazyRateLimitMiddleware)
app.add_middleware(_LazyTenantMiddleware)


def _tenant_id(request: Request) -> Optional[str]:
    return getattr(request.state, "tenant_id", None)


# -- Consistent Error Envelope --
from starlette.responses import JSONResponse

@app.exception_handler(HTTPException)
async def _http_exception_handler(request: Request, exc: HTTPException):
    """Return a consistent error envelope for all HTTP exceptions."""
    detail = exc.detail
    if isinstance(detail, dict):
        return JSONResponse({"error": detail}, status_code=exc.status_code)
    return JSONResponse({"error": {"code": exc.status_code, "message": str(detail)}},
                        status_code=exc.status_code)

@app.exception_handler(PermissionError)
async def _permission_error_handler(request: Request, exc: PermissionError):
    return JSONResponse({"error": {"code": 403, "message": "Permission denied"}},
                        status_code=403)

@app.exception_handler(Exception)
async def _generic_error_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse({"error": {"code": 500, "message": "Internal server error"}},
                        status_code=500)


# -- Models --

class QueryRequest(BaseModel):
    cortexql: str = Field(..., max_length=10000)
    params: Optional[Dict] = None
    hint: Optional[str] = None

class WriteRequest(BaseModel):
    data_type: str
    payload: Dict
    actor: str = "api"

class QueryResponse(BaseModel):
    data: Any = None
    tier_served: str = "R3"
    engines_hit: List[str] = []
    latency_ms: float = 0
    cache_hit: bool = False
    metadata: Dict = {}

class TenantOnboardRequest(BaseModel):
    tenant_id: str
    name: str
    plan: str = "free"
    config: Optional[Dict] = None

class AgentCardRequest(BaseModel):
    agent_id: str
    name: str
    description: str
    skills: List[str] = []
    tools: List[str] = []
    endpoint_url: str = ""
    protocol: str = "mcp"
    model: str = ""

class A2ATaskRequest(BaseModel):
    source_agent_id: str
    target_agent_id: str
    skill: str
    input_data: Dict = {}
    priority: int = 3

class IdentifyRequest(BaseModel):
    identifiers: Dict[str, str]
    attributes: Optional[Dict] = None

class TrackEventRequest(BaseModel):
    customer_id: str
    event_type: str
    properties: Optional[Dict] = None
    source: str = "api"
    session_id: str = ""
    channel: str = ""

class TrackBatchRequest(BaseModel):
    events: List[Dict]

class MergeCustomersRequest(BaseModel):
    canonical_id: str
    duplicate_id: str
    reason: str = "manual"

class MCPToolCallRequest(BaseModel):
    tool: str
    input: Dict = {}


# -- Core Endpoints --

@app.post("/v1/query", response_model=QueryResponse)
async def cortexql_query(req: QueryRequest, request: Request):
    tid = _tenant_id(request)
    with trace_span("cortexql_query", attributes={"tenant_id": tid or ""}):
        result = await db.query(req.cortexql, req.params, req.hint, tenant_id=tid)
        if metrics:
            metrics.record_query(result.tier_served.value, result.latency_ms, result.cache_hit, tid)
        # Return 403 if blocked by Amygdala
        if isinstance(result.data, dict) and result.data.get("error") == "BLOCKED_BY_AMYGDALA":
            raise HTTPException(403, detail={
                "error": "blocked_by_amygdala",
                "threats": result.data.get("threats", []),
            })
        return QueryResponse(data=result.data, tier_served=result.tier_served.value,
                             engines_hit=result.engines_hit, latency_ms=round(result.latency_ms, 3),
                             cache_hit=result.cache_hit, metadata=result.metadata)

@app.post("/v1/write")
async def cortexql_write(req: WriteRequest, request: Request):
    tid = _tenant_id(request)
    with trace_span("cortexql_write", attributes={"tenant_id": tid or "", "data_type": req.data_type}):
        try:
            result = await db.write(req.data_type, req.payload, req.actor, tenant_id=tid)
        except PermissionError as e:
            raise HTTPException(403, detail={"error": "blocked_by_amygdala", "message": str(e)})
        if metrics:
            metrics.record_write(req.data_type, result.get("latency_ms", 0),
                                 len(result.get("sync", {})), len(result.get("async", {})))
        return {"status": "success", "fan_out": result}


# -- Health Endpoints (DOC-014 + DOC-019) --

@app.get("/health/live")
async def health_live():
    return {"status": "alive", "timestamp": time.time()}

@app.get("/health/ready")
async def health_ready():
    if not db or not db._connected:
        raise HTTPException(503, "CortexDB not ready")
    result = await health_runner.check_readiness()
    if not result.is_healthy:
        raise HTTPException(503, result.errors)
    return {"status": result.status, "engines": result.checks}

@app.get("/health/deep")
async def health_deep():
    if not db:
        raise HTTPException(503, "CortexDB not initialized")
    db_health = await db.health()
    deep = await health_runner.check_deep_health()
    db_health["deep_health"] = {"status": deep.status, "warnings": deep.warnings, "errors": deep.errors}
    db_health["grid"] = {"active_nodes": grid_sm.topology_size if grid_sm else 0,
                         "ggc_stats": ggc.get_stats() if ggc else {}}
    db_health["tenants"] = tenant_mgr.get_stats() if tenant_mgr else {}
    db_health["a2a"] = a2a_registry.get_stats() if a2a_registry else {}
    db_health["rate_limiter"] = rate_limiter.get_stats() if rate_limiter else {}
    db_health["cortexgraph"] = cortexgraph.get_stats() if cortexgraph else {}
    db_health["sharding"] = shard_mgr.get_stats() if shard_mgr else {}
    db_health["replicas"] = replica_router.get_stats() if replica_router else {}
    db_health["ai_index"] = ai_index.get_stats() if ai_index else {}
    db_health["rendering"] = data_renderer.get_stats() if data_renderer else {}
    db_health["compliance"] = compliance.get_stats() if compliance else {}
    db_health["encryption"] = field_encryption.get_stats() if field_encryption else {}
    db_health["audit_trail"] = compliance_audit.get_stats() if compliance_audit else {}
    return db_health

@app.get("/health/metrics")
async def health_metrics():
    """Prometheus-compatible metrics endpoint."""
    if not metrics:
        return "# No metrics available\n"
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse(metrics.export_prometheus(), media_type="text/plain")


# -- Admin Endpoints --

def _require_admin(request):
    """Verify admin access via X-Admin-Token header (HMAC-verified)."""
    from starlette.responses import JSONResponse
    admin_token = os.environ.get("CORTEX_ADMIN_TOKEN", "")
    provided = request.headers.get("X-Admin-Token", "")
    if admin_token and provided and secrets.compare_digest(provided, admin_token):
        return None
    return JSONResponse({"error": "admin authentication required"}, status_code=403)

@app.get("/admin/cache/stats")
async def cache_stats(request: Request):
    denied = _require_admin(request)
    if denied: return denied
    return db.read_cascade.stats if db and db.read_cascade else {}

@app.get("/admin/plasticity/top-paths")
async def top_paths(request: Request):
    denied = _require_admin(request)
    if denied: return denied
    return db.plasticity.top_paths if db else []

@app.get("/admin/engines")
async def engine_list(request: Request):
    denied = _require_admin(request)
    if denied: return denied
    if not db: return {"engines": {}}
    result = {}
    for name, engine in db.engines.items():
        try: result[name] = await engine.health()
        except Exception as e: result[name] = {"status": "error", "error": str(e)}
    return {"engines": result}

@app.post("/admin/plasticity/decay")
async def trigger_decay(request: Request):
    denied = _require_admin(request)
    if denied: return denied
    if db: db.plasticity.decay()
    return {"status": "decay_triggered"}

@app.post("/admin/ledger/verify")
async def verify_ledger(request: Request):
    denied = _require_admin(request)
    if denied: return denied
    if "immutable" in db.engines:
        intact = await db.engines["immutable"].verify_chain()
        return {"chain_intact": intact, "entries": len(db.engines["immutable"]._chain)}
    return {"error": "ImmutableCore not connected"}

@app.post("/admin/sleep-cycle/run")
async def run_sleep_cycle(request: Request):
    denied = _require_admin(request)
    if denied: return denied
    if db and db.sleep_cycle:
        result = await db.sleep_cycle.run()
        return {"status": "completed", "tasks_run": result.tasks_run,
                "tasks_failed": result.tasks_failed, "details": result.details}
    return {"error": "Sleep cycle not available"}

@app.get("/admin/sleep-cycle/status")
async def sleep_cycle_status(request: Request):
    denied = _require_admin(request)
    if denied: return denied
    return db.sleep_cycle.get_status() if db and db.sleep_cycle else {}


@app.post("/admin/cache/config")
async def set_cache_config(request: Request):
    """Configure per-collection semantic cache thresholds.

    Body JSON fields:
      - collection (str, required): Collection name to configure
      - threshold (float, optional): Cosine similarity threshold (default 0.88)
      - r2_enabled (bool, optional): Enable/disable R2 semantic cache (default True)
      - ttl_seconds (int, optional): Cache entry TTL in seconds (default 3600)
      - negative_cache (bool, optional): Cache empty results (default False)
      - max_entries (int, optional): Max cached entries (default 10000)
    """
    denied = _require_admin(request)
    if denied: return denied
    if not db or not db.read_cascade:
        raise HTTPException(503, "CortexDB not initialized")
    body = await request.json()
    collection = body.get("collection")
    if not collection or not isinstance(collection, str):
        raise HTTPException(400, "collection (string) is required")
    import math
    try:
        ttl_val = int(body.get("ttl_seconds", 3600))
    except (ValueError, TypeError):
        raise HTTPException(400, "ttl_seconds must be a valid integer")
    try:
        max_ent_val = int(body.get("max_entries", 10000))
    except (ValueError, TypeError):
        raise HTTPException(400, "max_entries must be a valid integer")
    try:
        threshold_val = float(body.get("threshold", 0.88))
    except (ValueError, TypeError):
        raise HTTPException(400, "threshold must be a valid number")
    if not math.isfinite(threshold_val) or threshold_val < 0:
        raise HTTPException(400, "threshold must be a finite non-negative number")
    if ttl_val < 0:
        ttl_val = 3600
    if max_ent_val < 0:
        max_ent_val = 10000
    config = CollectionCacheConfig(
        threshold=threshold_val,
        r2_enabled=bool(body.get("r2_enabled", True)),
        ttl_seconds=max(0, ttl_val),
        negative_cache=bool(body.get("negative_cache", False)),
        max_entries=max(0, max_ent_val),
    )
    db.read_cascade.cache_config.set_collection_config(collection, config)
    return {
        "status": "ok",
        "collection": collection,
        "config": {
            "threshold": config.threshold,
            "r2_enabled": config.r2_enabled,
            "ttl_seconds": config.ttl_seconds,
            "negative_cache": config.negative_cache,
            "max_entries": config.max_entries,
        },
    }


@app.get("/admin/cache/config")
async def get_cache_config(request: Request):
    """Get current semantic cache configuration."""
    denied = _require_admin(request)
    if denied: return denied
    if not db or not db.read_cascade:
        raise HTTPException(503, "CortexDB not initialized")
    return db.read_cascade.cache_config.to_dict()


# -- Tenant Endpoints (DOC-019 Section 6) --

@app.post("/v1/admin/tenants")
async def tenant_onboard(req: TenantOnboardRequest, request: Request):
    denied = _require_admin(request)
    if denied: return denied
    plan = TenantPlan(req.plan) if req.plan in [p.value for p in TenantPlan] else TenantPlan.FREE
    result = await tenant_mgr.onboard(req.tenant_id, req.name, plan, req.config)
    return result

@app.get("/v1/admin/tenants")
async def tenant_list(request: Request, status: Optional[str] = None):
    denied = _require_admin(request)
    if denied: return denied
    return {"tenants": tenant_mgr.list_tenants(status) if tenant_mgr else []}

@app.get("/v1/admin/tenants/{tenant_id}")
async def tenant_get(tenant_id: str, request: Request):
    denied = _require_admin(request)
    if denied: return denied
    tenant = tenant_mgr.get_tenant(tenant_id) if tenant_mgr else None
    if not tenant:
        raise HTTPException(404, "Tenant not found")
    return {"tenant_id": tenant.tenant_id, "name": tenant.name,
            "plan": tenant.plan.value, "status": tenant.status.value,
            "rate_limits": tenant.effective_rate_limits}

@app.post("/v1/admin/tenants/{tenant_id}/activate")
async def tenant_activate(tenant_id: str, request: Request):
    denied = _require_admin(request)
    if denied: return denied
    await tenant_mgr.activate(tenant_id)
    return {"status": "activated"}

@app.post("/v1/admin/tenants/{tenant_id}/suspend")
async def tenant_suspend(tenant_id: str, request: Request, reason: str = ""):
    denied = _require_admin(request)
    if denied: return denied
    await tenant_mgr.suspend(tenant_id, reason)
    return {"status": "suspended"}

@app.post("/v1/admin/tenants/{tenant_id}/deactivate")
async def tenant_deactivate(tenant_id: str, request: Request):
    denied = _require_admin(request)
    if denied: return denied
    await tenant_mgr.deactivate(tenant_id)
    return {"status": "offboarding"}

@app.post("/v1/admin/tenants/{tenant_id}/export")
async def tenant_export(tenant_id: str, request: Request):
    denied = _require_admin(request)
    if denied: return denied
    return await tenant_mgr.export_data(tenant_id)

@app.post("/v1/admin/tenants/{tenant_id}/purge")
async def tenant_purge(tenant_id: str, request: Request):
    denied = _require_admin(request)
    if denied: return denied
    return await tenant_mgr.purge(tenant_id)

@app.get("/v1/admin/tenants/{tenant_id}/isolation")
async def tenant_isolation_report(tenant_id: str, request: Request):
    denied = _require_admin(request)
    if denied: return denied
    if db and db.tenant_isolation:
        return await db.tenant_isolation.isolation_report(tenant_id)
    return {"error": "Tenant isolation not initialized"}


# -- Convenience Endpoints --

@app.get("/v1/blocks")
async def list_blocks(request: Request, block_type: Optional[str] = None, limit: int = 50):
    limit = max(1, min(limit, 500))  # Bound limit
    params = []
    query = "SELECT * FROM blocks WHERE status = 'active'"
    if block_type:
        if not block_type.isalnum() and not all(c.isalnum() or c in '-_' for c in block_type):
            raise HTTPException(400, "Invalid block_type format")
        params.append(block_type)
        query += f" AND block_type = ${len(params)}"
    params.append(limit)
    query += f" ORDER BY usage_count DESC LIMIT ${len(params)}"
    result = await db.query(query, tenant_id=_tenant_id(request), params=params)
    return {"blocks": result.data, "tier": result.tier_served.value}

@app.get("/v1/agents")
async def list_agents(request: Request, state: Optional[str] = None, limit: int = 50):
    limit = max(1, min(limit, 500))  # Bound limit
    params = []
    query = "SELECT * FROM agents"
    if state:
        VALID_STATES = {"idle", "running", "paused", "stopped", "error", "active"}
        if state not in VALID_STATES:
            raise HTTPException(400, f"Invalid state. Must be one of: {VALID_STATES}")
        params.append(state)
        query += f" WHERE state = ${len(params)}"
    params.append(limit)
    query += f" ORDER BY created_at DESC LIMIT ${len(params)}"
    result = await db.query(query, tenant_id=_tenant_id(request), params=params)
    return {"agents": result.data, "tier": result.tier_served.value}


# -- Grid Endpoints (DOC-015) --

@app.get("/v1/grid/nodes")
async def list_grid_nodes(request: Request, state: Optional[str] = None):
    denied = _require_admin(request)
    if denied: return denied
    nodes = grid_sm.active_nodes if grid_sm else []
    if state: nodes = [n for n in nodes if n.state.value == state]
    return {"nodes": [{"node_id": n.node_id, "grid_address": n.grid_address,
                       "node_type": n.node_type, "state": n.state.value,
                       "health_score": n.health_score, "dashboard_color": n.dashboard_color,
                       "routes_traffic": n.routes_traffic,
                       "time_since_heartbeat": round(n.time_since_heartbeat, 1),
                       "failure_count": n.failure_count}
                      for n in nodes], "total": len(nodes)}

@app.get("/v1/grid/health-scores")
async def grid_health_scores(request: Request):
    denied = _require_admin(request)
    if denied: return denied
    if not grid_sm or not health_scorer: return {"distribution": {}}
    scores = {}
    for node in grid_sm.active_nodes:
        b = health_scorer.calculate(node)
        scores.setdefault(b.classification.value, []).append(
            {"node_id": node.node_id, "grid_address": node.grid_address, "score": round(b.total, 1)})
    return {"distribution": scores}

@app.get("/v1/grid/cemetery")
async def grid_cemetery(request: Request):
    denied = _require_admin(request)
    if denied: return denied
    return {"reports": coroner.get_reports() if coroner else [],
            "analytics": coroner.get_death_analytics() if coroner else {}}

@app.get("/v1/grid/ggc/stats")
async def ggc_stats(request: Request):
    denied = _require_admin(request)
    if denied: return denied
    return ggc.get_stats() if ggc else {}

@app.get("/v1/grid/resurrections")
async def resurrection_events(request: Request):
    denied = _require_admin(request)
    if denied: return denied
    return {"events": resurrection.get_events() if resurrection else []}


# -- ASA Endpoints (DOC-015) --

@app.get("/v1/asa/standards")
async def list_standards(request: Request, category: Optional[str] = None):
    denied = _require_admin(request)
    if denied: return denied
    standards = asa.get_all_standards(category=category) if asa else []
    return {"standards": [{"standard_id": s.standard_id, "category": s.category,
                           "title": s.title, "description": s.description,
                           "enforcement": s.enforcement.value, "source_document": s.source_document}
                          for s in standards]}

@app.get("/v1/asa/violations")
async def list_violations(request: Request):
    denied = _require_admin(request)
    if denied: return denied
    return {"violations": asa.get_violations() if asa else [],
            "stats": asa.get_violation_stats() if asa else {}}


# -- Heartbeat Endpoints (DOC-014) --

@app.get("/v1/heartbeat/status")
async def heartbeat_status(request: Request):
    denied = _require_admin(request)
    if denied: return denied
    return heartbeat.get_status() if heartbeat else {}

@app.get("/v1/heartbeat/circuit-breakers")
async def circuit_breaker_status(request: Request):
    denied = _require_admin(request)
    if denied: return denied
    return {"breakers": circuits.get_all_status() if circuits else [],
            "open_circuits": circuits.get_open_circuits() if circuits else []}

@app.get("/v1/heartbeat/health-history")
async def health_history(request: Request, tier: Optional[int] = None):
    denied = _require_admin(request)
    if denied: return denied
    from cortexdb.heartbeat.health_checks import HealthTier
    t = None
    if tier is not None:
        try:
            t = HealthTier(tier)
        except ValueError:
            raise HTTPException(400, f"Invalid tier: {tier}. Valid values: {[e.value for e in HealthTier]}")
    return {"history": health_runner.get_history(t) if health_runner else []}

@app.get("/v1/ledger/recent")
async def recent_ledger(request: Request, limit: int = 20):
    denied = _require_admin(request)
    if denied: return denied
    limit = max(1, min(limit, 500))
    if "immutable" in db.engines:
        entries = db.engines["immutable"]._chain[-limit:]
        return {"entries": entries, "total": len(db.engines["immutable"]._chain)}
    return {"error": "ImmutableCore not connected"}


# -- MCP Server Endpoints (DOC-017 Section 10, DOC-018 G18) --

@app.get("/v1/mcp/tools")
async def mcp_list_tools():
    return {"tools": mcp_server.list_tools() if mcp_server else [],
            "server_info": mcp_server.get_server_info() if mcp_server else {}}

@app.post("/v1/mcp/call")
async def mcp_call_tool(req: MCPToolCallRequest, request: Request):
    if not mcp_server:
        raise HTTPException(503, "MCP Server not initialized")
    # Enforce tenant isolation: override any user-supplied tenant_id with
    # the authenticated tenant from middleware to prevent cross-tenant access.
    tid = _tenant_id(request)
    tool_input = dict(req.input)
    if tid:
        tool_input["tenant_id"] = tid
    result = await mcp_server.call_tool(req.tool, tool_input)
    if result.is_error:
        raise HTTPException(400, result.error_message)
    return {"result": result.content}


# -- A2A Endpoints (DOC-017 Section 10, DOC-018 G19) --

@app.post("/v1/a2a/register")
async def a2a_register(req: AgentCardRequest, request: Request):
    card = AgentCard(
        agent_id=req.agent_id, name=req.name, description=req.description,
        skills=req.skills, tools=req.tools, endpoint_url=req.endpoint_url,
        protocol=req.protocol, model=req.model,
        tenant_id=_tenant_id(request))
    result = await a2a_registry.register(card)
    return result

@app.get("/v1/a2a/discover")
async def a2a_discover(skill: str, request: Request, limit: int = 5):
    return {"agents": await a2a_registry.discover(
        skill, tenant_id=_tenant_id(request), limit=limit)}

@app.get("/v1/a2a/agents")
async def a2a_list_agents(request: Request):
    return {"agents": a2a_registry.list_cards(tenant_id=_tenant_id(request))}

@app.post("/v1/a2a/heartbeat/{agent_id}")
async def a2a_heartbeat(agent_id: str):
    ok = await a2a_registry.heartbeat(agent_id)
    return {"status": "ok" if ok else "not_found"}

@app.post("/v1/a2a/task")
async def a2a_create_task(req: A2ATaskRequest, request: Request):
    task = await a2a_protocol.create_task(
        source_agent_id=req.source_agent_id,
        target_agent_id=req.target_agent_id,
        skill=req.skill, input_data=req.input_data,
        tenant_id=_tenant_id(request), priority=req.priority)
    return {"task_id": task.task_id, "status": task.status.value}

@app.get("/v1/a2a/tasks")
async def a2a_list_tasks(request: Request, agent_id: Optional[str] = None,
                         status: Optional[str] = None):
    return {"tasks": await a2a_protocol.list_tasks(
        agent_id=agent_id, status=status,
        tenant_id=_tenant_id(request))}

@app.post("/v1/a2a/task/{task_id}/complete")
async def a2a_complete_task(task_id: str, request: Request, body: dict = None):
    if not body or "output" not in body:
        raise HTTPException(422, "Required field: output")
    agent_id = body.get("agent_id") or request.headers.get("X-Agent-ID")
    task = await a2a_protocol.complete_task(task_id, body["output"], agent_id=agent_id)
    if not task:
        raise HTTPException(404, "Task not found, wrong state, or unauthorized agent")
    return {"task_id": task.task_id, "status": task.status.value}


# -- CortexGraph Endpoints (DOC-020) --

@app.post("/v1/cortexgraph/identify")
async def cg_identify(req: IdentifyRequest, request: Request):
    """Identity resolution: resolve identifiers to a customer_id."""
    tid = _tenant_id(request)
    result = await identity_resolver.identify(
        req.identifiers, tenant_id=tid, attributes=req.attributes)
    return result

@app.post("/v1/cortexgraph/track")
async def cg_track(req: TrackEventRequest, request: Request):
    """Track a customer event across all engines."""
    tid = _tenant_id(request)
    result = await event_tracker.track(
        customer_id=req.customer_id, event_type=req.event_type,
        properties=req.properties, source=req.source,
        session_id=req.session_id, channel=req.channel, tenant_id=tid)
    return result

@app.post("/v1/cortexgraph/track/batch")
async def cg_track_batch(req: TrackBatchRequest, request: Request):
    """Batch track multiple customer events."""
    tid = _tenant_id(request)
    result = await event_tracker.track_batch(req.events, tenant_id=tid)
    return result

@app.get("/v1/cortexgraph/customer/{customer_id}/360")
async def cg_customer_360(customer_id: str, request: Request):
    """Complete customer intelligence: identity + events + relationships + profile."""
    tid = _tenant_id(request)
    return await cortexgraph.customer_360(customer_id, tenant_id=tid)

@app.get("/v1/cortexgraph/customer/{customer_id}/profile")
async def cg_customer_profile(customer_id: str, request: Request):
    """Get or compute behavioral profile for a customer."""
    tid = _tenant_id(request)
    profile = await profiler.get_profile(customer_id, tenant_id=tid)
    return {"customer_id": customer_id, "profile": profile}

@app.get("/v1/cortexgraph/customer/{customer_id}/events")
async def cg_customer_events(customer_id: str, request: Request,
                              event_type: Optional[str] = None,
                              days: int = 90, limit: int = 100):
    """Query events for a customer."""
    tid = _tenant_id(request)
    events = await event_tracker.query_events(
        customer_id, event_type=event_type, days=days,
        tenant_id=tid, limit=limit)
    return {"customer_id": customer_id, "events": events}

@app.get("/v1/cortexgraph/customer/{customer_id}/connections")
async def cg_customer_connections(customer_id: str, request: Request):
    """Get all graph connections for a customer."""
    tid = _tenant_id(request)
    connections = await relationship_graph.get_customer_connections(customer_id, tid)
    return {"customer_id": customer_id, "connections": connections}

@app.get("/v1/cortexgraph/similar/{customer_id}")
async def cg_similar_customers(customer_id: str, request: Request, limit: int = 50):
    """Find customers with similar behavioral patterns."""
    tid = _tenant_id(request)
    results = await cortexgraph.find_similar_customers(customer_id, limit, tid)
    return {"customer_id": customer_id, "similar": results}

@app.get("/v1/cortexgraph/churn-risk")
async def cg_churn_risk(request: Request, threshold: float = 0.7, limit: int = 50):
    """Get customers at risk of churning."""
    tid = _tenant_id(request)
    results = await cortexgraph.get_churn_risk_customers(threshold, tid, limit)
    return {"at_risk": results, "threshold": threshold}

@app.post("/v1/cortexgraph/recommend/{customer_id}")
async def cg_recommend(customer_id: str, request: Request, limit: int = 5):
    """Product recommendations via collaborative filtering."""
    tid = _tenant_id(request)
    results = await cortexgraph.recommend_products(customer_id, limit, tid)
    return {"customer_id": customer_id, "recommendations": results}

@app.get("/v1/cortexgraph/attribution/{campaign_id}")
async def cg_attribution(campaign_id: str, request: Request):
    """Campaign attribution analysis."""
    tid = _tenant_id(request)
    return await cortexgraph.campaign_attribution(campaign_id, tid)

@app.post("/v1/cortexgraph/merge")
async def cg_merge(req: MergeCustomersRequest, request: Request):
    """Merge two customer records."""
    tid = _tenant_id(request)
    result = await identity_resolver.merge(
        req.canonical_id, req.duplicate_id, req.reason, tenant_id=tid)
    return result

@app.get("/v1/cortexgraph/stats")
async def cg_stats():
    """CortexGraph component statistics."""
    return cortexgraph.get_stats() if cortexgraph else {}

@app.post("/v1/cortexgraph/profiles/compute-all")
async def cg_compute_all_profiles(request: Request, limit: int = 1000):
    """Batch compute all customer profiles (Sleep Cycle trigger)."""
    tid = _tenant_id(request)
    result = await profiler.compute_all(tenant_id=tid, limit=limit)
    return result


# -- Bridge Endpoints (DOC-018 G9) --

class BridgeQueryRequest(BaseModel):
    sub_queries: List[Dict]
    merge_key: Optional[str] = None

@app.post("/v1/bridge/query")
async def bridge_query(req: BridgeQueryRequest):
    if not db or not db.bridge:
        raise HTTPException(503, "Bridge not initialized")
    return await db.bridge.query(req.sub_queries, req.merge_key)


# -- Scale: Sharding Endpoints (Citus) --

@app.post("/v1/admin/sharding/initialize")
async def sharding_init(request: Request):
    """Initialize Citus extension and sharding configuration."""
    denied = _require_admin(request)
    if denied: return denied
    if not shard_mgr:
        raise HTTPException(503, "Sharding not available")
    return await shard_mgr.initialize()

@app.post("/v1/admin/sharding/distribute")
async def sharding_distribute(request: Request):
    """Distribute all tables across Citus workers."""
    denied = _require_admin(request)
    if denied: return denied
    if not shard_mgr:
        raise HTTPException(503, "Sharding not available")
    return await shard_mgr.distribute_tables()

@app.post("/v1/admin/sharding/add-worker")
async def sharding_add_worker(request: Request, host: str, port: int = 5432):
    """Add a Citus worker node."""
    denied = _require_admin(request)
    if denied: return denied
    import re
    if not re.match(r'^[a-zA-Z0-9._-]+$', host) or len(host) > 253:
        raise HTTPException(400, "Invalid hostname format")
    if not (1 <= port <= 65535):
        raise HTTPException(400, "Port must be 1-65535")
    if not shard_mgr:
        raise HTTPException(503, "Sharding not available")
    return await shard_mgr.add_worker(host, port)

@app.post("/v1/admin/sharding/remove-worker")
async def sharding_remove_worker(request: Request, host: str, port: int = 5432):
    """Remove a Citus worker node (drains shards first)."""
    denied = _require_admin(request)
    if denied: return denied
    import re
    if not re.match(r'^[a-zA-Z0-9._-]+$', host) or len(host) > 253:
        raise HTTPException(400, "Invalid hostname format")
    if not (1 <= port <= 65535):
        raise HTTPException(400, "Port must be 1-65535")
    if not shard_mgr:
        raise HTTPException(503, "Sharding not available")
    return await shard_mgr.remove_worker(host, port)

@app.post("/v1/admin/sharding/rebalance")
async def sharding_rebalance(request: Request):
    """Rebalance shards across workers."""
    denied = _require_admin(request)
    if denied: return denied
    if not shard_mgr:
        raise HTTPException(503, "Sharding not available")
    result = await shard_mgr.rebalance()
    return {"moved": result.moved, "errors": result.errors,
            "duration_ms": result.duration_ms}

@app.get("/v1/admin/sharding/stats")
async def sharding_stats(request: Request):
    """Get shard distribution statistics."""
    denied = _require_admin(request)
    if denied: return denied
    return await shard_mgr.get_shard_stats() if shard_mgr else {}

@app.get("/v1/admin/sharding/tenant-placement/{tenant_id}")
async def sharding_tenant_placement(tenant_id: str, request: Request):
    """Find which worker hosts a tenant's data."""
    denied = _require_admin(request)
    if denied: return denied
    return await shard_mgr.get_tenant_placement(tenant_id) if shard_mgr else {}

@app.post("/v1/admin/sharding/isolate-tenant/{tenant_id}")
async def sharding_isolate_tenant(tenant_id: str, request: Request):
    """Isolate a premium tenant onto dedicated shard."""
    denied = _require_admin(request)
    if denied: return denied
    return await shard_mgr.isolate_tenant(tenant_id) if shard_mgr else {}

@app.post("/v1/admin/sharding/columnar/{table_name}")
async def sharding_enable_columnar(table_name: str, request: Request):
    """Convert a table to Citus columnar storage for analytics."""
    denied = _require_admin(request)
    if denied: return denied
    return await shard_mgr.enable_columnar(table_name) if shard_mgr else {}


# -- Scale: Replica Routing Endpoints --

@app.get("/v1/admin/replicas/stats")
async def replica_stats(request: Request):
    """Get read replica routing statistics."""
    denied = _require_admin(request)
    if denied: return denied
    return replica_router.get_stats() if replica_router else {}

@app.get("/v1/admin/replicas/lag")
async def replica_lag(request: Request):
    """Check replication lag on all replicas."""
    denied = _require_admin(request)
    if denied: return denied
    return await replica_router.check_replica_lag() if replica_router else []

@app.get("/v1/admin/replicas/pool")
async def replica_pool_stats(request: Request):
    """Get connection pool statistics."""
    denied = _require_admin(request)
    if denied: return denied
    return await replica_router.get_pool_stats() if replica_router else {}


# -- Scale: AI Index Management Endpoints --

@app.get("/v1/admin/indexes/slow-queries")
async def index_slow_queries(request: Request, limit: int = 50):
    """Analyze slow queries for index recommendations."""
    denied = _require_admin(request)
    if denied: return denied
    limit = max(1, min(limit, 200))
    return await ai_index.analyze_slow_queries(limit) if ai_index else []

@app.get("/v1/admin/indexes/recommend")
async def index_recommend(request: Request):
    """Get AI-powered index recommendations."""
    denied = _require_admin(request)
    if denied: return denied
    recs = await ai_index.recommend() if ai_index else []
    return {"recommendations": [
        {"table": r.table, "columns": r.columns, "type": r.index_type.value,
         "reason": r.reason, "priority": r.priority, "speedup": r.estimated_speedup}
        for r in recs
    ]}

@app.post("/v1/admin/indexes/create")
async def index_create(request: Request, concurrently: bool = True):
    """Create recommended indexes (CONCURRENTLY = no locks)."""
    denied = _require_admin(request)
    if denied: return denied
    if not ai_index:
        raise HTTPException(503, "AI index not available")
    await ai_index.recommend()  # Ensure recommendations are fresh
    return await ai_index.create_optimal(concurrently=concurrently)

@app.post("/v1/admin/indexes/tune-vector")
async def index_tune_vector(request: Request, collection: Optional[str] = None):
    """Auto-tune HNSW/IVF vector index parameters."""
    denied = _require_admin(request)
    if denied: return denied
    return await ai_index.tune_vector_indexes(collection) if ai_index else {}

@app.post("/v1/admin/indexes/garbage-collect")
async def index_gc(request: Request):
    """Find unused and duplicate indexes."""
    denied = _require_admin(request)
    if denied: return denied
    return await ai_index.garbage_collect() if ai_index else {}

@app.get("/v1/admin/indexes/stats")
async def index_stats(request: Request):
    """AI index manager statistics."""
    denied = _require_admin(request)
    if denied: return denied
    return ai_index.get_stats() if ai_index else {}


# -- Scale: Data Rendering Endpoints --

@app.post("/v1/admin/views/setup")
async def views_setup(request: Request):
    """Create all CortexDB materialized views."""
    denied = _require_admin(request)
    if denied: return denied
    return await data_renderer.setup_materialized_views() if data_renderer else {}

@app.post("/v1/admin/views/refresh")
async def views_refresh(request: Request, force: bool = False):
    """Refresh stale materialized views."""
    denied = _require_admin(request)
    if denied: return denied
    return await data_renderer.refresh_views(force) if data_renderer else {}

@app.get("/v1/admin/views/stats")
async def views_stats(request: Request):
    """Get materialized view statistics."""
    denied = _require_admin(request)
    if denied: return denied
    return await data_renderer.get_view_stats() if data_renderer else []

@app.get("/v1/admin/rendering/stats")
async def rendering_stats(request: Request):
    """Data rendering pipeline statistics."""
    denied = _require_admin(request)
    if denied: return denied
    return data_renderer.get_stats() if data_renderer else {}


# -- Compliance: Framework Endpoints --

@app.get("/v1/compliance/audit")
async def compliance_audit_all():
    """Run compliance audit across all frameworks."""
    if not compliance:
        raise HTTPException(503, "Compliance not available")
    report = await compliance.audit()
    return {"score": report.score, "total": report.total_controls,
            "compliant": report.compliant, "partial": report.partial,
            "non_compliant": report.non_compliant,
            "gaps": report.gaps}

@app.get("/v1/compliance/audit/{framework}")
async def compliance_audit_framework(framework: str):
    """Run compliance audit for a specific framework."""
    if not compliance:
        raise HTTPException(503, "Compliance not available")
    try:
        fw = Framework(framework)
    except ValueError:
        raise HTTPException(400, f"Unknown framework: {framework}. "
                            f"Valid: fedramp, soc2, hipaa, pci_dss, pa_dss")
    report = await compliance.audit(fw)
    return {"framework": framework, "score": report.score,
            "total": report.total_controls, "compliant": report.compliant,
            "controls": report.controls, "gaps": report.gaps}

@app.get("/v1/compliance/summary")
async def compliance_summary(request: Request):
    """Get compliance framework summary."""
    denied = _require_admin(request)
    if denied: return denied
    return compliance.get_framework_summary() if compliance else {}

@app.get("/v1/compliance/stats")
async def compliance_stats(request: Request):
    """Compliance engine statistics."""
    denied = _require_admin(request)
    if denied: return denied
    return compliance.get_stats() if compliance else {}


# -- Compliance: Encryption Endpoints --

@app.get("/v1/compliance/encryption/stats")
async def encryption_stats(request: Request):
    """Field encryption statistics and key health."""
    denied = _require_admin(request)
    if denied: return denied
    return field_encryption.get_stats() if field_encryption else {}

@app.get("/v1/compliance/encryption/classification/{table}")
async def encryption_classification(request: Request, table: str):
    """Get field sensitivity classification for a table."""
    denied = _require_admin(request)
    if denied: return denied
    return field_encryption.get_classification(table) if field_encryption else {}

@app.post("/v1/compliance/encryption/rotate-keys")
async def encryption_rotate(request: Request):
    """Rotate encryption keys that are due. Requires admin auth."""
    denied = _require_admin(request)
    if denied: return denied
    if not field_encryption:
        raise HTTPException(503, "Field encryption not available")
    due = field_encryption.key_manager.check_rotation_needed()
    rotated = []
    for key_id in due:
        field_encryption.key_manager.rotate_key(key_id)
        rotated.append(key_id)
    if compliance_audit:
        for key_id in rotated:
            await compliance_audit.log(
                AuditEventType.ENCRYPTION_KEY_ROTATED,
                actor="admin", resource=key_id, action="key_rotation")
    return {"rotated": rotated, "count": len(rotated)}


# -- Compliance: Audit Trail Endpoints --

@app.get("/v1/compliance/audit-log")
async def audit_log(request: Request,
                    event_type: Optional[str] = None,
                    actor: Optional[str] = None,
                    tenant_id: Optional[str] = None,
                    severity: Optional[str] = None,
                    limit: int = 100):
    """Query compliance audit trail."""
    if not compliance_audit:
        return {"events": []}
    # Enforce tenant access control: non-admin callers can only query their own tenant
    caller_tid = _tenant_id(request)
    is_admin = _require_admin(request) is None
    if not is_admin:
        # Restrict to caller's own tenant; ignore any user-supplied tenant_id
        tenant_id = caller_tid
    # Validate enum params to return 400 instead of 500
    et = None
    if event_type:
        try:
            et = AuditEventType(event_type)
        except ValueError:
            raise HTTPException(400, f"Invalid event_type: {event_type}")
    from cortexdb.compliance.audit import AuditSeverity
    sev = None
    if severity:
        try:
            sev = AuditSeverity(severity)
        except ValueError:
            raise HTTPException(400, f"Invalid severity: {severity}")
    events = compliance_audit.query_events(
        event_type=et, actor=actor, tenant_id=tenant_id,
        severity=sev, limit=limit)
    return {"events": events, "count": len(events)}

@app.get("/v1/compliance/evidence/{framework}")
async def compliance_evidence(framework: str):
    """Generate compliance evidence report for auditors."""
    if not compliance_audit:
        raise HTTPException(503, "Compliance audit not available")
    return await compliance_audit.generate_evidence_report(framework)

@app.get("/v1/compliance/audit-log/stats")
async def audit_log_stats():
    """Audit trail statistics."""
    return compliance_audit.get_stats() if compliance_audit else {}


# ── RAG: Hybrid Search Endpoint ──

@app.post("/v1/rag/search")
async def rag_hybrid_search(request: Request, body: dict):
    """Hybrid search: dense vectors + BM25 sparse + optional re-ranking."""
    from fastapi.responses import JSONResponse
    if "query" not in body:
        raise HTTPException(422, "Required field: query")
    tid = _tenant_id(request)
    if not db:
        return JSONResponse(status_code=503, content={"error": "Database not initialized"})
    if not db.hybrid_search:
        return JSONResponse(status_code=503, content={"error": "Hybrid search not available"})
    collection = _validate_collection(body.get("collection", "documents"))
    with trace_span("rag_hybrid_search", attributes={"tenant_id": tid or ""}):
        results = await db.hybrid_search.search(
            query=body["query"],
            collection=collection,
            limit=max(1, min(int(body.get("limit", 10)), 500)),
            tenant_id=tid,
            rerank=body.get("rerank", True),
        )
        return {"results": [{"chunk_id": r.chunk_id, "content": r.content,
                             "score": round(r.score, 4),
                             "dense_score": round(r.dense_score, 4),
                             "sparse_score": round(r.sparse_score, 4),
                             "rerank_score": round(r.rerank_score, 4) if r.rerank_score else None,
                             "metadata": r.metadata}
                            for r in results]}


# ── Benchmark Endpoints ──
# Lazy imports to avoid loading heavy benchmark deps at startup
_bench_runner = None
_stress_engine = None

def _get_bench_runner():
    global _bench_runner
    if _bench_runner is None:
        from cortexdb.benchmark.runner import BenchmarkRunner
        _bench_runner = BenchmarkRunner()
    return _bench_runner

def _get_stress_engine():
    global _stress_engine
    if _stress_engine is None:
        from cortexdb.benchmark.stress import StressTestEngine
        _stress_engine = StressTestEngine()
    return _stress_engine


@app.post("/v1/admin/benchmark/run")
async def run_benchmark(
    request: Request,
    suite: str = "quick",
    concurrency: int = 10,
    iterations: int = 1000,
):
    """Run built-in benchmark suite. suite: 'quick' or 'full'."""
    denied = _require_admin(request)
    if denied: return denied
    from cortexdb.benchmark.scenarios import ScenarioRegistry
    registry = ScenarioRegistry(db=db, engines={})
    scenarios = registry.get_quick_scenarios() if suite == "quick" else registry.get_all_scenarios()
    for s in scenarios:
        s["concurrency"] = concurrency
        if suite == "quick":
            s["iterations"] = min(iterations, 500)
    return await _get_bench_runner().run_suite(scenarios, concurrency=concurrency)


@app.get("/v1/admin/benchmark/results")
async def benchmark_results(request: Request):
    """Get results from the last benchmark run."""
    denied = _require_admin(request)
    if denied: return denied
    return _get_bench_runner().get_results()


@app.post("/v1/admin/benchmark/stress")
async def run_stress_test(
    request: Request,
    pattern: str = "ramp",
    duration_sec: int = 30,
    base_rps: int = 100,
    peak_rps: int = 500,
):
    """Run a stress test pattern (spike/soak/ramp/burst/mixed)."""
    denied = _require_admin(request)
    if denied: return denied
    stress = _get_stress_engine()
    if stress.is_running():
        return {"error": "Stress test already running"}
    valid_patterns = {"spike", "soak", "ramp", "burst", "mixed"}
    if pattern not in valid_patterns:
        raise HTTPException(400, f"Invalid pattern. Must be one of: {valid_patterns}")
    duration_sec = max(5, min(duration_sec, 300))
    base_rps = max(1, min(base_rps, 5000))
    peak_rps = max(base_rps, min(peak_rps, 10000))

    from cortexdb.benchmark.stress import StressConfig, StressPattern
    config = StressConfig(
        pattern=StressPattern(pattern),
        duration_sec=duration_sec,
        base_rps=base_rps,
        peak_rps=peak_rps,
    )

    async def _read():
        if db:
            await db.query("SELECT 1", tenant_id="__benchmark__")
        return {"ok": True}

    async def _write():
        if db:
            await db.query("SELECT 1", tenant_id="__benchmark__")
        return {"ok": True}

    result = await stress.run(config, _read, _write)
    return result.to_dict()


# ── RAG Pipeline Endpoints ─────────────────────────────────────────

MAX_RAG_TEXT_SIZE = 10 * 1024 * 1024  # 10MB max ingest size
_COLLECTION_RE = re.compile(r'^[a-zA-Z0-9_-]+$')


def _validate_collection(name: str) -> str:
    """Validate and return a collection name, or raise 400."""
    if not _COLLECTION_RE.match(name):
        raise HTTPException(status_code=400, detail="Invalid collection name. Must match ^[a-zA-Z0-9_-]+$")
    return name


@app.post("/v1/rag/ingest")
async def rag_ingest(request: Request, body: dict):
    """Ingest a document for RAG."""
    if not db or not db.rag:
        raise HTTPException(status_code=503, detail="RAG pipeline not initialized")
    if "text" not in body or "doc_id" not in body:
        raise HTTPException(status_code=422, detail="Required fields: text, doc_id")
    if len(body["text"]) > MAX_RAG_TEXT_SIZE:
        raise HTTPException(status_code=413, detail=f"Text exceeds {MAX_RAG_TEXT_SIZE // (1024*1024)}MB limit")
    tid = _tenant_id(request)
    collection = _validate_collection(body.get("collection", "documents"))
    with trace_span("rag_ingest", attributes={"tenant_id": tid or "", "doc_id": body["doc_id"]}):
        result = await db.rag.ingest(
            text=body["text"], doc_id=body["doc_id"],
            collection=collection,
            metadata=body.get("metadata"), tenant_id=tid)
        return result


@app.post("/v1/rag/retrieve")
async def rag_retrieve(request: Request, body: dict):
    """Retrieve relevant chunks for a query (basic or smart mode)."""
    if not db or not db.rag:
        raise HTTPException(status_code=503, detail="RAG pipeline not initialized")
    if "query" not in body:
        raise HTTPException(status_code=422, detail="Required field: query")
    tid = _tenant_id(request)
    collection = _validate_collection(body.get("collection", "documents"))
    result = await db.rag.retrieve_with_context(
        query=body["query"],
        collection=collection,
        limit=max(1, min(int(body.get("limit", 5)), 500)),
        max_tokens=body.get("max_tokens", 4000),
        tenant_id=tid,
        smart=body.get("smart", False))
    return result


@app.post("/v1/rag/smart-retrieve")
async def rag_smart_retrieve(request: Request, body: dict):
    """Intelligent RAG retrieval with query understanding, feedback loop, and grounding."""
    if not db or not db.rag:
        raise HTTPException(status_code=503, detail="RAG pipeline not initialized")
    if "query" not in body:
        raise HTTPException(status_code=422, detail="Required field: query")
    tid = _tenant_id(request)
    collection = _validate_collection(body.get("collection", "documents"))
    result = await db.rag.smart_retrieve(
        query=body["query"],
        collection=collection,
        limit=max(1, min(int(body.get("limit", 5)), 500)),
        threshold=body.get("threshold", 0.75),
        tenant_id=tid,
        use_feedback_loop=body.get("feedback_loop", True))
    return result


@app.post("/v1/rag/ingest/hierarchical")
async def rag_ingest_hierarchical(request: Request, body: dict):
    """Ingest with parent-child chunking for precision + rich context."""
    if not db or not db.rag:
        raise HTTPException(status_code=503, detail="RAG pipeline not initialized")
    if "text" not in body or "doc_id" not in body:
        raise HTTPException(status_code=422, detail="Required fields: text, doc_id")
    if len(body["text"]) > MAX_RAG_TEXT_SIZE:
        raise HTTPException(status_code=413, detail=f"Text exceeds {MAX_RAG_TEXT_SIZE // (1024*1024)}MB limit")
    tid = _tenant_id(request)
    collection = _validate_collection(body.get("collection", "documents"))
    result = await db.rag.ingest_hierarchical(
        text=body["text"], doc_id=body["doc_id"],
        collection=collection,
        metadata=body.get("metadata"), tenant_id=tid)
    return result


@app.delete("/v1/rag/documents/{doc_id}")
async def rag_delete(doc_id: str, request: Request):
    """Delete a document and all its chunks."""
    if not db or not db.rag:
        raise HTTPException(status_code=503, detail="RAG pipeline not initialized")
    tid = _tenant_id(request)
    result = await db.rag.delete_document(doc_id, tenant_id=tid)
    return result


@app.post("/v1/admin/benchmark/stop")
async def stop_benchmark(request: Request):
    """Stop any running benchmark or stress test."""
    denied = _require_admin(request)
    if denied: return denied
    if _bench_runner: _bench_runner.stop()
    if _stress_engine: _stress_engine.stop()
    return {"stopped": True}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5400)
