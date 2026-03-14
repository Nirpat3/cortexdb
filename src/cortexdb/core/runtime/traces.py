"""Trace store — Postgres-backed persistence for traces and trace steps.

Follows the same outbox pattern as RuntimeStore: writes to traces/trace_steps
AND write_outbox in a single transaction so StreamCore gets notified.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from cortexdb.core.runtime.schemas import StepStatus, TraceStatus

logger = logging.getLogger("cortexdb.runtime.traces")


class TraceStore:
    """Thin data-access layer for traces + trace_steps tables."""

    def __init__(self, pool: Any):
        self.pool = pool
        # In-memory storage for pool=None stub mode
        self._mem_traces: Dict[str, Dict[str, Any]] = {}
        self._mem_steps: Dict[str, List[Dict[str, Any]]] = {}

    # ------------------------------------------------------------------
    # Write: create trace
    # ------------------------------------------------------------------

    async def create_trace(
        self,
        *,
        tenant_id: str,
        merchant_id: Optional[str],
        name: str,
        task_id: Optional[str] = None,
        request_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        trace_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        meta = metadata or {}

        if self.pool is None:
            trace = {
                "id": trace_id,
                "tenant_id": tenant_id,
                "merchant_id": merchant_id,
                "task_id": task_id,
                "request_id": request_id,
                "name": name,
                "status": TraceStatus.open.value,
                "metadata": meta,
                "started_at": now,
                "ended_at": None,
                "created_at": now,
                "updated_at": now,
            }
            self._mem_traces[trace_id] = trace
            self._mem_steps[trace_id] = []
            return trace

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    """
                    INSERT INTO traces (id, tenant_id, merchant_id, task_id, request_id, name, status, metadata, started_at, created_at, updated_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9, $10, $11)
                    RETURNING *
                    """,
                    trace_id, tenant_id, merchant_id, task_id, request_id,
                    name, TraceStatus.open.value, json.dumps(meta),
                    now, now, now,
                )
                # Outbox for StreamCore
                await conn.execute(
                    """
                    INSERT INTO write_outbox (data_type, payload, actor, target_engine, tenant_id, status)
                    VALUES ('trace.created', $1::jsonb, 'traces', 'stream', $2, 'pending')
                    """,
                    json.dumps({
                        "trace_id": trace_id, "name": name,
                        "tenant_id": tenant_id, "task_id": task_id,
                        "request_id": request_id,
                    }),
                    tenant_id,
                )
        return dict(row) if row else {}

    # ------------------------------------------------------------------
    # Write: append step
    # ------------------------------------------------------------------

    async def append_step(
        self,
        *,
        trace_id: str,
        tenant_id: str,
        name: str,
        status: StepStatus = StepStatus.ok,
        input_data: Optional[Dict[str, Any]] = None,
        output_data: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
        duration_ms: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        step_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        meta = metadata or {}

        if self.pool is None:
            steps = self._mem_steps.get(trace_id, [])
            step_index = len(steps)
            step = {
                "id": step_id,
                "trace_id": trace_id,
                "tenant_id": tenant_id,
                "step_index": step_index,
                "name": name,
                "status": status.value,
                "input": input_data,
                "output": output_data,
                "error": error,
                "duration_ms": duration_ms,
                "metadata": meta,
                "created_at": now,
            }
            steps.append(step)
            self._mem_steps[trace_id] = steps
            return step

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                # Get next step index
                idx = await conn.fetchval(
                    "SELECT COALESCE(MAX(step_index), -1) + 1 FROM trace_steps WHERE trace_id = $1",
                    trace_id,
                )
                row = await conn.fetchrow(
                    """
                    INSERT INTO trace_steps (id, trace_id, tenant_id, step_index, name, status, input, output, error, duration_ms, metadata, created_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8::jsonb, $9, $10, $11::jsonb, $12)
                    RETURNING *
                    """,
                    step_id, trace_id, tenant_id, idx, name, status.value,
                    json.dumps(input_data) if input_data else None,
                    json.dumps(output_data) if output_data else None,
                    error, duration_ms, json.dumps(meta), now,
                )
                # Update trace updated_at
                await conn.execute(
                    "UPDATE traces SET updated_at = $1 WHERE id = $2 AND tenant_id = $3",
                    now, trace_id, tenant_id,
                )
                # Outbox for StreamCore
                await conn.execute(
                    """
                    INSERT INTO write_outbox (data_type, payload, actor, target_engine, tenant_id, status)
                    VALUES ('trace.step.appended', $1::jsonb, 'traces', 'stream', $2, 'pending')
                    """,
                    json.dumps({
                        "trace_id": trace_id, "step_id": step_id,
                        "step_name": name, "step_status": status.value,
                        "tenant_id": tenant_id,
                    }),
                    tenant_id,
                )
        return dict(row) if row else {}

    # ------------------------------------------------------------------
    # Write: close trace
    # ------------------------------------------------------------------

    async def close_trace(
        self,
        *,
        trace_id: str,
        tenant_id: str,
        status: TraceStatus = TraceStatus.closed,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        now = datetime.now(timezone.utc)

        if self.pool is None:
            trace = self._mem_traces.get(trace_id)
            if trace and trace["tenant_id"] == tenant_id:
                trace["status"] = status.value
                trace["ended_at"] = now
                trace["updated_at"] = now
                if metadata:
                    trace["metadata"].update(metadata)
                return trace
            return None

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                meta_update = f", metadata = metadata || $6::jsonb" if metadata else ""
                params = [status.value, now, now, trace_id, tenant_id]
                if metadata:
                    params.append(json.dumps(metadata))

                row = await conn.fetchrow(
                    f"""
                    UPDATE traces SET status = $1, ended_at = $2, updated_at = $3 {meta_update}
                    WHERE id = $4 AND tenant_id = $5
                    RETURNING *
                    """,
                    *params,
                )
                if row:
                    await conn.execute(
                        """
                        INSERT INTO write_outbox (data_type, payload, actor, target_engine, tenant_id, status)
                        VALUES ('trace.closed', $1::jsonb, 'traces', 'stream', $2, 'pending')
                        """,
                        json.dumps({"trace_id": trace_id, "status": status.value, "tenant_id": tenant_id}),
                        tenant_id,
                    )
        return dict(row) if row else None

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    async def get_trace(self, *, trace_id: str, tenant_id: str) -> Optional[Dict[str, Any]]:
        if self.pool is None:
            trace = self._mem_traces.get(trace_id)
            if trace and trace["tenant_id"] == tenant_id:
                result = dict(trace)
                result["steps"] = self._mem_steps.get(trace_id, [])
                return result
            return None

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM traces WHERE id = $1 AND tenant_id = $2",
                trace_id, tenant_id,
            )
            if not row:
                return None
            result = dict(row)
            steps = await conn.fetch(
                "SELECT * FROM trace_steps WHERE trace_id = $1 AND tenant_id = $2 ORDER BY step_index",
                trace_id, tenant_id,
            )
            result["steps"] = [dict(s) for s in steps]
            return result

    async def list_traces(
        self,
        *,
        tenant_id: str,
        task_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        if self.pool is None:
            traces = [t for t in self._mem_traces.values() if t["tenant_id"] == tenant_id]
            if task_id:
                traces = [t for t in traces if t.get("task_id") == task_id]
            if status:
                traces = [t for t in traces if t["status"] == status]
            return traces[:limit]

        clauses = ["tenant_id = $1"]
        params: list = [tenant_id]
        idx = 2
        if task_id:
            clauses.append(f"task_id = ${idx}")
            params.append(task_id)
            idx += 1
        if status:
            clauses.append(f"status = ${idx}")
            params.append(status)
            idx += 1

        params.append(limit)
        where = " AND ".join(clauses)

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT * FROM traces WHERE {where} ORDER BY created_at DESC LIMIT ${idx}",
                *params,
            )
        return [dict(r) for r in rows]
