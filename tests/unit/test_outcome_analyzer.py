"""Unit tests for OutcomeAnalyzer — parsing, scoring, storage."""

import pytest
from unittest.mock import MagicMock, AsyncMock


class FakePersistence:
    def __init__(self):
        self._store = {}

    def kv_get(self, key, default=None):
        return self._store.get(key, default)

    def kv_set(self, key, value):
        self._store[key] = value


@pytest.fixture
def persistence():
    return FakePersistence()


@pytest.fixture
def analyzer(persistence):
    from cortexdb.superadmin.outcome_analyzer import OutcomeAnalyzer
    router = MagicMock()
    memory = MagicMock()
    memory.remember = MagicMock()
    return OutcomeAnalyzer(router, memory, persistence)


class TestParseAnalysis:
    def test_parse_full_response(self, analyzer):
        response = """GRADE: 8
QUALITY: good
LEARNINGS:
- Always validate input
- Use type hints
PROMPT_INSIGHT: Clear task description led to good output
REUSABLE_PATTERN: Validate-then-process pattern"""
        result = analyzer._parse_analysis(response)
        assert result["grade"] == 8
        assert result["quality"] == "good"
        assert len(result["learnings"]) == 2
        assert "Always validate input" in result["learnings"]
        assert "Clear task description" in result["prompt_insight"]
        assert "Validate-then-process" in result["reusable_pattern"]

    def test_parse_minimal_response(self, analyzer):
        result = analyzer._parse_analysis("GRADE: 3\nQUALITY: poor")
        assert result["grade"] == 3
        assert result["quality"] == "poor"
        assert result["learnings"] == []

    def test_parse_invalid_grade(self, analyzer):
        result = analyzer._parse_analysis("GRADE: banana\nQUALITY: fair")
        assert result["grade"] == 5  # default

    def test_grade_clamping(self, analyzer):
        result = analyzer._parse_analysis("GRADE: 15")
        assert result["grade"] == 10  # clamped to max
        result = analyzer._parse_analysis("GRADE: -5")
        assert result["grade"] == 1  # clamped to min

    def test_parse_empty(self, analyzer):
        result = analyzer._parse_analysis("")
        assert result["grade"] == 5
        assert result["quality"] == "fair"


class TestScoring:
    def test_update_agent_scores(self, analyzer, persistence):
        analyzer._update_scores("agent-1", "bug", 8)
        scores = persistence.kv_get("quality_scores:agent:agent-1")
        assert scores["total"] == 1
        assert scores["avg"] == 8
        assert scores["by_category"]["bug"]["avg"] == 8

    def test_cumulative_scores(self, analyzer, persistence):
        analyzer._update_scores("agent-1", "bug", 8)
        analyzer._update_scores("agent-1", "bug", 6)
        scores = persistence.kv_get("quality_scores:agent:agent-1")
        assert scores["total"] == 2
        assert scores["avg"] == 7.0
        assert scores["by_category"]["bug"]["avg"] == 7.0

    def test_category_scores(self, analyzer, persistence):
        analyzer._update_scores("agent-1", "feature", 9)
        cat_scores = persistence.kv_get("quality_scores:category:feature")
        assert cat_scores["total"] == 1
        assert cat_scores["avg"] == 9

    def test_multi_agent_scores(self, analyzer, persistence):
        analyzer._update_scores("agent-1", "bug", 8)
        analyzer._update_scores("agent-2", "bug", 4)
        s1 = persistence.kv_get("quality_scores:agent:agent-1")
        s2 = persistence.kv_get("quality_scores:agent:agent-2")
        assert s1["avg"] == 8
        assert s2["avg"] == 4


class TestStoreLearnings:
    def test_stores_learnings_in_memory(self, analyzer):
        analysis = {
            "learnings": ["Always validate", "Use type hints"],
            "reusable_pattern": "Validate first, process second",
            "prompt_insight": "Clear descriptions help",
        }
        analyzer._store_learnings("agent-1", analysis, "bug")
        # 2 learnings + 1 pattern + 1 insight = 4 calls
        assert analyzer._memory.remember.call_count == 4

    def test_skips_short_learnings(self, analyzer):
        analysis = {"learnings": ["ok", "This is a valid learning point"], "reusable_pattern": "", "prompt_insight": ""}
        analyzer._store_learnings("agent-1", analysis, "bug")
        assert analyzer._memory.remember.call_count == 1  # only the long one


class TestStoreAnalysis:
    def test_stores_in_persistence(self, analyzer, persistence):
        analysis = {
            "task_id": "t-1", "agent_id": "a-1", "category": "bug",
            "grade": 7, "quality": "good", "learnings": ["x"],
            "timestamp": 1000,
        }
        analyzer._store_analysis(analysis)
        stored = persistence.kv_get("outcome_analyses")
        assert len(stored) == 1
        assert stored[0]["grade"] == 7

    def test_analysis_limit(self, analyzer, persistence):
        for i in range(510):
            analyzer._store_analysis({
                "task_id": f"t-{i}", "grade": 5, "quality": "fair",
                "learnings": [], "timestamp": 1000,
            })
        stored = persistence.kv_get("outcome_analyses")
        assert len(stored) == 500  # capped


class TestQueryMethods:
    def test_get_agent_scores_empty(self, analyzer):
        scores = analyzer.get_agent_scores("nonexistent")
        assert scores["total"] == 0

    def test_get_insights_empty(self, analyzer):
        insights = analyzer.get_insights()
        assert insights["total_analyzed"] == 0

    def test_get_insights_with_data(self, analyzer, persistence):
        analyses = [
            {"grade": 8, "quality": "good"},
            {"grade": 6, "quality": "fair"},
            {"grade": 9, "quality": "excellent"},
        ]
        persistence.kv_set("outcome_analyses", analyses)
        insights = analyzer.get_insights()
        assert insights["total_analyzed"] == 3
        assert round(insights["avg_grade"], 2) == 7.67
