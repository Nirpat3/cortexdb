"""Runtime / Workflows — Pydantic request & response schemas.

Aligned with RapidRMS_Complete_Technical_Design_v3:
  - Tenancy envelope on every request (tenant_id + merchant_id)
  - Status lifecycle: pending → running → completed | failed | cancelled
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class RunStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


# ---------------------------------------------------------------------------
# Tenancy envelope (shared mixin)
# ---------------------------------------------------------------------------

class TenantEnvelope(BaseModel):
    """Every runtime request carries tenant + merchant context."""
    tenant_id: str = Field(..., description="Tenant UUID from auth context")
    merchant_id: Optional[str] = Field(None, description="Merchant scope within tenant")


# ---------------------------------------------------------------------------
# Workflow schemas
# ---------------------------------------------------------------------------

class WorkflowStartRequest(TenantEnvelope):
    """POST /workflows/start"""
    workflow_type: str = Field(..., description="Registered workflow type name")
    input: Dict[str, Any] = Field(default_factory=dict, description="Workflow input payload")
    idempotency_key: Optional[str] = Field(None, description="Client-provided dedup key")
    tags: Dict[str, str] = Field(default_factory=dict, description="Arbitrary KV tags")


class WorkflowStartResponse(BaseModel):
    workflow_id: str = Field(..., description="Unique workflow run ID")
    status: RunStatus = RunStatus.pending
    created_at: datetime


class WorkflowSignalRequest(TenantEnvelope):
    """POST /workflows/signal"""
    workflow_id: str = Field(..., description="Target workflow run ID")
    signal_name: str = Field(..., description="Signal channel name")
    payload: Dict[str, Any] = Field(default_factory=dict)


class WorkflowSignalResponse(BaseModel):
    workflow_id: str
    signal_name: str
    accepted: bool = True


class WorkflowStatusResponse(BaseModel):
    """GET /workflows/{workflow_id}"""
    workflow_id: str
    tenant_id: str
    merchant_id: Optional[str] = None
    workflow_type: str
    status: RunStatus
    input: Dict[str, Any] = Field(default_factory=dict)
    output: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    tags: Dict[str, str] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Runtime convenience aliases
# ---------------------------------------------------------------------------

class RuntimeRunRequest(TenantEnvelope):
    """POST /runtime/run — alias for workflow start with simplified interface."""
    run_type: str = Field(..., description="Run type (maps to workflow_type)")
    input: Dict[str, Any] = Field(default_factory=dict)
    tags: Dict[str, str] = Field(default_factory=dict)


class RuntimeRunResponse(BaseModel):
    run_id: str
    status: RunStatus = RunStatus.pending
    created_at: datetime


class RuntimeCancelRequest(TenantEnvelope):
    """POST /runtime/cancel"""
    run_id: str = Field(..., description="Run ID to cancel")
    reason: Optional[str] = None


class RuntimeCancelResponse(BaseModel):
    run_id: str
    status: RunStatus
    cancelled: bool
