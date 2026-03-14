"""Tests for CortexEngine Traces API — trace persistence and tenant enforcement."""

import asyncio
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from cortexdb.core.runtime.schemas import (
    StepStatus,
    TraceAppendStepRequest,
    TraceCloseRequest,
    TraceStatus,
    TraceWriteRequest,
    TraceWriteResponse,
)
from cortexdb.core.runtime.traces import TraceStore


# ---------------------------------------------------------------------------
# Schema validation tests
# ---------------------------------------------------------------------------

class TestTraceSchemaValidation:
    """Verify Pydantic schemas enforce required fields."""

    def test_trace_write_requires_tenant(self):
        with pytest.raises(Exception):
            TraceWriteRequest(name="my-trace")  # missing tenant_id

    def test_trace_write_requires_name(self):
        with pytest.raises(Exception):
            TraceWriteRequest(tenant_id="t-001")  # missing name

    def test_trace_write_valid(self):
        req = TraceWriteRequest(
            tenant_id="t-001",
            merchant_id="m-001",
            name="order-processing",
            task_id="task-123",
            request_id="req-abc",
            metadata={"source": "api"},
        )
        assert req.tenant_id == "t-001"
        assert req.name == "order-processing"
        assert req.task_id == "task-123"

    def test_append_step_requires_trace_id(self):
        with pytest.raises(Exception):
            TraceAppendStepRequest(
                tenant_id="t-001",
                name="step-1",
            )  # missing trace_id

    def test_append_step_valid(self):
        req = TraceAppendStepRequest(
            tenant_id="t-001",
            trace_id="tr-001",
            name="validate-input",
            status=StepStatus.ok,
            input={"key": "value"},
            output={"result": True},
            duration_ms=42.5,
        )
        assert req.trace_id == "tr-001"
        assert req.status == StepStatus.ok
        assert req.duration_ms == 42.5

    def test_close_requires_trace_id(self):
        with pytest.raises(Exception):
            TraceCloseRequest(tenant_id="t-001")

    def test_trace_status_enum(self):
        assert TraceStatus.open == "open"
        assert TraceStatus.closed == "closed"
        assert TraceStatus.error == "error"

    def test_step_status_enum(self):
        assert StepStatus.ok == "ok"
        assert StepStatus.error == "error"
        assert StepStatus.warning == "warning"


# ---------------------------------------------------------------------------
# TraceStore tests (in-memory, no Postgres)
# ---------------------------------------------------------------------------

