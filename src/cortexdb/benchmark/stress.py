"""
Stress Test Engine — Simulates production load patterns against CortexDB.

Patterns: spike, soak, burst, ramp-up, mixed workload.
Measures system behavior under sustained high load.
"""

import asyncio
import time
import random
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional
from enum import Enum

logger = logging.getLogger("cortexdb.stress")


class StressPattern(str, Enum):
    SPIKE = "spike"           # Sudden 10x traffic burst
    SOAK = "soak"             # Sustained load over time
    RAMP = "ramp"             # Gradual increase to peak
    BURST = "burst"           # Repeated short bursts
    MIXED = "mixed"           # Concurrent read/write workload


@dataclass
class StressConfig:
    pattern: StressPattern = StressPattern.RAMP
    duration_sec: int = 60
    base_rps: int = 100           # Requests per second baseline
    peak_rps: int = 1000          # Peak requests per second
    burst_duration_sec: int = 5   # For BURST pattern
    burst_interval_sec: int = 15  # Pause between bursts
    ramp_steps: int = 10          # For RAMP pattern
    read_write_ratio: float = 0.8 # For MIXED pattern (80% reads)
    max_concurrency: int = 200
    timeout_ms: int = 5000


@dataclass
class StressMetrics:
    pattern: str = ""
    duration_sec: float = 0.0
    total_requests: int = 0
    successful: int = 0
    failed: int = 0
    timeouts: int = 0
    peak_rps_achieved: float = 0.0
    avg_rps: float = 0.0
    latencies_ms: List[float] = field(default_factory=list)
    p50_ms: float = 0.0
    p95_ms: float = 0.0
    p99_ms: float = 0.0
    max_ms: float = 0.0
    error_rate_pct: float = 0.0
    rps_timeline: List[Dict] = field(default_factory=list)

    def compute(self):
        if self.latencies_ms:
            s = sorted(self.latencies_ms)
            self.p50_ms = s[int(len(s) * 0.50)]
            self.p95_ms = s[int(len(s) * 0.95)]
            self.p99_ms = s[min(int(len(s) * 0.99), len(s) - 1)]
            self.max_ms = s[-1]
        if self.total_requests > 0:
            self.error_rate_pct = round(self.failed / self.total_requests * 100, 2)
        if self.duration_sec > 0:
            self.avg_rps = round(self.total_requests / self.duration_sec, 1)

    def to_dict(self) -> Dict:
        return {
            "pattern": self.pattern,
            "duration_sec": round(self.duration_sec, 1),
            "total_requests": self.total_requests,
            "successful": self.successful,
            "failed": self.failed,
            "timeouts": self.timeouts,
            "peak_rps_achieved": round(self.peak_rps_achieved, 1),
            "avg_rps": self.avg_rps,
            "latency_ms": {
                "p50": round(self.p50_ms, 2),
                "p95": round(self.p95_ms, 2),
                "p99": round(self.p99_ms, 2),
                "max": round(self.max_ms, 2),
            },
            "error_rate_pct": self.error_rate_pct,
            "rps_timeline": self.rps_timeline[-60:],  # Last 60 data points
        }


