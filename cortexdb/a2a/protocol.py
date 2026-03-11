"""A2A Task Protocol (DOC-017 Section 10)

Agent-to-Agent task lifecycle: Created -> Assigned -> Running -> Completed/Failed
Tasks flow through StreamCore for real-time coordination.

Storage: PostgreSQL (persistent) + Redis (cache) with in-memory fallback.
"""

import json
import time
import uuid
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger("cortexdb.a2a.protocol")

REDIS_TASK_TTL = 3600  # 1 hour cache TTL for active tasks


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


def _task_to_redis_dict(task: A2ATask) -> Dict:
    """Serialize a task to a dict suitable for Redis/JSON."""
    return {
        "task_id": task.task_id,
        "source_agent_id": task.source_agent_id,
        "target_agent_id": task.target_agent_id,
        "skill_requested": task.skill_requested,
        "input_data": task.input_data,
        "output_data": task.output_data,
        "status": task.status.value,
        "priority": task.priority,
        "tenant_id": task.tenant_id,
        "created_at": task.created_at,
        "assigned_at": task.assigned_at,
        "completed_at": task.completed_at,
        "error": task.error,
        "metadata": task.metadata,
    }


def _task_from_dict(d: Dict) -> A2ATask:
    """Deserialize a dict (from Redis or PG) back into an A2ATask."""
    # Validate status against known enum values; default to CREATED if unknown
    raw_status = d.get("status", "created")
    try:
        status = A2ATaskStatus(raw_status)
    except ValueError:
        logger.warning("Unknown A2A task status '%s' for task_id=%s, defaulting to CREATED",
                       raw_status, d.get("task_id"))
        status = A2ATaskStatus.CREATED
    return A2ATask(
        task_id=d["task_id"],
        source_agent_id=d.get("source_agent_id") or d.get("requester_agent", ""),
        target_agent_id=d.get("target_agent_id") or d.get("assigned_agent", ""),
        skill_requested=d.get("skill_requested") or d.get("task_type", ""),
        input_data=d.get("input_data") if isinstance(d.get("input_data"), dict) else {},
        output_data=d.get("output_data") if isinstance(d.get("output_data"), dict) else None,
        status=status,
        priority=int(d.get("priority", 3)),
        tenant_id=d.get("tenant_id"),
        created_at=float(d.get("created_at", 0)),
        assigned_at=float(d["assigned_at"]) if d.get("assigned_at") else None,
        completed_at=float(d["completed_at"]) if d.get("completed_at") else None,
        error=d.get("error") or d.get("error_message"),
        metadata=d.get("metadata") if isinstance(d.get("metadata"), dict) else {},
    )


def _redis_key(task_id: str) -> str:
    return f"a2a:task:{task_id}"


