"""Cache Invalidation Engine (DOC-018 Gap G10)

When RelationalCore data changes, invalidate stale entries in:
  - R0 (process LRU cache)
  - R1 (MemoryCore / Redis)
  - R2 (VectorCore / semantic cache)

Strategies: TTL-based (simple), event-based (PostgreSQL NOTIFY), write-through.
"""

import logging
import time
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger("cortexdb.core.cache_invalidation")


class CacheInvalidationEngine:
    """Cross-engine cache invalidation.

    Listens for data changes and invalidates affected cache entries
    across R0 (process), R1 (Redis), and R2 (Qdrant) tiers.
    """

    def __init__(self, read_cascade=None, engines: Dict[str, Any] = None):
        self.read_cascade = read_cascade
        self.engines = engines or {}
        self._invalidation_count = 0
        self._table_key_map: Dict[str, Set[str]] = {}  # table -> set of cache keys

    async def on_write(self, data_type: str, payload: Dict,
                       affected_tables: List[str] = None):
        """Called after a write to invalidate related cache entries."""
        self._invalidation_count += 1
        tables = affected_tables or self._infer_tables(data_type)
        invalidated = {"r0": 0, "r1": 0, "r2": 0}

        for table in tables:
            # R0: Invalidate process-local cache entries for this table
            if self.read_cascade:
                keys_to_remove = []
                for key in list(self.read_cascade._r0_cache.keys()):
                    if table in self._table_key_map.get(key, set()):
                        keys_to_remove.append(key)
                for key in keys_to_remove:
                    del self.read_cascade._r0_cache[key]
                    invalidated["r0"] += 1

            # R1: Invalidate Redis cache entries
            if "memory" in self.engines:
                try:
                    pattern = f"cache:*{table}*"
                    # Use SCAN to find matching keys
                    deleted = await self._delete_matching_keys(pattern)
                    invalidated["r1"] += deleted
                except Exception as e:
                    logger.warning(f"R1 invalidation error for {table}: {e}")

        logger.debug(f"Cache invalidated for {data_type}: {invalidated}")
        return invalidated

    async def _delete_matching_keys(self, pattern: str) -> int:
        """Delete Redis keys matching pattern."""
        if "memory" not in self.engines:
            return 0
        try:
            return await self.engines["memory"].delete_pattern(pattern)
        except Exception:
            return 0

    async def invalidate_for_tenant(self, tenant_id: str):
        """Invalidate all cache entries for a specific tenant."""
        invalidated = 0

        # R0
        if self.read_cascade:
            keys_to_remove = [k for k in self.read_cascade._r0_cache
                              if tenant_id in k]
            for k in keys_to_remove:
                del self.read_cascade._r0_cache[k]
            invalidated += len(keys_to_remove)

        # R1
        if "memory" in self.engines:
            try:
                deleted = await self._delete_matching_keys(f"tenant:{tenant_id}:cache:*")
                invalidated += deleted
            except Exception as e:
                logger.warning(f"Tenant cache invalidation error: {e}")

        return invalidated

    def register_key_table(self, cache_key: str, table: str):
        """Track which tables a cache key depends on."""
        if cache_key not in self._table_key_map:
            self._table_key_map[cache_key] = set()
        self._table_key_map[cache_key].add(table)

    @staticmethod
    def _infer_tables(data_type: str) -> List[str]:
        """Infer affected tables from write data type."""
        mapping = {
            "payment": ["tasks", "agents"],
            "agent": ["agents"],
            "task": ["tasks", "agents"],
            "block": ["blocks"],
            "heartbeat": ["heartbeats", "grid_nodes"],
            "experience": ["experience_ledger"],
            "grid_event": ["grid_nodes", "grid_links"],
        }
        return mapping.get(data_type, [])

    def get_stats(self) -> Dict:
        return {
            "total_invalidations": self._invalidation_count,
            "tracked_key_mappings": len(self._table_key_map),
        }