class StressTestEngine:
    """Generates controlled stress load against CortexDB."""

    def __init__(self):
        self._running = False
        self._metrics = StressMetrics()

    async def run(
        self,
        config: StressConfig,
        read_func: Callable,
        write_func: Optional[Callable] = None,
    ) -> StressMetrics:
        """Execute a stress test with the given pattern."""
        self._running = True
        self._metrics = StressMetrics(pattern=config.pattern.value)

        handler = {
            StressPattern.SPIKE: self._run_spike,
            StressPattern.SOAK: self._run_soak,
            StressPattern.RAMP: self._run_ramp,
            StressPattern.BURST: self._run_burst,
            StressPattern.MIXED: self._run_mixed,
        }[config.pattern]

        t0 = time.perf_counter()
        await handler(config, read_func, write_func)
        self._metrics.duration_sec = time.perf_counter() - t0
        self._metrics.compute()
        self._running = False
        return self._metrics

    def stop(self):
        self._running = False

    def is_running(self) -> bool:
        return self._running

    async def _fire_requests(
        self, func: Callable, count: int, concurrency: int, timeout_ms: int
    ) -> List[float]:
        """Fire N requests with bounded concurrency, return latencies."""
        sem = asyncio.Semaphore(concurrency)
        latencies = []

        async def _one():
            async with sem:
                start = time.perf_counter()
                try:
                    await asyncio.wait_for(func(), timeout=timeout_ms / 1000)
                    elapsed = (time.perf_counter() - start) * 1000
                    latencies.append(elapsed)
                    self._metrics.successful += 1
                except asyncio.TimeoutError:
                    self._metrics.timeouts += 1
                    self._metrics.failed += 1
                except Exception:
                    self._metrics.failed += 1
                self._metrics.total_requests += 1

        tasks = [asyncio.create_task(_one()) for _ in range(count)]
        await asyncio.gather(*tasks)
        return latencies

    async def _record_interval(self, interval_start: float, latencies: List[float]):
        """Record RPS for a time interval."""
        elapsed = time.perf_counter() - interval_start
        rps = len(latencies) / elapsed if elapsed > 0 else 0
        self._metrics.rps_timeline.append({
            "time_sec": round(time.perf_counter() - interval_start, 1),
            "rps": round(rps, 1),
            "count": len(latencies),
        })
        if rps > self._metrics.peak_rps_achieved:
            self._metrics.peak_rps_achieved = rps
        self._metrics.latencies_ms.extend(latencies)

    # ── Stress Patterns ──

    async def _run_spike(self, config: StressConfig, read_func, write_func):
        """Sudden 10x traffic spike in the middle of the test."""
        total_intervals = max(config.duration_sec, 6)
        spike_start = total_intervals // 3
        spike_end = spike_start + total_intervals // 3

        for i in range(total_intervals):
            if not self._running:
                break
            rps = config.peak_rps if spike_start <= i < spike_end else config.base_rps
            t0 = time.perf_counter()
            lats = await self._fire_requests(
                read_func, rps, config.max_concurrency, config.timeout_ms
            )
            await self._record_interval(t0, lats)
            # Pace to ~1 second intervals
            elapsed = time.perf_counter() - t0
            if elapsed < 1.0:
                await asyncio.sleep(1.0 - elapsed)

    async def _run_soak(self, config: StressConfig, read_func, write_func):
        """Sustained constant load for the full duration."""
        for _ in range(config.duration_sec):
            if not self._running:
                break
            t0 = time.perf_counter()
            lats = await self._fire_requests(
                read_func, config.base_rps, config.max_concurrency, config.timeout_ms
            )
            await self._record_interval(t0, lats)
            elapsed = time.perf_counter() - t0
            if elapsed < 1.0:
                await asyncio.sleep(1.0 - elapsed)

    async def _run_ramp(self, config: StressConfig, read_func, write_func):
        """Gradually increase load from base to peak."""
        step_duration = max(config.duration_sec // config.ramp_steps, 1)
        rps_increment = (config.peak_rps - config.base_rps) / config.ramp_steps

        for step in range(config.ramp_steps):
            if not self._running:
                break
            current_rps = int(config.base_rps + rps_increment * step)
            logger.info(f"[STRESS] Ramp step {step+1}/{config.ramp_steps}: {current_rps} RPS")

            for _ in range(step_duration):
                if not self._running:
                    break
                t0 = time.perf_counter()
                lats = await self._fire_requests(
                    read_func, current_rps, config.max_concurrency, config.timeout_ms
                )
                await self._record_interval(t0, lats)
                elapsed = time.perf_counter() - t0
                if elapsed < 1.0:
                    await asyncio.sleep(1.0 - elapsed)

    async def _run_burst(self, config: StressConfig, read_func, write_func):
        """Repeated short bursts of peak traffic with pauses."""
        end_time = time.perf_counter() + config.duration_sec
        while self._running and time.perf_counter() < end_time:
            # Burst phase
            for _ in range(config.burst_duration_sec):
                if not self._running:
                    break
                t0 = time.perf_counter()
                lats = await self._fire_requests(
                    read_func, config.peak_rps, config.max_concurrency, config.timeout_ms
                )
                await self._record_interval(t0, lats)
                elapsed = time.perf_counter() - t0
                if elapsed < 1.0:
                    await asyncio.sleep(1.0 - elapsed)
            # Cool-down
            await asyncio.sleep(min(config.burst_interval_sec, end_time - time.perf_counter()))

    async def _run_mixed(self, config: StressConfig, read_func, write_func):
        """Concurrent read + write workload at configured ratio."""
        wfunc = write_func or read_func

        for _ in range(config.duration_sec):
            if not self._running:
                break
            read_count = int(config.base_rps * config.read_write_ratio)
            write_count = config.base_rps - read_count

            t0 = time.perf_counter()
            read_lats = await self._fire_requests(
                read_func, read_count, config.max_concurrency, config.timeout_ms
            )
            write_lats = await self._fire_requests(
                wfunc, write_count, config.max_concurrency, config.timeout_ms
            )
            await self._record_interval(t0, read_lats + write_lats)
            elapsed = time.perf_counter() - t0
            if elapsed < 1.0:
                await asyncio.sleep(1.0 - elapsed)
