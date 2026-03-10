"""
Knowledge Graph Store — SQLite-backed graph of interconnected knowledge nodes.

Stores insights, facts, patterns, and procedures as nodes with typed edges
(requires, contradicts, extends, related_to, derived_from). Supports BFS
traversal, full-text search, and flexible filtered queries.
"""

import json
import time
import uuid
import logging
from collections import deque
from typing import Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from cortexdb.superadmin.persistence import PersistenceStore

logger = logging.getLogger(__name__)

NODE_TYPES = ("insight", "fact", "pattern", "procedure")
EDGE_RELATIONS = ("requires", "contradicts", "extends", "related_to", "derived_from")


class KnowledgeGraphStore:
    """Graph store for organisational knowledge backed by SQLite."""

    def __init__(self, persistence: "PersistenceStore"):
        self._persistence = persistence

    # ── Helpers ──

    def _row_to_node(self, row) -> dict:
        return {
            "node_id": row["node_id"],
            "node_type": row["node_type"],
            "topic": row["topic"],
            "content": row["content"],
            "source_agent": row["source_agent"],
            "department": row["department"],
            "confidence": row["confidence"],
            "metadata": json.loads(row["metadata"] or "{}"),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def _row_to_edge(self, row) -> dict:
        return {
            "edge_id": row["edge_id"],
            "from_node": row["from_node"],
            "to_node": row["to_node"],
            "relation": row["relation"],
            "weight": row["weight"],
            "metadata": json.loads(row["metadata"] or "{}"),
            "created_at": row["created_at"],
        }

    # ── Node CRUD ──

    def add_node(self, node_type: str, topic: str, content: str,
                 source_agent: str = None, department: str = None,
                 confidence: float = 0.5, metadata: dict = None) -> dict:
        """Insert a knowledge node and return it."""
        node_id = f"KN-{uuid.uuid4().hex[:8]}"
        now = time.time()
        self._persistence.conn.execute(
            "INSERT INTO knowledge_nodes "
            "(node_id, node_type, topic, content, source_agent, department, confidence, metadata, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (node_id, node_type, topic, content, source_agent, department,
             confidence, json.dumps(metadata or {}), now, now),
        )
        self._persistence.conn.commit()
        logger.info("Added knowledge node %s [%s] topic=%s", node_id, node_type, topic)
        return {"node_id": node_id, "node_type": node_type, "topic": topic,
                "content": content, "source_agent": source_agent,
                "department": department, "confidence": confidence,
                "metadata": metadata or {}, "created_at": now, "updated_at": now}

    def get_node(self, node_id: str) -> Optional[dict]:
        """Get a single node with its edges."""
        row = self._persistence.conn.execute(
            "SELECT * FROM knowledge_nodes WHERE node_id = ?", (node_id,)
        ).fetchone()
        if not row:
            return None
        node = self._row_to_node(row)
        edges = self._persistence.conn.execute(
            "SELECT * FROM knowledge_edges WHERE from_node = ? OR to_node = ?",
            (node_id, node_id),
        ).fetchall()
        node["edges"] = [self._row_to_edge(e) for e in edges]
        return node

    def update_node(self, node_id: str, updates: dict) -> dict:
        """Update content, confidence, and/or metadata fields on a node."""
        sets, params = [], []
        for col in ("content", "confidence"):
            if col in updates:
                sets.append(f"{col} = ?")
                params.append(updates[col])
        if "metadata" in updates:
            sets.append("metadata = ?")
            params.append(json.dumps(updates["metadata"]))
        if not sets:
            return self.get_node(node_id) or {}
        sets.append("updated_at = ?")
        params.append(time.time())
        params.append(node_id)
        self._persistence.conn.execute(
            f"UPDATE knowledge_nodes SET {', '.join(sets)} WHERE node_id = ?", params,
        )
        self._persistence.conn.commit()
        return self.get_node(node_id) or {}

    def delete_node(self, node_id: str) -> bool:
        """Delete a node and all its edges."""
        self._persistence.conn.execute(
            "DELETE FROM knowledge_edges WHERE from_node = ? OR to_node = ?",
            (node_id, node_id),
        )
        cur = self._persistence.conn.execute(
            "DELETE FROM knowledge_nodes WHERE node_id = ?", (node_id,),
        )
        self._persistence.conn.commit()
        return cur.rowcount > 0

    # ── Edge CRUD ──

    def add_edge(self, from_node: str, to_node: str, relation: str,
                 weight: float = 1.0, metadata: dict = None) -> dict:
        """Insert an edge between two nodes."""
        edge_id = f"KE-{uuid.uuid4().hex[:8]}"
        now = time.time()
        self._persistence.conn.execute(
            "INSERT INTO knowledge_edges "
            "(edge_id, from_node, to_node, relation, weight, metadata, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (edge_id, from_node, to_node, relation, weight,
             json.dumps(metadata or {}), now),
        )
        self._persistence.conn.commit()
        logger.info("Added edge %s: %s -[%s]-> %s", edge_id, from_node, relation, to_node)
        return {"edge_id": edge_id, "from_node": from_node, "to_node": to_node,
                "relation": relation, "weight": weight,
                "metadata": metadata or {}, "created_at": now}

    def delete_edge(self, edge_id: str) -> bool:
        """Delete a single edge."""
        cur = self._persistence.conn.execute(
            "DELETE FROM knowledge_edges WHERE edge_id = ?", (edge_id,),
        )
        self._persistence.conn.commit()
        return cur.rowcount > 0

    # ── Queries ──

    def query_nodes(self, topic: str = None, agent_id: str = None,
                    department: str = None, node_type: str = None,
                    limit: int = 50) -> List[dict]:
        """Flexible filtered query across knowledge nodes."""
        clauses, params = [], []
        if topic:
            clauses.append("topic = ?"); params.append(topic)
        if agent_id:
            clauses.append("source_agent = ?"); params.append(agent_id)
        if department:
            clauses.append("department = ?"); params.append(department)
        if node_type:
            clauses.append("node_type = ?"); params.append(node_type)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        rows = self._persistence.conn.execute(
            f"SELECT * FROM knowledge_nodes{where} ORDER BY updated_at DESC LIMIT ?",
            params + [limit],
        ).fetchall()
        return [self._row_to_node(r) for r in rows]

    def search_nodes(self, query: str, limit: int = 20) -> List[dict]:
        """Full-text search across content and topic using LIKE."""
        pattern = f"%{query}%"
        rows = self._persistence.conn.execute(
            "SELECT * FROM knowledge_nodes WHERE content LIKE ? OR topic LIKE ? "
            "ORDER BY confidence DESC, updated_at DESC LIMIT ?",
            (pattern, pattern, limit),
        ).fetchall()
        return [self._row_to_node(r) for r in rows]

    # ── Traversal ──

    def get_neighbors(self, node_id: str, relation: str = None,
                      depth: int = 1) -> Dict[str, list]:
        """Return connected nodes via BFS up to given depth."""
        visited_nodes, visited_edges = set(), set()
        result_nodes, result_edges = [], []
        queue: deque = deque([(node_id, 0)])
        visited_nodes.add(node_id)

        while queue:
            current, d = queue.popleft()
            if d >= depth:
                continue
            sql = "SELECT * FROM knowledge_edges WHERE from_node = ? OR to_node = ?"
            params: list = [current, current]
            if relation:
                sql += " AND relation = ?"
                params.append(relation)
            edges = self._persistence.conn.execute(sql, params).fetchall()
            for e in edges:
                edge = self._row_to_edge(e)
                if edge["edge_id"] not in visited_edges:
                    visited_edges.add(edge["edge_id"])
                    result_edges.append(edge)
                neighbor = edge["to_node"] if edge["from_node"] == current else edge["from_node"]
                if neighbor not in visited_nodes:
                    visited_nodes.add(neighbor)
                    node = self.get_node(neighbor)
                    if node:
                        node.pop("edges", None)
                        result_nodes.append(node)
                    queue.append((neighbor, d + 1))

        return {"nodes": result_nodes, "edges": result_edges}

    # ── Stats ──

    def get_stats(self) -> dict:
        """Aggregate statistics for the knowledge graph."""
        conn = self._persistence.conn
        node_counts = {r["node_type"]: r["cnt"] for r in conn.execute(
            "SELECT node_type, COUNT(*) as cnt FROM knowledge_nodes GROUP BY node_type"
        ).fetchall()}
        edge_counts = {r["relation"]: r["cnt"] for r in conn.execute(
            "SELECT relation, COUNT(*) as cnt FROM knowledge_edges GROUP BY relation"
        ).fetchall()}
        top_topics = [r["topic"] for r in conn.execute(
            "SELECT topic, COUNT(*) as cnt FROM knowledge_nodes "
            "GROUP BY topic ORDER BY cnt DESC LIMIT 10"
        ).fetchall()]
        dept_coverage = {r["department"]: r["cnt"] for r in conn.execute(
            "SELECT department, COUNT(*) as cnt FROM knowledge_nodes "
            "WHERE department IS NOT NULL GROUP BY department"
        ).fetchall()}
        return {
            "total_nodes": sum(node_counts.values()),
            "total_edges": sum(edge_counts.values()),
            "nodes_by_type": node_counts,
            "edges_by_relation": edge_counts,
            "top_topics": top_topics,
            "department_coverage": dept_coverage,
        }
