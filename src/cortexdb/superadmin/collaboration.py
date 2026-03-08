"""
Multi-Agent Collaboration — Structured sessions where multiple agents work together.

A collaboration session:
  1. Has a goal/task and a set of participating agents
  2. Agents take turns contributing based on their expertise
  3. Each agent sees the shared context + their own memory
  4. Results are synthesized into a final output
  5. The coordinator agent (or round-robin) manages turn order

Use cases:
  - Code review: architect + QA + security agent review together
  - Planning: exec + eng + ops collaborate on a plan
  - Problem solving: multiple specialists tackle a complex issue
"""

import time
import uuid
import logging
from typing import Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from cortexdb.superadmin.agent_team import AgentTeamManager
    from cortexdb.superadmin.llm_router import LLMRouter
    from cortexdb.superadmin.agent_memory import AgentMemory
    from cortexdb.superadmin.persistence import PersistenceStore

logger = logging.getLogger(__name__)


class CollaborationSession:
    """A single multi-agent collaboration session."""

    def __init__(self, session_id: str, goal: str, agent_ids: List[str],
                 coordinator_id: str = None):
        self.session_id = session_id
        self.goal = goal
        self.agent_ids = agent_ids
        self.coordinator_id = coordinator_id or (agent_ids[0] if agent_ids else None)
        self.status = "active"
        self.created_at = time.time()
        self.turns: List[dict] = []
        self.synthesis: Optional[str] = None
        self._turn_index = 0

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "goal": self.goal,
            "agent_ids": self.agent_ids,
            "coordinator_id": self.coordinator_id,
            "status": self.status,
            "created_at": self.created_at,
            "turn_count": len(self.turns),
            "turns": self.turns,
            "synthesis": self.synthesis,
        }

    def get_shared_context(self, max_chars: int = 4000) -> str:
        """Build shared context from all turns so far."""
        parts = [f"## Collaboration Goal\n{self.goal}\n"]
        total = len(parts[0])
        for turn in self.turns:
            line = f"**{turn['agent_name']}** ({turn['agent_id']}):\n{turn['content']}\n"
            total += len(line)
            if total > max_chars:
                break
            parts.append(line)
        return "\n".join(parts)

    def next_agent(self) -> Optional[str]:
        """Get the next agent in round-robin order."""
        if not self.agent_ids:
            return None
        agent_id = self.agent_ids[self._turn_index % len(self.agent_ids)]
        self._turn_index += 1
        return agent_id


