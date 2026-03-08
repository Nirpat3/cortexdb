"""
Integration tests for CortexDB core API endpoints.

Covers health checks, CortexQL query/write, CRUD semantics, and error responses.
All tests run against the real FastAPI app with external services mocked.
"""

import pytest
import httpx


# ── Health Endpoints ────────────────────────────────────────────────────────


class TestHealthEndpoints:
    """Tests for /health/live, /health/ready, /health/deep."""

    async def test_health_live_returns_alive(self, client: httpx.AsyncClient):
        resp = await client.get("/health/live")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "alive"
        assert "timestamp" in body

    async def test_health_live_timestamp_is_numeric(self, client: httpx.AsyncClient):
        resp = await client.get("/health/live")
        ts = resp.json()["timestamp"]
        assert isinstance(ts, (int, float))
        assert ts > 0

    async def test_health_ready_returns_healthy(self, client: httpx.AsyncClient):
        resp = await client.get("/health/ready")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "healthy"
        assert "engines" in body

    async def test_health_deep_returns_full_report(self, client: httpx.AsyncClient):
        resp = await client.get("/health/deep")
        assert resp.status_code == 200
        body = resp.json()
        # Deep health includes several subsystem keys
        for key in ("deep_health", "grid", "tenants", "rate_limiter"):
            assert key in body, f"Missing key '{key}' in deep health response"

    async def test_health_metrics_returns_text(self, client: httpx.AsyncClient):
        resp = await client.get("/health/metrics")
        assert resp.status_code == 200
        assert "text/plain" in resp.headers.get("content-type", "")


# ── CortexQL Query Endpoint ────────────────────────────────────────────────


class TestQueryEndpoint:
    """Tests for POST /v1/query."""

    async def test_select_query_returns_data(self, client: httpx.AsyncClient):
        resp = await client.post("/v1/query", json={"cortexql": "SELECT * FROM users"})
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body
        assert isinstance(body["data"], list)
        assert body["tier_served"] == "R3"
        assert "latency_ms" in body

    async def test_select_query_has_engine_info(self, client: httpx.AsyncClient):
        resp = await client.post("/v1/query", json={"cortexql": "SELECT id FROM orders"})
        body = resp.json()
        assert isinstance(body["engines_hit"], list)
        assert len(body["engines_hit"]) > 0

    async def test_insert_query(self, client: httpx.AsyncClient):
        resp = await client.post("/v1/query", json={
            "cortexql": "INSERT INTO users (name) VALUES ('test')",
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"] is not None

    async def test_update_query(self, client: httpx.AsyncClient):
        resp = await client.post("/v1/query", json={
            "cortexql": "UPDATE users SET name='updated' WHERE id=1",
        })
        assert resp.status_code == 200

    async def test_delete_query(self, client: httpx.AsyncClient):
        resp = await client.post("/v1/query", json={
            "cortexql": "DELETE FROM users WHERE id=999",
        })
        assert resp.status_code == 200

    async def test_query_with_params(self, client: httpx.AsyncClient):
        resp = await client.post("/v1/query", json={
            "cortexql": "SELECT * FROM users WHERE id = $1",
            "params": {"$1": 42},
        })
        assert resp.status_code == 200

    async def test_query_with_hint(self, client: httpx.AsyncClient):
        resp = await client.post("/v1/query", json={
            "cortexql": "SELECT * FROM large_table",
            "hint": "use_index",
        })
        assert resp.status_code == 200

    async def test_empty_cortexql_returns_422(self, client: httpx.AsyncClient):
        """FastAPI validation: cortexql is required."""
        resp = await client.post("/v1/query", json={})
        assert resp.status_code == 422

    async def test_missing_body_returns_422(self, client: httpx.AsyncClient):
        resp = await client.post("/v1/query", content=b"not json",
                                 headers={"content-type": "application/json"})
        assert resp.status_code == 422


# ── CortexQL Write Endpoint ────────────────────────────────────────────────


class TestWriteEndpoint:
    """Tests for POST /v1/write."""

    async def test_basic_write(self, client: httpx.AsyncClient):
        resp = await client.post("/v1/write", json={
            "data_type": "user",
            "payload": {"name": "Alice", "email": "alice@test.com"},
            "actor": "integration_test",
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "success"
        assert "fan_out" in body

    async def test_write_with_default_actor(self, client: httpx.AsyncClient):
        resp = await client.post("/v1/write", json={
            "data_type": "event",
            "payload": {"type": "page_view", "url": "/home"},
        })
        assert resp.status_code == 200

    async def test_write_missing_data_type_returns_422(self, client: httpx.AsyncClient):
        resp = await client.post("/v1/write", json={"payload": {"x": 1}})
        assert resp.status_code == 422

    async def test_write_missing_payload_returns_422(self, client: httpx.AsyncClient):
        resp = await client.post("/v1/write", json={"data_type": "user"})
        assert resp.status_code == 422


# ── Error Responses ─────────────────────────────────────────────────────────


class TestErrorResponses:
    """Verify correct HTTP status codes for error scenarios."""

    async def test_404_unknown_route(self, client: httpx.AsyncClient):
        resp = await client.get("/v1/nonexistent/endpoint")
        assert resp.status_code == 404

    async def test_405_wrong_method(self, client: httpx.AsyncClient):
        resp = await client.get("/v1/query")  # POST only
        assert resp.status_code == 405

    async def test_superadmin_403_without_token(self, client: httpx.AsyncClient):
        resp = await client.get("/v1/superadmin/team")
        assert resp.status_code == 403

    async def test_superadmin_403_with_bad_token(self, client: httpx.AsyncClient):
        resp = await client.get("/v1/superadmin/team",
                                headers={"X-SuperAdmin-Token": "bogus-token"})
        assert resp.status_code == 403

    async def test_superadmin_login_401_wrong_passphrase(self, client: httpx.AsyncClient):
        resp = await client.post("/v1/superadmin/login",
                                 json={"passphrase": "wrong-password"})
        assert resp.status_code == 401


# ── CORS Headers ────────────────────────────────────────────────────────────


class TestCORSHeaders:
    """Verify CORS middleware is active."""

    async def test_options_preflight(self, client: httpx.AsyncClient):
        resp = await client.options("/v1/query", headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
        })
        # CORS middleware should respond (200 or 204)
        assert resp.status_code in (200, 204)

    async def test_cors_allows_origin(self, client: httpx.AsyncClient):
        resp = await client.get("/health/live", headers={
            "Origin": "http://localhost:3000",
        })
        allow = resp.headers.get("access-control-allow-origin", "")
        # Should allow localhost:3000 (set in CORTEX_CORS_ORIGINS default)
        assert "localhost" in allow or allow == "*"
