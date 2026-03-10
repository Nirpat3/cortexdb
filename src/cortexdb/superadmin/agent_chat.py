"""
Agent Chat — Direct multi-turn conversation interface with any agent.

Provides a chat endpoint where users can talk to agents directly.
Each conversation:
  - Uses the agent's system prompt + memory context
  - Persists in agent short-term memory
  - Feeds into the learning loop (outcome analysis optional)
  - Supports streaming responses
"""

import time
import logging
from typing import AsyncIterator, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from cortexdb.superadmin.agent_team import AgentTeamManager
    from cortexdb.superadmin.llm_router import LLMRouter
    from cortexdb.superadmin.agent_memory import AgentMemory
    from cortexdb.superadmin.cost_tracker import CostTracker
    from cortexdb.superadmin.agent_tools import AgentToolSystem

logger = logging.getLogger(__name__)


class AgentChat:
    """Direct conversational interface with agents."""

    def __init__(self, team: "AgentTeamManager", router: "LLMRouter",
                 memory: "AgentMemory", cost_tracker: "CostTracker" = None,
                 tool_system: "AgentToolSystem" = None):
        self._team = team
        self._router = router
        self._memory = memory
        self._cost_tracker = cost_tracker
        self._tool_system = tool_system
        self._sessions: Dict[str, dict] = {}  # session_id -> metadata
        self._max_tool_rounds = 5  # prevent infinite tool loops

    def _build_system_prompt(self, agent: dict) -> str:
        """Build system prompt from agent identity + available tools."""
        parts = [agent.get("system_prompt", "")]
        parts.append(f"\nYou are {agent.get('name', 'an AI agent')} ({agent.get('title', '')}).")
        parts.append(f"Department: {agent.get('department', 'unknown')}")
        skills = agent.get("skills", [])
        if skills:
            parts.append(f"Skills: {', '.join(skills)}")
        # Inject tool descriptions so the agent knows what tools are available
        if self._tool_system:
            parts.append("")
            parts.append(self._tool_system.get_tool_descriptions(agent.get("agent_id")))
        parts.append("\nRespond helpfully and in character. Be concise and actionable.")
        return "\n".join(parts)

    async def send_message(self, agent_id: str, message: str,
                           session_id: str = None) -> dict:
        """Send a message to an agent and get a response."""
        agent = self._team.get_agent(agent_id)
        if not agent:
            return {"error": "Agent not found", "agent_id": agent_id}

        # Build context
        system_prompt = self._build_system_prompt(agent)
        if self._memory:
            context = self._memory.build_context(agent_id, include_history=False)
            if context:
                system_prompt += f"\n\n## Your Memory\n{context}"

        # Build messages from conversation history
        messages = []
        if self._memory:
            turns = self._memory.get_recent_turns(agent_id, limit=10)
            for turn in turns:
                messages.append({"role": turn["role"], "content": turn["content"]})
        messages.append({"role": "user", "content": message})

        # Determine provider
        provider = agent.get("llm_provider", "ollama")
        model = agent.get("llm_model", "")

        # Call LLM (with tool loop)
        start = time.time()
        result = await self._router.chat(
            provider, messages, model=model or None,
            system=system_prompt, temperature=0.6,
        )

        response_text = result.get("message", "") or result.get("error", "No response")
        success = result.get("success", False)

        # Tool execution loop — if the LLM output contains tool calls,
        # execute them, feed results back, and let the LLM continue
        tool_round = 0
        while (
            success
            and self._tool_system
            and self._tool_system.has_tool_calls(response_text)
            and tool_round < self._max_tool_rounds
        ):
            tool_round += 1
            tool_results = await self._tool_system.execute_tool_calls(agent_id, response_text)
            logger.info("Chat tool round %d for %s: %d calls", tool_round, agent_id, len(tool_results))

            # Build tool results feedback
            feedback_parts = []
            for tr in tool_results:
                name = tr.get("tool", "?")
                if "error" in tr:
                    feedback_parts.append(f"[[{name}]] Error: {tr['error']}")
                else:
                    feedback_parts.append(f"[[{name}]] Result:\n{tr['result']}")
            feedback = "\n\n".join(feedback_parts)

            # Append assistant response + tool feedback, then call LLM again
            messages.append({"role": "assistant", "content": response_text})
            messages.append({"role": "user", "content": f"Tool results:\n{feedback}\n\nContinue your response using these results."})

            result = await self._router.chat(
                provider, messages, model=model or None,
                system=system_prompt, temperature=0.6,
            )
            response_text = result.get("message", "") or result.get("error", "")
            success = result.get("success", False)

        elapsed = round((time.time() - start) * 1000, 1)

        # Store in memory
        if self._memory:
            self._memory.add_turn(agent_id, "user", message)
            if success:
                self._memory.add_turn(agent_id, "assistant", response_text[:1000])

        # Track costs
        if self._cost_tracker and result.get("usage"):
            self._cost_tracker.record(
                provider=provider,
                model=model or result.get("model", "default"),
                agent_id=agent_id,
                category="chat",
                usage=result["usage"],
                department=agent.get("department"),
            )

        # Track session
        if session_id:
            sess = self._sessions.setdefault(session_id, {
                "agent_id": agent_id, "started_at": time.time(), "turn_count": 0,
            })
            sess["turn_count"] += 1
            sess["last_active"] = time.time()

        return {
            "agent_id": agent_id,
            "response": response_text,
            "success": success,
            "provider": provider,
            "model": result.get("model", model),
            "elapsed_ms": elapsed,
            "session_id": session_id,
        }

    async def stream_message(self, agent_id: str, message: str) -> AsyncIterator[str]:
        """Stream a response from an agent token by token."""
        agent = self._team.get_agent(agent_id)
        if not agent:
            yield "Error: Agent not found"
            return

        system_prompt = self._build_system_prompt(agent)
        if self._memory:
            context = self._memory.build_context(agent_id, include_history=False)
            if context:
                system_prompt += f"\n\n## Your Memory\n{context}"

        messages = []
        if self._memory:
            turns = self._memory.get_recent_turns(agent_id, limit=10)
            for turn in turns:
                messages.append({"role": turn["role"], "content": turn["content"]})
        messages.append({"role": "user", "content": message})

        provider = agent.get("llm_provider", "ollama")
        model = agent.get("llm_model", "")

        # Store user turn
        if self._memory:
            self._memory.add_turn(agent_id, "user", message)

        full_response = []
        async for chunk in self._router.chat_stream(
            provider, messages, model=model or None,
            system=system_prompt, temperature=0.6,
        ):
            full_response.append(chunk)
            yield chunk

        # Store assistant turn
        if self._memory and full_response:
            self._memory.add_turn(agent_id, "assistant", "".join(full_response)[:1000])

    def get_sessions(self) -> List[dict]:
        """Get active chat sessions."""
        return [{"session_id": k, **v} for k, v in self._sessions.items()]

    def clear_session(self, agent_id: str):
        """Clear conversation history for an agent."""
        if self._memory:
            self._memory.clear_short_term(agent_id)
        self._sessions = {k: v for k, v in self._sessions.items()
                          if v.get("agent_id") != agent_id}
