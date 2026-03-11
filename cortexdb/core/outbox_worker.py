"""
OutboxWorker - Transactional Outbox Pattern for CortexDB Write Fan-Out.

Polls the write_outbox table for pending entries and dispatches them to
the appropriate async engine. Survives crashes because all pending work
is persisted in PostgreSQL rather than held in memory.
"""

import asyncio
import json
import time
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger("cortexdb.outbox")


class OutboxWorker:
    """Background worker that processes the write_outbox table.

    Constructor args:
        pool: asyncpg connection pool (shared with relational engine)
        engines: dict of engine name -> engine instance
    """

    POLL_INTERVAL = 1.0       # seconds between polls
    BATCH_SIZE = 50           # max entries claimed per poll
    CLEANUP_INTERVAL = 600.0  # 10 minutes between cleanup runs
    CLEANUP_AGE_HOURS = 24    # delete completed entries older than this
    STUCK_TIMEOUT_SECONDS = 300  # 5 min: reset stuck 'processing' entries
    RECOVER_STUCK_INTERVAL = 60.0  # seconds between stuck-recovery runs

    def __init__(self, pool: Any, engines: Dict[str, Any]):
        self.pool = pool
        self.engines = engines
        self._poll_task: Optional[asyncio.Task] = None
        self._cleanup_task: Optional[asyncio.Task] = None
        self._recover_task: Optional[asyncio.Task] = None
        self._running = False
        self._processed_total = 0
        self._failed_total = 0
        self._latency_sum = 0.0
        self._latency_count = 0
        self._metrics_cache: Optional[Dict] = None
        self._metrics_cache_ts: float = 0.0

    async def start(self):
        """Start the background polling and cleanup tasks."""
        if self._running:
            return
        self._running = True
        self._poll_task = asyncio.create_task(self._poll_loop())
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        self._recover_task = asyncio.create_task(self._recover_loop())
        logger.info("OutboxWorker started")

    async def stop(self, timeout: float = 30.0):
        """Stop the worker and wait for in-flight processing to finish."""
        if not self._running:
            return
        self._running = False

        tasks = []
        if self._poll_task and not self._poll_task.done():
            self._poll_task.cancel()
            tasks.append(self._poll_task)
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            tasks.append(self._cleanup_task)
        if self._recover_task and not self._recover_task.done():
            self._recover_task.cancel()
            tasks.append(self._recover_task)

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        logger.info("OutboxWorker stopped")

    async def _poll_loop(self):
        """Main polling loop: claim and process pending outbox entries."""
        while self._running:
            try:
                await self._process_batch()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"OutboxWorker poll error: {e}")
            try:
                await asyncio.sleep(self.POLL_INTERVAL)
            except asyncio.CancelledError:
                break

    async def _cleanup_loop(self):
        """Periodic cleanup of completed entries older than CLEANUP_AGE_HOURS."""
        while self._running:
            try:
                await asyncio.sleep(self.CLEANUP_INTERVAL)
            except asyncio.CancelledError:
                break
            try:
                await self.cleanup()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"OutboxWorker cleanup error: {e}")

    async def _recover_loop(self):
        """Periodic recovery of entries stuck in 'processing' state."""
        while self._running:
            try:
                await asyncio.sleep(self.RECOVER_STUCK_INTERVAL)
            except asyncio.CancelledError:
                break
            try:
                await self._recover_stuck()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"OutboxWorker recover-stuck error: {e}")

    async def _recover_stuck(self):
        """Reset entries stuck in 'processing' for longer than STUCK_TIMEOUT_SECONDS.

        This handles the case where a worker crashed mid-dispatch, leaving
        entries permanently in 'processing' state with no one to finish them.
        """
        async with self.pool.acquire() as conn:
            result = await conn.execute("""
                UPDATE write_outbox
                SET status = 'pending',
                    error_message = 'recovered from stuck processing state'
                WHERE status = 'processing'
                  AND processed_at IS NULL
                  AND created_at < NOW() - ($1 || ' seconds')::interval
            """, str(self.STUCK_TIMEOUT_SECONDS))
            if result and result != "UPDATE 0":
                logger.warning(f"OutboxWorker recovered stuck entries: {result}")

    async def _process_batch(self):
        """Claim a batch of pending/retryable entries and dispatch them."""
        # Claim entries atomically, then release the connection
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                UPDATE write_outbox
                SET status = 'processing'
                WHERE id IN (
                    SELECT id FROM write_outbox
                    WHERE status IN ('pending', 'failed')
                      AND next_retry_at <= NOW()
                      AND retry_count < max_retries
                    ORDER BY id
                    LIMIT $1
                    FOR UPDATE SKIP LOCKED
                )
                RETURNING *
            """, self.BATCH_SIZE)

        # Process dispatches individually, acquiring a new connection only for
        # the status update after each dispatch (avoids holding a connection
        # during slow engine.write() calls).
        for row in rows:
            async with self.pool.acquire() as conn:
                await self._dispatch(conn, row)

    async def _dispatch(self, conn: Any, row: Any):
        """Dispatch a single outbox entry to its target engine."""
        entry_id = row["id"]
        target_engine = row["target_engine"]
        data_type = row["data_type"]
        payload = json.loads(row["payload"]) if isinstance(row["payload"], str) else dict(row["payload"])
        actor = row["actor"]
        retry_count = row["retry_count"]
        max_retries = row["max_retries"]
        created_at = row["created_at"]

        engine = self.engines.get(target_engine)
        if engine is None:
            # Engine not available — mark as failed with a clear message
            await self._mark_failed(
                conn, entry_id, retry_count, max_retries,
                f"Engine '{target_engine}' not available"
            )
            return

        start = time.perf_counter()
        try:
            await engine.write(data_type, payload, actor)
            elapsed = time.perf_counter() - start

            # Mark completed
            await conn.execute("""
                UPDATE write_outbox
                SET status = 'completed', processed_at = NOW()
                WHERE id = $1
            """, entry_id)

            self._processed_total += 1
            self._latency_sum += elapsed
            self._latency_count += 1

        except Exception as e:
            elapsed = time.perf_counter() - start
            logger.warning(
                f"Outbox dispatch to {target_engine} failed (id={entry_id}, "
                f"attempt={retry_count + 1}): {e}"
            )
            await self._mark_failed(
                conn, entry_id, retry_count, max_retries, str(e)
            )
            self._failed_total += 1

    async def _mark_failed(self, conn: Any, entry_id: int,
                           retry_count: int, max_retries: int,
                           error_message: str):
        """Increment retry count and set next_retry_at with exponential backoff,
        or mark as dead_letter if retries exhausted."""
        new_retry = retry_count + 1
        if new_retry >= max_retries:
            # Exhausted retries — move to dead letter
            await conn.execute("""
                UPDATE write_outbox
                SET status = 'dead_letter',
                    retry_count = $2,
                    error_message = $3,
                    processed_at = NOW()
                WHERE id = $1
            """, entry_id, new_retry, error_message)
        else:
            # Schedule retry with exponential backoff: 2^retry_count seconds
            backoff_seconds = 2 ** new_retry
            await conn.execute("""
                UPDATE write_outbox
                SET status = 'failed',
                    retry_count = $2,
                    error_message = $3,
                    next_retry_at = NOW() + ($4 || ' seconds')::interval
                WHERE id = $1
            """, entry_id, new_retry, error_message, str(backoff_seconds))

    async def cleanup(self):
        """Delete completed entries older than CLEANUP_AGE_HOURS."""
        async with self.pool.acquire() as conn:
            deleted = await conn.execute("""
                DELETE FROM write_outbox
                WHERE status = 'completed'
                  AND processed_at < NOW() - ($1 || ' hours')::interval
            """, str(self.CLEANUP_AGE_HOURS))
            logger.debug(f"Outbox cleanup: {deleted}")

    METRICS_CACHE_TTL = 5.0  # seconds

    async def get_metrics(self) -> Dict:
        """Return current outbox metrics by querying the table.
        Results are cached for METRICS_CACHE_TTL seconds to avoid hammering PG."""
        now = time.monotonic()
        if self._metrics_cache is not None and (now - self._metrics_cache_ts) < self.METRICS_CACHE_TTL:
            return self._metrics_cache

        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT status, COUNT(*) as cnt
                FROM write_outbox
                GROUP BY status
            """)
            counts = {row["status"]: row["cnt"] for row in rows}

        avg_latency = (
            self._latency_sum / self._latency_count
            if self._latency_count > 0
            else 0.0
        )

        result = {
            "pending_count": counts.get("pending", 0),
            "processing_count": counts.get("processing", 0),
            "completed_count": counts.get("completed", 0),
            "failed_count": counts.get("failed", 0),
            "dead_letter_count": counts.get("dead_letter", 0),
            "processed_total": self._processed_total,
            "failed_total": self._failed_total,
            "avg_latency_ms": round(avg_latency * 1000, 3),
        }
        self._metrics_cache = result
        self._metrics_cache_ts = now
        return result

    async def wait_for_drain(self, timeout: float = 30.0):
        """Wait until all pending/failed entries are processed or timeout."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            async with self.pool.acquire() as conn:
                count = await conn.fetchval("""
                    SELECT COUNT(*) FROM write_outbox
                    WHERE status IN ('pending', 'processing', 'failed')
                """)
            if count == 0:
                return
            await asyncio.sleep(0.5)
        logger.warning(f"Outbox drain timeout after {timeout}s")
