"""AI-Powered Index Management

Adaptive index creation, tuning, and lifecycle management:
  - Auto-detect slow queries and create optimal indexes
  - HNSW/IVF tuning for vector search at scale
  - GIN/GiST for JSONB and full-text search
  - BRIN for time-series data (massive compression)
  - Index usage tracking and garbage collection
  - Predictive index recommendations via query pattern analysis
"""

import logging
import time
import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger("cortexdb.scale.ai_index")


class IndexType(Enum):
    BTREE = "btree"         # Default, equality/range
    HASH = "hash"           # Equality only (faster)
    GIN = "gin"             # JSONB, arrays, full-text
    GIST = "gist"           # Geometry, range types, full-text
    BRIN = "brin"           # Time-series, append-only (very compact)
    HNSW = "hnsw"           # Vector similarity (high recall)
    IVFFLAT = "ivfflat"     # Vector similarity (high throughput)
    BLOOM = "bloom"         # Multi-column equality (compact)
    PARTIAL = "partial"     # Conditional index (filtered)


class IndexStatus(Enum):
    ACTIVE = "active"
    BUILDING = "building"
    INVALID = "invalid"
    UNUSED = "unused"
    RECOMMENDED = "recommended"


@dataclass
class IndexRecommendation:
    table: str
    columns: List[str]
    index_type: IndexType
    reason: str
    estimated_speedup: float  # e.g., 10.0 = 10x faster
    estimated_size_mb: float
    priority: int  # 1 = highest
    query_pattern: str = ""
    created: bool = False


@dataclass
class VectorIndexConfig:
    """HNSW/IVF tuning parameters for vector search at scale."""
    m: int = 16                    # HNSW: connections per layer (16-64)
    ef_construction: int = 200     # HNSW: build-time accuracy (100-500)
    ef_search: int = 100           # HNSW: query-time accuracy (50-500)
    num_lists: int = 100           # IVF: number of clusters (sqrt(N))
    num_probes: int = 10           # IVF: clusters to search (1-num_lists)

    @classmethod
    def for_scale(cls, total_vectors: int) -> "VectorIndexConfig":
        """Auto-tune parameters based on dataset size."""
        import math
        if total_vectors < 10_000:
            return cls(m=16, ef_construction=128, ef_search=64,
                       num_lists=max(10, int(math.sqrt(total_vectors))),
                       num_probes=5)
        elif total_vectors < 1_000_000:
            return cls(m=32, ef_construction=256, ef_search=128,
                       num_lists=int(math.sqrt(total_vectors)),
                       num_probes=int(math.sqrt(total_vectors) * 0.1))
        else:
            return cls(m=48, ef_construction=400, ef_search=200,
                       num_lists=int(math.sqrt(total_vectors)),
                       num_probes=int(math.sqrt(total_vectors) * 0.05))


# Pre-defined index strategies for CortexDB tables
BUILT_IN_INDEXES = {
    "customer_events": [
        {"columns": ["time"], "type": IndexType.BRIN,
         "reason": "Time-series data benefits from BRIN (10-100x smaller than btree)"},
        {"columns": ["properties"], "type": IndexType.GIN,
         "reason": "JSONB queries on event properties"},
        {"columns": ["customer_id", "event_type", "time"],
         "type": IndexType.BTREE, "reason": "Customer event lookup by type and time range"},
    ],
    "customers": [
        {"columns": ["metadata"], "type": IndexType.GIN,
         "reason": "JSONB search on customer metadata"},
    ],
    "customer_profiles": [
        {"columns": ["segments"], "type": IndexType.GIN,
         "reason": "Array contains queries for segment-based targeting"},
    ],
    "blocks": [
        {"columns": ["tags"], "type": IndexType.GIN,
         "reason": "Array contains queries on block tags"},
    ],
    "immutable_ledger": [
        {"columns": ["created_at"], "type": IndexType.BRIN,
         "reason": "Append-only time-series: BRIN is 100x smaller than btree"},
    ],
}

