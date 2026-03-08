"""Unit tests for AgentMemory — short-term, long-term, context assembly."""

import pytest
import time
from unittest.mock import MagicMock


class FakePersistence:
    """In-memory persistence mock for testing."""
    def __init__(self):
        self._store = {}

    def kv_get(self, key, default=None):
        return self._store.get(key, default)

    def kv_set(self, key, value):
        self._store[key] = value


@pytest.fixture
def memory():
    from cortexdb.superadmin.agent_memory import AgentMemory
    return AgentMemory(FakePersistence())


class TestShortTermMemory:
    def test_add_and_retrieve_turns(self, memory):
        memory.add_turn("agent-1", "user", "Hello")
        memory.add_turn("agent-1", "assistant", "Hi there!")
        turns = memory.get_recent_turns("agent-1")
        assert len(turns) == 2
        assert turns[0]["role"] == "user"
        assert turns[1]["content"] == "Hi there!"

    def test_sliding_window_limit(self, memory):
        for i in range(25):
            memory.add_turn("agent-1", "user", f"Message {i}")
        turns = memory.get_recent_turns("agent-1", limit=100)
        assert len(turns) == 20  # MAX_SHORT_TERM

    def test_clear_short_term(self, memory):
        memory.add_turn("agent-1", "user", "Hello")
        memory.clear_short_term("agent-1")
        assert memory.get_recent_turns("agent-1") == []

    def test_agent_isolation(self, memory):
        memory.add_turn("agent-1", "user", "For agent 1")
        memory.add_turn("agent-2", "user", "For agent 2")
        assert len(memory.get_recent_turns("agent-1")) == 1
        assert len(memory.get_recent_turns("agent-2")) == 1


class TestLongTermMemory:
    def test_remember_and_recall(self, memory):
        memory.remember("agent-1", "Python is great", "tech")
        facts = memory.recall("agent-1")
        assert len(facts) == 1
        assert facts[0]["fact"] == "Python is great"
        assert facts[0]["category"] == "tech"

    def test_recall_by_category(self, memory):
        memory.remember("agent-1", "Fact A", "cat1")
        memory.remember("agent-1", "Fact B", "cat2")
        memory.remember("agent-1", "Fact C", "cat1")
        cat1_facts = memory.recall("agent-1", category="cat1")
        assert len(cat1_facts) == 2

    def test_long_term_limit(self, memory):
        for i in range(110):
            memory.remember("agent-1", f"Fact {i}")
        facts = memory.recall("agent-1", limit=200)
        assert len(facts) == 100  # MAX_LONG_TERM

    def test_forget(self, memory):
        memory.remember("agent-1", "Keep this")
        memory.remember("agent-1", "Remove this")
        memory.forget("agent-1", 1)
        facts = memory.recall("agent-1")
        assert len(facts) == 1
        assert facts[0]["fact"] == "Keep this"


class TestTaskHistory:
    def test_add_task_summary(self, memory):
        memory.add_task_summary("agent-1", "task-1", "Fix bug", "Fixed the bug", True)
        history = memory.get_task_history("agent-1")
        assert len(history) == 1
        assert history[0]["task_id"] == "task-1"
        assert history[0]["success"] is True

    def test_task_history_limit(self, memory):
        for i in range(60):
            memory.add_task_summary("agent-1", f"task-{i}", f"Task {i}", "Done", True)
        history = memory.get_task_history("agent-1", limit=100)
        assert len(history) == 50  # Max 50 stored


class TestContextAssembly:
    def test_build_context_empty(self, memory):
        ctx = memory.build_context("agent-1")
        assert ctx == ""

    def test_build_context_with_data(self, memory):
        memory.add_task_summary("agent-1", "t-1", "Deploy v2", "Deployed", True)
        memory.remember("agent-1", "Always use HTTPS", "security")
        memory.add_turn("agent-1", "user", "How do I deploy?")
        ctx = memory.build_context("agent-1")
        assert "Deploy v2" in ctx
        assert "Always use HTTPS" in ctx
        assert "How do I deploy?" in ctx

    def test_build_context_selective(self, memory):
        memory.remember("agent-1", "A fact")
        memory.add_turn("agent-1", "user", "A turn")
        ctx = memory.build_context("agent-1", include_history=False, include_facts=True, include_tasks=False)
        assert "A fact" in ctx
        assert "A turn" not in ctx


class TestMemoryStats:
    def test_stats(self, memory):
        memory.add_turn("agent-1", "user", "Hi")
        memory.remember("agent-1", "Fact")
        memory.add_task_summary("agent-1", "t-1", "Task", "Done", True)
        stats = memory.get_memory_stats("agent-1")
        assert stats["short_term_turns"] == 1
        assert stats["long_term_facts"] == 1
        assert stats["task_summaries"] == 1