class CollaborationManager:
    """Manages multi-agent collaboration sessions."""

    def __init__(self, team: "AgentTeamManager", router: "LLMRouter",
                 memory: "AgentMemory", persistence: "PersistenceStore"):
        self._team = team
        self._router = router
        self._memory = memory
        self._persistence = persistence
        self._sessions: Dict[str, CollaborationSession] = {}

    def create_session(self, goal: str, agent_ids: List[str],
                       coordinator_id: str = None) -> dict:
        """Create a new collaboration session."""
        # Validate agents exist
        valid_agents = []
        for aid in agent_ids:
            agent = self._team.get_agent(aid)
            if agent:
                valid_agents.append(aid)
            else:
                logger.warning("Agent %s not found, skipping from collaboration", aid)

        if len(valid_agents) < 2:
            return {"error": "Need at least 2 valid agents for collaboration"}

        session_id = f"collab-{uuid.uuid4().hex[:8]}"
        session = CollaborationSession(
            session_id=session_id,
            goal=goal,
            agent_ids=valid_agents,
            coordinator_id=coordinator_id,
        )
        self._sessions[session_id] = session
        self._save_session(session)

        logger.info("Collaboration session %s created: %d agents, goal=%s",
                     session_id, len(valid_agents), goal[:60])
        return session.to_dict()

    async def run_round(self, session_id: str, rounds: int = 1) -> dict:
        """Run one or more rounds of collaboration (each agent contributes once per round)."""
        session = self._sessions.get(session_id)
        if not session:
            return {"error": "Session not found"}
        if session.status != "active":
            return {"error": f"Session is {session.status}"}

        for _ in range(rounds):
            for agent_id in session.agent_ids:
                agent = self._team.get_agent(agent_id)
                if not agent:
                    continue

                # Build prompt with shared context + agent identity
                system = self._build_agent_system(agent, session)
                shared = session.get_shared_context()

                user_prompt = (
                    f"{shared}\n\n"
                    f"It's your turn to contribute. Based on the goal and what others have said, "
                    f"provide your expert input from your perspective as {agent.get('title', 'an agent')}. "
                    f"Be specific and actionable. Do not repeat what others have said."
                )

                provider = agent.get("llm_provider", "ollama")
                model = agent.get("llm_model", "")

                result = await self._router.chat(
                    provider,
                    [{"role": "user", "content": user_prompt}],
                    model=model or None,
                    system=system,
                    temperature=0.5,
                )

                response = result.get("message", "") or result.get("error", "No response")

                turn = {
                    "agent_id": agent_id,
                    "agent_name": agent.get("name", agent_id),
                    "content": response,
                    "timestamp": time.time(),
                    "provider": provider,
                    "success": result.get("success", False),
                }
                session.turns.append(turn)

                # Store in agent memory
                if self._memory:
                    self._memory.add_turn(
                        agent_id, "assistant",
                        f"[collab:{session_id}] {response[:500]}"
                    )

        self._save_session(session)
        return session.to_dict()

    async def synthesize(self, session_id: str) -> dict:
        """Have the coordinator synthesize all contributions into a final output."""
        session = self._sessions.get(session_id)
        if not session:
            return {"error": "Session not found"}

        if not session.turns:
            return {"error": "No contributions to synthesize"}

        coordinator_id = session.coordinator_id
        coordinator = self._team.get_agent(coordinator_id)
        if not coordinator:
            # Fallback: use first agent
            coordinator_id = session.agent_ids[0]
            coordinator = self._team.get_agent(coordinator_id)

        system = (
            f"You are {coordinator.get('name', 'the coordinator')}. "
            f"Your role: synthesize the team's contributions into a clear, "
            f"actionable final output. Combine the best ideas, resolve any "
            f"disagreements, and produce a cohesive result."
        )

        shared = session.get_shared_context(max_chars=6000)
        prompt = (
            f"{shared}\n\n"
            f"## Your Task\n"
            f"Synthesize all contributions above into a final, comprehensive response. "
            f"Combine insights, resolve conflicts, and produce the best possible output "
            f"for the goal: {session.goal}"
        )

        provider = coordinator.get("llm_provider", "ollama")
        model = coordinator.get("llm_model", "")

        result = await self._router.chat(
            provider,
            [{"role": "user", "content": prompt}],
            model=model or None,
            system=system,
            temperature=0.4,
        )

        synthesis = result.get("message", "") or "Synthesis failed"
        session.synthesis = synthesis
        session.status = "completed"
        self._save_session(session)

        return {
            "session_id": session_id,
            "synthesis": synthesis,
            "status": "completed",
            "total_turns": len(session.turns),
            "agents": session.agent_ids,
        }

    async def add_message(self, session_id: str, agent_id: str, message: str) -> dict:
        """Manually inject a message from a specific agent (or human)."""
        session = self._sessions.get(session_id)
        if not session:
            return {"error": "Session not found"}

        agent = self._team.get_agent(agent_id)
        agent_name = agent.get("name", agent_id) if agent else agent_id

        turn = {
            "agent_id": agent_id,
            "agent_name": agent_name,
            "content": message,
            "timestamp": time.time(),
            "provider": "manual",
            "success": True,
        }
        session.turns.append(turn)
        self._save_session(session)
        return {"status": "added", "turn_count": len(session.turns)}

    def close_session(self, session_id: str) -> dict:
        """Close a collaboration session."""
        session = self._sessions.get(session_id)
        if not session:
            return {"error": "Session not found"}
        session.status = "closed"
        self._save_session(session)
        return {"status": "closed", "session_id": session_id}

    def get_session(self, session_id: str) -> Optional[dict]:
        """Get a session by ID."""
        session = self._sessions.get(session_id)
        return session.to_dict() if session else None

    def get_all_sessions(self, status: str = None) -> List[dict]:
        """Get all collaboration sessions."""
        sessions = list(self._sessions.values())
        if status:
            sessions = [s for s in sessions if s.status == status]
        return [s.to_dict() for s in sessions]

    def _build_agent_system(self, agent: dict, session: CollaborationSession) -> str:
        parts = [agent.get("system_prompt", "")]
        parts.append(f"\nYou are {agent.get('name', '')} ({agent.get('title', '')}).")
        parts.append(f"You are in a multi-agent collaboration session with: "
                      f"{', '.join(session.agent_ids)}")
        parts.append(f"Goal: {session.goal}")
        parts.append("\nContribute your unique expertise. Be concise and specific.")
        return "\n".join(parts)

    def _save_session(self, session: CollaborationSession):
        """Persist session to storage."""
        key = f"collab_session:{session.session_id}"
        self._persistence.kv_set(key, session.to_dict())

        # Update index
        index = self._persistence.kv_get("collab_sessions_index", [])
        if session.session_id not in index:
            index.append(session.session_id)
            if len(index) > 100:
                index = index[-100:]
            self._persistence.kv_set("collab_sessions_index", index)
