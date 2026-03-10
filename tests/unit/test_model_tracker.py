"""Unit tests for ModelPerformanceTracker — recording, scoring, recommendations."""

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
    from cortexdb.superadmin.model_tracker import ModelPerformanceTracker
    return ModelPerformanceTracker(FakePersistence())


class TestRecord:
    def test_record_basic(self, tracker):
        tracker.record("ollama", "llama3.1:8b", "bug", True, 500, 7)
        data = tracker.get_performance_data()
        assert data["total_tracked"] >= 1

    def test_record_accumulates(self, tracker):
        tracker.record("ollama", "llama3.1:8b", "bug", True, 500, 8)
        tracker.record("ollama", "llama3.1:8b", "bug", True, 400, 6)
        data = tracker.get_performance_data()
        key = "ollama:llama3.1:8b:bug"
        assert key in data.get("entries", {})
        entry = data["entries"][key]
        assert entry["total_requests"] == 2

    def test_record_multiple_providers(self, tracker):
        tracker.record("ollama", "llama3.1:8b", "bug", True, 500, 7)
        tracker.record("claude", "sonnet", "bug", True, 1000, 9)
        data = tracker.get_performance_data()
        assert len(data.get("entries", {})) == 2


class TestRecommend:
    def test_recommend_best(self, tracker):
        # Claude gets high grades, Ollama gets low
        for _ in range(5):
            tracker.record("claude", "sonnet", "bug", True, 1000, 9)
            tracker.record("ollama", "llama", "bug", True, 500, 4)
        rec = tracker.recommend("bug")
        assert rec is not None
        assert rec["provider"] == "claude"

    def test_recommend_no_data(self, tracker):
        rec = tracker.recommend("nonexistent")
        assert rec is None

    def test_all_recommendations(self, tracker):
        for _ in range(3):
            tracker.record("ollama", "llama", "feature", True, 300, 8)
            tracker.record("claude", "sonnet", "bug", True, 1000, 9)
        recs = tracker.get_all_recommendations()
        assert "feature" in recs or "bug" in recs


class TestCompositeScore:
    def test_perfect_scores(self, tracker):
        for _ in range(10):
            tracker.record("ollama", "llama", "test", True, 100, 10)
        data = tracker.get_performance_data()
        entry = data["entries"].get("ollama:llama:test", {})
        assert entry.get("composite_score", 0) > 0.8

    def test_failure_penalizes(self, tracker):
        tracker.record("ollama", "llama", "test", True, 100, 8)
        tracker.record("ollama", "llama", "test", False, 100, 0)
        tracker.record("ollama", "llama", "test", False, 100, 0)
        data = tracker.get_performance_data()
        entry = data["entries"].get("ollama:llama:test", {})
        assert entry.get("success_rate", 1) < 0.5
