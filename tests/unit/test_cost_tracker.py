"""Unit tests for CostTracker — token counting, pricing, totals."""

import pytest


class FakePersistence:
    def __init__(self):
        self._store = {}

    def kv_get(self, key, default=None):
        return self._store.get(key, default)

    def kv_set(self, key, value):
        self._store[key] = value


@pytest.fixture
def tracker():
    from cortexdb.superadmin.cost_tracker import CostTracker
    return CostTracker(FakePersistence())


class TestRecordCost:
    def test_record_basic(self, tracker):
        tracker.record("claude", "claude-sonnet-4-20250514", "agent-1", "bug",
                       {"input_tokens": 1000, "output_tokens": 500}, "engineering")
        totals = tracker.get_totals()
        assert totals["total_tokens"] == 1500
        assert totals["total_calls"] == 1
        assert totals["total_cost"] > 0

    def test_ollama_is_free(self, tracker):
        tracker.record("ollama", "llama3.1:8b", "agent-1", "general",
                       {"input_tokens": 5000, "output_tokens": 2000})
        totals = tracker.get_totals()
        assert totals["total_cost"] == 0

    def test_openai_tokens(self, tracker):
        tracker.record("openai", "gpt-4o", "agent-1", "feature",
                       {"prompt_tokens": 1000, "completion_tokens": 500})
        totals = tracker.get_totals()
        assert totals["total_tokens"] == 1500  # prompt_tokens alias

    def test_cumulative_tracking(self, tracker):
        tracker.record("claude", "claude-sonnet-4-20250514", "a-1", "bug",
                       {"input_tokens": 100, "output_tokens": 50})
        tracker.record("claude", "claude-sonnet-4-20250514", "a-1", "bug",
                       {"input_tokens": 200, "output_tokens": 100})
        totals = tracker.get_totals()
        assert totals["total_calls"] == 2
        assert totals["total_tokens"] == 450


class TestBreakdowns:
    def test_by_provider(self, tracker):
        tracker.record("claude", "claude-sonnet-4-20250514", "a-1", "bug",
                       {"input_tokens": 100, "output_tokens": 50})
        tracker.record("openai", "gpt-4o", "a-2", "feature",
                       {"input_tokens": 100, "output_tokens": 50})
        totals = tracker.get_totals()
        assert "claude" in totals["by_provider"]
        assert "openai" in totals["by_provider"]
        assert totals["by_provider"]["claude"]["calls"] == 1
        assert totals["by_provider"]["openai"]["calls"] == 1

    def test_by_agent(self, tracker):
        tracker.record("claude", "claude-sonnet-4-20250514", "agent-1", "bug",
                       {"input_tokens": 100, "output_tokens": 50})
        tracker.record("claude", "claude-sonnet-4-20250514", "agent-2", "bug",
                       {"input_tokens": 200, "output_tokens": 100})
        costs_1 = tracker.get_agent_costs("agent-1")
        costs_2 = tracker.get_agent_costs("agent-2")
        assert costs_1["calls"] == 1
        assert costs_2["calls"] == 1
        assert costs_2["tokens"] > costs_1["tokens"]

    def test_by_department(self, tracker):
        tracker.record("claude", "claude-sonnet-4-20250514", "a-1", "bug",
                       {"input_tokens": 100, "output_tokens": 50}, "engineering")
        tracker.record("claude", "claude-sonnet-4-20250514", "a-2", "bug",
                       {"input_tokens": 100, "output_tokens": 50}, "security")
        depts = tracker.get_department_costs()
        assert "engineering" in depts
        assert "security" in depts

    def test_by_category(self, tracker):
        tracker.record("ollama", "llama3.1:8b", "a-1", "bug",
                       {"input_tokens": 100, "output_tokens": 50})
        tracker.record("ollama", "llama3.1:8b", "a-1", "feature",
                       {"input_tokens": 100, "output_tokens": 50})
        totals = tracker.get_totals()
        assert "bug" in totals["by_category"]
        assert "feature" in totals["by_category"]


class TestCostLog:
    def test_recent_entries(self, tracker):
        tracker.record("ollama", "llama3.1:8b", "a-1", "bug",
                       {"input_tokens": 100, "output_tokens": 50})
        recent = tracker.get_recent(10)
        assert len(recent) == 1
        assert recent[0]["provider"] == "ollama"

    def test_log_limit(self, tracker):
        for i in range(1010):
            tracker.record("ollama", "llama3.1:8b", "a-1", "bug",
                           {"input_tokens": 1, "output_tokens": 1})
        recent = tracker.get_recent(2000)
        assert len(recent) == 1000  # capped


class TestPricing:
    def test_pricing_table(self, tracker):
        pricing = tracker.get_pricing_table()
        assert "gpt-4o" in pricing
        assert "claude-sonnet-4-20250514" in pricing
        assert "_ollama_default" not in pricing  # internal key excluded

    def test_cost_calculation(self, tracker):
        # Claude Sonnet: $3/M input, $15/M output
        tracker.record("claude", "claude-sonnet-4-20250514", "a-1", "bug",
                       {"input_tokens": 1_000_000, "output_tokens": 0})
        totals = tracker.get_totals()
        assert abs(totals["total_cost"] - 3.0) < 0.01  # ~$3 for 1M input tokens
