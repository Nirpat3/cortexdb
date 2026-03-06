"""
Performance Benchmark Tests — Run against a live CortexDB instance via HTTP.

Usage:
    pytest tests/benchmark/ -v --benchmark-url http://localhost:5400
    pytest tests/benchmark/test_performance.py -v -k "test_query_latency"
"""

import pytest
import asyncio
import time
import uuid
import json
import statistics
from typing import Dict, List

# Use httpx for async HTTP testing
try:
    import httpx
except ImportError:
    httpx = None

BASE_URL = "http://localhost:5400"
TENANT_KEY = "bench-test-key"
HEADERS = {"X-Tenant-Key": TENANT_KEY, "Content-Type": "application/json"}


# Options registered in tests/conftest.py: --benchmark-url, --benchmark-iterations


@pytest.fixture
def base_url(request):
    return request.config.getoption("--benchmark-url")


@pytest.fixture
def iterations(request):
    return request.config.getoption("--benchmark-iterations")


class LatencyCollector:
    """Collects latencies and computes percentiles."""

    def __init__(self):
        self.latencies: List[float] = []
        self.errors: int = 0

    def record(self, ms: float):
        self.latencies.append(ms)

    def record_error(self):
        self.errors += 1

    @property
    def p50(self) -> float:
        if not self.latencies:
            return 0
        s = sorted(self.latencies)
        return s[len(s) // 2]

    @property
    def p95(self) -> float:
        if not self.latencies:
            return 0
        s = sorted(self.latencies)
        return s[int(len(s) * 0.95)]

    @property
    def p99(self) -> float:
        if not self.latencies:
            return 0
        s = sorted(self.latencies)
        return s[min(int(len(s) * 0.99), len(s) - 1)]

    @property
    def mean(self) -> float:
        return statistics.mean(self.latencies) if self.latencies else 0

    @property
    def ops_per_sec(self) -> float:
        total_sec = sum(self.latencies) / 1000
        return len(self.latencies) / total_sec if total_sec > 0 else 0

    def report(self, name: str) -> Dict:
        return {
            "name": name,
            "count": len(self.latencies),
            "errors": self.errors,
            "p50_ms": round(self.p50, 2),
            "p95_ms": round(self.p95, 2),
            "p99_ms": round(self.p99, 2),
            "mean_ms": round(self.mean, 2),
            "ops_sec": round(self.ops_per_sec, 1),
        }


# ── Health & Readiness ──

@pytest.mark.asyncio
async def test_health_endpoint(base_url):
    """Health endpoint should respond in < 50ms."""
    async with httpx.AsyncClient() as client:
        collector = LatencyCollector()
        for _ in range(50):
            t0 = time.perf_counter()
            resp = await client.get(f"{base_url}/health/live")
            elapsed = (time.perf_counter() - t0) * 1000
            collector.record(elapsed)
            assert resp.status_code == 200
        report = collector.report("health_live")
        print(f"\n  Health: p50={report['p50_ms']}ms p99={report['p99_ms']}ms")
        assert collector.p99 < 50, f"Health p99 too slow: {collector.p99:.1f}ms"


@pytest.mark.asyncio
async def test_deep_health(base_url):
    """Deep health should return all engine statuses."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{base_url}/health/deep")
        assert resp.status_code == 200
        data = resp.json()
        assert "engines" in data
        assert "status" in data


# ── CortexQL Query Performance ──

@pytest.mark.asyncio
async def test_query_latency(base_url, iterations):
    """CortexQL SELECT query latency benchmark."""
    async with httpx.AsyncClient(timeout=10) as client:
        collector = LatencyCollector()
        for i in range(iterations):
            t0 = time.perf_counter()
            resp = await client.post(
                f"{base_url}/v1/query",
                headers=HEADERS,
                json={"cortexql": f"SELECT * FROM customers LIMIT 10"},
            )
            elapsed = (time.perf_counter() - t0) * 1000
            if resp.status_code in (200, 201):
                collector.record(elapsed)
            else:
                collector.record_error()
        report = collector.report("cortexql_select")
        print(f"\n  CortexQL SELECT: p50={report['p50_ms']}ms p95={report['p95_ms']}ms "
              f"p99={report['p99_ms']}ms ({report['ops_sec']} ops/s)")


@pytest.mark.asyncio
async def test_write_latency(base_url, iterations):
    """CortexQL INSERT latency benchmark."""
    async with httpx.AsyncClient(timeout=10) as client:
        collector = LatencyCollector()
        for i in range(iterations):
            t0 = time.perf_counter()
            resp = await client.post(
                f"{base_url}/v1/query",
                headers=HEADERS,
                json={
                    "cortexql": (
                        f"INSERT INTO customer_events (customer_id, event_type, properties) "
                        f"VALUES ('{uuid.uuid4()}', 'benchmark', "
                        f"'{{\"iteration\": {i}}}')"
                    )
                },
            )
            elapsed = (time.perf_counter() - t0) * 1000
            if resp.status_code in (200, 201):
                collector.record(elapsed)
            else:
                collector.record_error()
        report = collector.report("cortexql_insert")
        print(f"\n  CortexQL INSERT: p50={report['p50_ms']}ms p95={report['p95_ms']}ms "
              f"({report['ops_sec']} ops/s)")


# ── Cache Performance ──

@pytest.mark.asyncio
async def test_cache_hit_rate(base_url):
    """Run same query twice to verify caching improves latency."""
    async with httpx.AsyncClient(timeout=10) as client:
        query = "SELECT * FROM customers LIMIT 5"

        # Cold query
        t0 = time.perf_counter()
        await client.post(
            f"{base_url}/v1/query", headers=HEADERS,
            json={"cortexql": query},
        )
        cold_ms = (time.perf_counter() - t0) * 1000

        # Warm query (should hit cache)
        t0 = time.perf_counter()
        await client.post(
            f"{base_url}/v1/query", headers=HEADERS,
            json={"cortexql": query, "hint": "cache_first"},
        )
        warm_ms = (time.perf_counter() - t0) * 1000

        print(f"\n  Cache: cold={cold_ms:.1f}ms warm={warm_ms:.1f}ms "
              f"speedup={cold_ms/warm_ms:.1f}x" if warm_ms > 0 else "")


@pytest.mark.asyncio
async def test_cache_stats(base_url):
    """Cache stats endpoint should return hit/miss metrics."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{base_url}/admin/cache/stats")
        if resp.status_code == 200:
            data = resp.json()
            print(f"\n  Cache Stats: {json.dumps(data, indent=2)[:200]}")


