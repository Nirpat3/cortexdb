"""Trace API router — FastAPI endpoints for trace persistence.

Endpoints:
  POST /traces/write         — create a new trace
  POST /traces/append-step   — append a step to an existing trace
  POST /traces/close         — close a trace
  GET  /traces/{trace_id}    — get trace with steps
  GET  /traces               — list traces (filterable)

All endpoints enforce tenant isolation.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Request

from cortexdb.core.runtime.schemas import (
    TraceAppendStepRequest,
    TraceAppendStepResponse,
    TraceCloseRequest,
    TraceCloseResponse,
    TraceDetailResponse,
    TraceStatus,
    TraceWriteRequest,
    TraceWriteResponse,
)
from cortexdb.core.runtime.traces import TraceStore

logger = logging.getLogger("cortexdb.runtime.trace_router")

traces_router = APIRouter(prefix="/traces", tags=["traces"])

_store: Optional[TraceStore] = None


def mount_trace_routes(app, pool) -> None:
    """Call once during lifespan startup to wire the store and include router.

    Mounts at both bare /traces/* and /v1/traces/* for consistency.
    """
    global _store
    _store = TraceStore(pool=pool)
    # Bare paths (backward compat)
    app.include_router(traces_router)
    # Versioned /v1 paths
    app.include_router(traces_router, prefix="/v1")
    logger.info("Trace routes mounted (bare + /v1)")


def _get_store() -> TraceStore:
    if _store is None:
        raise HTTPException(status_code=503, detail="Trace store not initialized")
    return _store


def _enforce_tenant(request: Request, body_tenant_id: str) -> str:
    resolved = getattr(request.state, "tenant_id", None)
    if resolved and resolved != body_tenant_id:
        raise HTTPException(
            status_code=403,
            detail=f"Tenant mismatch: auth={resolved}, body={body_tenant_id}",
        )
    return body_tenant_id


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@traces_router.post("/write", response_model=TraceWriteResponse)
async def trace_write(body: TraceWriteRequest, request: Request):
    """Create a new trace."""
    tenant_id = _enforce_tenant(request, body.tenant_id)
    store = _get_store()
    trace = await store.create_trace(
        tenant_id=tenant_id,
        merchant_id=body.merchant_id,
        name=body.name,
        task_id=body.task_id,
        request_id=body.request_id,
        metadata=body.metadata,
    )
    return TraceWriteResponse(
        trace_id=trace["id"],
        status=TraceStatus(trace["status"]),
        created_at=trace["created_at"],
    )


@traces_router.post("/append-step", response_model=TraceAppendStepResponse)
async def trace_append_step(body: TraceAppendStepRequest, request: Request):
    """Append a step to an existing trace."""
    tenant_id = _enforce_tenant(request, body.tenant_id)
    store = _get_store()
    step = await store.append_step(
        trace_id=body.trace_id,
        tenant_id=tenant_id,
        name=body.name,
        status=body.status,
        input_data=body.input,
        output_data=body.output,
        error=body.error,
        duration_ms=body.duration_ms,
        metadata=body.metadata,
    )
    return TraceAppendStepResponse(
        step_id=step["id"],
        trace_id=step["trace_id"],
        step_index=step["step_index"],
        created_at=step["created_at"],
    )


@traces_router.post("/close", response_model=TraceCloseResponse)
async def trace_close(body: TraceCloseRequest, request: Request):
    """Close a trace."""
    tenant_id = _enforce_tenant(request, body.tenant_id)
    store = _get_store()
    trace = await store.close_trace(
        trace_id=body.trace_id,
        tenant_id=tenant_id,
        status=body.status,
        metadata=body.metadata,
    )
    if not trace:
        raise HTTPException(status_code=404, detail="Trace not found or tenant mismatch")
    return TraceCloseResponse(
        trace_id=trace["id"],
        status=TraceStatus(trace["status"]),
        ended_at=trace["ended_at"],
    )


@traces_router.get("/{trace_id}", response_model=TraceDetailResponse)
async def trace_get(trace_id: str, request: Request):
    """Get a trace with all its steps."""
    tenant_id = getattr(request.state, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Tenant context required")
    store = _get_store()
    trace = await store.get_trace(trace_id=trace_id, tenant_id=tenant_id)
    if not trace:
        raise HTTPException(status_code=404, detail="Trace not found")
    return TraceDetailResponse(
        trace_id=trace["id"],
        tenant_id=trace["tenant_id"],
        merchant_id=trace.get("merchant_id"),
        task_id=trace.get("task_id"),
        request_id=trace.get("request_id"),
        name=trace["name"],
        status=TraceStatus(trace["status"]),
        metadata=trace.get("metadata", {}),
        started_at=trace["started_at"],
        ended_at=trace.get("ended_at"),
        steps=trace.get("steps", []),
    )


@traces_router.get("", response_model=None)
async def trace_list(
    request: Request,
    task_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
):
    """List traces for the current tenant."""
    tenant_id = getattr(request.state, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Tenant context required")
    store = _get_store()
    limit = max(1, min(limit, 500))
    traces = await store.list_traces(
        tenant_id=tenant_id,
        task_id=task_id,
        status=status,
        limit=limit,
    )
    return {"traces": traces, "count": len(traces)}
