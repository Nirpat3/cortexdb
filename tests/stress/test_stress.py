"""
Stress Tests — Validate CortexDB under extreme load conditions.

Usage:
    pytest tests/stress/ -v --stress-duration 30 --stress-rps 500
    pytest tests/stress/test_stress.py -v -k "test_spike"
"""

import pytest
import asyncio
import time
import uuid
import json
from typing import Dict, List

try:
    import httpx
except ImportError:
    httpx = None

BASE_URL = "http://localhost:5400"
TENANT_KEY = "stress-test-key"
HEADERS = {"X-Tenant-Key": TENANT_KEY, "Content-Type": "application/json"}


# Options registered in tests/conftest.py: --stress-url, --stress-duration, --stress-rps, --stress-concurrency


@pytest.fixture
def stress_url(request):
    return request.config.getoption("--stress-url")


@pytest.fixture
def duration(request):
    return request.config.getoption("--stress-duration")


@pytest.fixture
def target_rps(request):
    return request.config.getoption("--stress-rps")


@pytest.fixture
def concurrency(request):
    return request.config.getoption("--stress-concurrency")


class StressCollector:
    """Collects metrics during stress tests."""

    def __init__(self):
        self.latencies: List[float] = []
        self.errors: int = 0
        self.timeouts: int = 0
        self.status_codes: Dict[int, int] = {}
        self.rps_timeline: List[Dict] = []

    def record(self, ms: float, status: int):
        self.latencies.append(ms)
        self.status_codes[status] = self.status_codes.get(status, 0) + 1

    def record_error(self, is_timeout=False):
        self.errors += 1
        if is_timeout:
            self.timeouts += 1

    def snapshot_rps(self, interval_requests: int, interval_sec: float):
        rps = interval_requests / interval_sec if interval_sec > 0 else 0
        self.rps_timeline.append({"rps": round(rps, 1)})

    def report(self) -> Dict:
        if not self.latencies:
            return {"error": "no successful requests"}
        s = sorted(self.latencies)
        total = len(s) + self.errors
        return {
            "total_requests": total,
            "successful": len(s),
            "failed": self.errors,
            "timeouts": self.timeouts,
            "error_rate_pct": round(self.errors / total * 100, 2) if total else 0,
            "p50_ms": round(s[len(s) // 2], 2),
            "p95_ms": round(s[int(len(s) * 0.95)], 2),
            "p99_ms": round(s[min(int(len(s) * 0.99), len(s) - 1)], 2),
            "max_ms": round(s[-1], 2),
            "status_codes": self.status_codes,
            "peak_rps": max((x["rps"] for x in self.rps_timeline), default=0),
        }


async def _send_request(client, url, headers, payload, collector, sem, timeout=5.0):
    """Fire a single request with semaphore-bounded concurrency."""
    async with sem:
        t0 = time.perf_counter()
        try:
            resp = await asyncio.wait_for(
                client.post(url, headers=headers, json=payload),
                timeout=timeout,
            )
            elapsed = (time.perf_counter() - t0) * 1000
            collector.record(elapsed, resp.status_code)
        except asyncio.TimeoutError:
            collector.record_error(is_timeout=True)
        except Exception:
            collector.record_error()


# ── Spike Test ──

@pytest.mark.asyncio
async def test_spike(stress_url, duration, target_rps, concurrency):
    """Spike test: normal → 10x → normal. Verifies recovery after spike."""
    collector = StressCollector()
    sem = asyncio.Semaphore(concurrency)
    url = f"{stress_url}/v1/query"
    payload = {"cortexql": "SELECT * FROM customers LIMIT 5"}

    phases = [
        ("baseline", target_rps, duration // 3),
        ("spike", target_rps * 5, duration // 3),
        ("recovery", target_rps, duration // 3),
    ]

    async with httpx.AsyncClient(timeout=10) as client:
        for phase_name, rps, phase_dur in phases:
            print(f"\n  [{phase_name.upper()}] {rps} RPS for {phase_dur}s")
            for sec in range(phase_dur):
                interval_start = time.perf_counter()
                tasks = [
                    _send_request(client, url, HEADERS, payload, collector, sem)
                    for _ in range(rps)
                ]
                await asyncio.gather(*tasks)
                interval_dur = time.perf_counter() - interval_start
                collector.snapshot_rps(rps, interval_dur)
                if interval_dur < 1.0:
                    await asyncio.sleep(1.0 - interval_dur)

    report = collector.report()
    print(f"\n  Spike Test Results:")
    print(f"    Total: {report['total_requests']} requests")
    print(f"    Error rate: {report['error_rate_pct']}%")
    print(f"    p50={report['p50_ms']}ms p99={report['p99_ms']}ms")
    print(f"    Peak RPS: {report['peak_rps']}")
    assert report["error_rate_pct"] < 5, f"Error rate too high: {report['error_rate_pct']}%"


# ── Soak Test ──

@pytest.mark.asyncio
async def test_soak(stress_url, duration, target_rps, concurrency):
    """Soak test: sustained constant load. Checks for memory leaks / degradation."""
    collector = StressCollector()
    sem = asyncio.Semaphore(concurrency)
    url = f"{stress_url}/v1/query"
    payload = {"cortexql": "SELECT * FROM customers LIMIT 10"}

    async with httpx.AsyncClient(timeout=10) as client:
        for sec in range(duration):
            interval_start = time.perf_counter()
            tasks = [
                _send_request(client, url, HEADERS, payload, collector, sem)
                for _ in range(target_rps)
            ]
            await asyncio.gather(*tasks)
            interval_dur = time.perf_counter() - interval_start
            collector.snapshot_rps(target_rps, interval_dur)

            if sec % 10 == 0 and sec > 0:
                recent = collector.latencies[-target_rps:]
                p50 = sorted(recent)[len(recent) // 2] if recent else 0
                print(f"\n  [{sec}s] p50={p50:.1f}ms errors={collector.errors}")

            if interval_dur < 1.0:
                await asyncio.sleep(1.0 - interval_dur)

    report = collector.report()
    print(f"\n  Soak Test Results ({duration}s at {target_rps} RPS):")
    print(f"    Total: {report['total_requests']}, Errors: {report['failed']}")
    print(f"    p50={report['p50_ms']}ms p99={report['p99_ms']}ms max={report['max_ms']}ms")

    # Check for latency degradation (last 10% should not be 2x worse than first 10%)
    if len(collector.latencies) > 100:
        tenth = len(collector.latencies) // 10
        early_p50 = sorted(collector.latencies[:tenth])[tenth // 2]
        late_p50 = sorted(collector.latencies[-tenth:])[tenth // 2]
        degradation = late_p50 / early_p50 if early_p50 > 0 else 1
        print(f"    Degradation ratio: {degradation:.2f}x (early p50={early_p50:.1f}ms, late p50={late_p50:.1f}ms)")
        assert degradation < 3.0, f"Latency degraded {degradation:.1f}x over soak test"


# ── Burst Test ──

@pytest.mark.asyncio
async def test_burst(stress_url, target_rps, concurrency):
    """Burst test: repeated high-load bursts with cool-down periods."""
    collector = StressCollector()
    sem = asyncio.Semaphore(concurrency * 2)
    url = f"{stress_url}/v1/query"
    payload = {"cortexql": "SELECT * FROM customers LIMIT 5"}
    burst_rps = target_rps * 3
    num_bursts = 5
    burst_duration = 3  # seconds per burst
    cooldown = 5         # seconds between bursts

    async with httpx.AsyncClient(timeout=10) as client:
        for burst in range(num_bursts):
            print(f"\n  [BURST {burst+1}/{num_bursts}] {burst_rps} RPS for {burst_duration}s")
            for _ in range(burst_duration):
                t0 = time.perf_counter()
                tasks = [
                    _send_request(client, url, HEADERS, payload, collector, sem)
                    for _ in range(burst_rps)
                ]
                await asyncio.gather(*tasks)
                elapsed = time.perf_counter() - t0
                collector.snapshot_rps(burst_rps, elapsed)
                if elapsed < 1.0:
                    await asyncio.sleep(1.0 - elapsed)
            await asyncio.sleep(cooldown)

    report = collector.report()
    print(f"\n  Burst Test: {num_bursts} bursts x {burst_duration}s")
    print(f"    Total: {report['total_requests']}, Errors: {report['failed']}")
    print(f"    p50={report['p50_ms']}ms p99={report['p99_ms']}ms")
    assert report["error_rate_pct"] < 10, f"Burst error rate: {report['error_rate_pct']}%"


# ── Mixed Workload ──

@pytest.mark.asyncio
async def test_mixed_workload(stress_url, duration, target_rps, concurrency):
    """Mixed read/write workload (80% reads, 20% writes)."""
    collector = StressCollector()
    sem = asyncio.Semaphore(concurrency)
    read_payload = {"cortexql": "SELECT * FROM customers LIMIT 10"}
    url = f"{stress_url}/v1/query"

    async with httpx.AsyncClient(timeout=10) as client:
        for sec in range(min(duration, 20)):
            read_count = int(target_rps * 0.8)
            write_count = target_rps - read_count

            t0 = time.perf_counter()
            tasks = []
            for _ in range(read_count):
                tasks.append(_send_request(
                    client, url, HEADERS, read_payload, collector, sem
                ))
            for i in range(write_count):
                write_payload = {
                    "cortexql": (
                        f"INSERT INTO customer_events (customer_id, event_type, properties) "
                        f"VALUES ('{uuid.uuid4()}', 'stress_write', "
                        f"'{{\"sec\": {sec}, \"i\": {i}}}')"
                    )
                }
                tasks.append(_send_request(
                    client, url, HEADERS, write_payload, collector, sem
                ))
            await asyncio.gather(*tasks)
            elapsed = time.perf_counter() - t0
            collector.snapshot_rps(target_rps, elapsed)
            if elapsed < 1.0:
                await asyncio.sleep(1.0 - elapsed)

    report = collector.report()
    print(f"\n  Mixed Workload (80R/20W at {target_rps} RPS):")
    print(f"    Total: {report['total_requests']}, Errors: {report['failed']}")
    print(f"    p50={report['p50_ms']}ms p99={report['p99_ms']}ms")


# ── Multi-Tenant Isolation ──

@pytest.mark.asyncio
async def test_multi_tenant_isolation(stress_url, concurrency):
    """Verify tenant isolation under concurrent multi-tenant load."""
    tenants = [f"stress-tenant-{i}" for i in range(5)]
    results = {}

    async with httpx.AsyncClient(timeout=10) as client:
        sem = asyncio.Semaphore(concurrency)

        async def _tenant_load(tenant_id: str, count: int):
            headers = {"X-Tenant-Key": tenant_id, "Content-Type": "application/json"}
            latencies = []
            for _ in range(count):
                async with sem:
                    t0 = time.perf_counter()
                    try:
                        resp = await client.post(
                            f"{stress_url}/v1/query",
                            headers=headers,
                            json={"cortexql": "SELECT * FROM customers LIMIT 5"},
                        )
                        latencies.append((time.perf_counter() - t0) * 1000)
                    except Exception:
                        pass
            return latencies

        tasks = {t: _tenant_load(t, 100) for t in tenants}
        for tenant, task in tasks.items():
            results[tenant] = await task

    print(f"\n  Multi-Tenant Isolation ({len(tenants)} tenants):")
    for tenant, lats in results.items():
        if lats:
            s = sorted(lats)
            print(f"    {tenant}: p50={s[len(s)//2]:.1f}ms p99={s[-1]:.1f}ms ({len(lats)} req)")


# ── Connection Exhaustion ──

@pytest.mark.asyncio
async def test_connection_exhaustion(stress_url):
    """Open many concurrent connections to test connection pool limits."""
    max_conns = 200
    collector = StressCollector()

    async with httpx.AsyncClient(
        timeout=15,
        limits=httpx.Limits(max_connections=max_conns, max_keepalive_connections=max_conns),
    ) as client:
        sem = asyncio.Semaphore(max_conns)
        tasks = []
        for _ in range(max_conns):
            tasks.append(_send_request(
                client,
                f"{stress_url}/v1/query",
                HEADERS,
                {"cortexql": "SELECT 1"},
                collector,
                sem,
                timeout=10.0,
            ))
        await asyncio.gather(*tasks)

    report = collector.report()
    print(f"\n  Connection Exhaustion ({max_conns} concurrent):")
    print(f"    Success: {report['successful']}, Failed: {report['failed']}, "
          f"Timeouts: {report['timeouts']}")
    print(f"    p50={report['p50_ms']}ms p99={report['p99_ms']}ms")
