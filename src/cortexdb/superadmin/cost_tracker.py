"""
LLM Cost Tracker — Token-precise cost tracking per provider/model/agent.

Captures input_tokens, output_tokens, and computes precise USD cost
using per-model pricing tables. Tracks spend per agent, department, and category.
"""

import time
import logging
from typing import Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from cortexdb.superadmin.persistence import PersistenceStore

logger = logging.getLogger(__name__)

# Pricing per 1M tokens (USD) — updated March 2026
MODEL_PRICING = {
    # Anthropic
    "claude-sonnet-4-20250514": {"input": 3.00, "output": 15.00},
    "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.00},
    "claude-opus-4-6": {"input": 15.00, "output": 75.00},
    # OpenAI
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4.1": {"input": 2.00, "output": 8.00},
    # Ollama (local — zero cost)
    "_ollama_default": {"input": 0.0, "output": 0.0},
}


def _get_pricing(provider: str, model: str) -> dict:
    """Get per-million-token pricing for a model."""
    if provider == "ollama":
        return MODEL_PRICING["_ollama_default"]
    return MODEL_PRICING.get(model, {"input": 1.0, "output": 5.0})  # conservative fallback


class CostTracker:
    """Tracks token-precise LLM costs per agent, department, and category."""

    def __init__(self, persistence: "PersistenceStore"):
        self._persistence = persistence

    def record(self, provider: str, model: str, agent_id: str,
               category: str, usage: dict, department: str = None):
        """Record a single LLM call with token usage.

        Args:
            usage: dict with input_tokens, output_tokens (from API response)
        """
        input_tokens = usage.get("input_tokens", 0) or usage.get("prompt_tokens", 0) or 0
        output_tokens = usage.get("output_tokens", 0) or usage.get("completion_tokens", 0) or 0

        pricing = _get_pricing(provider, model)
        input_cost = (input_tokens / 1_000_000) * pricing["input"]
        output_cost = (output_tokens / 1_000_000) * pricing["output"]
        total_cost = round(input_cost + output_cost, 6)

        entry = {
            "timestamp": time.time(),
            "provider": provider,
            "model": model,
            "agent_id": agent_id or "",
            "department": department or "",
            "category": category or "general",
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
            "cost_usd": total_cost,
        }

        # Append to log
        log = self._persistence.kv_get("cost_log", [])
        log.append(entry)
        if len(log) > 1000:
            log = log[-1000:]
        self._persistence.kv_set("cost_log", log)

        # Update running totals
        self._update_totals(entry)

        logger.debug("Cost recorded: %s/%s %d+%d tokens = $%.6f",
                      provider, model, input_tokens, output_tokens, total_cost)

    def _update_totals(self, entry: dict):
        """Update running totals for agent, department, and global."""
        # Global totals
        totals = self._persistence.kv_get("cost_totals", {
            "total_cost": 0, "total_tokens": 0, "total_calls": 0,
            "by_provider": {}, "by_agent": {}, "by_department": {}, "by_category": {},
        })

        totals["total_cost"] = round(totals.get("total_cost", 0) + entry["cost_usd"], 6)
        totals["total_tokens"] = totals.get("total_tokens", 0) + entry["total_tokens"]
        totals["total_calls"] = totals.get("total_calls", 0) + 1

        # By provider
        bp = totals.setdefault("by_provider", {})
        prov = bp.setdefault(entry["provider"], {"cost": 0, "tokens": 0, "calls": 0})
        prov["cost"] = round(prov["cost"] + entry["cost_usd"], 6)
        prov["tokens"] = prov["tokens"] + entry["total_tokens"]
        prov["calls"] = prov["calls"] + 1

        # By agent
        if entry["agent_id"]:
            ba = totals.setdefault("by_agent", {})
            agent = ba.setdefault(entry["agent_id"], {"cost": 0, "tokens": 0, "calls": 0})
            agent["cost"] = round(agent["cost"] + entry["cost_usd"], 6)
            agent["tokens"] = agent["tokens"] + entry["total_tokens"]
            agent["calls"] = agent["calls"] + 1

        # By department
        if entry["department"]:
            bd = totals.setdefault("by_department", {})
            dept = bd.setdefault(entry["department"], {"cost": 0, "tokens": 0, "calls": 0})
            dept["cost"] = round(dept["cost"] + entry["cost_usd"], 6)
            dept["tokens"] = dept["tokens"] + entry["total_tokens"]
            dept["calls"] = dept["calls"] + 1

        # By category
        bc = totals.setdefault("by_category", {})
        cat = bc.setdefault(entry["category"], {"cost": 0, "tokens": 0, "calls": 0})
        cat["cost"] = round(cat["cost"] + entry["cost_usd"], 6)
        cat["tokens"] = cat["tokens"] + entry["total_tokens"]
        cat["calls"] = cat["calls"] + 1

        self._persistence.kv_set("cost_totals", totals)

    def get_totals(self) -> dict:
        """Get global cost totals."""
        return self._persistence.kv_get("cost_totals", {
            "total_cost": 0, "total_tokens": 0, "total_calls": 0,
        })

    def get_recent(self, limit: int = 50) -> List[dict]:
        """Get recent cost entries."""
        log = self._persistence.kv_get("cost_log", [])
        return log[-limit:]

    def get_agent_costs(self, agent_id: str) -> dict:
        """Get cost breakdown for a specific agent."""
        totals = self.get_totals()
        return totals.get("by_agent", {}).get(agent_id, {"cost": 0, "tokens": 0, "calls": 0})

    def get_department_costs(self) -> dict:
        """Get cost breakdown by department."""
        totals = self.get_totals()
        return totals.get("by_department", {})

    def get_pricing_table(self) -> dict:
        """Return the current pricing table."""
        return {k: v for k, v in MODEL_PRICING.items() if not k.startswith("_")}