class A2AProtocol:
    """Manages A2A task lifecycle between agents."""

    def __init__(self, registry=None, engines: Dict[str, Any] = None,
                 redis=None, pool=None):
        self.registry = registry
        self.engines = engines or {}
        self._redis = redis   # aioredis client (or None for standalone mode)
        self._pool = pool     # asyncpg pool (or None for standalone mode)
        self._tasks: Dict[str, A2ATask] = {}
        self._MAX_CACHED_TASKS = 5000  # bounded in-memory task cache

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _cache_task(self, task: A2ATask):
        """Add task to in-memory cache, evicting oldest if over limit."""
        if len(self._tasks) >= self._MAX_CACHED_TASKS:
            # Evict the oldest task by created_at
            oldest_id = min(self._tasks, key=lambda k: self._tasks[k].created_at)
            del self._tasks[oldest_id]
        self._tasks[task.task_id] = task

    async def _pg_insert_task(self, task: A2ATask):
        """INSERT task into PostgreSQL a2a_tasks table."""
        if not self._pool:
            return
        try:
            async with self._pool.acquire() as conn:
                await conn.execute(
                    """INSERT INTO a2a_tasks
                       (task_id, task_type, input_data, output_data, status,
                        requester_agent, assigned_agent, error_message, tenant_id)
                       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)""",
                    task.task_id,
                    task.skill_requested,
                    json.dumps(task.input_data, default=str),
                    json.dumps(task.output_data, default=str) if task.output_data else None,
                    task.status.value,
                    task.source_agent_id,
                    task.target_agent_id,
                    task.error,
                    task.tenant_id,
                )
        except Exception as e:
            logger.warning(f"PG insert task failed: {e}")

    async def _pg_update_task(self, task: A2ATask):
        """UPDATE task row in PostgreSQL."""
        if not self._pool:
            return
        try:
            async with self._pool.acquire() as conn:
                await conn.execute(
                    """UPDATE a2a_tasks
                       SET status=$2, assigned_agent=$3, output_data=$4,
                           error_message=$5, updated_at=NOW()
                       WHERE task_id=$1""",
                    task.task_id,
                    task.status.value,
                    task.target_agent_id,
                    json.dumps(task.output_data, default=str) if task.output_data else None,
                    task.error,
                )
        except Exception as e:
            logger.warning(f"PG update task failed: {e}")

    async def _pg_atomic_transition(self, task_id: str, from_status: str,
                                     to_status: str) -> bool:
        """Atomically transition a task's status in PG. Returns True if successful.

        Uses WHERE status=$2 to ensure only one concurrent caller wins.
        """
        if not self._pool:
            return True  # No PG, allow in-memory transition
        try:
            async with self._pool.acquire() as conn:
                result = await conn.execute(
                    """UPDATE a2a_tasks SET status=$2, updated_at=NOW()
                       WHERE task_id=$1 AND status=$3""",
                    task_id, to_status, from_status)
                return result == "UPDATE 1"
        except Exception as e:
            logger.warning(f"PG atomic transition failed: {e}")
            return False

    async def _redis_set_task(self, task: A2ATask):
        """Cache task in Redis."""
        if not self._redis:
            return
        try:
            await self._redis.set(
                _redis_key(task.task_id),
                json.dumps(_task_to_redis_dict(task), default=str),
                ex=REDIS_TASK_TTL,
            )
        except Exception as e:
            logger.warning(f"Redis set task failed: {e}")

    async def _redis_get_task(self, task_id: str) -> Optional[A2ATask]:
        """Try to load task from Redis cache."""
        if not self._redis:
            return None
        try:
            raw = await self._redis.get(_redis_key(task_id))
            if raw:
                return _task_from_dict(json.loads(raw))
        except Exception as e:
            logger.warning(f"Redis get task failed: {e}")
        return None

    async def _pg_get_task(self, task_id: str) -> Optional[A2ATask]:
        """Load task from PostgreSQL."""
        if not self._pool:
            return None
        try:
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT * FROM a2a_tasks WHERE task_id=$1", task_id)
            if row:
                d = dict(row)
                # asyncpg returns jsonb as str or dict depending on config
                for k in ("input_data", "output_data"):
                    if isinstance(d.get(k), str):
                        d[k] = json.loads(d[k])
                d["source_agent_id"] = d.pop("requester_agent", "")
                d["target_agent_id"] = d.pop("assigned_agent", "") or ""
                d["skill_requested"] = d.pop("task_type", "")
                d["error"] = d.pop("error_message", None)
                d.setdefault("priority", 3)
                d.setdefault("metadata", {})
                # Convert datetime to float
                if hasattr(d.get("created_at"), "timestamp"):
                    d["created_at"] = d["created_at"].timestamp()
                return _task_from_dict(d)
        except Exception as e:
            logger.warning(f"PG get task failed: {e}")
        return None

    async def _load_task(self, task_id: str) -> Optional[A2ATask]:
        """Load task: in-memory -> Redis -> PG."""
        task = self._tasks.get(task_id)
        if task:
            return task
        task = await self._redis_get_task(task_id)
        if task:
            self._cache_task(task)
            return task
        task = await self._pg_get_task(task_id)
        if task:
            self._cache_task(task)
            await self._redis_set_task(task)
            return task
        return None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

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
        self._cache_task(task)

        # Persist to PG and cache in Redis
        await self._pg_insert_task(task)
        await self._redis_set_task(task)

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
        task = await self._load_task(task_id)
        if task and task.status == A2ATaskStatus.CREATED:
            # Atomic PG transition to prevent double-assign
            if not await self._pg_atomic_transition(
                    task_id, A2ATaskStatus.CREATED.value, A2ATaskStatus.ASSIGNED.value):
                return None
            task.status = A2ATaskStatus.ASSIGNED
            task.assigned_at = time.time()
            await self._pg_update_task(task)  # update remaining fields
            await self._redis_set_task(task)
            return task
        return None

    async def start_task(self, task_id: str) -> Optional[A2ATask]:
        task = await self._load_task(task_id)
        if task and task.status == A2ATaskStatus.ASSIGNED:
            if not await self._pg_atomic_transition(
                    task_id, A2ATaskStatus.ASSIGNED.value, A2ATaskStatus.RUNNING.value):
                return None
            task.status = A2ATaskStatus.RUNNING
            await self._pg_update_task(task)
            await self._redis_set_task(task)
            return task
        return None

    async def complete_task(self, task_id: str,
                            output_data: Dict,
                            agent_id: str = None) -> Optional[A2ATask]:
        task = await self._load_task(task_id)
        if task and task.status == A2ATaskStatus.RUNNING:
            # Verify the caller is the assigned target agent
            if agent_id and task.target_agent_id and agent_id != task.target_agent_id:
                logger.warning(
                    f"A2A auth rejected: agent {agent_id} tried to complete "
                    f"task {task_id} owned by {task.target_agent_id}")
                return None
            # Atomic PG transition to prevent double-complete
            if not await self._pg_atomic_transition(
                    task_id, A2ATaskStatus.RUNNING.value, A2ATaskStatus.COMPLETED.value):
                return None
            task.status = A2ATaskStatus.COMPLETED
            task.output_data = output_data
            task.completed_at = time.time()
            await self._pg_update_task(task)
            await self._redis_set_task(task)
            logger.info(f"A2A task completed: {task_id}")
            return task
        return None

    async def fail_task(self, task_id: str, error: str,
                        agent_id: str = None) -> Optional[A2ATask]:
        task = await self._load_task(task_id)
        if task and task.status in (A2ATaskStatus.ASSIGNED, A2ATaskStatus.RUNNING):
            # Verify the caller is the assigned target agent
            if agent_id and task.target_agent_id and agent_id != task.target_agent_id:
                logger.warning(
                    f"A2A auth rejected: agent {agent_id} tried to fail "
                    f"task {task_id} owned by {task.target_agent_id}")
                return None
            # Atomic PG transition
            if not await self._pg_atomic_transition(
                    task_id, task.status.value, A2ATaskStatus.FAILED.value):
                return None
            task.status = A2ATaskStatus.FAILED
            task.error = error
            task.completed_at = time.time()
            await self._pg_update_task(task)
            await self._redis_set_task(task)
            logger.warning(f"A2A task failed: {task_id} - {error}")
            return task
        return None

    async def get_task(self, task_id: str) -> Optional[A2ATask]:
        return await self._load_task(task_id)

    async def list_tasks(self, agent_id: Optional[str] = None,
                         status: Optional[str] = None,
                         tenant_id: Optional[str] = None,
                         limit: int = 50) -> List[Dict]:
        limit = max(1, min(limit, 500))
        # When PG is available, query it for the authoritative list
        if self._pool:
            try:
                clauses = []
                params = []
                idx = 1
                if agent_id:
                    clauses.append(f"(requester_agent=${idx} OR assigned_agent=${idx})")
                    params.append(agent_id)
                    idx += 1
                if status:
                    clauses.append(f"status=${idx}")
                    params.append(status)
                    idx += 1
                if tenant_id:
                    clauses.append(f"tenant_id=${idx}")
                    params.append(tenant_id)
                    idx += 1
                where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
                query = (f"SELECT * FROM a2a_tasks{where} "
                         f"ORDER BY created_at DESC LIMIT ${idx}")
                params.append(limit)
                async with self._pool.acquire() as conn:
                    rows = await conn.fetch(query, *params)
                results = []
                for row in rows:
                    d = dict(row)
                    created = d.get("created_at")
                    completed = d.get("completed_at")
                    results.append({
                        "task_id": d["task_id"],
                        "source": d.get("requester_agent", ""),
                        "target": d.get("assigned_agent", ""),
                        "skill": d.get("task_type", ""),
                        "status": d["status"],
                        "priority": d.get("priority", 3),
                        "created_at": created.timestamp() if hasattr(created, "timestamp") else created,
                        "completed_at": completed.timestamp() if hasattr(completed, "timestamp") else completed,
                    })
                return results
            except Exception as e:
                logger.warning(f"PG list_tasks failed, falling back to in-memory: {e}")

        # Fallback: in-memory
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
