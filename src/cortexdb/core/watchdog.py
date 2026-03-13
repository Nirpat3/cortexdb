"""
CortexDB Process Watchdog — Self-Healing Monitor.

Background asyncio task that checks every 10s:
- Event loop latency (warn if >500ms)
- Memory usage (>80% → GC + log, >90% → purge R0)
- Engine circuit breaker states
- OutboxWorker task health
"""

import asyncio
import gc
import logging
import time
from typing import Any, Dict, Optional

try:
    import psutil
except ImportError:
    psutil = None

logger = logging.getLogger("cortexdb.watchdog")


class Watchdog:
    """Process-level health watchdog for CortexDB."""

    CHECK_INTERVAL = 10.0         # seconds between checks
    LOOP_LATENCY_WARN_MS = 500    # warn if event loop blocks >500ms
    MEMORY_WARN_PCT = 80          # log warning at 80% memory
    MEMORY_CRITICAL_PCT = 90      # purge R0 cache at 90%

    def __init__(self, db: Any = None, outbox_worker: Any = None,
                 circuits: Any = None):
        self._db = db
        self._outbox_worker = outbox_worker
        self._circuits = circuits
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._last_check: Optional[float] = None
        self._checks_total = 0
        self._warnings_total = 0
        self._gc_forced_total = 0
        self._r0_purges_total = 0
        self._loop_latency_ms: float = 0.0
        self._memory_pct: float = 0.0

    async def start(self):
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._check_loop())
        logger.info("Watchdog started (interval=%ds)", self.CHECK_INTERVAL)

    async def stop(self):
        if not self._running:
            return
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Watchdog stopped")

    async def _check_loop(self):
        while self._running:
            try:
                await self._run_checks()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Watchdog check error: {e}")
            try:
                await asyncio.sleep(self.CHECK_INTERVAL)
            except asyncio.CancelledError:
                break

    async def _run_checks(self):
        self._checks_total += 1
        self._last_check = time.time()

        # 1. Event loop latency
        await self._check_loop_latency()

        # 2. Memory usage
        self._check_memory()

        # 3. Circuit breaker states
        self._check_circuits()

        # 4. OutboxWorker health
        self._check_outbox()

    async def _check_loop_latency(self):
        """Measure event loop responsiveness by scheduling a callback."""
        start = time.perf_counter()
        await asyncio.sleep(0)  # Yield to event loop
        latency_ms = (time.perf_counter() - start) * 1000
        self._loop_latency_ms = latency_ms

        if latency_ms > self.LOOP_LATENCY_WARN_MS:
            self._warnings_total += 1
            logger.warning(
                "Event loop latency: %.1fms (threshold: %dms). "
                "Possible blocking operation.",
                latency_ms, self.LOOP_LATENCY_WARN_MS
            )

    def _check_memory(self):
        """Check process memory usage via psutil."""
        if psutil is None:
            return

        process = psutil.Process()
        mem_info = process.memory_info()
        total_mem = psutil.virtual_memory().total
        pct = (mem_info.rss / total_mem) * 100 if total_mem > 0 else 0
        self._memory_pct = pct

        if pct > self.MEMORY_CRITICAL_PCT:
            self._warnings_total += 1
            logger.warning(
                "Memory CRITICAL: %.1f%% (%.0fMB RSS). Forcing GC + R0 purge.",
                pct, mem_info.rss / 1024 / 1024
            )
            gc.collect()
            self._gc_forced_total += 1
            # Purge R0 cache
            if self._db and self._db.read_cascade:
                self._db.read_cascade._r0_cache.clear()
                self._r0_purges_total += 1
                logger.info("R0 cache purged due to memory pressure")

        elif pct > self.MEMORY_WARN_PCT:
            self._warnings_total += 1
            logger.warning(
                "Memory high: %.1f%% (%.0fMB RSS). Running GC.",
                pct, mem_info.rss / 1024 / 1024
            )
            gc.collect()
            self._gc_forced_total += 1

    def _check_circuits(self):
        """Check circuit breaker states."""
        if not self._circuits:
            return

        try:
            states = self._circuits.get_all_states()
            open_circuits = [name for name, state in states.items()
                             if state.get("state") == "open"]
            if open_circuits:
                self._warnings_total += 1
                logger.warning("Open circuit breakers: %s", open_circuits)
        except Exception as e:
            logger.debug(f"Circuit breaker check error: {e}")

    def _check_outbox(self):
        """Check OutboxWorker task health."""
        if not self._outbox_worker:
            return

        try:
            health = self._outbox_worker.task_health
            dead_tasks = [name for name, status in health.items()
                          if status == "dead" and name != "restarts_total"]
            if dead_tasks:
                self._warnings_total += 1
                logger.warning("OutboxWorker dead tasks: %s (supervisor will restart)",
                               dead_tasks)
        except Exception as e:
            logger.debug(f"OutboxWorker health check error: {e}")

    def get_status(self) -> Dict:
        """Return watchdog status for /health/watchdog endpoint."""
        return {
            "running": self._running,
            "checks_total": self._checks_total,
            "warnings_total": self._warnings_total,
            "gc_forced_total": self._gc_forced_total,
            "r0_purges_total": self._r0_purges_total,
            "last_check": self._last_check,
            "loop_latency_ms": round(self._loop_latency_ms, 2),
            "memory_pct": round(self._memory_pct, 1),
            "outbox_health": (self._outbox_worker.task_health
                              if self._outbox_worker else None),
            "psutil_available": psutil is not None,
        }
