"""Embedding Sync Pipeline — Automatic vector freshness.

When data changes in PostgreSQL, re-embeds and upserts to Qdrant.
Eliminates stale embeddings — the #1 quality issue in RAG applications.

Architecture:
  PG trigger → NOTIFY embedding_sync → Listener → Re-embed → Qdrant upsert

Supported tables (configurable):
  - agents: embed name + description
  - blocks: embed name + description
  - a2a_agent_cards: embed name + description + skills
  - customers: embed name + email (for identity matching)
  - experience_ledger: embed description

Usage:
  sync = EmbeddingSyncPipeline(engines, embedding_pipeline)
  await sync.start()  # Starts listening in background
  await sync.stop()   # Graceful shutdown
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("cortexdb.core.embedding_sync")

# Channel name used by PostgreSQL NOTIFY/LISTEN
NOTIFY_CHANNEL = "embedding_sync"

# Debounce window: accumulate changes for this long before processing
BATCH_WINDOW_MS = 500

# Maximum retry attempts for failed syncs
MAX_RETRIES = 3

# Maximum items in the retry queue before dropping oldest
MAX_RETRY_QUEUE = 1000


@dataclass
class SyncEvent:
    """A single embedding sync event from PostgreSQL NOTIFY."""
    table: str
    op: str  # INSERT, UPDATE, DELETE
    row_id: str
    tenant_id: str = ""
    retry_count: int = 0
    created_at: float = field(default_factory=time.time)


# Table-to-embedding configuration.
# text_fields: columns to concatenate for embedding text
# collection: target Qdrant collection name
# id_column: primary key column name (defaults to "id")
SYNC_CONFIG: Dict[str, Dict[str, Any]] = {
    "agents": {
        "text_fields": ["name", "description"],
        "collection": "agents",
        "id_column": "agent_id",
        "fetch_query": "SELECT * FROM agents WHERE agent_id = $1",
    },
    "blocks": {
        "text_fields": ["name", "description"],
        "collection": "blocks",
        "id_column": "block_id",
        "fetch_query": "SELECT * FROM blocks WHERE block_id = $1",
    },
    "a2a_agent_cards": {
        "text_fields": ["name", "description", "skills"],
        "collection": "agent_cards",
        "id_column": "agent_id",
        "fetch_query": "SELECT * FROM a2a_agent_cards WHERE agent_id = $1",
    },
    "customers": {
        "text_fields": ["name", "email"],
        "collection": "customers",
        "id_column": "customer_id",
        "fetch_query": "SELECT * FROM customers WHERE customer_id = $1",
    },
    "experience_ledger": {
        "text_fields": ["context_summary", "lessons_learned"],
        "collection": "experiences",
        "id_column": "experience_id",
        "fetch_query": "SELECT * FROM experience_ledger WHERE experience_id = $1",
    },
}


@dataclass
class SyncMetrics:
    """Tracks embedding sync pipeline performance."""
    syncs_total: int = 0
    syncs_failed: int = 0
    sync_latency_ms_sum: float = 0.0
    sync_latency_ms_count: int = 0
    batch_size_sum: int = 0
    batch_count: int = 0
    retries_total: int = 0
    deletes_total: int = 0

    @property
    def sync_latency_ms_avg(self) -> float:
        if self.sync_latency_ms_count == 0:
            return 0.0
        return round(self.sync_latency_ms_sum / self.sync_latency_ms_count, 2)

    @property
    def batch_size_avg(self) -> float:
        if self.batch_count == 0:
            return 0.0
        return round(self.batch_size_sum / self.batch_count, 2)

    def to_dict(self) -> Dict:
        return {
            "syncs_total": self.syncs_total,
            "syncs_failed": self.syncs_failed,
            "sync_latency_ms_avg": self.sync_latency_ms_avg,
            "batch_size_avg": self.batch_size_avg,
            "retries_total": self.retries_total,
            "deletes_total": self.deletes_total,
        }


class EmbeddingSyncPipeline:
    """Listens for PostgreSQL NOTIFY events and keeps Qdrant vectors fresh.

    When a row changes in a synced table, this pipeline:
    1. Receives the NOTIFY payload (table, op, row id, tenant_id)
    2. Batches events over a 500ms window to avoid per-row overhead
    3. Fetches the changed rows from PostgreSQL
    4. Re-embeds the text fields using EmbeddingPipeline
    5. Upserts the new vectors to Qdrant via VectorEngine

    Designed for production:
    - Batched processing to reduce embedding overhead
    - Tenant-aware collection routing
    - Retry queue for transient failures
    - Graceful shutdown with drain
    """

    def __init__(
        self,
        engines: Dict[str, Any],
        embedding_pipeline: Any,
        sync_config: Optional[Dict[str, Dict[str, Any]]] = None,
        batch_window_ms: int = BATCH_WINDOW_MS,
    ):
        self.engines = engines
        self.embedding = embedding_pipeline
        self.config = sync_config or SYNC_CONFIG
        self.batch_window_ms = batch_window_ms
        self.metrics = SyncMetrics()

        # Internal state
        self._pending_events: Dict[str, SyncEvent] = {}  # Dedup by table:id
        self._retry_queue: List[SyncEvent] = []
        self._listener_task: Optional[asyncio.Task] = None
        self._batch_task: Optional[asyncio.Task] = None
        self._retry_task: Optional[asyncio.Task] = None
        self._listen_connection: Any = None  # Dedicated asyncpg connection
        self._running = False
        self._drain_event = asyncio.Event()

    async def start(self) -> None:
        """Start the embedding sync listener and batch processor."""
        if self._running:
            logger.warning("EmbeddingSyncPipeline already running")
            return

        if "relational" not in self.engines:
            logger.error("Cannot start embedding sync: relational engine not available")
            return

        if "vector" not in self.engines:
            logger.error("Cannot start embedding sync: vector engine not available")
            return

        self._running = True
        self._drain_event.clear()

        # Start background tasks
        self._listener_task = asyncio.create_task(
            self._listen_loop(), name="embedding_sync_listener"
        )
        self._batch_task = asyncio.create_task(
            self._batch_loop(), name="embedding_sync_batcher"
        )
        self._retry_task = asyncio.create_task(
            self._retry_loop(), name="embedding_sync_retry"
        )

        logger.info(
            "EmbeddingSyncPipeline started — listening on channel '%s' "
            "for tables: %s",
            NOTIFY_CHANNEL,
            ", ".join(self.config.keys()),
        )

    async def stop(self) -> None:
        """Graceful shutdown: process remaining events, then stop."""
        if not self._running:
            return

        logger.info("EmbeddingSyncPipeline stopping — draining pending events...")
        self._running = False

        # Process any remaining pending events
        if self._pending_events:
            await self._process_batch()

        # Cancel background tasks
        for task in (self._listener_task, self._batch_task, self._retry_task):
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        # Close dedicated listener connection
        if self._listen_connection and not self._listen_connection.is_closed():
            await self._listen_connection.close()
            self._listen_connection = None

        self._drain_event.set()
        logger.info(
            "EmbeddingSyncPipeline stopped — stats: %s", self.metrics.to_dict()
        )

    async def _listen_loop(self) -> None:
        """Maintain a dedicated connection for LISTEN/NOTIFY."""
        import asyncpg

        while self._running:
            try:
                # Get the connection URL from the relational engine
                relational = self.engines["relational"]
                url = relational.url

                self._listen_connection = await asyncpg.connect(url)
                await self._listen_connection.add_listener(
                    NOTIFY_CHANNEL, self._on_notify
                )
                logger.info("LISTEN connection established on '%s'", NOTIFY_CHANNEL)

                # Keep the connection alive until shutdown
                while self._running:
                    # Periodic keepalive / check connection health
                    try:
                        await asyncio.wait_for(
                            self._listen_connection.fetchval("SELECT 1"),
                            timeout=5.0,
                        )
                    except (asyncio.TimeoutError, Exception):
                        logger.warning("LISTEN connection lost, reconnecting...")
                        break
                    await asyncio.sleep(30)

            except asyncio.CancelledError:
                return
            except Exception as e:
                logger.error("LISTEN loop error: %s — retrying in 5s", e)
                await asyncio.sleep(5)
            finally:
                if self._listen_connection and not self._listen_connection.is_closed():
                    try:
                        await self._listen_connection.remove_listener(
                            NOTIFY_CHANNEL, self._on_notify
                        )
                        await self._listen_connection.close()
                    except Exception:
                        pass
                    self._listen_connection = None

    def _on_notify(
        self,
        connection: Any,
        pid: int,
        channel: str,
        payload: str,
    ) -> None:
        """Callback invoked by asyncpg when a NOTIFY arrives.

        Parses the JSON payload and adds the event to the pending batch.
        Deduplicates by table+id so rapid updates to the same row
        only trigger one re-embed per batch window.
        """
        try:
            data = json.loads(payload)
            table = data.get("table", "")
            op = data.get("op", "")
            row_id = data.get("id", "")
            tenant_id = data.get("tenant_id", "")

            if not table or not row_id:
                logger.warning("Malformed NOTIFY payload: %s", payload)
                return

            if table not in self.config:
                logger.debug("Ignoring NOTIFY for unconfigured table: %s", table)
                return

            event = SyncEvent(
                table=table, op=op, row_id=row_id, tenant_id=tenant_id
            )

            # Dedup key: latest event for this table+row wins
            dedup_key = f"{table}:{row_id}"
            self._pending_events[dedup_key] = event

            logger.debug(
                "NOTIFY received: %s %s on %s (id=%s, tenant=%s)",
                op, table, table, row_id, tenant_id or "none",
            )
        except json.JSONDecodeError:
            logger.warning("Invalid JSON in NOTIFY payload: %s", payload)
        except Exception as e:
            logger.error("Error processing NOTIFY: %s", e)

    async def _batch_loop(self) -> None:
        """Periodically flush the pending event buffer into a batch for processing."""
        while self._running:
            try:
                await asyncio.sleep(self.batch_window_ms / 1000.0)

                if self._pending_events:
                    await self._process_batch()

            except asyncio.CancelledError:
                return
            except Exception as e:
                logger.error("Batch loop error: %s", e)

    async def _process_batch(self) -> None:
        """Process all pending events as a single batch.

        Steps:
        1. Snapshot and clear the pending buffer
        2. Group events by table for efficient fetching
        3. Fetch rows, embed text, upsert vectors
        4. Send failures to the retry queue
        """
        # Atomically swap out the pending events
        events = self._pending_events
        self._pending_events = {}

        if not events:
            return

        batch_start = time.perf_counter()
        batch_size = len(events)
        self.metrics.batch_count += 1
        self.metrics.batch_size_sum += batch_size

        logger.info("Processing embedding sync batch: %d events", batch_size)

        # Group by table for efficient batch fetching
        by_table: Dict[str, List[SyncEvent]] = {}
        for event in events.values():
            by_table.setdefault(event.table, []).append(event)

        for table, table_events in by_table.items():
            try:
                await self._sync_table_events(table, table_events)
            except Exception as e:
                logger.error(
                    "Batch processing failed for table %s: %s", table, e
                )
                # Send all events for this table to retry queue
                for event in table_events:
                    self._enqueue_retry(event)

        batch_latency = (time.perf_counter() - batch_start) * 1000
        self.metrics.sync_latency_ms_sum += batch_latency
        self.metrics.sync_latency_ms_count += 1

        logger.info(
            "Batch complete: %d events in %.1fms", batch_size, batch_latency
        )

    async def _sync_table_events(
        self, table: str, events: List[SyncEvent]
    ) -> None:
        """Sync a group of events for a single table."""
        table_config = self.config[table]
        text_fields = table_config["text_fields"]
        collection = table_config["collection"]
        fetch_query = table_config["fetch_query"]

        relational = self.engines["relational"]
        vector = self.engines["vector"]

        # Separate deletes from inserts/updates
        deletes = [e for e in events if e.op == "DELETE"]
        upserts = [e for e in events if e.op != "DELETE"]

        # Handle deletes: remove vectors from Qdrant
        if deletes:
            for event in deletes:
                target_collection = self._resolve_collection(
                    collection, event.tenant_id
                )
                try:
                    await vector.delete_vectors(
                        target_collection, [event.row_id]
                    )
                    self.metrics.deletes_total += 1
                    self.metrics.syncs_total += 1
                except Exception as e:
                    logger.warning(
                        "Delete vector failed for %s:%s — %s",
                        table, event.row_id, e,
                    )
                    self._enqueue_retry(event)
                    self.metrics.syncs_failed += 1

        # Handle inserts/updates: fetch rows, embed, upsert
        if not upserts:
            return

        # Fetch rows from PostgreSQL in batch
        rows_by_id: Dict[str, Dict] = {}
        for event in upserts:
            try:
                async with relational.pool.acquire() as conn:
                    row = await conn.fetchrow(fetch_query, event.row_id)
                if row:
                    rows_by_id[event.row_id] = dict(row)
                else:
                    # Row was deleted between NOTIFY and fetch — treat as delete
                    target_collection = self._resolve_collection(
                        collection, event.tenant_id
                    )
                    try:
                        await vector.delete_vectors(
                            target_collection, [event.row_id]
                        )
                        self.metrics.deletes_total += 1
                    except Exception:
                        pass
            except Exception as e:
                logger.warning(
                    "Fetch failed for %s:%s — %s", table, event.row_id, e
                )
                self._enqueue_retry(event)
                self.metrics.syncs_failed += 1

        if not rows_by_id:
            return

        # Build texts for embedding
        event_ids: List[str] = []
        texts: List[str] = []
        payloads: List[Dict] = []
        tenant_ids: List[str] = []

        for event in upserts:
            if event.row_id not in rows_by_id:
                continue
            row = rows_by_id[event.row_id]

            # Extract and concatenate text fields
            text_parts = []
            for f in text_fields:
                val = row.get(f)
                if val is not None:
                    # Handle list fields (e.g., skills TEXT[])
                    if isinstance(val, (list, tuple)):
                        text_parts.append(" ".join(str(v) for v in val))
                    else:
                        text_parts.append(str(val))
            text = " ".join(text_parts).strip()

            if not text:
                continue

            event_ids.append(event.row_id)
            texts.append(text)
            tenant_ids.append(event.tenant_id)

            # Build payload with useful metadata
            payload = {
                "table": table,
                "row_id": event.row_id,
                "synced_at": time.time(),
            }
            if event.tenant_id:
                payload["tenant_id"] = event.tenant_id
            # Include text fields in payload for retrieval
            for f in text_fields:
                val = row.get(f)
                if val is not None:
                    if isinstance(val, (list, tuple)):
                        payload[f] = list(val)
                    else:
                        payload[f] = str(val)
            payloads.append(payload)

        if not texts:
            return

        # Batch embed
        try:
            vectors = self.embedding.embed_batch(texts)
        except Exception as e:
            logger.error("Embedding batch failed: %s", e)
            for event in upserts:
                self._enqueue_retry(event)
                self.metrics.syncs_failed += 1
            return

        # Group upserts by target collection (different tenants go to different collections)
        by_collection: Dict[str, List[Dict]] = {}
        for i, row_id in enumerate(event_ids):
            target_collection = self._resolve_collection(
                collection, tenant_ids[i]
            )
            point = {
                "id": row_id,
                "vector": vectors[i],
                "payload": payloads[i],
            }
            by_collection.setdefault(target_collection, []).append(point)

        # Upsert to Qdrant
        for target_collection, points in by_collection.items():
            try:
                count = await vector.upsert_vectors(target_collection, points)
                self.metrics.syncs_total += count
                logger.debug(
                    "Upserted %d vectors to collection '%s'",
                    count, target_collection,
                )
            except Exception as e:
                logger.error(
                    "Qdrant upsert failed for collection '%s': %s",
                    target_collection, e,
                )
                self.metrics.syncs_failed += len(points)
                # Re-enqueue the events that correspond to these points
                for point in points:
                    failed_event = next(
                        (ev for ev in upserts if ev.row_id == point["id"]),
                        None,
                    )
                    if failed_event:
                        self._enqueue_retry(failed_event)

    def _resolve_collection(self, base_collection: str, tenant_id: str) -> str:
        """Resolve the Qdrant collection name, incorporating tenant isolation."""
        if tenant_id:
            return f"tenant_{tenant_id}_{base_collection}"
        return base_collection

    def _enqueue_retry(self, event: SyncEvent) -> None:
        """Add a failed event to the retry queue."""
        if event.retry_count >= MAX_RETRIES:
            logger.error(
                "Event exhausted retries: %s:%s (op=%s) — dropping",
                event.table, event.row_id, event.op,
            )
            self.metrics.syncs_failed += 1
            return

        event.retry_count += 1
        self.metrics.retries_total += 1

        # Enforce max retry queue size (drop oldest)
        if len(self._retry_queue) >= MAX_RETRY_QUEUE:
            dropped = self._retry_queue.pop(0)
            logger.warning(
                "Retry queue full — dropping oldest event: %s:%s",
                dropped.table, dropped.row_id,
            )

        self._retry_queue.append(event)

    async def _retry_loop(self) -> None:
        """Periodically retry failed sync events with exponential backoff."""
        while self._running:
            try:
                # Retry every 5 seconds
                await asyncio.sleep(5.0)

                if not self._retry_queue:
                    continue

                # Take up to 50 events from the retry queue
                batch = self._retry_queue[:50]
                self._retry_queue = self._retry_queue[50:]

                logger.info("Retrying %d failed sync events", len(batch))

                # Re-inject into pending events for next batch window
                for event in batch:
                    dedup_key = f"{event.table}:{event.row_id}"
                    # Only add if not already pending
                    if dedup_key not in self._pending_events:
                        self._pending_events[dedup_key] = event

            except asyncio.CancelledError:
                return
            except Exception as e:
                logger.error("Retry loop error: %s", e)

    def get_status(self) -> Dict:
        """Return current pipeline status and metrics."""
        return {
            "running": self._running,
            "pending_events": len(self._pending_events),
            "retry_queue_size": len(self._retry_queue),
            "listener_connected": (
                self._listen_connection is not None
                and not self._listen_connection.is_closed()
                if self._listen_connection
                else False
            ),
            "synced_tables": list(self.config.keys()),
            "metrics": self.metrics.to_dict(),
        }

    async def install_triggers(self) -> None:
        """Install the PostgreSQL NOTIFY triggers for all synced tables.

        This is idempotent — safe to call on every startup.
        Reads and executes the SQL from embedding_sync_triggers.sql.
        """
        import os

        sql_path = os.path.join(
            os.path.dirname(__file__), "embedding_sync_triggers.sql"
        )

        try:
            with open(sql_path, "r") as f:
                sql = f.read()
        except FileNotFoundError:
            logger.error(
                "Trigger SQL not found at %s — skipping trigger install",
                sql_path,
            )
            return

        relational = self.engines.get("relational")
        if not relational or not relational.pool:
            logger.error("Cannot install triggers: relational engine not connected")
            return

        try:
            async with relational.pool.acquire() as conn:
                await conn.execute(sql)
            logger.info("Embedding sync triggers installed successfully")
        except Exception as e:
            logger.warning("Failed to install embedding sync triggers: %s", e)
