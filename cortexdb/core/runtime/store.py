"""Runtime store — Postgres-backed persistence for runtime_runs.

Uses the same asyncpg pool as the relational engine.  Follows the outbox
pattern: writes to runtime_runs AND write_outbox in a single transaction
so StreamCore gets notified crash-safely.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from cortexdb.core.runtime.schemas import RunStatus

logger = logging.getLogger("cortexdb.runtime.store")


class RuntimeStore:
    """Thin data-access layer for the runtime_runs table."""

    def __init__(self, pool: Any):
        """pool: asyncpg connection pool."""
        self.pool = pool

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    async def create_run(
        self,
        *,
        tenant_id: str,
        merchant_id: Optional[str],
        workflow_type: str,
        input_data: Dict[str, Any],
        tags: Dict[str, str],
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Insert a new runtime_run and enqueue an outbox event atomically."""
        run_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        spec = {
            "workflow_type": workflow_type,
            "input": input_data,
            "tags": tags,
            "idempotency_key": idempotency_key,
        }

        if self.pool is None:
            # In-memory stub for testing without Postgres
            return {
                "id": run_id,
                "tenant_id": tenant_id,
                "merchant_id": merchant_id,
                "workflow_type": workflow_type,
                "status": RunStatus.pending.value,
                "spec": spec,
                "input": input_data,
                "output": None,
                "error": None,
                "tags": tags,
                "created_at": now,
                "updated_at": now,
            }

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    """
                    INSERT INTO runtime_runs (id, tenant_id, merchant_id, workflow_type, status, spec, created_at, updated_at)
                    VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7, $8)
                    RETURNING *
                    """,
                    run_id,
                    tenant_id,
                    merchant_id,
                    workflow_type,
                    RunStatus.pending.value,
                    json.dumps(spec),
                    now,
                    now,
                )
                # Outbox entry so StreamCore picks it up
                await conn.execute(
                    """
                    INSERT INTO write_outbox (data_type, payload, actor, target_engine, tenant_id, status)
                    VALUES ('runtime.run.created', $1::jsonb, 'runtime', 'stream', $2, 'pending')
                    """,
                    json.dumps({"run_id": run_id, "workflow_type": workflow_type, "tenant_id": tenant_id}),
                    tenant_id,
                )
        return dict(row) if row else {}

    async def update_status(self, *, run_id: str, tenant_id: str, status: RunStatus, error: Optional[str] = None) -> Optional[Dict[str, Any]]:
        now = datetime.now(timezone.utc)
        if self.pool is None:
            return {"id": run_id, "status": status.value, "updated_at": now}

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE runtime_runs SET status = $1, error = $2, updated_at = $3
                WHERE id = $4 AND tenant_id = $5
                RETURNING *
                """,
                status.value,
                error,
                now,
                run_id,
                tenant_id,
            )
        return dict(row) if row else None

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    async def get_run(self, *, run_id: str, tenant_id: str) -> Optional[Dict[str, Any]]:
        if self.pool is None:
            return None
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM runtime_runs WHERE id = $1 AND tenant_id = $2",
                run_id,
                tenant_id,
            )
        return dict(row) if row else None

    async def signal_run(self, *, run_id: str, tenant_id: str, signal_name: str, payload: Dict[str, Any]) -> bool:
        """Record signal delivery via outbox (actual dispatch is stubbed)."""
        if self.pool is None:
            return True

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT id FROM runtime_runs WHERE id = $1 AND tenant_id = $2",
                run_id,
                tenant_id,
            )
            if not row:
                return False

            await conn.execute(
                """
                INSERT INTO write_outbox (data_type, payload, actor, target_engine, tenant_id, status)
                VALUES ('runtime.run.signal', $1::jsonb, 'runtime', 'stream', $2, 'pending')
                """,
                json.dumps({"run_id": run_id, "signal_name": signal_name, "payload": payload}),
                tenant_id,
            )
        return True
