"""Runtime & Workflows FastAPI routers.

Endpoints:
  POST /workflows/start
  POST /workflows/signal
  GET  /workflows/{workflow_id}
  POST /runtime/run          (alias of /workflows/start)
  GET  /runtime/{run_id}
  POST /runtime/cancel

All endpoints enforce tenant isolation via the tenancy envelope in the
request body AND the middleware-resolved tenant context.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Request

from cortexdb.core.runtime.schemas import (
    RunStatus,
    RuntimeCancelRequest,
    RuntimeCancelResponse,
    RuntimeRunRequest,
    RuntimeRunResponse,
    WorkflowSignalRequest,
    WorkflowSignalResponse,
    WorkflowStartRequest,
    WorkflowStartResponse,
    WorkflowStatusResponse,
)
from cortexdb.core.runtime.store import RuntimeStore

logger = logging.getLogger("cortexdb.runtime.router")

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

workflows_router = APIRouter(prefix="/workflows", tags=["workflows"])
runtime_router = APIRouter(prefix="/runtime", tags=["runtime"])

# The store is injected at app startup (see mount_runtime_routes).
_store: Optional[RuntimeStore] = None


def mount_runtime_routes(app, pool) -> None:
    """Call once during lifespan startup to wire the store and include routers."""
    global _store
    _store = RuntimeStore(pool=pool)
    app.include_router(workflows_router)
    app.include_router(runtime_router)
    logger.info("Runtime routes mounted (workflows + runtime)")


def _get_store() -> RuntimeStore:
    if _store is None:
        raise HTTPException(status_code=503, detail="Runtime store not initialized")
    return _store


def _enforce_tenant(request: Request, body_tenant_id: str) -> str:
    """Ensure the body's tenant_id matches the auth-resolved tenant."""
    resolved = getattr(request.state, "tenant_id", None)
    if resolved and resolved != body_tenant_id:
        raise HTTPException(
            status_code=403,
            detail=f"Tenant mismatch: auth={resolved}, body={body_tenant_id}",
        )
    return body_tenant_id


# ---------------------------------------------------------------------------
# /workflows endpoints
# ---------------------------------------------------------------------------

@workflows_router.post("/start", response_model=WorkflowStartResponse)
async def workflow_start(body: WorkflowStartRequest, request: Request):
    tenant_id = _enforce_tenant(request, body.tenant_id)
    store = _get_store()
    run = await store.create_run(
        tenant_id=tenant_id,
        merchant_id=body.merchant_id,
        workflow_type=body.workflow_type,
        input_data=body.input,
        tags=body.tags,
        idempotency_key=body.idempotency_key,
    )
    return WorkflowStartResponse(
        workflow_id=run["id"],
        status=RunStatus(run["status"]),
        created_at=run["created_at"],
    )


@workflows_router.post("/signal", response_model=WorkflowSignalResponse)
async def workflow_signal(body: WorkflowSignalRequest, request: Request):
    tenant_id = _enforce_tenant(request, body.tenant_id)
    store = _get_store()
    ok = await store.signal_run(
        run_id=body.workflow_id,
        tenant_id=tenant_id,
        signal_name=body.signal_name,
        payload=body.payload,
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Workflow not found or tenant mismatch")
    return WorkflowSignalResponse(
        workflow_id=body.workflow_id,
        signal_name=body.signal_name,
        accepted=True,
    )


@workflows_router.get("/{workflow_id}", response_model=WorkflowStatusResponse)
async def workflow_status(workflow_id: str, request: Request):
    tenant_id = getattr(request.state, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Tenant context required")
    store = _get_store()
    run = await store.get_run(run_id=workflow_id, tenant_id=tenant_id)
    if not run:
        raise HTTPException(status_code=404, detail="Workflow not found")
    spec = run.get("spec") or {}
    return WorkflowStatusResponse(
        workflow_id=run["id"],
        tenant_id=run["tenant_id"],
        merchant_id=run.get("merchant_id"),
        workflow_type=run.get("workflow_type", spec.get("workflow_type", "")),
        status=RunStatus(run["status"]),
        input=spec.get("input", {}),
        output=run.get("output"),
        error=run.get("error"),
        tags=spec.get("tags", {}),
        created_at=run["created_at"],
        updated_at=run["updated_at"],
    )


# ---------------------------------------------------------------------------
# /runtime endpoints (convenience aliases)
# ---------------------------------------------------------------------------

@runtime_router.post("/run", response_model=RuntimeRunResponse)
async def runtime_run(body: RuntimeRunRequest, request: Request):
    """Alias of POST /workflows/start with simplified schema."""
    tenant_id = _enforce_tenant(request, body.tenant_id)
    store = _get_store()
    run = await store.create_run(
        tenant_id=tenant_id,
        merchant_id=body.merchant_id,
        workflow_type=body.run_type,
        input_data=body.input,
        tags=body.tags,
    )
    return RuntimeRunResponse(
        run_id=run["id"],
        status=RunStatus(run["status"]),
        created_at=run["created_at"],
    )


@runtime_router.get("/{run_id}", response_model=WorkflowStatusResponse)
async def runtime_get(run_id: str, request: Request):
    """Get runtime run status — delegates to the same store."""
    tenant_id = getattr(request.state, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Tenant context required")
    store = _get_store()
    run = await store.get_run(run_id=run_id, tenant_id=tenant_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    spec = run.get("spec") or {}
    return WorkflowStatusResponse(
        workflow_id=run["id"],
        tenant_id=run["tenant_id"],
        merchant_id=run.get("merchant_id"),
        workflow_type=run.get("workflow_type", spec.get("workflow_type", "")),
        status=RunStatus(run["status"]),
        input=spec.get("input", {}),
        output=run.get("output"),
        error=run.get("error"),
        tags=spec.get("tags", {}),
        created_at=run["created_at"],
        updated_at=run["updated_at"],
    )


@runtime_router.post("/cancel", response_model=RuntimeCancelResponse)
async def runtime_cancel(body: RuntimeCancelRequest, request: Request):
    tenant_id = _enforce_tenant(request, body.tenant_id)
    store = _get_store()
    run = await store.get_run(run_id=body.run_id, tenant_id=tenant_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    if RunStatus(run["status"]) in (RunStatus.completed, RunStatus.cancelled):
        return RuntimeCancelResponse(
            run_id=body.run_id,
            status=RunStatus(run["status"]),
            cancelled=False,
        )
    updated = await store.update_status(
        run_id=body.run_id,
        tenant_id=tenant_id,
        status=RunStatus.cancelled,
        error=body.reason or "Cancelled by user",
    )
    return RuntimeCancelResponse(
        run_id=body.run_id,
        status=RunStatus(updated["status"]) if updated else RunStatus.cancelled,
        cancelled=True,
    )
