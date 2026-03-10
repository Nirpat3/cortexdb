"""Fast Data Rendering Pipeline

High-performance query result delivery:
  - Server-side cursors for streaming large result sets
  - Response compression (gzip, zstd, lz4)
  - Materialized view management for hot queries
  - Pagination with cursor-based keyset pagination
  - Columnar projections (return only needed fields)
  - Result format negotiation (JSON, MessagePack, Arrow, CSV)
"""

import logging
import time
import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, AsyncIterator

logger = logging.getLogger("cortexdb.scale.rendering")


class RenderFormat(Enum):
    JSON = "json"               # Default, human-readable
    JSON_LINES = "jsonl"        # Streaming line-delimited JSON
    MSGPACK = "msgpack"         # Binary, 30-50% smaller than JSON
    CSV = "csv"                 # Tabular export
    ARROW = "arrow"             # Apache Arrow columnar (analytics)


class CompressionType(Enum):
    NONE = "none"
    GZIP = "gzip"
    ZSTD = "zstd"
    LZ4 = "lz4"


@dataclass
class RenderConfig:
    format: RenderFormat = RenderFormat.JSON
    compression: CompressionType = CompressionType.NONE
    page_size: int = 100
    max_page_size: int = 10000
    stream_chunk_size: int = 1000  # Rows per streaming chunk
    projections: List[str] = field(default_factory=list)  # Column subset
    cursor: Optional[str] = None   # Keyset pagination cursor
    include_metadata: bool = True


@dataclass
class RenderResult:
    data: Any = None
    format: str = "json"
    compressed: bool = False
    original_size: int = 0
    rendered_size: int = 0
    compression_ratio: float = 1.0
    page_info: Dict = field(default_factory=dict)
    render_ms: float = 0


@dataclass
class MaterializedViewDef:
    name: str
    query: str
    refresh_interval: int = 3600  # Seconds
    last_refresh: float = 0
    row_count: int = 0
    size_bytes: int = 0
    auto_refresh: bool = True


# Pre-defined materialized views for CortexDB hot queries
CORTEX_MATERIALIZED_VIEWS = {
    "mv_customer_summary": {
        "query": """
            SELECT c.customer_id, c.canonical_name, c.canonical_email,
                   cp.rfm_segment, cp.health_score, cp.churn_probability,
                   cp.monetary_90d, cp.frequency_90d, cp.recency_days,
                   cp.segments, c.tenant_id
            FROM customers c
            LEFT JOIN customer_profiles cp ON c.customer_id = cp.customer_id
            WHERE c.status = 'active'
        """,
        "refresh_interval": 900,  # 15 min
        "indexes": ["tenant_id", "rfm_segment", "health_score"],
    },
    "mv_churn_risk_dashboard": {
        "query": """
            SELECT customer_id, canonical_name, churn_probability,
                   health_score, rfm_segment, recency_days,
                   monetary_90d, frequency_90d, tenant_id
            FROM customers c
            JOIN customer_profiles cp USING (customer_id)
            WHERE cp.churn_probability > 0.5
            ORDER BY cp.churn_probability DESC
        """,
        "refresh_interval": 1800,  # 30 min
        "indexes": ["tenant_id", "churn_probability"],
    },
    "mv_event_hourly": {
        "query": """
            SELECT time_bucket('1 hour', time) AS hour,
                   event_type, COUNT(*) AS event_count,
                   COUNT(DISTINCT customer_id) AS unique_customers,
                   COALESCE(SUM(amount), 0) AS total_revenue,
                   tenant_id
            FROM customer_events
            WHERE time > NOW() - INTERVAL '7 days'
            GROUP BY hour, event_type, tenant_id
        """,
        "refresh_interval": 300,  # 5 min
        "indexes": ["tenant_id", "hour"],
    },
    "mv_segment_analytics": {
        "query": """
            SELECT unnest(segments) AS segment,
                   COUNT(*) AS customer_count,
                   AVG(health_score) AS avg_health,
                   AVG(churn_probability) AS avg_churn,
                   SUM(monetary_90d) AS total_revenue,
                   AVG(monetary_90d) AS avg_revenue,
                   tenant_id
            FROM customer_profiles
            GROUP BY segment, tenant_id
        """,
        "refresh_interval": 3600,  # 1 hour
        "indexes": ["tenant_id", "segment"],
    },
}


