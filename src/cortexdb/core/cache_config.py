"""
Adaptive Semantic Cache Thresholds for CortexDB R2 Cache Tier.

Replaces the hardcoded 0.95 cosine similarity threshold with per-collection,
per-query-type adaptive thresholds based on AI/ML expert recommendations:

  - SQL/structured queries: R2 disabled (hash-based R0/R1 only)
  - Natural language search: 0.85-0.88 (paraphrases score 0.88-0.94 with MiniLM)
  - Agent tool calls: 0.90-0.92
  - RAG retrieval: 0.82-0.87
"""

from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class CollectionCacheConfig:
    """Per-collection semantic cache configuration."""
    threshold: float = 0.88          # Cosine similarity threshold for R2
    r2_enabled: bool = True          # Whether to use semantic matching at all
    ttl_seconds: int = 3600          # Cache entry TTL
    negative_cache: bool = False     # Cache "no results" responses
    max_entries: int = 10000         # Max cached entries per collection


class SemanticCacheConfig:
    """Manages per-collection R2 cache thresholds with smart defaults.

    Priority order for config resolution:
      1. Explicit per-collection config (set via set_collection_config)
      2. Auto-detected query type defaults
      3. Global default (threshold=0.88)
    """

    # Default thresholds by query type
    QUERY_TYPE_DEFAULTS = {
        "sql": CollectionCacheConfig(r2_enabled=False),  # SQL uses hash match only
        "natural_language": CollectionCacheConfig(threshold=0.87),
        "agent_tool_call": CollectionCacheConfig(threshold=0.91),
        "rag_retrieval": CollectionCacheConfig(threshold=0.85),
    }

    def __init__(self):
        self._collection_configs: Dict[str, CollectionCacheConfig] = {}
        self._default = CollectionCacheConfig(threshold=0.88)

    def set_collection_config(self, collection: str, config: CollectionCacheConfig):
        """Set custom config for a specific collection."""
        self._collection_configs[collection] = config

    def get_collection_config(self, collection: str) -> Optional[CollectionCacheConfig]:
        """Get explicit config for a collection, or None if not set."""
        return self._collection_configs.get(collection)

    def remove_collection_config(self, collection: str) -> bool:
        """Remove explicit config for a collection. Returns True if it existed."""
        return self._collection_configs.pop(collection, None) is not None

    def get_config(self, collection: str, query: str = "") -> CollectionCacheConfig:
        """Get cache config for a collection+query combination.

        Priority: explicit collection config > query type detection > default
        """
        # Explicit collection config takes priority
        if collection in self._collection_configs:
            return self._collection_configs[collection]

        # Auto-detect query type
        query_type = self._detect_query_type(query)
        if query_type in self.QUERY_TYPE_DEFAULTS:
            return self.QUERY_TYPE_DEFAULTS[query_type]

        return self._default

    def _detect_query_type(self, query: str) -> str:
        """Detect whether a query is SQL, natural language, etc."""
        if not query:
            return "natural_language"

        upper = query.strip().upper()

        # SQL detection
        sql_keywords = [
            "SELECT", "INSERT", "UPDATE", "DELETE",
            "CREATE", "ALTER", "DROP", "WITH",
        ]
        if any(upper.startswith(kw) for kw in sql_keywords):
            return "sql"

        # Agent tool call detection (JSON-like or function-call patterns)
        if query.strip().startswith("{") or "tool_call" in query.lower():
            return "agent_tool_call"

        # RAG retrieval detection (short queries, question patterns)
        rag_prefixes = [
            "what", "how", "why", "when", "where", "who",
            "find", "search", "show", "list", "get",
        ]
        if len(query.split()) <= 10 and any(
            query.lower().startswith(w) for w in rag_prefixes
        ):
            return "rag_retrieval"

        return "natural_language"

    def to_dict(self) -> Dict:
        """Serialize current configuration for inspection."""
        return {
            "default": {
                "threshold": self._default.threshold,
                "r2_enabled": self._default.r2_enabled,
            },
            "query_type_defaults": {
                qt: {"threshold": cfg.threshold, "r2_enabled": cfg.r2_enabled}
                for qt, cfg in self.QUERY_TYPE_DEFAULTS.items()
            },
            "collection_overrides": {
                col: {
                    "threshold": cfg.threshold,
                    "r2_enabled": cfg.r2_enabled,
                    "ttl_seconds": cfg.ttl_seconds,
                    "negative_cache": cfg.negative_cache,
                    "max_entries": cfg.max_entries,
                }
                for col, cfg in self._collection_configs.items()
            },
        }
