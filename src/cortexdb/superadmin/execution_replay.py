"""
Execution Replay — Step-by-step reasoning trace for task executions.

Records each phase of task execution:
  prompt_built, context_injected, model_selected,
  llm_called, result_received, outcome_analyzed, skills_enhanced
"""

import time
import logging
from typing import List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from cortexdb.superadmin.persistence import PersistenceStore

logger = logging.getLogger(__name__)


class ExecutionTrace:
    """Captures step-by-step trace of a task execution."""

    def __init__(self, task_id: str, agent_id: str):
        self.task_id = task_id
        self.agent_id = agent_id
        self.steps: List[dict] = []
        self.started_at = time.time()
        self.completed_at: Optional[float] = None

    def add_step(self, name: str, duration_ms: float = 0,
                 inputs: dict = None, outputs: dict = None, metadata: dict = None):
        self.steps.append({
            "step": name,
            "index": len(self.steps),
            "timestamp": time.time(),
            "duration_ms": round(duration_ms, 2),
            "inputs": self._truncate(inputs or {}),
            "outputs": self._truncate(outputs or {}),
            "metadata": metadata or {},
        })

    def complete(self):
        self.completed_at = time.time()

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "agent_id": self.agent_id,
            "steps": self.steps,
            "step_count": len(self.steps),
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "total_ms": round((self.completed_at or time.time()) - self.started_at, 2) * 1000,
        }

    @staticmethod
    def _truncate(d: dict, max_len: int = 300) -> dict:
        result = {}
        for k, v in d.items():
            if isinstance(v, str) and len(v) > max_len:
                result[k] = v[:max_len] + "..."
            else:
                result[k] = v
        return result


class ExecutionReplay:
    """Stores and retrieves execution traces."""

    def __init__(self, persistence: "PersistenceStore"):
        self._persistence = persistence
        self._active_traces: dict = {}  # task_id -> ExecutionTrace

    def start_trace(self, task_id: str, agent_id: str) -> ExecutionTrace:
        trace = ExecutionTrace(task_id, agent_id)
        self._active_traces[task_id] = trace
        return trace

    def get_active_trace(self, task_id: str) -> Optional[ExecutionTrace]:
        return self._active_traces.get(task_id)

    def finish_trace(self, task_id: str):
        trace = self._active_traces.pop(task_id, None)
        if not trace:
            return
        trace.complete()

        # Store
        traces = self._persistence.kv_get("execution_traces", [])
        traces.append(trace.to_dict())
        if len(traces) > 200:
            traces = traces[-200:]
        self._persistence.kv_set("execution_traces", traces)

    def get_trace(self, task_id: str) -> Optional[dict]:
        traces = self._persistence.kv_get("execution_traces", [])
        for t in traces:
            if t.get("task_id") == task_id:
                return t
        # Check active
        active = self._active_traces.get(task_id)
        return active.to_dict() if active else None

    def get_recent(self, limit: int = 20) -> List[dict]:
        traces = self._persistence.kv_get("execution_traces", [])
        return traces[-limit:]

    def get_step_stats(self) -> dict:
        """Average time per step across all traces."""
        traces = self._persistence.kv_get("execution_traces", [])
        step_times: dict = {}
        for t in traces:
            for s in t.get("steps", []):
                name = s.get("step", "")
                if name not in step_times:
                    step_times[name] = []
                step_times[name].append(s.get("duration_ms", 0))

        return {
            name: {
                "avg_ms": round(sum(times) / len(times), 2),
                "count": len(times),
                "max_ms": round(max(times), 2),
            }
            for name, times in step_times.items()
        }
