"""
CortexDB API Server
Port 5400: CortexQL API  |  Port 5401: Health  |  Port 5402: Admin

Run: uvicorn cortexdb.server:app --host 0.0.0.0 --port 5400
"""

import time
import logging
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Any, Dict, Optional, List
from contextlib import asynccontextmanager

from cortexdb.core.database import CortexDB
from cortexdb.grid import (NodeStateMachine, RepairEngine, GridGarbageCollector,
                            GridHealthScorer, GridCoroner, ResurrectionProtocol)
from cortexdb.heartbeat import HeartbeatProtocol, HealthCheckRunner
from cortexdb.heartbeat.circuit_breaker import CircuitBreakerRegistry
from cortexdb.asa import ASAEnforcer

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")

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


@asynccontextmanager
async def lifespan(app: FastAPI):
    global db, grid_sm, repair_eng, ggc, health_scorer
    global coroner, resurrection, heartbeat, circuits, health_runner, asa

    db = CortexDB()
    await db.connect()

    grid_sm = NodeStateMachine()
    repair_eng = RepairEngine(grid_sm)
    ggc = GridGarbageCollector(grid_sm)
    health_scorer = GridHealthScorer()
    coroner = GridCoroner()
    resurrection = ResurrectionProtocol(grid_sm)

    heartbeat = HeartbeatProtocol()
    circuits = CircuitBreakerRegistry()
    health_runner = HealthCheckRunner(db.engines)
    asa = ASAEnforcer()

    await ggc.start()
    yield
    await ggc.stop()
    await db.close()


app = FastAPI(title="CortexDB", description="Consciousness-Inspired Unified Database",
              version="2.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# -- Models --

class QueryRequest(BaseModel):
    cortexql: str
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


# -- Core Endpoints --

@app.post("/v1/query", response_model=QueryResponse)
async def cortexql_query(req: QueryRequest):
    result = await db.query(req.cortexql, req.params, req.hint)
    return QueryResponse(data=result.data, tier_served=result.tier_served.value,
                         engines_hit=result.engines_hit, latency_ms=round(result.latency_ms, 3),
                         cache_hit=result.cache_hit, metadata=result.metadata)

@app.post("/v1/write")
async def cortexql_write(req: WriteRequest):
    result = await db.write(req.data_type, req.payload, req.actor)
    return {"status": "success", "fan_out": result}


# -- Health Endpoints (DOC-014) --

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
    return db_health


# -- Admin Endpoints --

@app.get("/admin/cache/stats")
async def cache_stats():
    return db.read_cascade.stats if db and db.read_cascade else {}

@app.get("/admin/plasticity/top-paths")
async def top_paths():
    return db.plasticity.top_paths if db else []

@app.get("/admin/engines")
async def engine_list():
    if not db: return {"engines": {}}
    result = {}
    for name, engine in db.engines.items():
        try: result[name] = await engine.health()
        except Exception as e: result[name] = {"status": "error", "error": str(e)}
    return {"engines": result}

@app.post("/admin/plasticity/decay")
async def trigger_decay():
    if db: db.plasticity.decay()
    return {"status": "decay_triggered"}

@app.post("/admin/ledger/verify")
async def verify_ledger():
    if "immutable" in db.engines:
        intact = await db.engines["immutable"].verify_chain()
        return {"chain_intact": intact, "entries": len(db.engines["immutable"]._chain)}
    return {"error": "ImmutableCore not connected"}


# -- Convenience Endpoints --

@app.get("/v1/blocks")
async def list_blocks(block_type: Optional[str] = None, limit: int = 50):
    query = "SELECT * FROM blocks WHERE status = 'active'"
    if block_type: query += f" AND block_type = '{block_type}'"
    query += f" ORDER BY usage_count DESC LIMIT {limit}"
    result = await db.query(query)
    return {"blocks": result.data, "tier": result.tier_served.value}

@app.get("/v1/agents")
async def list_agents(state: Optional[str] = None, limit: int = 50):
    query = "SELECT * FROM agents"
    if state: query += f" WHERE state = '{state}'"
    query += f" ORDER BY created_at DESC LIMIT {limit}"
    result = await db.query(query)
    return {"agents": result.data, "tier": result.tier_served.value}


# -- Grid Endpoints (DOC-015) --

@app.get("/v1/grid/nodes")
async def list_grid_nodes(state: Optional[str] = None):
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
async def grid_health_scores():
    if not grid_sm or not health_scorer: return {"distribution": {}}
    scores = {}
    for node in grid_sm.active_nodes:
        b = health_scorer.calculate(node)
        scores.setdefault(b.classification.value, []).append(
            {"node_id": node.node_id, "grid_address": node.grid_address, "score": round(b.total, 1)})
    return {"distribution": scores}

@app.get("/v1/grid/cemetery")
async def grid_cemetery():
    return {"reports": coroner.get_reports() if coroner else [],
            "analytics": coroner.get_death_analytics() if coroner else {}}

@app.get("/v1/grid/ggc/stats")
async def ggc_stats():
    return ggc.get_stats() if ggc else {}

@app.get("/v1/grid/resurrections")
async def resurrection_events():
    return {"events": resurrection.get_events() if resurrection else []}


# -- ASA Endpoints (DOC-015) --

@app.get("/v1/asa/standards")
async def list_standards(category: Optional[str] = None):
    standards = asa.get_all_standards(category=category) if asa else []
    return {"standards": [{"standard_id": s.standard_id, "category": s.category,
                           "title": s.title, "description": s.description,
                           "enforcement": s.enforcement.value, "source_document": s.source_document}
                          for s in standards]}

@app.get("/v1/asa/violations")
async def list_violations():
    return {"violations": asa.get_violations() if asa else [],
            "stats": asa.get_violation_stats() if asa else {}}


# -- Heartbeat Endpoints (DOC-014) --

@app.get("/v1/heartbeat/status")
async def heartbeat_status():
    return heartbeat.get_status() if heartbeat else {}

@app.get("/v1/heartbeat/circuit-breakers")
async def circuit_breaker_status():
    return {"breakers": circuits.get_all_status() if circuits else [],
            "open_circuits": circuits.get_open_circuits() if circuits else []}

@app.get("/v1/heartbeat/health-history")
async def health_history(tier: Optional[int] = None):
    from cortexdb.heartbeat.health_checks import HealthTier
    t = HealthTier(tier) if tier else None
    return {"history": health_runner.get_history(t) if health_runner else []}

@app.get("/v1/ledger/recent")
async def recent_ledger(limit: int = 20):
    if "immutable" in db.engines:
        entries = db.engines["immutable"]._chain[-limit:]
        return {"entries": entries, "total": len(db.engines["immutable"]._chain)}
    return {"error": "ImmutableCore not connected"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5400)
