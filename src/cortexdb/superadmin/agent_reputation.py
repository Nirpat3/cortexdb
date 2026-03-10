"""
Agent Reputation System — Trust scores that gate delegation authority.

Trust is computed from:
  - Task quality grades (rolling average)
  - Delegation success/failure rate
  - Task completion rate
  - Peer endorsement count (from skills)

Score range: 0.0 - 1.0
Agents need trust >= threshold to delegate tasks to others.
"""

import time
import logging
from typing import Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from cortexdb.superadmin.persistence import PersistenceStore

logger = logging.getLogger(__name__)

DELEGATION_TRUST_THRESHOLD = 0.6


class AgentReputationManager:
    """Manages trust scores for all agents."""

    def __init__(self, persistence: "PersistenceStore"):
        self._persistence = persistence
        self._scores: Dict[str, dict] = {}
        self._load()

    def _load(self):
        self._scores = self._persistence.kv_get("agent_reputation", {})

    def _save(self):
        self._persistence.kv_set("agent_reputation", self._scores)

    def _ensure(self, agent_id: str) -> dict:
        if agent_id not in self._scores:
            self._scores[agent_id] = {
                "trust_score": 0.5,
                "quality_sum": 0, "quality_count": 0,
                "delegations_sent": 0, "delegations_success": 0, "delegations_failed": 0,
                "tasks_completed": 0, "tasks_failed": 0,
                "endorsements": 0,
                "updated_at": time.time(),
            }
        return self._scores[agent_id]

    def update_from_outcome(self, agent_id: str, grade: int):
        """Update trust from a task outcome grade (1-10)."""
        s = self._ensure(agent_id)
        s["quality_sum"] = s.get("quality_sum", 0) + grade
        s["quality_count"] = s.get("quality_count", 0) + 1
        if grade >= 5:
            s["tasks_completed"] = s.get("tasks_completed", 0) + 1
        else:
            s["tasks_failed"] = s.get("tasks_failed", 0) + 1
        if grade >= 8:
            s["endorsements"] = s.get("endorsements", 0) + 1
        self._recalculate(agent_id)

    def update_from_delegation(self, delegator_id: str, success: bool):
        """Update trust when a delegated task completes."""
        s = self._ensure(delegator_id)
        s["delegations_sent"] = s.get("delegations_sent", 0) + 1
        if success:
            s["delegations_success"] = s.get("delegations_success", 0) + 1
        else:
            s["delegations_failed"] = s.get("delegations_failed", 0) + 1
        self._recalculate(delegator_id)

    def _recalculate(self, agent_id: str):
        """Recalculate trust score from all factors."""
        s = self._scores[agent_id]
        quality_avg = (s.get("quality_sum", 0) / max(s.get("quality_count", 1), 1)) / 10.0
        completed = s.get("tasks_completed", 0)
        failed = s.get("tasks_failed", 0)
        completion_rate = completed / max(completed + failed, 1)
        deleg_sent = s.get("delegations_sent", 0)
        deleg_success = s.get("delegations_success", 0)
        deleg_rate = deleg_success / max(deleg_sent, 1) if deleg_sent > 0 else 0.5

        # Weighted: quality 50%, completion 30%, delegation 20%
        score = quality_avg * 0.5 + completion_rate * 0.3 + deleg_rate * 0.2
        s["trust_score"] = round(max(0.0, min(1.0, score)), 3)
        s["updated_at"] = time.time()
        self._save()

    def get_trust_score(self, agent_id: str) -> float:
        s = self._scores.get(agent_id)
        return s["trust_score"] if s else 0.5

    def get_profile(self, agent_id: str) -> dict:
        s = self._ensure(agent_id)
        return {"agent_id": agent_id, **s, "can_delegate": s["trust_score"] >= DELEGATION_TRUST_THRESHOLD}

    def get_all_scores(self) -> List[dict]:
        return [{"agent_id": aid, **s} for aid, s in sorted(
            self._scores.items(), key=lambda x: -x[1].get("trust_score", 0))]

    def can_delegate(self, agent_id: str) -> bool:
        return self.get_trust_score(agent_id) >= DELEGATION_TRUST_THRESHOLD

    def recalculate_all(self):
        for aid in list(self._scores.keys()):
            self._recalculate(aid)
