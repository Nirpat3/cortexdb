"""
Shared fixtures for CortexDB integration tests.

Uses httpx.AsyncClient with the FastAPI app directly (no live server needed).
External services (Postgres, Redis, Qdrant) are mocked at the engine level.
"""

import pytest
import time
import secrets
from unittest.mock import AsyncMock, MagicMock, patch
from typing import AsyncGenerator

import httpx

# ---------------------------------------------------------------------------
# Stubs for heavy external dependencies so the FastAPI app can be imported
# without real Postgres / Redis / Qdrant connections.
# ---------------------------------------------------------------------------


class FakeEngines:
    """Mimics the db.engines dict used throughout CortexDB."""

    def __init__(self):
        self._store: dict = {}

    def get(self, key, default=None):
        return self._store.get(key, default)

    def __getitem__(self, key):
        return self._store[key]

    def __contains__(self, key):
        return key in self._store


class FakeQueryResult:
    """Mimics cortexdb.core.database.QueryResult."""

    def __init__(self, data=None):
        self.data = data or []
        self.tier_served = MagicMock(value="R3")
        self.engines_hit = ["relational"]
        self.latency_ms = 1.23
        self.cache_hit = False
        self.metadata = {}


class FakeDB:
    """Lightweight stand-in for CortexDB so lifespan doesn't touch real DBs."""

    _connected = True

    def __init__(self):
        self.engines = FakeEngines()
        self.write_fanout = None
        self.embedding = None

    async def connect(self):
        self._connected = True

    async def close(self):
        self._connected = False

    async def health(self):
        return {"status": "healthy", "engines": {}}

    async def query(self, cortexql, params=None, hint=None, tenant_id=None):
        # Simple dispatcher for test assertions
        sql = (cortexql or "").strip().upper()
        if sql.startswith("SELECT"):
            return FakeQueryResult(data=[{"id": 1, "value": "test"}])
        if sql.startswith("INSERT") or sql.startswith("CREATE"):
            return FakeQueryResult(data={"inserted": 1})
        if sql.startswith("UPDATE"):
            return FakeQueryResult(data={"updated": 1})
        if sql.startswith("DELETE"):
            return FakeQueryResult(data={"deleted": 1})
        if "INVALID" in sql:
            raise ValueError("Parse error: unrecognized CortexQL statement")
        return FakeQueryResult(data=[])

    async def write(self, data_type, payload, actor, tenant_id=None):
        return {"sync": {"relational": "ok"}, "async": {}, "latency_ms": 0.5}


class FakeHealthResult:
    is_healthy = True
    status = "healthy"
    checks = {"relational": "ok", "memory": "ok"}
    errors = []
    warnings = []


class FakeHealthRunner:
    async def check_readiness(self):
        return FakeHealthResult()

    async def check_deep_health(self):
        return FakeHealthResult()


# ---------------------------------------------------------------------------
# Patch map — replace heavy constructors with fakes before importing server
# ---------------------------------------------------------------------------


