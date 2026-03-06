"""Cross-Engine Bridge / Corpus Callosum (DOC-018 Gap G9)

Runs a single query that spans multiple engines, merges results.
Example: FIND SIMILAR products (VectorCore) + sales history (TemporalCore) + vendor graph (GraphCore)
"""

import asyncio
import time
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("cortexdb.core.bridge")


class BridgeEngine:
    """Cross-engine query coordinator.

    Decomposes multi-engine queries into sub-queries, fans out in parallel,
    and merges results by common key (application-level JOIN).
    """

    def __init__(self, engines: Dict[str, Any] = None):
        self.engines = engines or {}
        self._query_count = 0

    async def query(self, sub_queries: List[Dict],
                    merge_key: Optional[str] = None) -> Dict:
        """Execute sub-queries across engines in parallel and merge results.

        Args:
            sub_queries: List of {engine, query, params?} dicts
            merge_key: Common field to join results on (e.g. "agent_id")

        Returns:
            {results: [...], engines_hit: [...], latency_ms: float}
        """
        start = time.perf_counter()
        self._query_count += 1

        # Fan out sub-queries in parallel
        tasks = []
        for sq in sub_queries:
            engine_name = sq.get("engine")
            if engine_name not in self.engines:
                logger.warning(f"Bridge: engine '{engine_name}' not available")
                continue
            tasks.append(self._execute_sub_query(engine_name, sq))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Collect successful results
        engine_results = {}
        engines_hit = []
        for sq, result in zip(sub_queries, results):
            engine_name = sq.get("engine")
            if isinstance(result, Exception):
                logger.error(f"Bridge sub-query failed [{engine_name}]: {result}")
                engine_results[engine_name] = {"error": str(result)}
            else:
                engine_results[engine_name] = result
                engines_hit.append(engine_name)

        # Merge results
        if merge_key and len(engines_hit) > 1:
            merged = self._merge_results(engine_results, merge_key)
        else:
            merged = engine_results

        latency_ms = (time.perf_counter() - start) * 1000
        return {"results": merged, "engines_hit": engines_hit,
                "latency_ms": round(latency_ms, 3),
                "sub_queries": len(sub_queries)}

    async def _execute_sub_query(self, engine_name: str, sq: Dict) -> Any:
        """Execute a single sub-query against an engine."""
        engine = self.engines[engine_name]
        query = sq.get("query", "")
        params = sq.get("params")

        if hasattr(engine, "execute"):
            return await engine.execute(query, params)
        elif hasattr(engine, "search_similar") and "similar" in query.lower():
            return await engine.search_similar(
                collection=sq.get("collection", "default"),
                query_text=query, limit=sq.get("limit", 10))
        elif hasattr(engine, "query"):
            return await engine.query(query, params)
        else:
            return await engine.health()

    @staticmethod
    def _merge_results(engine_results: Dict, merge_key: str) -> List[Dict]:
        """Merge results from multiple engines by common key."""
        merged_index: Dict[str, Dict] = {}

        for engine_name, data in engine_results.items():
            if isinstance(data, dict) and "error" in data:
                continue
            rows = data if isinstance(data, list) else [data] if data else []
            for row in rows:
                if not isinstance(row, dict):
                    continue
                key_val = str(row.get(merge_key, ""))
                if key_val:
                    if key_val not in merged_index:
                        merged_index[key_val] = {}
                    merged_index[key_val].update(row)
                    merged_index[key_val][f"_source_{engine_name}"] = True

        return list(merged_index.values())

    async def enrich(self, primary_results: List[Dict],
                     enrichments: List[Dict],
                     join_key: str) -> List[Dict]:
        """Enrich primary results with data from other engines.

        Example: enrich vector search results with relational metadata.
        """
        if not primary_results:
            return []

        # Collect IDs to look up
        ids = [str(r.get(join_key, "")) for r in primary_results if r.get(join_key)]
        if not ids:
            return primary_results

        # Fetch enrichment data
        for enrichment in enrichments:
            engine_name = enrichment.get("engine")
            if engine_name not in self.engines:
                continue
            try:
                # Sanitize IDs — only allow alphanumeric, hyphens, underscores
                safe_ids = [i for i in ids if all(c.isalnum() or c in '-_' for c in str(i))]
                if not safe_ids:
                    continue
                placeholders = ",".join(f"${idx+1}" for idx in range(len(safe_ids)))
                query = enrichment.get("query", "").replace("$IDS", placeholders)
                data = await self.engines[engine_name].execute(query)
                if data:
                    lookup = {str(r.get(join_key, "")): r
                              for r in data if isinstance(r, dict)}
                    for row in primary_results:
                        extra = lookup.get(str(row.get(join_key, "")), {})
                        row.update(extra)
            except Exception as e:
                logger.warning(f"Bridge enrichment from {engine_name} failed: {e}")

        return primary_results

    def get_stats(self) -> Dict:
        return {"total_bridge_queries": self._query_count,
                "available_engines": list(self.engines.keys())}
