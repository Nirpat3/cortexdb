"""CortexEngine Runtime — Unified runtime API layer orchestrating proven infra components.

Namespaces: context / vector / events / config / traces / workflows / runtime
This module adds the runtime + workflows layer on top of existing engines.
"""

from cortexdb.core.runtime.schemas import (
    WorkflowStartRequest,
    WorkflowStartResponse,
    WorkflowSignalRequest,
    WorkflowSignalResponse,
    WorkflowStatusResponse,
    RuntimeRunRequest,
    RuntimeRunResponse,
    RuntimeCancelRequest,
    RuntimeCancelResponse,
    RunStatus,
)
from cortexdb.core.runtime.router import runtime_router, workflows_router
from cortexdb.core.runtime.trace_router import traces_router
from cortexdb.core.runtime.schemas import (
    TraceStatus,
    StepStatus,
    TraceWriteRequest,
    TraceWriteResponse,
    TraceAppendStepRequest,
    TraceAppendStepResponse,
    TraceCloseRequest,
    TraceCloseResponse,
    TraceDetailResponse,
)

__all__ = [
    "runtime_router",
    "workflows_router",
    "traces_router",
    "WorkflowStartRequest",
    "WorkflowStartResponse",
    "WorkflowSignalRequest",
    "WorkflowSignalResponse",
    "WorkflowStatusResponse",
    "RuntimeRunRequest",
    "RuntimeRunResponse",
    "RuntimeCancelRequest",
    "RuntimeCancelResponse",
    "RunStatus",
    "TraceStatus",
    "StepStatus",
    "TraceWriteRequest",
    "TraceWriteResponse",
    "TraceAppendStepRequest",
    "TraceAppendStepResponse",
    "TraceCloseRequest",
    "TraceCloseResponse",
    "TraceDetailResponse",
]