def _build_patches():
    """Return a list of (target, replacement) pairs."""
    noop = MagicMock
    anoop = AsyncMock
    return [
        ("cortexdb.server.CortexDB", FakeDB),
        ("cortexdb.server.HealthCheckRunner", lambda *a, **kw: FakeHealthRunner()),
        ("cortexdb.server.NodeStateMachine", noop),
        ("cortexdb.server.RepairEngine", noop),
        ("cortexdb.server.GridGarbageCollector", lambda *a, **kw: MagicMock(start=AsyncMock(), stop=AsyncMock(), get_stats=lambda: {})),
        ("cortexdb.server.GridHealthScorer", noop),
        ("cortexdb.server.GridCoroner", noop),
        ("cortexdb.server.ResurrectionProtocol", noop),
        ("cortexdb.server.HeartbeatProtocol", noop),
        ("cortexdb.server.CircuitBreakerRegistry", noop),
        ("cortexdb.server.ASAEnforcer", noop),
        ("cortexdb.server.TenantManager", noop),
        ("cortexdb.server.RateLimiter", lambda *a, **kw: MagicMock(check=AsyncMock(return_value=MagicMock(allowed=True, headers={})), get_stats=lambda: {})),
        ("cortexdb.server.MetricsCollector", lambda: MagicMock(record_query=MagicMock(), record_write=MagicMock(), export_prometheus=lambda: "# empty\n")),
        ("cortexdb.server.CortexMCPServer", lambda *a, **kw: MagicMock(register_cortexgraph_tools=MagicMock())),
        ("cortexdb.server.A2ARegistry", lambda *a, **kw: MagicMock(get_stats=lambda: {})),
        ("cortexdb.server.A2AProtocol", noop),
        ("cortexdb.server.IdentityResolver", noop),
        ("cortexdb.server.EventTracker", noop),
        ("cortexdb.server.RelationshipGraph", noop),
        ("cortexdb.server.BehavioralProfiler", noop),
        ("cortexdb.server.CortexGraphInsights", lambda *a, **kw: MagicMock(get_stats=lambda: {})),
        ("cortexdb.server.CitusShardManager", lambda *a, **kw: MagicMock(get_stats=lambda: {})),
        ("cortexdb.server.ReplicaRouter", lambda *a, **kw: MagicMock(get_stats=lambda: {})),
        ("cortexdb.server.AIIndexManager", lambda *a, **kw: MagicMock(get_stats=lambda: {})),
        ("cortexdb.server.DataRenderer", lambda *a, **kw: MagicMock(get_stats=lambda: {})),
        ("cortexdb.server.ComplianceFramework", lambda *a, **kw: MagicMock(get_stats=lambda: {})),
        ("cortexdb.server.FieldEncryption", lambda *a, **kw: MagicMock(get_stats=lambda: {})),
        ("cortexdb.server.KeyManager", noop),
        ("cortexdb.server.ComplianceAudit", lambda *a, **kw: MagicMock(get_stats=lambda: {})),
        ("cortexdb.server.BudgetTracker", lambda: MagicMock(initialize=AsyncMock())),
        ("cortexdb.server.ForecastingAgent", noop),
        ("cortexdb.server.AgentRegistry", lambda: MagicMock(
            register=MagicMock(), update_status=MagicMock(),
            get_all_agents=lambda: [{"agent_id": "AGT-SYS-001"}],
        )),
        ("cortexdb.server.SystemMetricsAgent", lambda: MagicMock(collect=MagicMock())),
        ("cortexdb.server.DatabaseMonitorAgent", lambda: MagicMock(initialize=AsyncMock())),
        ("cortexdb.server.ServiceMonitorAgent", lambda: MagicMock(initialize=AsyncMock())),
        ("cortexdb.server.SecurityAgent", lambda: MagicMock(initialize=AsyncMock())),
        ("cortexdb.server.ErrorTrackingAgent", lambda: MagicMock(initialize=AsyncMock())),
        ("cortexdb.server.NotificationAgent", lambda: MagicMock(initialize=AsyncMock())),
    ]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def _patched_app():
    """Import the FastAPI app with heavy deps patched out.

    Scope is *session* so we only do the expensive import+patch dance once.
    """
    patches = []
    for target, replacement in _build_patches():
        p = patch(target, replacement)
        p.start()
        patches.append(p)

    # Now safe to import
    from cortexdb.server import app  # noqa: E402
    yield app

    for p in patches:
        p.stop()


@pytest.fixture
async def client(_patched_app) -> AsyncGenerator[httpx.AsyncClient, None]:
    """Async HTTP client bound to the FastAPI app (no network)."""
    from httpx import ASGITransport
    transport = ASGITransport(app=_patched_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def superadmin_token(client: httpx.AsyncClient) -> str:
    """Authenticate as superadmin and return session token."""
    resp = await client.post("/v1/superadmin/login", json={"passphrase": "thisismydatabasebaby"})
    assert resp.status_code == 200, f"SuperAdmin login failed: {resp.text}"
    return resp.json()["token"]


@pytest.fixture
def auth_headers(superadmin_token: str) -> dict:
    """Convenience — headers dict with the superadmin token."""
    return {"X-SuperAdmin-Token": superadmin_token}


@pytest.fixture
def sample_task() -> dict:
    """A minimal task payload for creation tests."""
    return {
        "title": f"Integration test task {secrets.token_hex(4)}",
        "description": "Created by integration test suite",
        "priority": "medium",
    }


@pytest.fixture
def sample_tenant() -> dict:
    """Tenant onboarding payload."""
    tid = f"test-tenant-{secrets.token_hex(4)}"
    return {
        "tenant_id": tid,
        "name": f"Test Tenant {tid}",
        "plan": "growth",
    }
