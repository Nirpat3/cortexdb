"""GraphCore — Relationship Traversal Engine
Graph queries via recursive CTEs on PostgreSQL.
Provides graph traversal without a separate graph database."""

import json
from typing import Any, Dict, List, Optional
from cortexdb.engines import BaseEngine

try:
    import asyncpg
except ImportError:
    asyncpg = None


class GraphEngine(BaseEngine):
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
            nodes = await conn.fetchval("SELECT COUNT(*) FROM grid_nodes WHERE state != 'PURGED'")
            links = await conn.fetchval("SELECT COUNT(*) FROM grid_links WHERE state = 'active'")
            return {
                "engine": "SQL Graph (upgrade: Apache AGE)",
                "brain_region": "Association Cortex",
                "nodes": nodes,
                "links": links,
            }

    async def find_path(self, source_id: str, target_id: str,
                        max_hops: int = 10) -> List[Dict]:
        """Find shortest path between two grid nodes using BFS via recursive CTE"""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """WITH RECURSIVE path AS (
                    SELECT source_node_id, target_node_id,
                           ARRAY[source_node_id] AS visited,
                           1 AS depth, weight
                    FROM grid_links
                    WHERE source_node_id = $1 AND state = 'active'
                    UNION ALL
                    SELECT gl.source_node_id, gl.target_node_id,
                           p.visited || gl.source_node_id,
                           p.depth + 1, p.weight + gl.weight
                    FROM grid_links gl
                    JOIN path p ON gl.source_node_id = p.target_node_id
                    WHERE gl.target_node_id != ALL(p.visited)
                      AND p.depth < $3 AND gl.state = 'active'
                )
                SELECT * FROM path WHERE target_node_id = $2
                ORDER BY weight ASC LIMIT 5""",
                source_id, target_id, max_hops
            )
            return [dict(r) for r in rows]

    async def get_neighbors(self, node_id: str) -> List[Dict]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT gn.node_id, gn.grid_address, gn.node_type, gn.state,
                          gn.health_score, gl.protocol, gl.latency_ms, gl.weight
                   FROM grid_links gl
                   JOIN grid_nodes gn ON gl.target_node_id = gn.node_id
                   WHERE gl.source_node_id = $1 AND gl.state = 'active'
                     AND gn.state NOT IN ('REMOVED', 'TOMBSTONED', 'PURGED')""",
                node_id
            )
            return [dict(r) for r in rows]

    async def get_topology(self) -> Dict:
        async with self.pool.acquire() as conn:
            nodes = await conn.fetch(
                "SELECT node_id, grid_address, node_type, state, health_score "
                "FROM grid_nodes WHERE state NOT IN ('REMOVED', 'TOMBSTONED', 'PURGED')"
            )
            links = await conn.fetch(
                "SELECT source_node_id, target_node_id, protocol, latency_ms, weight "
                "FROM grid_links WHERE state = 'active'"
            )
            return {
                "nodes": [dict(r) for r in nodes],
                "links": [dict(r) for r in links],
                "node_count": len(nodes),
                "link_count": len(links),
            }

    async def write(self, data_type: str, payload: Dict, actor: str = "system") -> Any:
        if data_type == "grid_link":
            async with self.pool.acquire() as conn:
                return await conn.fetchval(
                    """INSERT INTO grid_links (source_node_id, target_node_id, protocol,
                       latency_ms, weight)
                       VALUES ($1, $2, $3, $4, $5) RETURNING link_id""",
                    payload["source"], payload["target"],
                    payload.get("protocol", "grpc"),
                    payload.get("latency_ms", 0),
                    payload.get("weight", 1.0)
                )
        return None