# ── Vector Search Performance ──

@pytest.mark.asyncio
async def test_vector_search_latency(base_url, iterations):
    """FIND SIMILAR vector search benchmark."""
    async with httpx.AsyncClient(timeout=10) as client:
        collector = LatencyCollector()
        for _ in range(min(iterations, 50)):
            t0 = time.perf_counter()
            resp = await client.post(
                f"{base_url}/v1/query",
                headers=HEADERS,
                json={"cortexql": "FIND SIMILAR TO 'loyal high-value customer' IN customers LIMIT 5"},
            )
            elapsed = (time.perf_counter() - t0) * 1000
            if resp.status_code in (200, 201):
                collector.record(elapsed)
            else:
                collector.record_error()
        report = collector.report("vector_search")
        print(f"\n  Vector Search: p50={report['p50_ms']}ms p99={report['p99_ms']}ms")


# ── Concurrent Load ──

@pytest.mark.asyncio
async def test_concurrent_reads(base_url):
    """Measure throughput under concurrent read load (50 parallel)."""
    concurrency = 50
    total = 500

    async with httpx.AsyncClient(timeout=15) as client:
        sem = asyncio.Semaphore(concurrency)
        collector = LatencyCollector()

        async def _one():
            async with sem:
                t0 = time.perf_counter()
                try:
                    resp = await client.post(
                        f"{base_url}/v1/query",
                        headers=HEADERS,
                        json={"cortexql": "SELECT * FROM customers LIMIT 5"},
                    )
                    elapsed = (time.perf_counter() - t0) * 1000
                    if resp.status_code in (200, 201):
                        collector.record(elapsed)
                    else:
                        collector.record_error()
                except Exception:
                    collector.record_error()

        t0 = time.perf_counter()
        await asyncio.gather(*[_one() for _ in range(total)])
        wall_time = time.perf_counter() - t0
        throughput = len(collector.latencies) / wall_time if wall_time > 0 else 0

        report = collector.report("concurrent_reads")
        print(f"\n  Concurrent Reads ({concurrency} parallel): "
              f"{throughput:.0f} req/s, p50={report['p50_ms']}ms, "
              f"p99={report['p99_ms']}ms, errors={report['errors']}")


