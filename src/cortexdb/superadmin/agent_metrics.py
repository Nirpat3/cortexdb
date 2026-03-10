"""
Agent Metrics — Per-agent throughput, latency, cost, quality aggregation.

Aggregates data from: tasks, outcome analyses, cost tracker, skills, reputation.
"""

import time
import logging
from typing import Dict, List, TYPE_CHECKING

if TYPE_CHECKING:
    from cortexdb.superadmin.agent_team import AgentTeamManager
    from cortexdb.superadmin.agent_skills import AgentSkillManager
    from cortexdb.superadmin.agent_reputation import AgentReputationManager
    from cortexdb.superadmin.persistence import PersistenceStore

logger = logging.getLogger(__name__)

DAY = 86400
WEEK = 604800


class AgentMetrics:
    """Aggregates per-agent and team-wide performance metrics."""

    def __init__(self, team: "AgentTeamManager", skills: "AgentSkillManager",
                 reputation: "AgentReputationManager",
                 persistence: "PersistenceStore"):
        self._team = team
        self._skills = skills
        self._reputation = reputation
        self._persistence = persistence

    def get_agent_metrics(self, agent_id: str) -> dict:
        agent = self._team.get_agent(agent_id)
        if not agent:
            return {"error": "Agent not found"}

        tasks = self._team.get_all_tasks()
        agent_tasks = [t for t in tasks if t.get("assigned_to") == agent_id]
        now = time.time()

        # Throughput
        completed = [t for t in agent_tasks if t.get("status") == "completed"]
        week_completed = [t for t in completed if t.get("completed_at", 0) > now - WEEK]
        day_completed = [t for t in completed if t.get("completed_at", 0) > now - DAY]

        # Latency
        durations = []
        for t in completed:
            started = t.get("started_at", 0)
            ended = t.get("completed_at", 0)
            if started and ended:
                durations.append((ended - started) * 1000)  # ms
        durations.sort()

        avg_latency = sum(durations) / len(durations) if durations else 0
        p50 = durations[len(durations)//2] if durations else 0
        p95 = durations[int(len(durations)*0.95)] if durations else 0

        # Quality
        analyses = self._persistence.kv_get("outcome_analyses", [])
        agent_analyses = [a for a in analyses if a.get("agent_id") == agent_id]
        grades = [a.get("grade", 5) for a in agent_analyses]
        avg_grade = sum(grades) / len(grades) if grades else 0

        # Cost
        costs = self._persistence.kv_get("cost_log", [])
        if isinstance(costs, dict):
            costs = costs.get("entries", [])
        agent_costs = [c for c in costs if c.get("agent_id") == agent_id]
        total_cost = sum(c.get("cost_usd", 0) for c in agent_costs)
        cost_per_task = total_cost / max(len(completed), 1)

        # Skills
        profile = self._skills.get_profile(agent_id)
        trust = self._reputation.get_trust_score(agent_id)

        return {
            "agent_id": agent_id,
            "agent_name": agent.get("name", ""),
            "department": agent.get("department", ""),
            "throughput": {
                "total_completed": len(completed),
                "total_failed": agent.get("tasks_failed", 0),
                "this_week": len(week_completed),
                "today": len(day_completed),
            },
            "latency": {
                "avg_ms": round(avg_latency, 1),
                "p50_ms": round(p50, 1),
                "p95_ms": round(p95, 1),
            },
            "quality": {
                "avg_grade": round(avg_grade, 2),
                "total_graded": len(grades),
                "recent_grades": grades[-10:],
            },
            "cost": {
                "total_usd": round(total_cost, 4),
                "per_task_usd": round(cost_per_task, 4),
                "total_calls": len(agent_costs),
            },
            "skills": profile.get("summary", {}),
            "trust_score": trust,
        }

    def get_team_metrics(self) -> dict:
        agents = self._team.get_all_agents()
        tasks = self._team.get_all_tasks()
        now = time.time()

        completed = [t for t in tasks if t.get("status") == "completed"]
        failed = [t for t in tasks if t.get("status") == "failed"]

        analyses = self._persistence.kv_get("outcome_analyses", [])
        grades = [a.get("grade", 5) for a in analyses]

        costs = self._persistence.kv_get("cost_log", [])
        if isinstance(costs, dict):
            costs = costs.get("entries", [])
        total_cost = sum(c.get("cost_usd", 0) for c in costs)

        return {
            "total_agents": len(agents),
            "active_agents": sum(1 for a in agents if a.get("state") in ("active", "working")),
            "total_tasks": len(tasks),
            "completed_tasks": len(completed),
            "failed_tasks": len(failed),
            "avg_grade": round(sum(grades) / max(len(grades), 1), 2),
            "total_cost_usd": round(total_cost, 4),
            "tasks_this_week": sum(1 for t in completed if t.get("completed_at", 0) > now - WEEK),
        }

    def get_department_metrics(self, dept: str) -> dict:
        agents = [a for a in self._team.get_all_agents() if a.get("department") == dept]
        agent_ids = {a["agent_id"] for a in agents}

        tasks = self._team.get_all_tasks()
        dept_tasks = [t for t in tasks if t.get("assigned_to") in agent_ids]
        completed = [t for t in dept_tasks if t.get("status") == "completed"]

        analyses = self._persistence.kv_get("outcome_analyses", [])
        dept_grades = [a.get("grade", 5) for a in analyses if a.get("agent_id") in agent_ids]

        return {
            "department": dept,
            "agent_count": len(agents),
            "total_tasks": len(dept_tasks),
            "completed": len(completed),
            "avg_grade": round(sum(dept_grades) / max(len(dept_grades), 1), 2),
            "agents": [{"agent_id": a["agent_id"], "name": a.get("name", ""),
                        "state": a.get("state", "")} for a in agents],
        }

    def get_summary(self) -> dict:
        """High-level KPIs for dashboard cards."""
        team = self.get_team_metrics()
        profiles = self._skills.get_all_profiles_summary()
        return {
            **team,
            "total_skills": sum(p.get("total_skills", 0) for p in profiles),
            "total_xp": sum(p.get("total_xp", 0) for p in profiles),
            "expert_skills": sum(p.get("expert_skills", 0) for p in profiles),
        }
