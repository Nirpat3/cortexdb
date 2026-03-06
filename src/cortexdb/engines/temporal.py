"""TemporalCore - Brain Region: Cerebellum (Temporal Patterns)
Time-series storage via TimescaleDB extension on PostgreSQL.
Handles heartbeats, metrics, and continuous aggregates.
REPLACES: TimescaleDB standalone (runs inside RelationalCore's PostgreSQL)"""

import json
from typing import Any, Dict, List, Optional
from cortexdb.engines import BaseEngine

try:
    import asyncpg
except ImportError:
    asyncpg = None


class TemporalEngine(BaseEngine):
    def __init__(self, config: Dict):
        self.url = config.get("url", "postgresql://cortex:cortex_secret@localhost:5432/cortexdb")
        self.pool = None

    async def connect(self):
        if asyncpg is None:
            raise ImportError("asyncpg required: pip install asyncpg")
        self.pool = await asyncpg.create_pool(
            self.url, min_size=1, max_size=10, command_timeout=30
        )

    async def close(self):
        if self.pool:
            await self.pool.close()

    async def health(self) -> Dict:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT COUNT(*) as count FROM heartbeats WHERE time > NOW() - INTERVAL '1 hour'"
            )
            return {
                "engine": "TimescaleDB (PostgreSQL extension)",
                "brain_region": "Cerebellum",
                "heartbeats_last_hour": row["count"] if row else 0,
            }

    async def write_heartbeat(self, node_id: str, grid_address: str,
                              state: str, metrics: Dict) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO heartbeats (time, node_id, grid_address, state,
                   cpu_pct, memory_pct, latency_p95_ms, error_rate,
                   active_connections, metadata)
                   VALUES (NOW(), $1, $2, $3, $4, $5, $6, $7, $8, $9)""",
                node_id, grid_address, state,
                metrics.get("cpu_pct", 0), metrics.get("memory_pct", 0),
                metrics.get("latency_p95_ms", 0), metrics.get("error_rate", 0),
                metrics.get("active_connections", 0),
                json.dumps(metrics.get("metadata", {}))
            )

    async def write_agent_metric(self, agent_id: str, metrics: Dict) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO agent_metrics (time, agent_id, tokens_used_delta,
                   cost_delta, tasks_completed_delta, avg_score, cache_hit_rate)
                   VALUES (NOW(), $1, $2, $3, $4, $5, $6)""",
                agent_id,
                metrics.get("tokens_used", 0), metrics.get("cost", 0),
                metrics.get("tasks_completed", 0), metrics.get("avg_score"),
                metrics.get("cache_hit_rate")
            )

    async def query_heartbeats(self, node_id: str, hours: int = 24,
                               interval: str = "1 hour") -> List[Dict]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                f"""SELECT time_bucket($1::INTERVAL, time) AS bucket,
                    AVG(cpu_pct) AS avg_cpu, AVG(memory_pct) AS avg_memory,
                    AVG(latency_p95_ms) AS avg_latency, MAX(error_rate) AS max_error_rate,
                    COUNT(*) AS heartbeat_count
                    FROM heartbeats
                    WHERE node_id = $2 AND time > NOW() - ($3 || ' hours')::INTERVAL
                    GROUP BY bucket ORDER BY bucket DESC""",
                interval, node_id, str(hours)
            )
            return [dict(r) for r in rows]

    async def write(self, data_type: str, payload: Dict, actor: str = "system") -> Any:
        if data_type == "heartbeat":
            await self.write_heartbeat(
                payload.get("node_id", "unknown"),
                payload.get("grid_address", "unknown"),
                payload.get("state", "HEALTHY"),
                payload
            )
            return "heartbeat_recorded"
        return None
