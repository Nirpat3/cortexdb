"""RelationalCore — Primary Storage Engine
Wraps PostgreSQL 16 + Citus + TimescaleDB extensions.
ACID transactions, business data, and the backbone of CortexDB."""

import json
import os
from typing import Any, Dict, Optional
from cortexdb.engines import BaseEngine

try:
    import asyncpg
except ImportError:
    asyncpg = None


class RelationalEngine(BaseEngine):
    def __init__(self, config: Dict):
        self.url = config.get("url", "postgresql://cortex:cortex_secret@localhost:5432/cortexdb")
        self.pool = None

    async def connect(self):
        if asyncpg is None:
            raise ImportError("asyncpg required: pip install asyncpg")
        self.pool = await asyncpg.create_pool(
            self.url,
            min_size=int(os.getenv("CORTEX_PG_POOL_MIN", "10")),
            max_size=int(os.getenv("CORTEX_PG_POOL_MAX", "50")),
            command_timeout=30,
        )

    async def close(self):
        if self.pool:
            await self.pool.close()

    async def health(self) -> Dict:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT NOW() as time, pg_database_size('cortexdb') as db_size")
            pool_size = self.pool.get_size()
            return {
                "engine": "PostgreSQL 16 + TimescaleDB",
                "brain_region": "Neocortex",
                "server_time": str(row["time"]),
                "db_size_mb": round(row["db_size"] / 1024 / 1024, 2),
                "pool_size": pool_size,
            }

    async def execute(self, query: str, params: Optional[Dict] = None) -> Any:
        async with self.pool.acquire() as conn:
            if query.strip().upper().startswith(("SELECT", "WITH")):
                rows = await conn.fetch(query, *(params.values() if params else []))
                return [dict(r) for r in rows]
            else:
                return await conn.execute(query, *(params.values() if params else []))

    async def write(self, data_type: str, payload: Dict, actor: str = "system") -> Any:
        async with self.pool.acquire() as conn:
            if data_type == "agent":
                return await conn.fetchval(
                    "INSERT INTO agents (birth_certificate, model, state) VALUES ($1, $2, 'SPAWNED') RETURNING agent_id",
                    json.dumps(payload.get("birth_certificate", {})),
                    payload.get("model", "claude-sonnet-4")
                )
            elif data_type == "task":
                return await conn.fetchval(
                    "INSERT INTO tasks (agent_id, description, status, input_data) VALUES ($1, $2, 'queued', $3) RETURNING task_id",
                    payload.get("agent_id"), payload.get("description"), json.dumps(payload.get("input_data", {}))
                )
            elif data_type == "block":
                return await conn.fetchval(
                    """INSERT INTO blocks (block_type, name, version, description, input_schema, output_schema, tags)
                    VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING block_id""",
                    payload.get("block_type", "L0_function"), payload.get("name"),
                    payload.get("version", "1.0.0"), payload.get("description"),
                    json.dumps(payload.get("input_schema", {})),
                    json.dumps(payload.get("output_schema", {})),
                    payload.get("tags", [])
                )
            elif data_type == "experience":
                return await conn.fetchval(
                    """INSERT INTO experience_ledger (context_summary, confidence, action_taken, outcome_score, lessons_learned, agent_id, task_type, model_used)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8) RETURNING experience_id""",
                    payload.get("context"), payload.get("confidence"), payload.get("action"),
                    payload.get("outcome_score"), payload.get("lessons"),
                    payload.get("agent_id"), payload.get("task_type"), payload.get("model")
                )
            elif data_type == "grid_event":
                return await conn.fetchval(
                    """INSERT INTO grid_nodes (grid_address, node_type, zone, state, metadata)
                    VALUES ($1, $2, $3, $4, $5) RETURNING node_id""",
                    payload.get("grid_address"), payload.get("node_type", "service"),
                    payload.get("zone", "default"), payload.get("state", "HEALTHY"),
                    json.dumps(payload.get("metadata", {}))
                )
            elif data_type in ("payment", "default"):
                return await conn.fetchval(
                    "INSERT INTO tasks (description, input_data, status) VALUES ($1, $2, 'queued') RETURNING task_id",
                    data_type, json.dumps(payload)
                )
            return None

    async def get(self, key: str) -> Optional[str]:
        return None
