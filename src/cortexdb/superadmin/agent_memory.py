"""
Agent Memory System — Per-agent context window and long-term memory.

Each agent maintains:
  - Short-term memory: recent conversation turns (sliding window)
  - Long-term memory: key facts, learnings, task summaries
  - Context window: assembled prompt context for LLM calls

Stored in SQLite via the persistence layer's kv_store.
"""

import time
import json
import logging
from typing import Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from cortexdb.superadmin.persistence import PersistenceStore

logger = logging.getLogger(__name__)

MAX_SHORT_TERM = 20  # Max conversation turns kept
MAX_LONG_TERM = 100  # Max facts/learnings stored
MAX_CONTEXT_TOKENS_APPROX = 6000  # ~chars to include in context window


class AgentMemory:
    """Manages per-agent memory with short-term and long-term storage."""

    def __init__(self, persistence: "PersistenceStore"):
        self._persistence = persistence

    def _key(self, agent_id: str, mem_type: str) -> str:
        return f"agent_memory:{agent_id}:{mem_type}"

    # ── Short-term memory (conversation history) ──

    def add_turn(self, agent_id: str, role: str, content: str):
        """Add a conversation turn to short-term memory."""
        key = self._key(agent_id, "short_term")
        turns = self._persistence.kv_get(key, [])
        turns.append({
            "role": role,
            "content": content,
            "timestamp": time.time(),
        })
        # Slide window
        if len(turns) > MAX_SHORT_TERM:
            turns = turns[-MAX_SHORT_TERM:]
        self._persistence.kv_set(key, turns)

    def get_recent_turns(self, agent_id: str, limit: int = 10) -> List[dict]:
        """Get recent conversation turns."""
        key = self._key(agent_id, "short_term")
        turns = self._persistence.kv_get(key, [])
        return turns[-limit:]

    def clear_short_term(self, agent_id: str):
        """Clear short-term memory."""
        self._persistence.kv_set(self._key(agent_id, "short_term"), [])

    # ── Long-term memory (facts, learnings) ──

    def remember(self, agent_id: str, fact: str, category: str = "general"):
        """Store a fact or learning in long-term memory."""
        key = self._key(agent_id, "long_term")
        facts = self._persistence.kv_get(key, [])
        facts.append({
            "fact": fact,
            "category": category,
            "timestamp": time.time(),
        })
        if len(facts) > MAX_LONG_TERM:
            facts = facts[-MAX_LONG_TERM:]
        self._persistence.kv_set(key, facts)

    def recall(self, agent_id: str, category: str = None, limit: int = 20) -> List[dict]:
        """Recall facts from long-term memory."""
        key = self._key(agent_id, "long_term")
        facts = self._persistence.kv_get(key, [])
        if category:
            facts = [f for f in facts if f.get("category") == category]
        return facts[-limit:]

    def forget(self, agent_id: str, fact_index: int):
        """Remove a specific fact by index."""
        key = self._key(agent_id, "long_term")
        facts = self._persistence.kv_get(key, [])
        if 0 <= fact_index < len(facts):
            facts.pop(fact_index)
            self._persistence.kv_set(key, facts)

    # ── Task summaries ──

    def add_task_summary(self, agent_id: str, task_id: str, title: str,
                         result_summary: str, success: bool):
        """Store a compressed task result for future context."""
        key = self._key(agent_id, "task_history")
        history = self._persistence.kv_get(key, [])
        history.append({
            "task_id": task_id,
            "title": title,
            "summary": result_summary[:500],
            "success": success,
            "timestamp": time.time(),
        })
        if len(history) > 50:
            history = history[-50:]
        self._persistence.kv_set(key, history)

    def get_task_history(self, agent_id: str, limit: int = 10) -> List[dict]:
        """Get recent task summaries."""
        key = self._key(agent_id, "task_history")
        history = self._persistence.kv_get(key, [])
        return history[-limit:]

    # ── Context window assembly ──

    def build_context(self, agent_id: str, include_history: bool = True,
                      include_facts: bool = True, include_tasks: bool = True) -> str:
        """Assemble a context window for LLM calls."""
        parts = []
        total_chars = 0

        # Recent task history
        if include_tasks:
            tasks = self.get_task_history(agent_id, limit=5)
            if tasks:
                parts.append("## Recent Task History")
                for t in tasks:
                    line = f"- [{t['task_id']}] {t['title']}: {'success' if t['success'] else 'failed'}"
                    parts.append(line)
                    total_chars += len(line)
                parts.append("")

        # Long-term facts
        if include_facts:
            facts = self.recall(agent_id, limit=10)
            if facts:
                parts.append("## Known Facts & Learnings")
                for f in facts:
                    line = f"- [{f['category']}] {f['fact']}"
                    parts.append(line)
                    total_chars += len(line)
                    if total_chars > MAX_CONTEXT_TOKENS_APPROX:
                        break
                parts.append("")

        # Conversation history (most recent)
        if include_history:
            turns = self.get_recent_turns(agent_id, limit=6)
            if turns:
                parts.append("## Recent Conversation")
                for t in turns:
                    line = f"{t['role'].upper()}: {t['content'][:300]}"
                    parts.append(line)
                    total_chars += len(line)
                    if total_chars > MAX_CONTEXT_TOKENS_APPROX:
                        break
                parts.append("")

        return "\n".join(parts)

    # ── Stats ──

    def get_memory_stats(self, agent_id: str) -> dict:
        """Get memory usage stats for an agent."""
        short = self._persistence.kv_get(self._key(agent_id, "short_term"), [])
        long = self._persistence.kv_get(self._key(agent_id, "long_term"), [])
        tasks = self._persistence.kv_get(self._key(agent_id, "task_history"), [])
        return {
            "agent_id": agent_id,
            "short_term_turns": len(short),
            "long_term_facts": len(long),
            "task_summaries": len(tasks),
            "max_short_term": MAX_SHORT_TERM,
            "max_long_term": MAX_LONG_TERM,
        }
