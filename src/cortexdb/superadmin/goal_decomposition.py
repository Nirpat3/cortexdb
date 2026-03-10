"""
Goal Decomposition — Break high-level goals into task DAGs automatically.

Uses LLM to decompose a goal into structured subtasks with:
  - Title, description, category, required skills
  - Dependencies between tasks
  - Auto-assignment based on skill profiles
"""

import time
import uuid
import json
import logging
from typing import List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from cortexdb.superadmin.agent_team import AgentTeamManager
    from cortexdb.superadmin.llm_router import LLMRouter
    from cortexdb.superadmin.agent_skills import AgentSkillManager
    from cortexdb.superadmin.persistence import PersistenceStore

logger = logging.getLogger(__name__)

DECOMPOSE_PROMPT = """You are a project planning AI. Break this goal into specific subtasks.

GOAL: {goal}

Respond with a JSON array of tasks. Each task:
{{
  "title": "short task title",
  "description": "what needs to be done",
  "category": "bug|feature|enhancement|qa|docs|security|ops",
  "required_skills": ["skill1", "skill2"],
  "depends_on": [],
  "priority": "critical|high|medium|low"
}}

Create 3-8 tasks. Use depends_on to reference earlier task indices (0-based).
Return ONLY the JSON array, no other text."""


class GoalDecomposer:
    """Decomposes high-level goals into task DAGs."""

    def __init__(self, team: "AgentTeamManager", router: "LLMRouter",
                 skills: "AgentSkillManager", persistence: "PersistenceStore"):
        self._team = team
        self._router = router
        self._skills = skills
        self._persistence = persistence

    async def decompose(self, goal: str, auto_assign: bool = True,
                        auto_execute: bool = False) -> dict:
        """Decompose a goal into tasks via LLM."""
        goal_id = f"GOAL-{uuid.uuid4().hex[:8]}"

        # LLM call
        prompt = DECOMPOSE_PROMPT.format(goal=goal)
        result = await self._router.chat(
            "ollama", [{"role": "user", "content": prompt}],
            temperature=0.3, failover=True,
        )

        if not result.get("success"):
            return {"error": result.get("error", "LLM call failed")}

        # Parse tasks from response
        response = result.get("message", "")
        subtasks = self._parse_tasks(response)
        if not subtasks:
            return {"error": "Failed to parse tasks from LLM response", "raw": response[:500]}

        # Create actual tasks
        created = []
        task_id_map = {}  # index -> task_id

        for i, st in enumerate(subtasks):
            assigned_to = None
            if auto_assign:
                assigned_to = self._find_best_agent(st)

            task = self._team.create_task(
                title=st.get("title", f"Subtask {i+1}"),
                description=st.get("description", ""),
                assigned_to=assigned_to,
                priority=st.get("priority", "medium"),
                category=st.get("category", "general"),
            )
            task_id_map[i] = task["task_id"]
            created.append({**task, "required_skills": st.get("required_skills", [])})

        # Store decomposition
        decomp = {
            "goal_id": goal_id,
            "goal": goal,
            "tasks": created,
            "task_count": len(created),
            "created_at": time.time(),
        }
        history = self._persistence.kv_get("goal_decompositions", [])
        history.append(decomp)
        if len(history) > 100:
            history = history[-100:]
        self._persistence.kv_set("goal_decompositions", history)

        logger.info("Decomposed goal '%s' into %d tasks", goal[:50], len(created))
        return decomp

    async def suggest(self, goal: str) -> dict:
        """Return a decomposition plan without creating tasks."""
        prompt = DECOMPOSE_PROMPT.format(goal=goal)
        result = await self._router.chat(
            "ollama", [{"role": "user", "content": prompt}],
            temperature=0.3, failover=True,
        )
        if not result.get("success"):
            return {"error": result.get("error", "LLM call failed")}

        subtasks = self._parse_tasks(result.get("message", ""))
        for st in subtasks:
            st["suggested_agent"] = self._find_best_agent(st)

        return {"goal": goal, "suggested_tasks": subtasks}

    def _parse_tasks(self, response: str) -> List[dict]:
        """Parse JSON task array from LLM response."""
        try:
            # Try direct parse
            tasks = json.loads(response.strip())
            if isinstance(tasks, list):
                return tasks
        except json.JSONDecodeError:
            pass

        # Try extracting JSON array from response
        import re
        match = re.search(r'\[[\s\S]*\]', response)
        if match:
            try:
                tasks = json.loads(match.group())
                if isinstance(tasks, list):
                    return tasks
            except json.JSONDecodeError:
                pass

        return []

    def _find_best_agent(self, subtask: dict) -> Optional[str]:
        """Find best agent for a subtask based on required skills."""
        required = subtask.get("required_skills", [])
        if not required:
            return None

        best_id = None
        best_score = -1
        for agent in self._team.get_all_agents():
            aid = agent["agent_id"]
            profile = self._skills.get_profile(aid)
            agent_skills = {s["name"] for s in profile.get("skills", [])}
            match = len(agent_skills & set(required))
            if match > best_score and agent.get("state") != "working":
                best_score = match
                best_id = aid

        return best_id

    def get_decompositions(self, limit: int = 20) -> List[dict]:
        history = self._persistence.kv_get("goal_decompositions", [])
        return history[-limit:]

    def get_decomposition(self, goal_id: str) -> Optional[dict]:
        history = self._persistence.kv_get("goal_decompositions", [])
        for g in history:
            if g.get("goal_id") == goal_id:
                return g
        return None
