"""
Prompt Evolution — Learns and refines system prompts based on task outcomes.

Tracks:
  - Which system prompt templates produce the highest grades per category
  - Prompt insights extracted by the outcome analyzer
  - Evolved prompts: periodically generates improved prompts from insights

The system starts with static agent prompts, then evolves them based on
what actually produces good results.
"""

import time
import logging
from typing import Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from cortexdb.superadmin.persistence import PersistenceStore
    from cortexdb.superadmin.llm_router import LLMRouter

logger = logging.getLogger(__name__)

EVOLUTION_PROMPT = """You are an AI prompt engineer. Based on the performance data below, generate an improved system prompt for an AI agent.

AGENT ROLE: {role}
DEPARTMENT: {department}
CURRENT PROMPT:
{current_prompt}

PERFORMANCE DATA:
- Average grade: {avg_grade}/10
- Total tasks: {total_tasks}
- Success rate: {success_rate}%

PROMPT INSIGHTS FROM PAST TASKS (what worked/didn't):
{insights}

TASK CATEGORIES THIS AGENT HANDLES: {categories}

Generate an improved system prompt that:
1. Keeps the agent's core identity and role
2. Incorporates the prompt insights (what led to better/worse results)
3. Adds specific guidance for the weak categories
4. Is concise but effective

Respond with ONLY the new system prompt text, nothing else."""


class PromptEvolution:
    """Tracks prompt effectiveness and evolves prompts over time."""

    def __init__(self, persistence: "PersistenceStore", llm_router: "LLMRouter" = None):
        self._persistence = persistence
        self._router = llm_router

    # ── Tracking ──

    def record_prompt_result(self, agent_id: str, category: str,
                             system_prompt_hash: str, grade: int):
        """Record how a system prompt performed for a given category."""
        key = "prompt_performance"
        data = self._persistence.kv_get(key, {})

        entry_key = f"{agent_id}:{category}"
        entry = data.get(entry_key, {
            "agent_id": agent_id, "category": category,
            "prompt_hash": system_prompt_hash,
            "total": 0, "grade_sum": 0,
        })
        entry["total"] = entry.get("total", 0) + 1
        entry["grade_sum"] = entry.get("grade_sum", 0) + grade
        entry["avg_grade"] = round(entry["grade_sum"] / entry["total"], 2)
        entry["last_updated"] = time.time()
        data[entry_key] = entry
        self._persistence.kv_set(key, data)

    def get_prompt_performance(self, agent_id: str = None) -> dict:
        """Get prompt performance data, optionally filtered by agent."""
        data = self._persistence.kv_get("prompt_performance", {})
        if agent_id:
            return {k: v for k, v in data.items() if v.get("agent_id") == agent_id}
        return data

    def get_weak_categories(self, agent_id: str, threshold: float = 6.0) -> List[str]:
        """Get categories where an agent scores below threshold."""
        perf = self.get_prompt_performance(agent_id)
        weak = []
        for entry in perf.values():
            if entry.get("avg_grade", 10) < threshold and entry.get("total", 0) >= 2:
                weak.append(entry.get("category", ""))
        return weak

    # ── Evolution ──

    async def evolve_prompt(self, agent_id: str, agent_data: dict,
                            provider: str = "ollama") -> Optional[dict]:
        """Generate an evolved system prompt for an agent based on performance data.

        Returns:
            dict with new_prompt, improvements, or None if not enough data
        """
        if not self._router:
            return None

        # Gather performance data
        perf = self.get_prompt_performance(agent_id)
        if not perf:
            return None

        total_tasks = sum(e.get("total", 0) for e in perf.values())
        if total_tasks < 3:
            return None  # Need at least 3 data points

        avg_grade = sum(e.get("grade_sum", 0) for e in perf.values()) / max(1, total_tasks)
        success_entries = [e for e in perf.values() if e.get("total", 0) > 0]
        categories = [e.get("category", "") for e in success_entries]

        # Gather prompt insights from agent memory
        insights_key = f"agent_memory:{agent_id}:long_term"
        all_facts = self._persistence.kv_get(insights_key, [])
        prompt_insights = [f["fact"] for f in all_facts
                          if f.get("category") in ("prompt_insights", "patterns")]
        insights_text = "\n".join(f"- {i}" for i in prompt_insights[-10:]) or "No insights yet"

        current_prompt = agent_data.get("system_prompt", "")

        # Generate evolved prompt
        prompt = EVOLUTION_PROMPT.format(
            role=agent_data.get("title", "AI Agent"),
            department=agent_data.get("department", ""),
            current_prompt=current_prompt[:1000],
            avg_grade=round(avg_grade, 1),
            total_tasks=total_tasks,
            success_rate=round(sum(1 for e in success_entries if e.get("avg_grade", 0) >= 5) / max(1, len(success_entries)) * 100),
            insights=insights_text,
            categories=", ".join(set(categories)),
        )

        try:
            result = await self._router.chat(
                provider,
                [{"role": "user", "content": prompt}],
                temperature=0.3,
                failover=True,
            )
        except Exception as e:
            logger.warning("Prompt evolution failed for %s: %s", agent_id, e)
            return None

        if not result.get("success"):
            return None

        new_prompt = result.get("message", "").strip()
        if not new_prompt or len(new_prompt) < 20:
            return None

        # Store the evolution record
        evolution = {
            "agent_id": agent_id,
            "old_prompt_preview": current_prompt[:200],
            "new_prompt": new_prompt,
            "based_on_tasks": total_tasks,
            "avg_grade_before": round(avg_grade, 1),
            "weak_categories": self.get_weak_categories(agent_id),
            "timestamp": time.time(),
        }

        evolutions = self._persistence.kv_get("prompt_evolutions", [])
        evolutions.append(evolution)
        if len(evolutions) > 100:
            evolutions = evolutions[-100:]
        self._persistence.kv_set("prompt_evolutions", evolutions)

        return evolution

    def get_evolutions(self, agent_id: str = None, limit: int = 20) -> List[dict]:
        """Get prompt evolution history."""
        evolutions = self._persistence.kv_get("prompt_evolutions", [])
        if agent_id:
            evolutions = [e for e in evolutions if e.get("agent_id") == agent_id]
        return evolutions[-limit:]

    def apply_evolution(self, agent_id: str, new_prompt: str, agent_team) -> bool:
        """Apply an evolved prompt to an agent."""
        result = agent_team.update_agent(agent_id, {"system_prompt": new_prompt})
        if result:
            self._persistence.audit(
                "prompt_evolved", "agent", agent_id,
                {"prompt_length": len(new_prompt)},
            ) if hasattr(self._persistence, 'audit') else None
            logger.info("Applied evolved prompt to agent %s (%d chars)", agent_id, len(new_prompt))
            return True
        return False
