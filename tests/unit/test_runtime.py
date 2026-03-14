"""Tests for CortexEngine Runtime API contracts and tenant enforcement."""

import asyncio
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cortexdb.core.runtime.schemas import (
    RunStatus,
    RuntimeCancelRequest,
    RuntimeRunRequest,
    WorkflowSignalRequest,
    WorkflowStartRequest,
    WorkflowStartResponse,
    WorkflowStatusResponse,
)
from cortexdb.core.runtime.store import RuntimeStore


# ---------------------------------------------------------------------------
# Schema validation tests
# ---------------------------------------------------------------------------

class TestSchemaValidation:
    """Verify Pydantic schemas enforce required fields and types."""

    def test_workflow_start_requires_tenant(self):
        with pytest.raises(Exception):
            WorkflowStartRequest(workflow_type="order_pipeline")  # missing tenant_id

    def test_workflow_start_valid(self):
        req = WorkflowStartRequest(
            tenant_id="t-001",
            merchant_id="m-001",
            workflow_type="order_pipeline",
            input={"order_id": 42},
            tags={"env": "staging"},
        )
        assert req.tenant_id == "t-001"
        assert req.workflow_type == "order_pipeline"
        assert req.input == {"order_id": 42}

    def test_runtime_run_request(self):
        req = RuntimeRunRequest(
            tenant_id="t-002",
            run_type="etl_ingest",
            input={"source": "s3://bucket"},
        )
        assert req.run_type == "etl_ingest"

    def test_signal_requires_workflow_id(self):
        with pytest.raises(Exception):
            WorkflowSignalRequest(tenant_id="t-001", signal_name="approve")

    def test_cancel_requires_run_id(self):
        with pytest.raises(Exception):
            RuntimeCancelRequest(tenant_id="t-001")

    def test_run_status_enum(self):
        assert RunStatus.pending == "pending"
        assert RunStatus.cancelled == "cancelled"

    def test_workflow_start_response(self):
        now = datetime.now(timezone.utc)
        resp = WorkflowStartResponse(
            workflow_id="wf-123",
            status=RunStatus.pending,
            created_at=now,
        )
        assert resp.workflow_id == "wf-123"
        assert resp.status == RunStatus.pending


# ---------------------------------------------------------------------------
# Store tests (in-memory, no Postgres)
# ---------------------------------------------------------------------------

