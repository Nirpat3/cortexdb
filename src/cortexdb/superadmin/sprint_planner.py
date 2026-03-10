"""
Autonomous Sprint Planning — Atlas generates sprint backlogs from goals.

Uses the GoalDecomposer to break goals into tasks, then organizes them
into a sprint with assignments, estimates, and dependencies.
"""

import time
import uuid
import logging
from typing import List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from cortexdb.superadmin.agent_team import AgentTeamManager
    from cortexdb.superadmin.llm_router import LLMRouter
    from cortexdb.superadmin.goal_decomposition import GoalDecomposer
    from cortexdb.superadmin.persistence import PersistenceStore

logger = logging.getLogger(__name__)


class SprintPlanner:
    """Plans and manages sprints with auto-generated task backlogs."""

    def __init__(self, team: "AgentTeamManager", router: "LLMRouter",
                 decomposer: "GoalDecomposer", persistence: "PersistenceStore"):
        self._team = team
        self._router = router
        self._decomposer = decomposer
        self._persistence = persistence

    async def plan_sprint(self, goal: str, duration_days: int = 14,
                          name: str = None) -> dict:
        """Create a sprint plan from a goal."""
        sprint_id = f"SPR-{uuid.uuid4().hex[:8]}"

        # Decompose goal into tasks
        decomp = await self._decomposer.decompose(goal, auto_assign=True)
        if "error" in decomp:
            return decomp

        sprint = {
            "sprint_id": sprint_id,
            "name": name or f"Sprint {sprint_id[-4:]}",
            "goal": goal,
            "duration_days": duration_days,
            "status": "planned",
            "tasks": decomp.get("tasks", []),
            "task_count": decomp.get("task_count", 0),
            "created_at": time.time(),
            "started_at": None,
            "completed_at": None,
        }

        sprints = self._persistence.kv_get("sprints", {})
        sprints[sprint_id] = sprint
        self._persistence.kv_set("sprints", sprints)

        logger.info("Sprint %s planned: %d tasks for '%s'", sprint_id, sprint["task_count"], goal[:50])
        return sprint

    def activate_sprint(self, sprint_id: str) -> dict:
        """Activate a sprint, setting all tasks to pending."""
        sprints = self._persistence.kv_get("sprints", {})
        sprint = sprints.get(sprint_id)
        if not sprint:
            return {"error": "Sprint not found"}

        sprint["status"] = "active"
        sprint["started_at"] = time.time()
        self._persistence.kv_set("sprints", sprints)
        return sprint

    async def standup(self, sprint_id: str) -> dict:
        """Generate a sprint standup report."""
        sprints = self._persistence.kv_get("sprints", {})
        sprint = sprints.get(sprint_id)
        if not sprint:
            return {"error": "Sprint not found"}

        tasks = sprint.get("tasks", [])
        completed = sum(1 for t in tasks if t.get("status") == "completed")
        in_progress = sum(1 for t in tasks if t.get("status") == "in_progress")
        pending = sum(1 for t in tasks if t.get("status") == "pending")

        # Refresh task statuses
        for i, t in enumerate(tasks):
            tid = t.get("task_id")
            if tid:
                current = self._team.get_task(tid)
                if current:
                    tasks[i]["status"] = current.get("status", tasks[i].get("status"))

        return {
            "sprint_id": sprint_id,
            "name": sprint["name"],
            "goal": sprint["goal"],
            "progress": {
                "completed": completed,
                "in_progress": in_progress,
                "pending": pending,
                "total": len(tasks),
                "pct": round(completed / max(len(tasks), 1) * 100, 1),
            },
            "tasks": tasks,
            "days_elapsed": round((time.time() - (sprint.get("started_at") or sprint["created_at"])) / 86400, 1),
            "days_remaining": sprint.get("duration_days", 14) - round(
                (time.time() - (sprint.get("started_at") or sprint["created_at"])) / 86400, 1),
        }

    def get_sprints(self) -> List[dict]:
        sprints = self._persistence.kv_get("sprints", {})
        return sorted(sprints.values(), key=lambda s: -s.get("created_at", 0))

    def get_sprint(self, sprint_id: str) -> Optional[dict]:
        sprints = self._persistence.kv_get("sprints", {})
        return sprints.get(sprint_id)

    def delete_sprint(self, sprint_id: str) -> dict:
        sprints = self._persistence.kv_get("sprints", {})
        if sprint_id in sprints:
            del sprints[sprint_id]
            self._persistence.kv_set("sprints", sprints)
            return {"deleted": True}
        return {"error": "Sprint not found"}