class TestTraceStoreInMemory:
    """Test TraceStore with pool=None (in-memory stub mode)."""

    @pytest.fixture
    def store(self):
        return TraceStore(pool=None)

    @pytest.mark.asyncio
    async def test_create_trace(self, store):
        trace = await store.create_trace(
            tenant_id="t-100",
            merchant_id="m-100",
            name="test-trace",
            task_id="task-1",
            request_id="req-1",
            metadata={"env": "test"},
        )
        assert trace["tenant_id"] == "t-100"
        assert trace["name"] == "test-trace"
        assert trace["status"] == "open"
        assert trace["task_id"] == "task-1"
        assert trace["request_id"] == "req-1"
        assert "id" in trace
        assert isinstance(trace["created_at"], datetime)

    @pytest.mark.asyncio
    async def test_append_step(self, store):
        trace = await store.create_trace(
            tenant_id="t-100", merchant_id=None, name="test",
        )
        step = await store.append_step(
            trace_id=trace["id"],
            tenant_id="t-100",
            name="step-1",
            status=StepStatus.ok,
            input_data={"in": 1},
            output_data={"out": 2},
            duration_ms=10.5,
        )
        assert step["trace_id"] == trace["id"]
        assert step["step_index"] == 0
        assert step["name"] == "step-1"
        assert step["duration_ms"] == 10.5

        # Second step gets index 1
        step2 = await store.append_step(
            trace_id=trace["id"],
            tenant_id="t-100",
            name="step-2",
        )
        assert step2["step_index"] == 1

    @pytest.mark.asyncio
    async def test_close_trace(self, store):
        trace = await store.create_trace(
            tenant_id="t-100", merchant_id=None, name="test",
        )
        closed = await store.close_trace(
            trace_id=trace["id"],
            tenant_id="t-100",
            status=TraceStatus.closed,
            metadata={"close_reason": "done"},
        )
        assert closed["status"] == "closed"
        assert closed["ended_at"] is not None

    @pytest.mark.asyncio
    async def test_close_trace_tenant_mismatch(self, store):
        trace = await store.create_trace(
            tenant_id="t-100", merchant_id=None, name="test",
        )
        result = await store.close_trace(
            trace_id=trace["id"],
            tenant_id="t-WRONG",
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_get_trace_with_steps(self, store):
        trace = await store.create_trace(
            tenant_id="t-100", merchant_id=None, name="test",
        )
        await store.append_step(
            trace_id=trace["id"], tenant_id="t-100", name="s1",
        )
        await store.append_step(
            trace_id=trace["id"], tenant_id="t-100", name="s2",
        )

        result = await store.get_trace(trace_id=trace["id"], tenant_id="t-100")
        assert result is not None
        assert len(result["steps"]) == 2
        assert result["steps"][0]["name"] == "s1"
        assert result["steps"][1]["name"] == "s2"

    @pytest.mark.asyncio
    async def test_get_trace_tenant_isolation(self, store):
        trace = await store.create_trace(
            tenant_id="t-100", merchant_id=None, name="test",
        )
        result = await store.get_trace(trace_id=trace["id"], tenant_id="t-OTHER")
        assert result is None

    @pytest.mark.asyncio
    async def test_list_traces(self, store):
        await store.create_trace(tenant_id="t-100", merchant_id=None, name="a")
        await store.create_trace(tenant_id="t-100", merchant_id=None, name="b", task_id="task-1")
        await store.create_trace(tenant_id="t-200", merchant_id=None, name="c")

        # All for t-100
        traces = await store.list_traces(tenant_id="t-100")
        assert len(traces) == 2

        # Filtered by task_id
        traces = await store.list_traces(tenant_id="t-100", task_id="task-1")
        assert len(traces) == 1
        assert traces[0]["name"] == "b"

        # Different tenant
        traces = await store.list_traces(tenant_id="t-200")
        assert len(traces) == 1


# ---------------------------------------------------------------------------
# Tenant enforcement tests
# ---------------------------------------------------------------------------

class TestTracesTenantEnforcement:
    def test_tenant_mismatch_raises(self):
        from cortexdb.core.runtime.trace_router import _enforce_tenant
        from fastapi import HTTPException

        request = MagicMock()
        request.state.tenant_id = "t-AAA"

        with pytest.raises(HTTPException) as exc_info:
            _enforce_tenant(request, "t-BBB")
        assert exc_info.value.status_code == 403

    def test_tenant_match_passes(self):
        from cortexdb.core.runtime.trace_router import _enforce_tenant

        request = MagicMock()
        request.state.tenant_id = "t-AAA"

        result = _enforce_tenant(request, "t-AAA")
        assert result == "t-AAA"


# ---------------------------------------------------------------------------
# Router endpoint tests via FastAPI TestClient
# ---------------------------------------------------------------------------

class TestTraceEndpoints:
    """Integration-style tests using FastAPI TestClient."""

    @pytest.fixture
    def client(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from cortexdb.core.runtime.trace_router import mount_trace_routes
        from starlette.middleware.base import BaseHTTPMiddleware

        app = FastAPI()

        class FakeTenantMiddleware(BaseHTTPMiddleware):
            async def dispatch(self, request, call_next):
                request.state.tenant_id = request.headers.get("X-Tenant-Id", "test-tenant")
                return await call_next(request)

        app.add_middleware(FakeTenantMiddleware)
        mount_trace_routes(app, pool=None)

        return TestClient(app)

    def test_trace_write(self, client):
        resp = client.post(
            "/v1/traces/write",
            json={
                "tenant_id": "test-tenant",
                "name": "order-trace",
                "task_id": "task-42",
                "request_id": "req-abc",
            },
            headers={"X-Tenant-Id": "test-tenant"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "open"
        assert "trace_id" in data

    def test_trace_write_tenant_mismatch(self, client):
        resp = client.post(
            "/v1/traces/write",
            json={
                "tenant_id": "wrong-tenant",
                "name": "test",
            },
            headers={"X-Tenant-Id": "test-tenant"},
        )
        assert resp.status_code == 403

    def test_trace_append_step(self, client):
        # Create trace first
        create_resp = client.post(
            "/v1/traces/write",
            json={"tenant_id": "test-tenant", "name": "test-trace"},
            headers={"X-Tenant-Id": "test-tenant"},
        )
        trace_id = create_resp.json()["trace_id"]

        # Append step
        resp = client.post(
            "/v1/traces/append-step",
            json={
                "tenant_id": "test-tenant",
                "trace_id": trace_id,
                "name": "validate",
                "status": "ok",
                "duration_ms": 15.3,
            },
            headers={"X-Tenant-Id": "test-tenant"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["trace_id"] == trace_id
        assert data["step_index"] == 0

    def test_trace_close(self, client):
        create_resp = client.post(
            "/v1/traces/write",
            json={"tenant_id": "test-tenant", "name": "test-trace"},
            headers={"X-Tenant-Id": "test-tenant"},
        )
        trace_id = create_resp.json()["trace_id"]

        resp = client.post(
            "/v1/traces/close",
            json={
                "tenant_id": "test-tenant",
                "trace_id": trace_id,
                "status": "closed",
            },
            headers={"X-Tenant-Id": "test-tenant"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "closed"
        assert data["ended_at"] is not None

    def test_trace_close_not_found(self, client):
        resp = client.post(
            "/v1/traces/close",
            json={
                "tenant_id": "test-tenant",
                "trace_id": "nonexistent",
            },
            headers={"X-Tenant-Id": "test-tenant"},
        )
        assert resp.status_code == 404

    def test_trace_get(self, client):
        create_resp = client.post(
            "/v1/traces/write",
            json={"tenant_id": "test-tenant", "name": "test-trace"},
            headers={"X-Tenant-Id": "test-tenant"},
        )
        trace_id = create_resp.json()["trace_id"]

        # Add a step
        client.post(
            "/v1/traces/append-step",
            json={
                "tenant_id": "test-tenant",
                "trace_id": trace_id,
                "name": "step-a",
            },
            headers={"X-Tenant-Id": "test-tenant"},
        )

        resp = client.get(
            f"/v1/traces/{trace_id}",
            headers={"X-Tenant-Id": "test-tenant"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["trace_id"] == trace_id
        assert data["name"] == "test-trace"
        assert len(data["steps"]) == 1

    def test_trace_get_not_found(self, client):
        resp = client.get(
            "/v1/traces/nonexistent",
            headers={"X-Tenant-Id": "test-tenant"},
        )
        assert resp.status_code == 404

    def test_trace_list(self, client):
        client.post(
            "/v1/traces/write",
            json={"tenant_id": "test-tenant", "name": "trace-a"},
            headers={"X-Tenant-Id": "test-tenant"},
        )
        client.post(
            "/v1/traces/write",
            json={"tenant_id": "test-tenant", "name": "trace-b"},
            headers={"X-Tenant-Id": "test-tenant"},
        )

        resp = client.get(
            "/v1/traces",
            headers={"X-Tenant-Id": "test-tenant"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] >= 2

    def test_bare_path_backward_compat(self, client):
        """Verify bare /traces/* paths work alongside /v1/traces/*."""
        resp = client.post(
            "/traces/write",
            json={"tenant_id": "test-tenant", "name": "bare-test"},
            headers={"X-Tenant-Id": "test-tenant"},
        )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# V1 Runtime routing tests
# ---------------------------------------------------------------------------

class TestV1RuntimeRouting:
    """Verify /v1/runtime/* and /v1/workflows/* paths work."""

    @pytest.fixture
    def client(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from cortexdb.core.runtime.router import mount_runtime_routes
        from starlette.middleware.base import BaseHTTPMiddleware

        app = FastAPI()

        class FakeTenantMiddleware(BaseHTTPMiddleware):
            async def dispatch(self, request, call_next):
                request.state.tenant_id = request.headers.get("X-Tenant-Id", "test-tenant")
                return await call_next(request)

        app.add_middleware(FakeTenantMiddleware)
        mount_runtime_routes(app, pool=None)

        return TestClient(app)

    def test_v1_workflow_start(self, client):
        resp = client.post(
            "/v1/workflows/start",
            json={
                "tenant_id": "test-tenant",
                "workflow_type": "order_pipeline",
                "input": {"order_id": 42},
            },
            headers={"X-Tenant-Id": "test-tenant"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "pending"

    def test_v1_runtime_run(self, client):
        resp = client.post(
            "/v1/runtime/run",
            json={
                "tenant_id": "test-tenant",
                "run_type": "etl_ingest",
                "input": {"source": "s3://data"},
            },
            headers={"X-Tenant-Id": "test-tenant"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "pending"

    def test_bare_workflow_start_still_works(self, client):
        """Backward compat: bare /workflows/start still works."""
        resp = client.post(
            "/workflows/start",
            json={
                "tenant_id": "test-tenant",
                "workflow_type": "test",
            },
            headers={"X-Tenant-Id": "test-tenant"},
        )
        assert resp.status_code == 200

    def test_bare_runtime_run_still_works(self, client):
        resp = client.post(
            "/runtime/run",
            json={
                "tenant_id": "test-tenant",
                "run_type": "test",
            },
            headers={"X-Tenant-Id": "test-tenant"},
        )
        assert resp.status_code == 200
