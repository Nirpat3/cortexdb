"""
LLM Rate Limiter — Per-agent and per-department token budgets.

Enforces daily/hourly token limits to prevent cost overruns.
Tracks usage in sliding windows and rejects requests that exceed budgets.
"""

import time
import logging
from typing import Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from cortexdb.superadmin.persistence import PersistenceStore

logger = logging.getLogger(__name__)

# Default daily token budgets (input + output)
DEFAULT_BUDGETS = {
    "engineering": 500_000,
    "qa": 200_000,
    "operations": 200_000,
    "security": 150_000,
    "documentation": 150_000,
    "executive": 100_000,
    "_per_agent": 100_000,  # Default per-agent daily limit
    "_global_hourly": 200_000,  # Global hourly limit
}


class LLMRateLimiter:
    """Enforces token budgets per agent and department."""

    def __init__(self, persistence: "PersistenceStore"):
        self._persistence = persistence
        self._budgets = dict(DEFAULT_BUDGETS)
        # Load custom budgets from persistence
        custom = self._persistence.kv_get("llm_budgets")
        if custom:
            self._budgets.update(custom)

    def check(self, agent_id: str, department: str = None,
              estimated_tokens: int = 0) -> dict:
        """Check if a request is allowed under current budgets.

        Returns:
            dict with 'allowed' bool and optional 'reason' if denied.
        """
        now = time.time()
        day_start = now - (now % 86400)  # Start of current UTC day
        hour_start = now - 3600

        # Check per-agent daily limit
        agent_usage = self._get_usage(f"agent:{agent_id}", day_start)
        agent_budget = self._budgets.get("_per_agent", 100_000)
        if agent_usage + estimated_tokens > agent_budget:
            return {
                "allowed": False,
                "reason": f"Agent {agent_id} daily budget exceeded ({agent_usage}/{agent_budget} tokens)",
                "usage": agent_usage,
                "budget": agent_budget,
            }

        # Check per-department daily limit
        if department:
            dept_usage = self._get_usage(f"dept:{department}", day_start)
            dept_budget = self._budgets.get(department, 200_000)
            if dept_usage + estimated_tokens > dept_budget:
                return {
                    "allowed": False,
                    "reason": f"Department {department} daily budget exceeded ({dept_usage}/{dept_budget} tokens)",
                    "usage": dept_usage,
                    "budget": dept_budget,
                }

        # Check global hourly limit
        global_usage = self._get_usage("global", hour_start)
        global_budget = self._budgets.get("_global_hourly", 200_000)
        if global_usage + estimated_tokens > global_budget:
            return {
                "allowed": False,
                "reason": f"Global hourly limit exceeded ({global_usage}/{global_budget} tokens)",
                "usage": global_usage,
                "budget": global_budget,
            }

        return {"allowed": True}

    def record_usage(self, agent_id: str, department: str = None,
                     tokens: int = 0):
        """Record token usage after a request completes."""
        now = time.time()
        entry = {"timestamp": now, "tokens": tokens}

        # Agent tracking
        self._append_usage(f"agent:{agent_id}", entry)

        # Department tracking
        if department:
            self._append_usage(f"dept:{department}", entry)

        # Global tracking
        self._append_usage("global", entry)

    def set_budget(self, key: str, tokens: int):
        """Set a custom budget (department name or '_per_agent')."""
        self._budgets[key] = tokens
        self._persistence.kv_set("llm_budgets", self._budgets)

    def get_budgets(self) -> dict:
        """Get all current budgets."""
        return dict(self._budgets)

    def get_usage_summary(self) -> dict:
        """Get current usage across all tracked entities."""
        now = time.time()
        day_start = now - (now % 86400)
        hour_start = now - 3600

        summary = {
            "global_hourly": self._get_usage("global", hour_start),
            "global_hourly_budget": self._budgets.get("_global_hourly", 200_000),
            "departments": {},
            "top_agents": {},
        }

        for dept in ["engineering", "qa", "operations", "security", "documentation", "executive"]:
            usage = self._get_usage(f"dept:{dept}", day_start)
            if usage > 0:
                summary["departments"][dept] = {
                    "usage": usage,
                    "budget": self._budgets.get(dept, 200_000),
                    "pct": round(usage / max(self._budgets.get(dept, 200_000), 1) * 100, 1),
                }

        return summary

    def _get_usage(self, key: str, since: float) -> int:
        """Get total token usage for a key since a timestamp."""
        entries = self._persistence.kv_get(f"llm_usage:{key}", [])
        return sum(e.get("tokens", 0) for e in entries if e.get("timestamp", 0) >= since)

    def _append_usage(self, key: str, entry: dict):
        """Append usage entry, pruning old data."""
        full_key = f"llm_usage:{key}"
        entries = self._persistence.kv_get(full_key, [])
        entries.append(entry)
        # Keep only last 48 hours of data
        cutoff = time.time() - (48 * 3600)
        entries = [e for e in entries if e.get("timestamp", 0) >= cutoff]
        self._persistence.kv_set(full_key, entries)
