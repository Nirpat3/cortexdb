"""
CortexDB Connection Pool Manager

Centralized asyncpg connection pool with:
- Configurable pool sizing via environment variables
- Async context manager for connection acquisition
- Health checks, stats, retry logic, graceful shutdown
- Event logging for pool lifecycle
"""

import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional

try:
    import asyncpg
except ImportError:
    asyncpg = None

logger = logging.getLogger("cortexdb.pool")


class ConnectionPoolManager:
    """Centralized connection pool manager for CortexDB.

    Reads configuration from environment variables:
        DB_POOL_MIN_SIZE                        - Minimum pool size (default: 5)
        DB_POOL_MAX_SIZE                        - Maximum pool size (default: 20)
        DB_POOL_MAX_QUERIES                     - Max queries per connection before recycling (default: 50000)
        DB_POOL_MAX_INACTIVE_CONNECTION_LIFETIME - Seconds before idle connections are closed (default: 300)
    """

    def __init__(
        self,
        dsn: Optional[str] = None,
        min_size: Optional[int] = None,
        max_size: Optional[int] = None,
        max_queries: Optional[int] = None,
        max_inactive_connection_lifetime: Optional[float] = None,
    ):
        if asyncpg is None:
            raise ImportError("asyncpg is required: pip install asyncpg")

        self._dsn = dsn or os.getenv(
            "RELATIONAL_CORE_URL",
            "postgresql://cortex:cortex_secret@localhost:5432/cortexdb",
        )
        self._min_size = min_size or int(os.getenv("DB_POOL_MIN_SIZE", "5"))
        self._max_size = max_size or int(os.getenv("DB_POOL_MAX_SIZE", "20"))
        self._max_queries = max_queries or int(os.getenv("DB_POOL_MAX_QUERIES", "50000"))
        self._max_inactive_lifetime = max_inactive_connection_lifetime or float(
            os.getenv("DB_POOL_MAX_INACTIVE_CONNECTION_LIFETIME", "300.0")
        )

        self._pool: Optional[asyncpg.Pool] = None
        self._created_at: Optional[float] = None
        self._acquire_count: int = 0
        self._error_count: int = 0
        self._retry_attempts: int = 3
        self._retry_base_delay: float = 0.5  # seconds, exponential backoff base

        # Auto-scaling state
        self._auto_scale_task: Optional[asyncio.Task] = None
        self._scale_check_interval: float = 30.0  # seconds
        self._high_util_count: int = 0  # consecutive high utilization checks
        self._low_util_count: int = 0  # consecutive low utilization checks
        self._max_pool_ceiling: int = 100
        self._original_max_size: int = self._max_size

    async def initialize(self) -> None:
        """Create the connection pool with retry logic.

        Retries up to 3 times with exponential backoff on failure.
        """
        last_error: Optional[Exception] = None

        for attempt in range(1, self._retry_attempts + 1):
            try:
                logger.info(
                    "Creating connection pool (attempt %d/%d): "
                    "min=%d, max=%d, max_queries=%d, max_inactive=%.0fs",
                    attempt,
                    self._retry_attempts,
                    self._min_size,
                    self._max_size,
                    self._max_queries,
                    self._max_inactive_lifetime,
                )
                self._pool = await asyncpg.create_pool(
                    dsn=self._dsn,
                    min_size=self._min_size,
                    max_size=self._max_size,
                    max_queries=self._max_queries,
                    max_inactive_connection_lifetime=self._max_inactive_lifetime,
                    command_timeout=30,
                )
                self._created_at = time.time()
                logger.info(
                    "Connection pool created successfully (%d connections ready)",
                    self._pool.get_size(),
                )
                return
            except Exception as exc:
                last_error = exc
                self._error_count += 1
                if attempt < self._retry_attempts:
                    delay = self._retry_base_delay * (2 ** (attempt - 1))
                    logger.warning(
                        "Pool creation failed (attempt %d/%d): %s. Retrying in %.1fs...",
                        attempt,
                        self._retry_attempts,
                        exc,
                        delay,
                    )
                    await asyncio.sleep(delay)

        logger.error(
            "Failed to create connection pool after %d attempts", self._retry_attempts
        )
        raise last_error  # type: ignore[misc]

    @asynccontextmanager
    async def acquire(self):
        """Acquire a connection from the pool as an async context manager.

        Usage::

            async with pool_manager.acquire() as conn:
                rows = await conn.fetch("SELECT 1")

        Raises RuntimeError if the pool has not been initialized.
        Logs a warning when the pool is near exhaustion.
        """
        if self._pool is None:
            raise RuntimeError(
                "Connection pool not initialized. Call await pool.initialize() first."
            )

        self._acquire_count += 1

        # Warn if pool is near exhaustion (>80% used)
        free = self._pool.get_idle_size()
        total = self._pool.get_size()
        if total > 0 and free == 0:
            logger.warning(
                "Pool exhaustion warning: 0 idle connections out of %d total "
                "(%d max). Queries may block.",
                total,
                self._max_size,
            )

        try:
            async with self._pool.acquire() as conn:
                yield conn
        except Exception as exc:
            self._error_count += 1
            logger.error("Error acquiring/using connection: %s", exc)
            raise

    async def health_check(self) -> Dict[str, Any]:
        """Validate a connection from the pool by executing a simple query.

        Returns a dict with status and latency information.
        """
        if self._pool is None:
            return {"status": "not_initialized", "healthy": False}

        start = time.perf_counter()
        try:
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow("SELECT 1 AS ok, NOW() AS server_time")
                latency_ms = (time.perf_counter() - start) * 1000
                return {
                    "status": "healthy",
                    "healthy": True,
                    "latency_ms": round(latency_ms, 2),
                    "server_time": str(row["server_time"]),
                }
        except Exception as exc:
            self._error_count += 1
            latency_ms = (time.perf_counter() - start) * 1000
            logger.error("Health check failed: %s", exc)
            return {
                "status": "unhealthy",
                "healthy": False,
                "error": str(exc),
                "latency_ms": round(latency_ms, 2),
            }

    def stats(self) -> Dict[str, Any]:
        """Return current pool statistics.

        Returns pool size, free/used connections, lifetime counters.
        """
        if self._pool is None:
            return {
                "initialized": False,
                "pool_size": 0,
                "free_connections": 0,
                "used_connections": 0,
            }

        pool_size = self._pool.get_size()
        free = self._pool.get_idle_size()
        used = pool_size - free

        return {
            "initialized": True,
            "pool_size": pool_size,
            "pool_min_size": self._min_size,
            "pool_max_size": self._max_size,
            "free_connections": free,
            "used_connections": used,
            "utilization_pct": round((used / max(pool_size, 1)) * 100, 1),
            "total_acquires": self._acquire_count,
            "total_errors": self._error_count,
            "uptime_seconds": round(time.time() - self._created_at, 1)
            if self._created_at
            else 0,
            "auto_scaling": {
                "enabled": self._auto_scale_task is not None
                and not self._auto_scale_task.done(),
                "original_max_size": self._original_max_size,
                "max_pool_ceiling": self._max_pool_ceiling,
                "high_util_streak": self._high_util_count,
                "low_util_streak": self._low_util_count,
            },
        }

    async def start_auto_scaling(self) -> None:
        """Start the background auto-scaling loop.

        The loop checks pool utilization every ``_scale_check_interval`` seconds
        and adjusts pool size when sustained high or low utilization is detected.
        """
        if self._auto_scale_task is not None and not self._auto_scale_task.done():
            logger.warning("Auto-scaling is already running.")
            return

        self._auto_scale_task = asyncio.create_task(self._auto_scale_loop())
        logger.info(
            "Auto-scaling started (check every %.0fs, ceiling=%d)",
            self._scale_check_interval,
            self._max_pool_ceiling,
        )

    async def stop_auto_scaling(self) -> None:
        """Cancel the background auto-scaling loop."""
        if self._auto_scale_task is None or self._auto_scale_task.done():
            return

        self._auto_scale_task.cancel()
        try:
            await self._auto_scale_task
        except asyncio.CancelledError:
            pass
        self._auto_scale_task = None
        self._high_util_count = 0
        self._low_util_count = 0
        logger.info("Auto-scaling stopped.")

    async def _auto_scale_loop(self) -> None:
        """Background loop that monitors utilization and triggers pool resizing.

        Scale-up: >80% utilization for 3 consecutive checks → increase max_size by 25%.
        Scale-down: <20% utilization for 5 consecutive checks → decrease max_size by 25%.
        """
        try:
            while True:
                await asyncio.sleep(self._scale_check_interval)

                if self._pool is None:
                    continue

                pool_size = self._pool.get_size()
                if pool_size == 0:
                    continue

                idle = self._pool.get_idle_size()
                used = pool_size - idle
                utilization = (used / pool_size) * 100

                # --- Scale up check ---
                if utilization > 80:
                    self._high_util_count += 1
                    self._low_util_count = 0
                    logger.debug(
                        "High utilization %.1f%% (count %d/3)",
                        utilization,
                        self._high_util_count,
                    )

                    if self._high_util_count >= 3:
                        new_size = min(
                            int(self._max_size * 1.25),
                            self._max_pool_ceiling,
                        )
                        if new_size > self._max_size:
                            logger.info(
                                "Scaling up pool: %d → %d (utilization %.1f%% for 3 checks)",
                                self._max_size,
                                new_size,
                                utilization,
                            )
                            await self._swap_pool(new_size)
                        else:
                            logger.info(
                                "Pool at ceiling (%d), cannot scale up further.",
                                self._max_pool_ceiling,
                            )
                        self._high_util_count = 0

                # --- Scale down check ---
                elif utilization < 20:
                    self._low_util_count += 1
                    self._high_util_count = 0
                    logger.debug(
                        "Low utilization %.1f%% (count %d/5)",
                        utilization,
                        self._low_util_count,
                    )

                    if self._low_util_count >= 5:
                        new_size = max(
                            int(self._max_size * 0.75),
                            self._original_max_size,
                        )
                        if new_size < self._max_size:
                            logger.info(
                                "Scaling down pool: %d → %d (utilization %.1f%% for 5 checks)",
                                self._max_size,
                                new_size,
                                utilization,
                            )
                            await self._swap_pool(new_size)
                        else:
                            logger.debug(
                                "Pool already at original size (%d), skip scale-down.",
                                self._original_max_size,
                            )
                        self._low_util_count = 0

                else:
                    # Utilization in normal range — reset counters
                    self._high_util_count = 0
                    self._low_util_count = 0

        except asyncio.CancelledError:
            logger.debug("Auto-scale loop cancelled.")
            raise

    async def _swap_pool(self, new_max_size: int) -> None:
        """Create a new pool with *new_max_size* and atomically swap it in.

        The old pool is closed with a 10-second timeout; in-flight queries on
        already-acquired connections finish against the old pool while new
        ``acquire()`` calls use the replacement.
        """
        old_pool = self._pool
        old_max = self._max_size

        try:
            new_pool = await asyncpg.create_pool(
                dsn=self._dsn,
                min_size=self._min_size,
                max_size=new_max_size,
                max_queries=self._max_queries,
                max_inactive_connection_lifetime=self._max_inactive_lifetime,
                command_timeout=30,
            )
        except Exception as exc:
            self._error_count += 1
            logger.error("Failed to create replacement pool (max=%d): %s", new_max_size, exc)
            return

        # Atomic swap
        self._pool = new_pool
        self._max_size = new_max_size
        logger.info(
            "Pool swapped: max_size %d → %d (%d connections ready)",
            old_max,
            new_max_size,
            new_pool.get_size(),
        )

        # Drain old pool
        if old_pool is not None:
            try:
                await asyncio.wait_for(old_pool.close(), timeout=10.0)
                logger.debug("Old pool closed gracefully.")
            except asyncio.TimeoutError:
                logger.warning("Old pool close timed out, terminating.")
                old_pool.terminate()

    async def close(self, timeout: float = 10.0) -> None:
        """Gracefully shut down the pool.

        Waits up to ``timeout`` seconds for in-flight connections to be
        released, then forcefully closes remaining connections.
        """
        await self.stop_auto_scaling()

        if self._pool is None:
            return

        logger.info(
            "Shutting down connection pool (timeout=%.1fs, %d connections)...",
            timeout,
            self._pool.get_size(),
        )

        try:
            await asyncio.wait_for(self._pool.close(), timeout=timeout)
            logger.info("Connection pool closed gracefully.")
        except asyncio.TimeoutError:
            logger.warning(
                "Pool close timed out after %.1fs. Terminating remaining connections.",
                timeout,
            )
            self._pool.terminate()
            logger.info("Connection pool terminated.")
        finally:
            self._pool = None
            logger.info("Connection pool shutdown complete.")

    @property
    def is_initialized(self) -> bool:
        return self._pool is not None

    @property
    def pool(self) -> Optional["asyncpg.Pool"]:
        """Direct access to the underlying asyncpg pool (for advanced use)."""
        return self._pool


# Module-level singleton for convenience
_default_pool: Optional[ConnectionPoolManager] = None


async def get_pool(dsn: Optional[str] = None) -> ConnectionPoolManager:
    """Get or create the default singleton pool manager.

    Initializes the pool on first call. Subsequent calls return the same instance.
    """
    global _default_pool
    if _default_pool is None or not _default_pool.is_initialized:
        _default_pool = ConnectionPoolManager(dsn=dsn)
        await _default_pool.initialize()
    return _default_pool


async def close_pool() -> None:
    """Close the default singleton pool."""
    global _default_pool
    if _default_pool is not None:
        await _default_pool.close()
        _default_pool = None
