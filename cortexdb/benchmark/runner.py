"""
Benchmark Runner — Executes performance scenarios against CortexDB engines.

Measures latency (p50/p95/p99), throughput (ops/sec), and resource usage
for each engine and composite operations (read cascade, write fan-out).
"""

import time
import asyncio
import statistics
import uuid
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional
from enum import Enum

logger = logging.getLogger("cortexdb.benchmark")


class BenchmarkStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class BenchmarkResult:
    name: str
    status: BenchmarkStatus = BenchmarkStatus.PENDING
    ops_total: int = 0
    ops_success: int = 0
    ops_failed: int = 0
    duration_sec: float = 0.0
    throughput_ops: float = 0.0
    latencies_ms: List[float] = field(default_factory=list)
    p50_ms: float = 0.0
    p95_ms: float = 0.0
    p99_ms: float = 0.0
    min_ms: float = 0.0
    max_ms: float = 0.0
    mean_ms: float = 0.0
    errors: List[str] = field(default_factory=list)

    def compute_stats(self):
        if not self.latencies_ms:
            return
        sorted_lat = sorted(self.latencies_ms)
        self.min_ms = sorted_lat[0]
        self.max_ms = sorted_lat[-1]
        self.mean_ms = statistics.mean(sorted_lat)
        self.p50_ms = self._percentile(sorted_lat, 50)
        self.p95_ms = self._percentile(sorted_lat, 95)
        self.p99_ms = self._percentile(sorted_lat, 99)
        if self.duration_sec > 0:
            self.throughput_ops = self.ops_success / self.duration_sec

    def _percentile(self, data: List[float], pct: int) -> float:
        idx = int(len(data) * pct / 100)
        return data[min(idx, len(data) - 1)]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status.value,
            "ops_total": self.ops_total,
            "ops_success": self.ops_success,
            "ops_failed": self.ops_failed,
            "duration_sec": round(self.duration_sec, 3),
            "throughput_ops_sec": round(self.throughput_ops, 1),
            "latency_ms": {
                "min": round(self.min_ms, 3),
                "p50": round(self.p50_ms, 3),
                "p95": round(self.p95_ms, 3),
                "p99": round(self.p99_ms, 3),
                "max": round(self.max_ms, 3),
                "mean": round(self.mean_ms, 3),
            },
            "error_count": len(self.errors),
            "errors": self.errors[:10],
        }


class BenchmarkRunner:
    """Runs benchmark scenarios against a live CortexDB instance."""

    def __init__(self, db=None, engines: Dict[str, Any] = None):
        self.db = db
        self.engines = engines or {}
        self._results: Dict[str, BenchmarkResult] = {}
        self._running = False

    async def run_scenario(
        self,
        name: str,
        func: Callable,
        iterations: int = 1000,
        concurrency: int = 10,
        warmup: int = 50,
    ) -> BenchmarkResult:
        """Run a single benchmark scenario with controlled concurrency."""
        result = BenchmarkResult(name=name)
        result.status = BenchmarkStatus.RUNNING
        self._results[name] = result

        # Warmup phase
        for _ in range(warmup):
            try:
                await func()
            except Exception:
                pass

        # Benchmark phase
        sem = asyncio.Semaphore(concurrency)
        latencies = []
        errors = []
        ops_success = 0
        ops_failed = 0

        async def _run_one():
            nonlocal ops_success, ops_failed
            async with sem:
                start = time.perf_counter()
                try:
                    await func()
                    elapsed = (time.perf_counter() - start) * 1000
                    latencies.append(elapsed)
                    ops_success += 1
                except Exception as e:
                    elapsed = (time.perf_counter() - start) * 1000
                    latencies.append(elapsed)
                    ops_failed += 1
                    errors.append(f"{type(e).__name__}: {str(e)[:100]}")

        t0 = time.perf_counter()
        tasks = [asyncio.create_task(_run_one()) for _ in range(iterations)]
        await asyncio.gather(*tasks)
        duration = time.perf_counter() - t0

        result.ops_total = iterations
        result.ops_success = ops_success
        result.ops_failed = ops_failed
        result.duration_sec = duration
        result.latencies_ms = latencies
        result.errors = errors
        result.compute_stats()
        result.status = BenchmarkStatus.COMPLETED
        return result

    async def run_suite(self, scenarios: List[Dict], concurrency: int = 10) -> Dict:
        """Run a full benchmark suite."""
        self._running = True
        results = []
        for scenario in scenarios:
            if not self._running:
                break
            r = await self.run_scenario(
                name=scenario["name"],
                func=scenario["func"],
                iterations=scenario.get("iterations", 1000),
                concurrency=scenario.get("concurrency", concurrency),
                warmup=scenario.get("warmup", 50),
            )
            results.append(r)
            logger.info(
                f"[BENCH] {r.name}: {r.throughput_ops:.0f} ops/s, "
                f"p50={r.p50_ms:.1f}ms, p99={r.p99_ms:.1f}ms"
            )
        self._running = False

        return {
            "suite_results": [r.to_dict() for r in results],
            "summary": {
                "total_scenarios": len(results),
                "total_ops": sum(r.ops_total for r in results),
                "total_duration_sec": round(sum(r.duration_sec for r in results), 2),
            },
        }

    def stop(self):
        self._running = False

    def get_results(self) -> Dict:
        return {k: v.to_dict() for k, v in self._results.items()}
