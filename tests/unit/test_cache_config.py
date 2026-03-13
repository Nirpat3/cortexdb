"""Unit tests for SemanticCacheConfig (P1.4)."""

import pytest
from cortexdb.core.cache_config import SemanticCacheConfig, CollectionCacheConfig


class TestSemanticCacheConfig:
    def setup_method(self):
        self.config = SemanticCacheConfig()

    def test_sql_queries_skip_cache(self):
        """SQL queries should have r2_enabled=False."""
        cfg = self.config.get_config("default", "SELECT * FROM users")
        assert cfg.r2_enabled is False

    def test_natural_language_threshold(self):
        cfg = self.config.get_config("default", "Tell me about the latest user signups")
        assert cfg.r2_enabled is True
        assert 0.8 <= cfg.threshold <= 0.95

    def test_custom_collection_override(self):
        self.config.set_collection_config("my_collection",
                                          CollectionCacheConfig(threshold=0.75))
        cfg = self.config.get_config("my_collection", "some query")
        assert cfg.threshold == 0.75

    def test_detect_sql_patterns(self):
        sql_queries = [
            "SELECT id FROM agents",
            "INSERT INTO tasks VALUES (1)",
            "UPDATE blocks SET name = 'x'",
            "DELETE FROM experiences WHERE id = 1",
            "CREATE TABLE test (id INT)",
        ]
        for q in sql_queries:
            cfg = self.config.get_config("default", q)
            assert cfg.r2_enabled is False, f"Should skip cache for: {q}"

    def test_default_threshold_for_unknown_type(self):
        cfg = self.config.get_config("default", "")
        assert cfg.r2_enabled is True
        assert isinstance(cfg.threshold, float)

    def test_rag_retrieval_detection(self):
        cfg = self.config.get_config("default", "What is CortexDB?")
        assert cfg.threshold == 0.85  # rag_retrieval default

    def test_to_dict(self):
        d = self.config.to_dict()
        assert "default" in d
        assert "query_type_defaults" in d
        assert "sql" in d["query_type_defaults"]
