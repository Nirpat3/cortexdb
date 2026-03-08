"""
Tool Rate Limiter — Prevents abuse of CLI tools by agents.

Tracks per-agent, per-tool call counts within sliding windows.
"""

import time
import logging
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)


class ToolRateLimiter:
    """Rate limits tool calls per agent using a sliding window."""

    # Default limits: (max_calls, window_seconds)
    DEFAULT_LIMITS: Dict[str, Tuple[int, int]] = {
        "run_command": (10, 60),      # 10 commands per minute
        "write_file": (20, 60),       # 20 writes per minute
        "read_file": (50, 60),        # 50 reads per minute
        "list_dir": (30, 60),         # 30 listings per minute
        "search_memory": (30, 60),
        "remember": (20, 60),
        "list_agents": (10, 60),
        "get_task_history": (20, 60),
        "query_data": (20, 60),
        "_default": (30, 60),         # default for unspecified tools
    }

    def __init__(self, custom_limits: Dict[str, Tuple[int, int]] = None):
        self._limits = {**self.DEFAULT_LIMITS, **(custom_limits or {})}
        # agent_id -> tool_name -> [timestamps]
        self._windows: Dict[str, Dict[str, List[float]]] = {}

    def check(self, agent_id: str, tool_name: str) -> bool:
        """Check if a tool call is allowed. Returns True if allowed."""
        max_calls, window_s = self._limits.get(tool_name, self._limits["_default"])
        now = time.time()
        cutoff = now - window_s

        agent_windows = self._windows.setdefault(agent_id, {})
        timestamps = agent_windows.setdefault(tool_name, [])

        # Prune old entries
        timestamps[:] = [t for t in timestamps if t > cutoff]

        if len(timestamps) >= max_calls:
            logger.warning(
                "Rate limit hit: agent=%s tool=%s (%d/%d in %ds)",
                agent_id, tool_name, len(timestamps), max_calls, window_s,
            )
            return False

        timestamps.append(now)
        return True

    def get_remaining(self, agent_id: str, tool_name: str) -> dict:
        """Get remaining calls for an agent/tool combo."""
        max_calls, window_s = self._limits.get(tool_name, self._limits["_default"])
        now = time.time()
        cutoff = now - window_s

        timestamps = self._windows.get(agent_id, {}).get(tool_name, [])
        recent = [t for t in timestamps if t > cutoff]

        return {
            "tool": tool_name,
            "remaining": max(0, max_calls - len(recent)),
            "limit": max_calls,
            "window_seconds": window_s,
            "used": len(recent),
        }

    def get_agent_usage(self, agent_id: str) -> List[dict]:
        """Get rate limit usage for all tools for an agent."""
        results = []
        for tool_name in self._limits:
            if tool_name == "_default":
                continue
            results.append(self.get_remaining(agent_id, tool_name))
        return results

    def set_limit(self, tool_name: str, max_calls: int, window_s: int):
        """Set a custom rate limit for a tool."""
        self._limits[tool_name] = (max_calls, window_s)

    def reset(self, agent_id: str = None, tool_name: str = None):
        """Reset rate limit counters."""
        if agent_id and tool_name:
            self._windows.get(agent_id, {}).pop(tool_name, None)
        elif agent_id:
            self._windows.pop(agent_id, None)
        else:
            self._windows.clear()