class DataRenderer:
    """High-performance data rendering pipeline.

    Features:
      - Keyset pagination (cursor-based, no OFFSET performance cliff)
      - Server-side streaming for large result sets
      - Automatic compression for responses > 1KB
      - Materialized view management and auto-refresh
      - Column projection (only return requested fields)
    """

    AUTO_COMPRESS_THRESHOLD = 1024  # Bytes

    def __init__(self, engines: Dict[str, Any] = None):
        self.engines = engines or {}
        self._views: Dict[str, MaterializedViewDef] = {}
        self._render_count = 0
        self._bytes_rendered = 0
        self._bytes_saved_compression = 0

    async def render(self, data: Any, config: RenderConfig = None) -> RenderResult:
        """Render query results with format, compression, and pagination."""
        start = time.perf_counter()
        config = config or RenderConfig()
        self._render_count += 1

        result = RenderResult(format=config.format.value)

        # Apply column projections
        if config.projections and isinstance(data, list):
            data = self._project_columns(data, config.projections)

        # Apply keyset pagination
        if isinstance(data, list):
            data, page_info = self._paginate(data, config)
            result.page_info = page_info

        # Format conversion
        rendered = self._format_data(data, config.format)
        result.original_size = len(rendered) if isinstance(rendered, (str, bytes)) else 0

        # Compression
        if (config.compression != CompressionType.NONE or
                (result.original_size > self.AUTO_COMPRESS_THRESHOLD and
                 config.compression == CompressionType.NONE)):
            compressed, comp_type = self._compress(rendered, config.compression)
            if len(compressed) < result.original_size:
                rendered = compressed
                result.compressed = True
                result.compression_ratio = round(
                    len(compressed) / max(result.original_size, 1), 3)
                self._bytes_saved_compression += (result.original_size - len(compressed))

        result.data = rendered if isinstance(rendered, (dict, list)) else data
        result.rendered_size = len(rendered) if isinstance(rendered, (str, bytes)) else 0
        result.render_ms = (time.perf_counter() - start) * 1000
        self._bytes_rendered += result.rendered_size

        return result

    def _project_columns(self, rows: List[Dict], columns: List[str]) -> List[Dict]:
        """Return only requested columns from result rows."""
        if not rows or not columns:
            return rows
        return [{k: row.get(k) for k in columns if k in row} for row in rows]

    def _paginate(self, data: List, config: RenderConfig) -> tuple:
        """Keyset pagination - no OFFSET performance cliff."""
        page_size = min(config.page_size, config.max_page_size)
        total = len(data)

        if config.cursor:
            # Find cursor position
            cursor_idx = 0
            for i, row in enumerate(data):
                row_cursor = self._row_cursor(row)
                if row_cursor == config.cursor:
                    cursor_idx = i + 1
                    break
            data = data[cursor_idx:cursor_idx + page_size]
        else:
            data = data[:page_size]

        # Generate next cursor
        next_cursor = None
        if data and len(data) == page_size:
            next_cursor = self._row_cursor(data[-1])

        page_info = {
            "page_size": page_size,
            "returned": len(data),
            "total": total,
            "has_more": next_cursor is not None,
            "next_cursor": next_cursor,
        }
        return data, page_info

    @staticmethod
    def _row_cursor(row) -> str:
        """Generate cursor from row (uses id or first field)."""
        if isinstance(row, dict):
            for key in ("id", "customer_id", "block_id", "agent_id",
                        "event_id", "entry_id", "task_id"):
                if key in row:
                    return str(row[key])
            return hashlib.md5(json.dumps(row, default=str).encode()).hexdigest()[:16]
        return str(row)

    def _format_data(self, data: Any, fmt: RenderFormat) -> Any:
        """Convert data to requested format."""
        if fmt == RenderFormat.JSON:
            return data  # FastAPI handles JSON serialization

        elif fmt == RenderFormat.JSON_LINES:
            if isinstance(data, list):
                return "\n".join(json.dumps(row, default=str) for row in data)
            return json.dumps(data, default=str)

        elif fmt == RenderFormat.CSV:
            if isinstance(data, list) and data and isinstance(data[0], dict):
                headers = list(data[0].keys())
                lines = [",".join(headers)]
                for row in data:
                    lines.append(",".join(
                        str(row.get(h, "")).replace(",", ";") for h in headers))
                return "\n".join(lines)
            return str(data)

        elif fmt == RenderFormat.MSGPACK:
            try:
                import msgpack
                return msgpack.packb(data, default=str)
            except ImportError:
                return data

        elif fmt == RenderFormat.ARROW:
            try:
                import pyarrow as pa
                import pyarrow.ipc as ipc
                if isinstance(data, list) and data:
                    table = pa.Table.from_pylist(data)
                    sink = pa.BufferOutputStream()
                    writer = ipc.new_stream(sink, table.schema)
                    writer.write_table(table)
                    writer.close()
                    return sink.getvalue().to_pybytes()
            except ImportError:
                pass
            return data

        return data

    @staticmethod
    def _compress(data: Any, comp_type: CompressionType) -> tuple:
        """Compress rendered data."""
        if isinstance(data, str):
            data = data.encode("utf-8")
        elif not isinstance(data, bytes):
            data = json.dumps(data, default=str).encode("utf-8")

        if comp_type == CompressionType.GZIP or comp_type == CompressionType.NONE:
            import gzip
            return gzip.compress(data), "gzip"
        elif comp_type == CompressionType.ZSTD:
            try:
                import zstandard
                cctx = zstandard.ZstdCompressor(level=3)
                return cctx.compress(data), "zstd"
            except ImportError:
                import gzip
                return gzip.compress(data), "gzip"
        elif comp_type == CompressionType.LZ4:
            try:
                import lz4.frame
                return lz4.frame.compress(data), "lz4"
            except ImportError:
                import gzip
                return gzip.compress(data), "gzip"

        return data, "none"

    # -- Materialized View Management --

    async def setup_materialized_views(self) -> Dict:
        """Create all CortexDB materialized views for fast rendering."""
        engine = self.engines.get("relational")
        if not engine:
            return {"error": "RelationalCore not available"}

        results = {"created": [], "errors": []}

        for view_name, view_def in CORTEX_MATERIALIZED_VIEWS.items():
            try:
                await engine.execute(
                    f"CREATE MATERIALIZED VIEW IF NOT EXISTS {view_name} AS "
                    f"{view_def['query']}")

                # Create indexes on the materialized view
                for idx_col in view_def.get("indexes", []):
                    await engine.execute(
                        f"CREATE INDEX IF NOT EXISTS idx_{view_name}_{idx_col} "
                        f"ON {view_name} ({idx_col})")

                self._views[view_name] = MaterializedViewDef(
                    name=view_name, query=view_def["query"],
                    refresh_interval=view_def["refresh_interval"])
                results["created"].append(view_name)
            except Exception as e:
                results["errors"].append({"view": view_name, "error": str(e)})

        return results

    async def refresh_views(self, force: bool = False) -> Dict:
        """Refresh stale materialized views (CONCURRENTLY = no locks)."""
        engine = self.engines.get("relational")
        if not engine:
            return {"error": "RelationalCore not available"}

        results = {"refreshed": [], "skipped": []}
        now = time.time()

        for name, view in self._views.items():
            if not force and (now - view.last_refresh) < view.refresh_interval:
                results["skipped"].append(name)
                continue

            try:
                await engine.execute(
                    f"REFRESH MATERIALIZED VIEW CONCURRENTLY {name}")
                view.last_refresh = now

                # Update row count
                # Validate view name against whitelist (prevents SQL injection)
                if name not in self._views:
                    continue
                count = await engine.execute(
                    f"SELECT COUNT(*) as cnt FROM {name}")  # Safe: name from trusted whitelist
                if count:
                    view.row_count = count[0].get("cnt", 0)

                results["refreshed"].append(name)
            except Exception as e:
                # CONCURRENTLY requires unique index; fall back to blocking refresh
                try:
                    await engine.execute(
                        f"REFRESH MATERIALIZED VIEW {name}")
                    view.last_refresh = now
                    results["refreshed"].append(name)
                except Exception as e2:
                    results["skipped"].append({"view": name, "error": str(e2)})

        return results

    async def get_view_stats(self) -> List[Dict]:
        """Get materialized view statistics."""
        engine = self.engines.get("relational")
        stats = []

        for name, view in self._views.items():
            info = {
                "name": name,
                "refresh_interval": view.refresh_interval,
                "last_refresh": view.last_refresh,
                "row_count": view.row_count,
                "auto_refresh": view.auto_refresh,
                "stale": time.time() - view.last_refresh > view.refresh_interval,
            }

            if engine:
                try:
                    size = await engine.execute(
                        f"SELECT pg_total_relation_size('{name}') AS size_bytes")
                    if size:
                        info["size_bytes"] = size[0].get("size_bytes", 0)
                except Exception:
                    pass

            stats.append(info)

        return stats

    def get_stats(self) -> Dict:
        return {
            "renders": self._render_count,
            "bytes_rendered": self._bytes_rendered,
            "bytes_saved_compression": self._bytes_saved_compression,
            "materialized_views": len(self._views),
            "compression_savings_pct": round(
                self._bytes_saved_compression /
                max(self._bytes_rendered, 1) * 100, 1),
        }
