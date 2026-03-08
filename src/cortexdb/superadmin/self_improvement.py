"""
Agent Self-Improvement — Agents identify weak areas and propose training.

Analyzes skill profiles, recent outcomes, and peer comparisons to generate
improvement proposals that can be approved and turned into training tasks.
"""

import time
import uuid
import logging
from typing import List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from cortexdb.superadmin.agent_team import AgentTeamManager
    from cortexdb.superadmin.agent_skills import AgentSkillManager
    from cortexdb.superadmin.llm_router import LLMRouter
    from cortexdb.superadmin.persistence import PersistenceStore

logger = logging.getLogger(__name__)

IMPROVEMENT_PROMPT = """You are {agent_name} ({agent_title}), an AI agent in the CortexDB team.

Review your performance data and suggest one specific area for improvement.

Your skills: {skills}
Your weak areas (low confidence): {weak_areas}
Recent task grades: {recent_grades}
Department peers average level: {peer_avg}

Respond in this format:
AREA: <specific skill or capability to improve>
JUSTIFICATION: <why this improvement matters, based on the data>
TRAINING_TYPE: practice_tasks|skill_study|peer_shadowing
TRAINING_PROMPT: <a specific task prompt that would help you improve in this area>"""


class SelfImprovementEngine:
    """Generates and manages agent self-improvement proposals."""

    def __init__(self, team: "AgentTeamManager", skills: "AgentSkillManager",
                 router: "LLMRouter", persistence: "PersistenceStore"):
        self._team = team
        self._skills = skills
        self._router = router
        self._persistence = persistence

    async def generate_proposal(self, agent_id: str) -> dict:
        """Generate an improvement proposal for an agent."""
        agent = self._team.get_agent(agent_id)
        if not agent:
            return {"error": "Agent not found"}

        profile = self._skills.get_profile(agent_id)
        skills_list = profile.get("skills", [])

        # Find weak areas (low confidence or low level)
        weak = [s for s in skills_list if s.get("confidence", 0.5) < 0.5 or s.get("level", 1) <= 2]
        weak_names = [s["name"] for s in weak[:5]]

        # Get recent grades
        analyses = self._persistence.kv_get("outcome_analyses", [])
        agent_grades = [a.get("grade", 5) for a in analyses if a.get("agent_id") == agent_id][-10:]

        # Peer comparison
        dept = agent.get("department", "")
        dept_profiles = [
            self._skills.get_profile(a["agent_id"])
            for a in self._team.get_all_agents()
            if a.get("department") == dept and a["agent_id"] != agent_id
        ]
        peer_avg = sum(
            p.get("summary", {}).get("avg_level", 1) for p in dept_profiles
        ) / max(len(dept_profiles), 1)

        # LLM call
        prompt = IMPROVEMENT_PROMPT.format(
            agent_name=agent.get("name", "Agent"),
            agent_title=agent.get("title", ""),
            skills=", ".join(s["name"] + f"(lv{s['level']})" for s in skills_list[:10]),
            weak_areas=", ".join(weak_names) or "none identified",
            recent_grades=str(agent_grades) if agent_grades else "no data",
            peer_avg=f"{peer_avg:.1f}",
        )

        result = await self._router.chat(
            agent.get("llm_provider", "ollama"),
            [{"role": "user", "content": prompt}],
            temperature=0.4, failover=True,
        )

        if not result.get("success"):
            return {"error": "LLM call failed"}

        response = result.get("message", "")
        proposal = self._parse_proposal(response, agent_id)

        # Store
        proposals = self._persistence.kv_get("improvement_proposals", [])
        proposals.append(proposal)
        if len(proposals) > 200:
            proposals = proposals[-200:]
        self._persistence.kv_set("improvement_proposals", proposals)

        return proposal

    async def generate_all(self) -> List[dict]:
        """Generate proposals for all agents."""
        results = []
        for agent in self._team.get_all_agents():
            try:
                p = await self.generate_proposal(agent["agent_id"])
                if "error" not in p:
                    results.append(p)
            except Exception as e:
                logger.warning("Proposal generation failed for %s: %s", agent["agent_id"], e)
        return results

    def _parse_proposal(self, response: str, agent_id: str) -> dict:
        proposal = {
            "proposal_id": f"IMP-{uuid.uuid4().hex[:8]}",
            "agent_id": agent_id,
            "area": "",
            "justification": "",
            "training_type": "practice_tasks",
            "training_prompt": "",
            "status": "pending",
            "created_at": time.time(),
        }

        for line in response.split("\n"):
            line = line.strip()
            if line.startswith("AREA:"):
                proposal["area"] = line.split(":", 1)[1].strip()
            elif line.startswith("JUSTIFICATION:"):
                proposal["justification"] = line.split(":", 1)[1].strip()
            elif line.startswith("TRAINING_TYPE:"):
                val = line.split(":", 1)[1].strip().lower()
                if val in ("practice_tasks", "skill_study", "peer_shadowing"):
                    proposal["training_type"] = val
            elif line.startswith("TRAINING_PROMPT:"):
                proposal["training_prompt"] = line.split(":", 1)[1].strip()

        return proposal

    def approve_proposal(self, proposal_id: str) -> dict:
        """Approve a proposal and create a training task."""
        proposals = self._persistence.kv_get("improvement_proposals", [])
        for p in proposals:
            if p.get("proposal_id") == proposal_id:
                if p["status"] != "pending":
                    return {"error": "Proposal already processed"}

                # Create training task
                task = self._team.create_task(
                    title=f"[Training] {p['area']}",
                    description=p.get("training_prompt", p["justification"]),
                    assigned_to=p["agent_id"],
                    priority="low",
                    category="enhancement",
                )

                p["status"] = "approved"
                p["task_id"] = task["task_id"]
                self._persistence.kv_set("improvement_proposals", proposals)
                return {**p, "task": task}

        return {"error": "Proposal not found"}

    def reject_proposal(self, proposal_id: str) -> dict:
        proposals = self._persistence.kv_get("improvement_proposals", [])
        for p in proposals:
            if p.get("proposal_id") == proposal_id:
                p["status"] = "rejected"
                self._persistence.kv_set("improvement_proposals", proposals)
                return p
        return {"error": "Proposal not found"}

    def get_proposals(self, agent_id: str = None, status: str = None) -> List[dict]:
        proposals = self._persistence.kv_get("improvement_proposals", [])
        if agent_id:
            proposals = [p for p in proposals if p.get("agent_id") == agent_id]
        if status:
            proposals = [p for p in proposals if p.get("status") == status]
        return proposals