class TestRuntimeStoreInMemory:
    """Test RuntimeStore with pool=None (in-memory stub mode)."""

    @pytest.fixture
    def store(self):
        return RuntimeStore(pool=None)

    @pytest.mark.asyncio
    async def test_create_run_returns_dict(self, store):
        run = await store.create_run(
            tenant_id="t-100",
            merchant_id="m-100",
            workflow_type="test_flow",
            input_data={"key": "value"},
            tags={"env": "test"},
        )
        assert run["tenant_id"] == "t-100"
        assert run["merchant_id"] == "m-100"
        assert run["workflow_type"] == "test_flow"
        assert run["status"] == "pending"
        assert "id" in run
        assert isinstance(run["created_at"], datetime)

    @pytest.mark.asyncio
    async def test_get_run_returns_none_without_pool(self, store):
        result = await store.get_run(run_id="nonexistent", tenant_id="t-100")
        assert result is None

    @pytest.mark.asyncio
    async def test_signal_run_returns_true_without_pool(self, store):
        result = await store.signal_run(
            run_id="wf-1", tenant_id="t-100",
            signal_name="approve", payload={"approved": True},
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_update_status_without_pool(self, store):
        result = await store.update_status(
            run_id="wf-1", tenant_id="t-100",
            status=RunStatus.cancelled, error="test cancel",
        )
        assert result["status"] == "cancelled"


# ---------------------------------------------------------------------------
# Tenant enforcement tests
# ---------------------------------------------------------------------------

class TestTenantEnforcement:
    """Verify tenant context is enforced at the router level."""

    def test_tenant_mismatch_raises(self):
        """_enforce_tenant should raise HTTPException on mismatch."""
        from cortexdb.core.runtime.router import _enforce_tenant
        from fastapi import HTTPException

        request = MagicMock()
        request.state.tenant_id = "t-AAA"

        with pytest.raises(HTTPException) as exc_info:
            _enforce_tenant(request, "t-BBB")
        assert exc_info.value.status_code == 403

    def test_tenant_match_passes(self):
        from cortexdb.core.runtime.router import _enforce_tenant

        request = MagicMock()
        request.state.tenant_id = "t-AAA"

        result = _enforce_tenant(request, "t-AAA")
        assert result == "t-AAA"

    def test_no_resolved_tenant_passes_body(self):
        """If middleware didn't set tenant (e.g. dev mode), body value is trusted."""
        from cortexdb.core.runtime.router import _enforce_tenant

        request = MagicMock()
        request.state.tenant_id = None

        result = _enforce_tenant(request, "t-CCC")
        assert result == "t-CCC"


# ---------------------------------------------------------------------------
# Router endpoint tests via FastAPI TestClient
# ---------------------------------------------------------------------------

class TestRuntimeEndpoints:
    """Integration-style tests using FastAPI TestClient."""

    @pytest.fixture
    def client(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from cortexdb.core.runtime.router import (
            mount_runtime_routes,
            workflows_router,
            runtime_router,
        )
        from starlette.middleware.base import BaseHTTPMiddleware

        app = FastAPI()

        # Fake tenant middleware that always sets tenant_id
        class FakeTenantMiddleware(BaseHTTPMiddleware):
            async def dispatch(self, request, call_next):
                request.state.tenant_id = request.headers.get("X-Tenant-Id", "test-tenant")
                return await call_next(request)

        app.add_middleware(FakeTenantMiddleware)
        mount_runtime_routes(app, pool=None)

        return TestClient(app)

    def test_workflow_start(self, client):
        resp = client.post(
            "/workflows/start",
            json={
                "tenant_id": "test-tenant",
                "workflow_type": "order_pipeline",
                "input": {"order_id": 42},
            },
            headers={"X-Tenant-Id": "test-tenant"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "pending"
        assert "workflow_id" in data

    def test_workflow_start_tenant_mismatch(self, client):
        resp = client.post(
            "/workflows/start",
            json={
                "tenant_id": "wrong-tenant",
                "workflow_type": "order_pipeline",
            },
            headers={"X-Tenant-Id": "test-tenant"},
        )
        assert resp.status_code == 403

    def test_runtime_run(self, client):
        resp = client.post(
            "/runtime/run",
            json={
                "tenant_id": "test-tenant",
                "run_type": "etl_ingest",
                "input": {"source": "s3://data"},
            },
            headers={"X-Tenant-Id": "test-tenant"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "pending"
        assert "run_id" in data

    def test_runtime_cancel_not_found(self, client):
        """Cancel a non-existent run should 404 (pool=None returns None on get)."""
        resp = client.post(
            "/runtime/cancel",
            json={
                "tenant_id": "test-tenant",
                "run_id": "nonexistent",
            },
            headers={"X-Tenant-Id": "test-tenant"},
        )
        assert resp.status_code == 404

    def test_workflow_status_not_found(self, client):
        resp = client.get(
            "/workflows/nonexistent",
            headers={"X-Tenant-Id": "test-tenant"},
        )
        assert resp.status_code == 404

    def test_runtime_get_not_found(self, client):
        resp = client.get(
            "/runtime/nonexistent",
            headers={"X-Tenant-Id": "test-tenant"},
        )
        assert resp.status_code == 404

    def test_workflow_signal_not_found(self, client):
        """Signal to non-existent workflow when pool=None signals succeed (stub)."""
        resp = client.post(
            "/workflows/signal",
            json={
                "tenant_id": "test-tenant",
                "workflow_id": "wf-stub",
                "signal_name": "approve",
                "payload": {"ok": True},
            },
            headers={"X-Tenant-Id": "test-tenant"},
        )
        # With pool=None, signal_run returns True (stub)
        assert resp.status_code == 200
        assert resp.json()["accepted"] is True
