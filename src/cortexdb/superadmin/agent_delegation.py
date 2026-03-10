"""
Agent-to-Agent Delegation — Autonomous subtask delegation based on skill profiles.

Flow:
  1. Check delegator's trust score (must exceed threshold)
  2. Analyze task requirements (category, skills, keywords)
  3. Find best-match agents via skill leaderboard
  4. Filter by: department, tier, workload, trust
  5. Delegate via agent bus, reassign task
  6. Log delegation for tracking
"""

import time
import uuid
import logging
from typing import Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from cortexdb.superadmin.agent_team import AgentTeamManager
    from cortexdb.superadmin.agent_skills import AgentSkillManager
    from cortexdb.superadmin.agent_reputation import AgentReputationManager
    from cortexdb.superadmin.persistence import PersistenceStore

logger = logging.getLogger(__name__)


class AgentDelegationEngine:
    """Manages autonomous task delegation between agents."""

    def __init__(self, team: "AgentTeamManager", skills: "AgentSkillManager",
                 reputation: "AgentReputationManager", persistence: "PersistenceStore"):
        self._team = team
        self._skills = skills
        self._reputation = reputation
        self._persistence = persistence

    def find_candidates(self, task_id: str, exclude_agent: str = None) -> List[dict]:
        """Find best candidate agents for a task based on skills."""
        task = self._team.get_task(task_id)
        if not task:
            return []

        category = task.get("category", "general")
        agents = self._team.get_all_agents()
        candidates = []

        for a in agents:
            aid = a["agent_id"]
            if aid == exclude_agent:
                continue
            if a.get("state") == "working":
                continue

            # Skill match score
            profile = self._skills.get_profile(aid)
            skill_names = [s["name"] for s in profile.get("skills", [])]
            skill_match = sum(1 for s in skill_names if category.lower() in s or s in category.lower())
            avg_level = profile.get("summary", {}).get("avg_level", 1)

            # Trust score
            trust = self._reputation.get_trust_score(aid)

            # Availability bonus
            avail = 1.0 if a.get("state") == "idle" else 0.5 if a.get("state") == "active" else 0.1

            composite = (skill_match * 3 + avg_level * 2) * 0.4 + trust * 30 * 0.3 + avail * 10 * 0.3

            candidates.append({
                "agent_id": aid,
                "name": a.get("name", ""),
                "department": a.get("department", ""),
                "state": a.get("state", ""),
                "skill_match": skill_match,
                "avg_level": avg_level,
                "trust_score": trust,
                "composite_score": round(composite, 2),
            })

        candidates.sort(key=lambda x: -x["composite_score"])
        return candidates[:10]

    def delegate(self, from_agent: str, task_id: str,
                 to_agent: str = None, reason: str = "") -> dict:
        """Delegate a task from one agent to another."""
        # Check trust
        if not self._reputation.can_delegate(from_agent):
            return {"error": "Delegator trust score too low", "trust": self._reputation.get_trust_score(from_agent)}

        task = self._team.get_task(task_id)
        if not task:
            return {"error": "Task not found"}

        # Auto-select if no target specified
        if not to_agent:
            candidates = self.find_candidates(task_id, exclude_agent=from_agent)
            if not candidates:
                return {"error": "No suitable candidates found"}
            to_agent = candidates[0]["agent_id"]

        target = self._team.get_agent(to_agent)
        if not target:
            return {"error": "Target agent not found"}

        # Reassign
        self._team.update_task(task_id, {
            "assigned_to": to_agent,
            "metadata": {
                **task.get("metadata", {}),
                "delegated_from": from_agent,
                "delegation_reason": reason,
                "delegation_time": time.time(),
            },
        })

        # Log
        log_entry = {
            "delegation_id": f"DEL-{uuid.uuid4().hex[:8]}",
            "from_agent": from_agent,
            "to_agent": to_agent,
            "task_id": task_id,
            "reason": reason,
            "created_at": time.time(),
            "outcome": "pending",
        }
        history = self._persistence.kv_get("delegation_log", [])
        history.append(log_entry)
        if len(history) > 500:
            history = history[-500:]
        self._persistence.kv_set("delegation_log", history)

        logger.info("Delegated task %s: %s -> %s (%s)", task_id, from_agent, to_agent, reason)
        return {**log_entry, "target_name": target.get("name", "")}

    def auto_delegate(self, task_id: str) -> dict:
        """Auto-delegate a task to the best available agent."""
        task = self._team.get_task(task_id)
        if not task:
            return {"error": "Task not found"}
        current = task.get("assigned_to", "")
        candidates = self.find_candidates(task_id, exclude_agent=current)
        if not candidates:
            return {"error": "No candidates"}
        best = candidates[0]
        return self.delegate(current or "system", task_id, best["agent_id"], "auto-delegation")

    def get_history(self, agent_id: str = None, limit: int = 50) -> List[dict]:
        history = self._persistence.kv_get("delegation_log", [])
        if agent_id:
            history = [h for h in history if h.get("from_agent") == agent_id or h.get("to_agent") == agent_id]
        return history[-limit:]

    def get_stats(self) -> dict:
        history = self._persistence.kv_get("delegation_log", [])
        return {
            "total_delegations": len(history),
            "pending": sum(1 for h in history if h.get("outcome") == "pending"),
            "top_delegators": self._top_n(history, "from_agent"),
            "top_delegates": self._top_n(history, "to_agent"),
        }

    def _top_n(self, history: list, field: str, n: int = 5) -> List[dict]:
        counts: Dict[str, int] = {}
        for h in history:
            v = h.get(field, "")
            counts[v] = counts.get(v, 0) + 1
        return [{"agent_id": k, "count": v} for k, v in
                sorted(counts.items(), key=lambda x: -x[1])[:n]]