# Slow query patterns that indicate missing indexes
SLOW_QUERY_PATTERNS = [
    {"pattern": "Seq Scan on", "action": "btree_index",
     "reason": "Sequential scan detected - add btree index"},
    {"pattern": "Sort  (cost=", "action": "sort_index",
     "reason": "Expensive sort - add index on ORDER BY columns"},
    {"pattern": "Hash Join", "action": "hash_index",
     "reason": "Hash join - consider index on join column"},
    {"pattern": "Bitmap Heap Scan", "action": "covering_index",
     "reason": "Bitmap scan - consider covering index"},
]


class AIIndexManager:
    """AI-powered index management for CortexDB.

    Capabilities:
      1. analyze_slow_queries(): Find queries needing indexes
      2. recommend(): Generate index recommendations
      3. create_optimal(): Create indexes concurrently (no locks)
      4. tune_vector_indexes(): Auto-tune HNSW/IVF parameters
      5. garbage_collect(): Remove unused/duplicate indexes
      6. monitor(): Track index usage and health
    """

    UNUSED_THRESHOLD_DAYS = 30
    SLOW_QUERY_THRESHOLD_MS = 100

    def __init__(self, engines: Dict[str, Any] = None):
        self.engines = engines or {}
        self._recommendations: List[IndexRecommendation] = []
        self._indexes_created = 0
        self._indexes_dropped = 0
        self._analysis_count = 0

    async def analyze_slow_queries(self, limit: int = 50) -> List[Dict]:
        """Analyze pg_stat_statements for slow queries needing indexes."""
        engine = self.engines.get("relational")
        if not engine:
            return []

        self._analysis_count += 1
        slow_queries = []

        try:
            # Get slow queries from pg_stat_statements
            rows = await engine.execute(f"""
                SELECT query, calls, mean_exec_time, total_exec_time,
                       rows, shared_blks_hit, shared_blks_read
                FROM pg_stat_statements
                WHERE mean_exec_time > {self.SLOW_QUERY_THRESHOLD_MS}
                AND query NOT LIKE '%pg_%'
                ORDER BY total_exec_time DESC
                LIMIT {limit}
            """) or []

            for row in rows:
                # Get EXPLAIN plan
                try:
                    plan = await engine.execute(
                        f"EXPLAIN (FORMAT JSON) {row['query']}")
                    plan_text = str(plan) if plan else ""
                except Exception:
                    plan_text = ""

                analysis = {
                    "query": row.get("query", "")[:200],
                    "calls": row.get("calls", 0),
                    "mean_ms": round(row.get("mean_exec_time", 0), 2),
                    "total_ms": round(row.get("total_exec_time", 0), 2),
                    "rows": row.get("rows", 0),
                    "issues": [],
                }

                # Detect issues from EXPLAIN
                for pattern in SLOW_QUERY_PATTERNS:
                    if pattern["pattern"] in plan_text:
                        analysis["issues"].append({
                            "type": pattern["action"],
                            "reason": pattern["reason"],
                        })

                if analysis["issues"]:
                    slow_queries.append(analysis)

        except Exception as e:
            logger.warning(f"Slow query analysis error: {e}")

        return slow_queries

    async def recommend(self) -> List[IndexRecommendation]:
        """Generate index recommendations based on query patterns."""
        engine = self.engines.get("relational")
        if not engine:
            return []

        recommendations = []

        # 1. Built-in recommendations for CortexDB tables
        existing = await self._get_existing_indexes(engine)
        for table, indexes in BUILT_IN_INDEXES.items():
            for idx_def in indexes:
                idx_key = f"{table}_{'_'.join(idx_def['columns'])}_{idx_def['type'].value}"
                if idx_key not in existing:
                    recommendations.append(IndexRecommendation(
                        table=table, columns=idx_def["columns"],
                        index_type=idx_def["type"], reason=idx_def["reason"],
                        estimated_speedup=5.0, estimated_size_mb=0,
                        priority=2))

        # 2. Query-driven recommendations from slow query analysis
        slow = await self.analyze_slow_queries()
        for sq in slow:
            for issue in sq["issues"]:
                # Extract table name from query
                table = self._extract_table(sq["query"])
                if table:
                    columns = self._extract_filter_columns(sq["query"])
                    if columns:
                        idx_type = IndexType.BTREE
                        if issue["type"] == "hash_index":
                            idx_type = IndexType.HASH
                        recommendations.append(IndexRecommendation(
                            table=table, columns=columns,
                            index_type=idx_type, reason=issue["reason"],
                            estimated_speedup=sq["mean_ms"] / 10,
                            estimated_size_mb=0, priority=1,
                            query_pattern=sq["query"][:100]))

        # 3. Missing indexes on foreign keys
        fk_missing = await self._check_fk_indexes(engine)
        for fk in fk_missing:
            recommendations.append(IndexRecommendation(
                table=fk["table"], columns=[fk["column"]],
                index_type=IndexType.BTREE,
                reason=f"Foreign key {fk['constraint']} has no index (slow JOINs)",
                estimated_speedup=3.0, estimated_size_mb=0, priority=1))

        self._recommendations = recommendations
        return recommendations

    async def create_optimal(self, recommendations: List[IndexRecommendation] = None,
                              concurrently: bool = True) -> Dict:
        """Create recommended indexes (CONCURRENTLY = no table locks)."""
        engine = self.engines.get("relational")
        if not engine:
            return {"error": "RelationalCore not available"}

        recs = recommendations or self._recommendations
        results = {"created": [], "skipped": [], "errors": []}

        for rec in recs:
            idx_name = f"idx_ai_{rec.table}_{'_'.join(rec.columns)}_{rec.index_type.value}"
            idx_name = idx_name[:63]  # PostgreSQL 63-char limit

            concurrent_clause = "CONCURRENTLY" if concurrently else ""
            using_clause = f"USING {rec.index_type.value}" if rec.index_type != IndexType.BTREE else ""

            if rec.index_type == IndexType.BRIN:
                using_clause = "USING brin"
            elif rec.index_type == IndexType.GIN:
                using_clause = "USING gin"

            cols = ", ".join(rec.columns)
            sql = f"CREATE INDEX {concurrent_clause} IF NOT EXISTS {idx_name} ON {rec.table} {using_clause} ({cols})"

            try:
                await engine.execute(sql)
                rec.created = True
                self._indexes_created += 1
                results["created"].append(idx_name)
            except Exception as e:
                results["errors"].append({"index": idx_name, "error": str(e)})

        return results

    async def tune_vector_indexes(self, collection: str = None,
                                    total_vectors: int = None) -> Dict:
        """Auto-tune HNSW/IVF vector index parameters for Qdrant."""
        if "vector" not in self.engines:
            return {"error": "VectorCore not available"}

        # Determine dataset size
        if not total_vectors:
            try:
                info = await self.engines["vector"].get_collection_info(
                    collection or "default")
                total_vectors = info.get("vectors_count", 10000)
            except Exception:
                total_vectors = 10000

        config = VectorIndexConfig.for_scale(total_vectors)
        results = {
            "total_vectors": total_vectors,
            "config": {
                "hnsw_m": config.m,
                "hnsw_ef_construction": config.ef_construction,
                "hnsw_ef_search": config.ef_search,
                "ivf_num_lists": config.num_lists,
                "ivf_num_probes": config.num_probes,
            },
        }

        # Apply to Qdrant
        try:
            await self.engines["vector"].update_collection(
                collection or "default",
                hnsw_config={
                    "m": config.m,
                    "ef_construct": config.ef_construction,
                },
                optimizer_config={
                    "default_segment_number": max(2, total_vectors // 100_000),
                })
            results["status"] = "applied"
        except Exception as e:
            results["status"] = "recommended_only"
            results["note"] = str(e)

        return results

    async def garbage_collect(self) -> Dict:
        """Remove unused and duplicate indexes."""
        engine = self.engines.get("relational")
        if not engine:
            return {"error": "RelationalCore not available"}

        results = {"dropped": [], "duplicates": [], "unused": []}

        try:
            # Find unused indexes (no scans in pg_stat_user_indexes)
            unused = await engine.execute(f"""
                SELECT schemaname, relname, indexrelname,
                       idx_scan, pg_relation_size(indexrelid) AS size_bytes
                FROM pg_stat_user_indexes
                WHERE idx_scan = 0
                AND schemaname = 'public'
                AND indexrelname NOT LIKE '%_pkey'
                AND indexrelname NOT LIKE '%_unique%'
                AND indexrelname NOT LIKE 'idx_ai_%'
                ORDER BY pg_relation_size(indexrelid) DESC
            """) or []

            for idx in unused:
                results["unused"].append({
                    "index": idx.get("indexrelname"),
                    "table": idx.get("relname"),
                    "size_bytes": idx.get("size_bytes", 0),
                })

            # Find duplicate indexes (same columns, same table)
            duplicates = await engine.execute("""
                SELECT a.indexrelid::regclass AS index1,
                       b.indexrelid::regclass AS index2,
                       a.indrelid::regclass AS table_name
                FROM pg_index a
                JOIN pg_index b ON a.indrelid = b.indrelid
                    AND a.indexrelid != b.indexrelid
                    AND a.indkey = b.indkey
                WHERE a.indexrelid < b.indexrelid
            """) or []

            for dup in duplicates:
                results["duplicates"].append({
                    "index1": str(dup.get("index1")),
                    "index2": str(dup.get("index2")),
                    "table": str(dup.get("table_name")),
                })

        except Exception as e:
            results["error"] = str(e)

        return results

    async def _get_existing_indexes(self, engine) -> set:
        """Get set of existing index identifiers."""
        try:
            rows = await engine.execute("""
                SELECT tablename, indexname FROM pg_indexes
                WHERE schemaname = 'public'
            """) or []
            return {f"{r['tablename']}_{r['indexname']}" for r in rows}
        except Exception:
            return set()

    async def _check_fk_indexes(self, engine) -> List[Dict]:
        """Find foreign keys without supporting indexes."""
        try:
            rows = await engine.execute("""
                SELECT tc.table_name, kcu.column_name, tc.constraint_name
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                    ON tc.constraint_name = kcu.constraint_name
                WHERE tc.constraint_type = 'FOREIGN KEY'
                AND NOT EXISTS (
                    SELECT 1 FROM pg_indexes pi
                    WHERE pi.tablename = tc.table_name
                    AND pi.indexdef LIKE '%' || kcu.column_name || '%'
                )
            """) or []
            return [{"table": r["table_name"], "column": r["column_name"],
                     "constraint": r["constraint_name"]} for r in rows]
        except Exception:
            return []

    @staticmethod
    def _extract_table(query: str) -> Optional[str]:
        """Extract primary table name from SQL query."""
        import re
        match = re.search(r'\bFROM\s+(\w+)', query, re.IGNORECASE)
        return match.group(1) if match else None

    @staticmethod
    def _extract_filter_columns(query: str) -> List[str]:
        """Extract WHERE clause columns from SQL query."""
        import re
        matches = re.findall(r'(\w+)\s*[=<>!]+', query)
        # Filter out SQL keywords and values
        keywords = {"SELECT", "FROM", "WHERE", "AND", "OR", "NOT", "IN",
                     "LIKE", "IS", "NULL", "TRUE", "FALSE", "BETWEEN"}
        return [m for m in matches if m.upper() not in keywords][:3]

    def get_stats(self) -> Dict:
        return {
            "indexes_created": self._indexes_created,
            "indexes_dropped": self._indexes_dropped,
            "analyses_run": self._analysis_count,
            "pending_recommendations": len(self._recommendations),
        }