@pytest.mark.asyncio
async def test_concurrent_writes(base_url):
    """Measure write throughput under concurrent load (20 parallel)."""
    concurrency = 20
    total = 200

    async with httpx.AsyncClient(timeout=15) as client:
        sem = asyncio.Semaphore(concurrency)
        collector = LatencyCollector()

        async def _one(i):
            async with sem:
                t0 = time.perf_counter()
                try:
                    resp = await client.post(
                        f"{base_url}/v1/query",
                        headers=HEADERS,
                        json={
                            "cortexql": (
                                f"INSERT INTO customer_events "
                                f"(customer_id, event_type, properties) VALUES "
                                f"('{uuid.uuid4()}', 'bench_write', "
                                f"'{{\"i\": {i}}}')"
                            )
                        },
                    )
                    elapsed = (time.perf_counter() - t0) * 1000
                    if resp.status_code in (200, 201):
                        collector.record(elapsed)
                    else:
                        collector.record_error()
                except Exception:
                    collector.record_error()

        t0 = time.perf_counter()
        await asyncio.gather(*[_one(i) for i in range(total)])
        wall_time = time.perf_counter() - t0
        throughput = len(collector.latencies) / wall_time if wall_time > 0 else 0

        report = collector.report("concurrent_writes")
        print(f"\n  Concurrent Writes ({concurrency} parallel): "
              f"{throughput:.0f} req/s, p50={report['p50_ms']}ms, errors={report['errors']}")


# ── CortexGraph Performance ──

@pytest.mark.asyncio
async def test_identity_resolution(base_url):
    """Benchmark identity resolution endpoint."""
    async with httpx.AsyncClient(timeout=10) as client:
        collector = LatencyCollector()
        for i in range(50):
            t0 = time.perf_counter()
            resp = await client.post(
                f"{base_url}/v1/cortexgraph/identify",
                headers=HEADERS,
                json={
                    "email": f"bench-{i}@test.cortexdb.io",
                    "name": f"Benchmark User {i}",
                },
            )
            elapsed = (time.perf_counter() - t0) * 1000
            collector.record(elapsed)
        report = collector.report("identity_resolution")
        print(f"\n  Identity Resolution: p50={report['p50_ms']}ms p99={report['p99_ms']}ms")


@pytest.mark.asyncio
async def test_customer_360(base_url):
    """Benchmark Customer 360 profile retrieval."""
    async with httpx.AsyncClient(timeout=10) as client:
        # First create a customer
        resp = await client.post(
            f"{base_url}/v1/cortexgraph/identify",
            headers=HEADERS,
            json={"email": "bench-360@test.cortexdb.io", "name": "Bench 360"},
        )
        if resp.status_code == 200:
            customer_id = resp.json().get("customer_id", "unknown")
            collector = LatencyCollector()
            for _ in range(30):
                t0 = time.perf_counter()
                await client.get(
                    f"{base_url}/v1/cortexgraph/customer/{customer_id}/360",
                    headers=HEADERS,
                )
                collector.record((time.perf_counter() - t0) * 1000)
            report = collector.report("customer_360")
            print(f"\n  Customer 360: p50={report['p50_ms']}ms p99={report['p99_ms']}ms")


# ── Compliance Performance ──

@pytest.mark.asyncio
async def test_amygdala_throughput(base_url):
    """Amygdala threat detection should add < 1ms overhead."""
    queries = [
        "SELECT * FROM customers WHERE email = 'test@test.com'",
        "UPDATE profiles SET score = 85 WHERE id = 1",
        "INSERT INTO events (type) VALUES ('click')",
    ]
    async with httpx.AsyncClient(timeout=10) as client:
        collector = LatencyCollector()
        for _ in range(200):
            t0 = time.perf_counter()
            resp = await client.post(
                f"{base_url}/v1/query",
                headers=HEADERS,
                json={"cortexql": queries[_ % len(queries)]},
            )
            collector.record((time.perf_counter() - t0) * 1000)
        report = collector.report("amygdala_overhead")
        print(f"\n  Amygdala: p50={report['p50_ms']}ms "
              f"(target: query overhead < 1ms)")


@pytest.mark.asyncio
async def test_encryption_overhead(base_url):
    """Test compliance encryption endpoint performance."""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(f"{base_url}/v1/compliance/encryption/stats")
        if resp.status_code == 200:
            print(f"\n  Encryption Stats: {json.dumps(resp.json(), indent=2)[:200]}")


# ── Data Rendering ──

@pytest.mark.asyncio
async def test_rendering_formats(base_url):
    """Test data rendering in different output formats."""
    formats = ["json", "jsonl", "csv"]
    async with httpx.AsyncClient(timeout=10) as client:
        for fmt in formats:
            t0 = time.perf_counter()
            resp = await client.post(
                f"{base_url}/v1/render",
                headers=HEADERS,
                json={
                    "cortexql": "SELECT * FROM customers LIMIT 100",
                    "format": fmt,
                },
            )
            elapsed = (time.perf_counter() - t0) * 1000
            size = len(resp.content)
            print(f"\n  Render {fmt}: {elapsed:.1f}ms, {size} bytes")
