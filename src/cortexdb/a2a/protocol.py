"""A2A Task Protocol (DOC-017 Section 10)

Agent-to-Agent task lifecycle: Created -> Assigned -> Running -> Completed/Failed
Tasks flow through StreamCore for real-time coordination.
"""

import time
import uuid
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger("cortexdb.a2a.protocol")


class A2ATaskStatus(Enum):
    CREATED = "created"
    ASSIGNED = "assigned"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class A2ATask:
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    source_agent_id: str = ""
    target_agent_id: str = ""
    skill_requested: str = ""
    input_data: Dict = field(default_factory=dict)
    output_data: Optional[Dict] = None
    status: A2ATaskStatus = A2ATaskStatus.CREATED
    priority: int = 3  # 0=critical, 1=high, 2=medium, 3=low
    tenant_id: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    assigned_at: Optional[float] = None
    completed_at: Optional[float] = None
    error: Optional[str] = None
    metadata: Dict = field(default_factory=dict)


class A2AProtocol:
    """Manages A2A task lifecycle between agents."""

    def __init__(self, registry=None, engines: Dict[str, Any] = None):
        self.registry = registry
        self.engines = engines or {}
        self._tasks: Dict[str, A2ATask] = {}

    async def create_task(self, source_agent_id: str, target_agent_id: str,
                          skill: str, input_data: Dict,
                          tenant_id: Optional[str] = None,
                          priority: int = 3) -> A2ATask:
        """Create a new A2A task."""
        task = A2ATask(
            source_agent_id=source_agent_id,
            target_agent_id=target_agent_id,
            skill_requested=skill,
            input_data=input_data,
            priority=priority,
            tenant_id=tenant_id,
        )
        self._tasks[task.task_id] = task

        # Publish to StreamCore
        if "stream" in self.engines:
            try:
                stream_key = f"a2a:tasks:{target_agent_id}"
                if tenant_id:
                    stream_key = f"tenant:{tenant_id}:{stream_key}"
                await self.engines["stream"].publish(stream_key, {
                    "task_id": task.task_id,
                    "source": source_agent_id,
                    "skill": skill,
                    "priority": priority,
                })
            except Exception as e:
                logger.warning(f"Failed to publish A2A task to stream: {e}")

        logger.info(f"A2A task created: {task.task_id} "
                     f"{source_agent_id} -> {target_agent_id} [{skill}]")
        return task

    async def assign_task(self, task_id: str) -> Optional[A2ATask]:
        task = self._tasks.get(task_id)
        if task and task.status == A2ATaskStatus.CREATED:
            task.status = A2ATaskStatus.ASSIGNED
            task.assigned_at = time.time()
            return task
        return None

    async def start_task(self, task_id: str) -> Optional[A2ATask]:
        task = self._tasks.get(task_id)
        if task and task.status == A2ATaskStatus.ASSIGNED:
            task.status = A2ATaskStatus.RUNNING
            return task
        return None

    async def complete_task(self, task_id: str,
                            output_data: Dict) -> Optional[A2ATask]:
        task = self._tasks.get(task_id)
        if task and task.status == A2ATaskStatus.RUNNING:
            task.status = A2ATaskStatus.COMPLETED
            task.output_data = output_data
            task.completed_at = time.time()
            logger.info(f"A2A task completed: {task_id}")
            return task
        return None

    async def fail_task(self, task_id: str, error: str) -> Optional[A2ATask]:
        task = self._tasks.get(task_id)
        if task and task.status in (A2ATaskStatus.ASSIGNED, A2ATaskStatus.RUNNING):
            task.status = A2ATaskStatus.FAILED
            task.error = error
            task.completed_at = time.time()
            logger.warning(f"A2A task failed: {task_id} - {error}")
            return task
        return None

    def get_task(self, task_id: str) -> Optional[A2ATask]:
        return self._tasks.get(task_id)

    def list_tasks(self, agent_id: Optional[str] = None,
                   status: Optional[str] = None,
                   tenant_id: Optional[str] = None,
                   limit: int = 50) -> List[Dict]:
        tasks = list(self._tasks.values())
        if agent_id:
            tasks = [t for t in tasks
                     if t.source_agent_id == agent_id or t.target_agent_id == agent_id]
        if status:
            tasks = [t for t in tasks if t.status.value == status]
        if tenant_id:
            tasks = [t for t in tasks if t.tenant_id == tenant_id]
        tasks.sort(key=lambda t: t.created_at, reverse=True)
        return [{"task_id": t.task_id, "source": t.source_agent_id,
                 "target": t.target_agent_id, "skill": t.skill_requested,
                 "status": t.status.value, "priority": t.priority,
                 "created_at": t.created_at, "completed_at": t.completed_at}
                for t in tasks[:limit]]

    def get_stats(self) -> Dict:
        by_status = {}
        for t in self._tasks.values():
            by_status[t.status.value] = by_status.get(t.status.value, 0) + 1
        return {"total_tasks": len(self._tasks), "by_status": by_status}
