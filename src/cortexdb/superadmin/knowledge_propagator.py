"""
Knowledge Propagator — Propagates high-quality knowledge insights to skill-matched agents.

Uses the knowledge_propagations SQLite table to track which insights have been
shared with which agents, based on skill overlap and relevance scoring.
"""

import json
import time
import uuid
import logging
from typing import Dict, List, TYPE_CHECKING

if TYPE_CHECKING:
    from cortexdb.superadmin.knowledge_graph import KnowledgeGraphStore
    from cortexdb.superadmin.agent_team import AgentTeamManager
    from cortexdb.superadmin.agent_skills import AgentSkillManager
    from cortexdb.superadmin.persistence import PersistenceStore

logger = logging.getLogger(__name__)


class KnowledgePropagator:
    """Propagates knowledge nodes to agents whose skills match the node's topic."""

    def __init__(self, knowledge_graph: "KnowledgeGraphStore", team: "AgentTeamManager",
                 skills: "AgentSkillManager", persistence: "PersistenceStore"):
        self._kg = knowledge_graph
        self._team = team
        self._skills = skills
        self._persistence = persistence

    def propagate_insight(self, node_id: str) -> dict:
        """Find skill-matched agents for a knowledge node and create propagation records."""
        row = self._persistence.conn.execute(
            "SELECT * FROM knowledge_nodes WHERE node_id = ?", (node_id,)
        ).fetchone()
        if not row:
            return {"error": "Node not found", "node_id": node_id}

        node = dict(row)
        source_agent = node.get("source_agent", "")
        topic = (node.get("topic", "") or "").lower()
        content = (node.get("content", "") or "").lower()

        # Score all agents by skill overlap
        candidates: List[dict] = []
        for agent in self._team.get_all_agents():
            aid = agent["agent_id"]
            if aid == source_agent:
                continue
            profile = self._skills.get_profile(aid)
            best_score = 0.0
            for skill in profile.get("skills", []):
                name = skill["name"].lower()
                if name in topic or name in content:
                    best_score = max(best_score, skill["level"] * 0.2)
            if best_score > 0:
                candidates.append({"agent_id": aid, "score": round(best_score, 2)})

        candidates.sort(key=lambda c: -c["score"])
        targets = candidates[:5]

        now = time.time()
        for t in targets:
            pid = f"KP-{uuid.uuid4().hex[:12]}"
            self._persistence.conn.execute(
                "INSERT INTO knowledge_propagations (propagation_id, source_agent, target_agent, "
                "node_id, status, relevance_score, created_at) VALUES (?, ?, ?, ?, 'pending', ?, ?)",
                (pid, source_agent, t["agent_id"], node_id, t["score"], now),
            )
        self._persistence.conn.commit()

        logger.info("Propagated node %s to %d agents", node_id, len(targets))
        return {"node_id": node_id, "propagations_created": len(targets), "targets": targets}

    def get_pending_propagations(self, agent_id: str) -> List[dict]:
        """Get pending propagations for an agent, including node content."""
        rows = self._persistence.conn.execute(
            "SELECT p.*, n.topic, n.content, n.node_type, n.confidence AS node_confidence "
            "FROM knowledge_propagations p "
            "JOIN knowledge_nodes n ON p.node_id = n.node_id "
            "WHERE p.target_agent = ? AND p.status = 'pending' "
            "ORDER BY p.relevance_score DESC",
            (agent_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def accept_propagation(self, propagation_id: str, agent_id: str) -> dict:
        """Mark a propagation as accepted by the target agent."""
        self._persistence.conn.execute(
            "UPDATE knowledge_propagations SET status = 'accepted' "
            "WHERE propagation_id = ? AND target_agent = ?",
            (propagation_id, agent_id),
        )
        self._persistence.conn.commit()
        row = self._persistence.conn.execute(
            "SELECT * FROM knowledge_propagations WHERE propagation_id = ?",
            (propagation_id,),
        ).fetchone()
        return dict(row) if row else {"error": "Not found"}

    def dismiss_propagation(self, propagation_id: str) -> dict:
        """Mark a propagation as dismissed."""
        self._persistence.conn.execute(
            "UPDATE knowledge_propagations SET status = 'dismissed' WHERE propagation_id = ?",
            (propagation_id,),
        )
        self._persistence.conn.commit()
        row = self._persistence.conn.execute(
            "SELECT * FROM knowledge_propagations WHERE propagation_id = ?",
            (propagation_id,),
        ).fetchone()
        return dict(row) if row else {"error": "Not found"}

    def auto_propagate_high_grade(self, min_confidence: float = 0.8) -> dict:
        """Propagate all high-confidence nodes that haven't been propagated yet."""
        rows = self._persistence.conn.execute(
            "SELECT n.node_id FROM knowledge_nodes n "
            "WHERE n.confidence >= ? AND NOT EXISTS ("
            "  SELECT 1 FROM knowledge_propagations p WHERE p.node_id = n.node_id"
            ")",
            (min_confidence,),
        ).fetchall()

        total = 0
        for row in rows:
            result = self.propagate_insight(row["node_id"])
            total += result.get("propagations_created", 0)

        logger.info("Auto-propagated %d nodes, %d total propagations", len(rows), total)
        return {"nodes_processed": len(rows), "total_propagations": total}

    def get_propagation_stats(self) -> dict:
        """Aggregate propagation statistics."""
        conn = self._persistence.conn
        total = conn.execute("SELECT COUNT(*) AS c FROM knowledge_propagations").fetchone()["c"]
        accepted = conn.execute(
            "SELECT COUNT(*) AS c FROM knowledge_propagations WHERE status = 'accepted'"
        ).fetchone()["c"]
        acceptance_rate = round(accepted / max(total, 1), 3)

        # Flow by department
        dept_rows = conn.execute(
            "SELECT n.department AS src_dept, a_target.department AS tgt_dept, COUNT(*) AS cnt "
            "FROM knowledge_propagations p "
            "JOIN knowledge_nodes n ON p.node_id = n.node_id "
            "LEFT JOIN (SELECT agent_id, department FROM knowledge_nodes GROUP BY agent_id) a_target "
            "  ON p.target_agent = a_target.agent_id "
            "GROUP BY src_dept, tgt_dept",
        ).fetchall()
        by_department = [dict(r) for r in dept_rows]

        # Top propagators
        top_rows = conn.execute(
            "SELECT source_agent, COUNT(*) AS cnt "
            "FROM knowledge_propagations GROUP BY source_agent ORDER BY cnt DESC LIMIT 10"
        ).fetchall()
        top_propagators = [dict(r) for r in top_rows]

        return {
            "total_propagations": total,
            "accepted": accepted,
            "acceptance_rate": acceptance_rate,
            "by_department": by_department,
            "top_propagators": top_propagators,
        }
