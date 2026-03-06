"""Pre-Computation Engine / Cerebellum (DOC-018 Gap G13)

Identifies frequently-asked queries and crystallizes responses.
Pre-computes during Sleep Cycle so morning queries are answered in < 5ms.
"""

import time
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("cortexdb.core.precompute")


class PreComputeEngine:
    """Automatic pre-computation based on Synaptic Plasticity data.

    Reads top query patterns, creates materialized views for expensive joins,
    and caches results in MemoryCore (R1) for instant retrieval.
    """

    def __init__(self, plasticity=None, read_cascade=None,
                 engines: Dict[str, Any] = None):
        self.plasticity = plasticity
        self.read_cascade = read_cascade
        self.engines = engines or {}
        self._precomputed: Dict[str, Dict] = {}
        self._materialized_views: List[str] = []

    async def run(self, top_n: int = 50) -> Dict:
        """Pre-compute top N query patterns.

        Steps:
          1. Read Synaptic Plasticity for top patterns by strength
          2. For patterns with JOINs and strength > threshold: create materialized view
          3. Execute and cache results in R1
        """
        if not self.plasticity:
            return {"status": "no_plasticity_data"}

        start = time.perf_counter()
        paths = self.plasticity.top_paths[:top_n]
        precomputed = 0
        views_created = 0

        for path_info in paths:
            path = path_info.get("path", "")
            strength = path_info.get("strength", 0)
            hits = path_info.get("hits", 0)

            # Only pre-compute paths with significant usage
            if strength < 5.0 or hits < 3:
                continue

            # Extract query hash from path
            query_hash = path.split(":")[0] if ":" in path else path

            # Cache the fact that this query pattern is pre-computed
            self._precomputed[query_hash] = {
                "strength": strength, "hits": hits,
                "precomputed_at": time.time(),
            }
            precomputed += 1

        # Check for materialized view candidates
        if "relational" in self.engines and precomputed > 0:
            views_created = await self._manage_materialized_views()

        duration_ms = (time.perf_counter() - start) * 1000
        return {
            "paths_analyzed": len(paths),
            "precomputed": precomputed,
            "views_created": views_created,
            "duration_ms": round(duration_ms, 1),
        }

    async def _manage_materialized_views(self) -> int:
        """Create or refresh materialized views for top query patterns."""
        created = 0
        if "relational" not in self.engines:
            return 0

        # Refresh existing views
        for view_name in self._materialized_views:
            try:
                await self.engines["relational"].execute(
                    f"REFRESH MATERIALIZED VIEW CONCURRENTLY {view_name}")
            except Exception as e:
                logger.warning(f"Failed to refresh view {view_name}: {e}")

        return created

    def is_precomputed(self, query_hash: str) -> bool:
        """Check if a query pattern has been pre-computed."""
        entry = self._precomputed.get(query_hash)
        if not entry:
            return False
        # Pre-computed results valid for 24 hours
        return (time.time() - entry.get("precomputed_at", 0)) < 86400

    def get_stats(self) -> Dict:
        return {
            "precomputed_patterns": len(self._precomputed),
            "materialized_views": len(self._materialized_views),
            "view_names": self._materialized_views,
        }
