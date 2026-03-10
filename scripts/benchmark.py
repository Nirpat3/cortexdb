#!/usr/bin/env python3
"""
CortexDB Benchmark CLI — Run performance and stress tests from the command line.

Usage:
    # Quick benchmark (5 scenarios, ~30 seconds)
    python scripts/benchmark.py --quick

    # Full benchmark suite (16 scenarios)
    python scripts/benchmark.py --full

    # Stress test with specific pattern
    python scripts/benchmark.py --stress spike --duration 60 --rps 500

    # Custom HTTP benchmark against live server
    python scripts/benchmark.py --http --url http://localhost:5400 --concurrency 50

    # Export results to JSON
    python scripts/benchmark.py --full --output results.json
"""

import argparse
import asyncio
import json
import sys
import time
import uuid
import statistics
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import httpx
except ImportError:
    httpx = None


# ── Colors for terminal output ──

class Colors:
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RESET = "\033[0m"


def color(text, c):
    return f"{c}{text}{Colors.RESET}"


def print_header(text):
    width = 60
    print(f"\n{Colors.CYAN}{'=' * width}")
    print(f"  {text}")
    print(f"{'=' * width}{Colors.RESET}")


def print_result(name, p50, p95, p99, ops_sec, errors=0, passed=True):
    status = color("PASS", Colors.GREEN) if passed else color("FAIL", Colors.RED)
    print(f"  {status}  {name:<30} p50={p50:>8.1f}ms  p95={p95:>8.1f}ms  "
          f"p99={p99:>8.1f}ms  {ops_sec:>8.0f} ops/s  err={errors}")


def print_summary(results):
    print_header("SUMMARY")
    total = len(results)
    passed = sum(1 for r in results if r.get("passed", True))
    failed = total - passed
    total_ops = sum(r.get("count", 0) for r in results)
    total_dur = sum(r.get("duration_sec", 0) for r in results)

    print(f"  Scenarios: {color(str(passed), Colors.GREEN)} passed, "
          f"{color(str(failed), Colors.RED) if failed else '0'} failed, {total} total")
    print(f"  Total ops: {total_ops:,}")
    print(f"  Duration:  {total_dur:.1f}s")
    print()


# ── HTTP Benchmark Functions ──

async def http_benchmark(url, concurrency, iterations, headers):
    """Run HTTP benchmarks against a live CortexDB instance."""
    if not httpx:
        print(color("  httpx not installed. Run: pip install httpx", Colors.RED))
        return []

    results = []

    async with httpx.AsyncClient(timeout=15) as client:
        # Check health first
        try:
            resp = await client.get(f"{url}/health/live")
            if resp.status_code != 200:
                print(color(f"  CortexDB not healthy at {url}", Colors.RED))
                return []
            print(color(f"  Connected to CortexDB at {url}", Colors.GREEN))
        except Exception as e:
            print(color(f"  Cannot reach CortexDB at {url}: {e}", Colors.RED))
            return []

        # Deep health
        try:
            resp = await client.get(f"{url}/health/deep")
            if resp.status_code == 200:
                health = resp.json()
                print(f"  Status: {health.get('status', 'unknown')}, "
                      f"Version: {health.get('version', '?')}, "
                      f"Engines: {len(health.get('engines', {}))}")
        except Exception:
            pass

        tenant_headers = {**headers, "X-Tenant-Key": "benchmark-cli"}

        # Define HTTP benchmark scenarios
        scenarios = [
            {
                "name": "health_check",
                "method": "GET",
                "path": "/health/live",
                "iterations": iterations * 2,
                "target_p99_ms": 50,
            },
            {
                "name": "cortexql_select",
                "method": "POST",
                "path": "/v1/query",
                "body": {"cortexql": "SELECT * FROM customers LIMIT 10"},
                "headers": tenant_headers,
                "iterations": iterations,
                "target_p99_ms": 100,
            },
            {
                "name": "cortexql_insert",
                "method": "POST",
                "path": "/v1/query",
                "body_func": lambda i: {
                    "cortexql": f"INSERT INTO customer_events (customer_id, event_type, properties) "
                                f"VALUES ('{uuid.uuid4()}', 'bench', '{{\"i\": {i}}}')"
                },
                "headers": tenant_headers,
                "iterations": iterations,
                "target_p99_ms": 200,
            },
            {
                "name": "vector_search",
                "method": "POST",
                "path": "/v1/query",
                "body": {"cortexql": "FIND SIMILAR TO 'high-value customer' IN customers LIMIT 5"},
                "headers": tenant_headers,
                "iterations": min(iterations, 50),
                "target_p99_ms": 500,
            },
            {
                "name": "identity_resolve",
                "method": "POST",
                "path": "/v1/cortexgraph/identify",
                "body_func": lambda i: {
                    "email": f"bench-{i}@cortexdb.io",
                    "name": f"Bench User {i}",
                },
                "headers": tenant_headers,
                "iterations": min(iterations, 50),
                "target_p99_ms": 200,
            },
            {
                "name": "cache_stats",
                "method": "GET",
                "path": "/admin/cache/stats",
                "iterations": iterations,
                "target_p99_ms": 50,
            },
        ]

        for scenario in scenarios:
            name = scenario["name"]
            iters = scenario["iterations"]
            target = scenario.get("target_p99_ms", 500)
            h = scenario.get("headers", headers)
            sem = asyncio.Semaphore(concurrency)
            latencies = []
            errors = 0

            async def _one(idx):
                nonlocal errors
                async with sem:
                    body = None
                    if "body_func" in scenario:
                        body = scenario["body_func"](idx)
                    elif "body" in scenario:
                        body = scenario["body"]

                    t0 = time.perf_counter()
                    try:
                        if scenario["method"] == "GET":
                            resp = await client.get(f"{url}{scenario['path']}", headers=h)
                        else:
                            resp = await client.post(
                                f"{url}{scenario['path']}", headers=h, json=body
                            )
                        elapsed = (time.perf_counter() - t0) * 1000
                        latencies.append(elapsed)
                        if resp.status_code >= 500:
                            errors += 1
                    except Exception:
                        errors += 1

            t_start = time.perf_counter()
            await asyncio.gather(*[_one(i) for i in range(iters)])
            duration = time.perf_counter() - t_start

            if latencies:
                s = sorted(latencies)
                p50 = s[len(s) // 2]
                p95 = s[int(len(s) * 0.95)]
                p99 = s[min(int(len(s) * 0.99), len(s) - 1)]
                ops = len(latencies) / duration if duration > 0 else 0
                passed = p99 < target

                print_result(name, p50, p95, p99, ops, errors, passed)
                results.append({
                    "name": name,
                    "count": iters,
                    "p50_ms": round(p50, 2),
                    "p95_ms": round(p95, 2),
                    "p99_ms": round(p99, 2),
                    "ops_sec": round(ops, 1),
                    "errors": errors,
                    "duration_sec": round(duration, 2),
                    "target_p99_ms": target,
                    "passed": passed,
                })
            else:
                print_result(name, 0, 0, 0, 0, errors, False)
                results.append({"name": name, "count": 0, "errors": errors, "passed": False})

    return results


# ── Stress Test via HTTP ──

async def http_stress(url, pattern, duration, rps, concurrency):
    """Run HTTP-based stress tests."""
    if not httpx:
        print(color("  httpx not installed. Run: pip install httpx", Colors.RED))
        return {}

    print(f"  Pattern: {pattern}, Duration: {duration}s, Target: {rps} RPS, Concurrency: {concurrency}")

    latencies = []
    errors = 0
    timeouts = 0
    rps_timeline = []
    headers = {"X-Tenant-Key": "stress-cli", "Content-Type": "application/json"}
    payload = {"cortexql": "SELECT * FROM customers LIMIT 5"}

    async with httpx.AsyncClient(timeout=10) as client:
        sem = asyncio.Semaphore(concurrency)

        async def _one():
            nonlocal errors, timeouts
            async with sem:
                t0 = time.perf_counter()
                try:
                    resp = await asyncio.wait_for(
                        client.post(f"{url}/v1/query", headers=headers, json=payload),
                        timeout=5.0,
                    )
                    latencies.append((time.perf_counter() - t0) * 1000)
                except asyncio.TimeoutError:
                    timeouts += 1
                    errors += 1
                except Exception:
                    errors += 1

        # Generate RPS schedule based on pattern
        schedule = []
        if pattern == "spike":
            for s in range(duration):
                if duration // 3 <= s < 2 * duration // 3:
                    schedule.append(rps * 5)
                else:
                    schedule.append(rps)
        elif pattern == "ramp":
            for s in range(duration):
                schedule.append(int(rps * (s + 1) / duration))
        elif pattern == "burst":
            for s in range(duration):
                if s % 10 < 3:  # 3s burst every 10s
                    schedule.append(rps * 3)
                else:
                    schedule.append(rps // 5)
        elif pattern == "soak":
            schedule = [rps] * duration
        else:  # mixed
            schedule = [rps] * duration

        for sec, target in enumerate(schedule):
            t0 = time.perf_counter()
            batch_before = len(latencies)
            await asyncio.gather(*[_one() for _ in range(target)])
            elapsed = time.perf_counter() - t0
            batch_count = len(latencies) - batch_before + (errors - sum(1 for _ in []))
            actual_rps = target / elapsed if elapsed > 0 else 0
            rps_timeline.append({"sec": sec, "target_rps": target, "actual_rps": round(actual_rps, 1)})

            if sec % 5 == 0:
                recent = latencies[-target:] if latencies else [0]
                p50 = sorted(recent)[len(recent) // 2] if recent else 0
                print(f"  [{sec:>3}s] target={target:>5} RPS  actual={actual_rps:>7.0f}  "
                      f"p50={p50:>6.1f}ms  errors={errors}")

            if elapsed < 1.0:
                await asyncio.sleep(1.0 - elapsed)

    # Final report
    if latencies:
        s = sorted(latencies)
        total = len(s) + errors
        result = {
            "pattern": pattern,
            "duration_sec": duration,
            "target_rps": rps,
            "total_requests": total,
            "successful": len(s),
            "failed": errors,
            "timeouts": timeouts,
            "error_rate_pct": round(errors / total * 100, 2),
            "p50_ms": round(s[len(s) // 2], 2),
            "p95_ms": round(s[int(len(s) * 0.95)], 2),
            "p99_ms": round(s[min(int(len(s) * 0.99), len(s) - 1)], 2),
            "max_ms": round(s[-1], 2),
            "avg_rps": round(len(s) / duration, 1),
            "peak_rps": max((x["actual_rps"] for x in rps_timeline), default=0),
        }
        print_header(f"STRESS TEST RESULTS — {pattern.upper()}")
        print(f"  Total requests:  {result['total_requests']:,}")
        print(f"  Successful:      {result['successful']:,}")
        print(f"  Failed:          {result['failed']:,} ({result['error_rate_pct']}%)")
        print(f"  Timeouts:        {result['timeouts']:,}")
        print(f"  Avg RPS:         {result['avg_rps']}")
        print(f"  Peak RPS:        {result['peak_rps']}")
        print(f"  Latency p50:     {result['p50_ms']}ms")
        print(f"  Latency p95:     {result['p95_ms']}ms")
        print(f"  Latency p99:     {result['p99_ms']}ms")
        print(f"  Latency max:     {result['max_ms']}ms")
        return result
    return {"error": "no successful requests"}


# ── In-Process Benchmark (no HTTP) ──

async def in_process_benchmark(quick=False):
    """Run benchmarks directly against CortexDB engines (requires running instance)."""
    try:
        from cortexdb.benchmark.runner import BenchmarkRunner
        from cortexdb.benchmark.scenarios import ScenarioRegistry
    except ImportError as e:
        print(color(f"  Cannot import benchmark module: {e}", Colors.RED))
        return []

    runner = BenchmarkRunner()
    registry = ScenarioRegistry()
    scenarios = registry.get_quick_scenarios() if quick else registry.get_all_scenarios()

    print(f"  Running {len(scenarios)} scenarios (in-process mode)...")
    result = await runner.run_suite(scenarios, concurrency=10)

    results = []
    for r in result["suite_results"]:
        lat = r["latency_ms"]
        passed = r["error_count"] == 0
        print_result(r["name"], lat["p50"], lat["p95"], lat["p99"],
                     r["throughput_ops_sec"], r["error_count"], passed)
        results.append({**r, "passed": passed})

    return results


# ── Main ──

def main():
    parser = argparse.ArgumentParser(
        description="CortexDB Performance Benchmark CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/benchmark.py --quick
  python scripts/benchmark.py --http --url http://localhost:5400
  python scripts/benchmark.py --stress spike --duration 60 --rps 500
  python scripts/benchmark.py --full --output results.json
        """,
    )
    parser.add_argument("--quick", action="store_true", help="Quick benchmark (5 scenarios)")
    parser.add_argument("--full", action="store_true", help="Full benchmark suite")
    parser.add_argument("--http", action="store_true", help="HTTP benchmark against live server")
    parser.add_argument("--stress", choices=["spike", "soak", "ramp", "burst", "mixed"],
                        help="Run stress test with pattern")
    parser.add_argument("--url", default="http://localhost:5400", help="CortexDB URL")
    parser.add_argument("--concurrency", type=int, default=50, help="Max concurrent requests")
    parser.add_argument("--iterations", type=int, default=100, help="Iterations per scenario")
    parser.add_argument("--duration", type=int, default=30, help="Stress test duration (seconds)")
    parser.add_argument("--rps", type=int, default=100, help="Target requests per second")
    parser.add_argument("--output", help="Save results to JSON file")
    args = parser.parse_args()

    print_header("CortexDB Performance Benchmark")
    print(f"  Time:        {datetime.now().isoformat()}")
    print(f"  Target:      {args.url}")
    print(f"  Concurrency: {args.concurrency}")

    results = {}

    if args.stress:
        print_header(f"STRESS TEST — {args.stress.upper()}")
        results = asyncio.run(http_stress(
            args.url, args.stress, args.duration, args.rps, args.concurrency
        ))
    elif args.http or args.full:
        print_header("HTTP BENCHMARK")
        res = asyncio.run(http_benchmark(
            args.url, args.concurrency, args.iterations,
            {"Content-Type": "application/json"},
        ))
        print_summary(res)
        results = {"scenarios": res}
    elif args.quick:
        print_header("QUICK BENCHMARK (In-Process)")
        res = asyncio.run(in_process_benchmark(quick=True))
        print_summary(res)
        results = {"scenarios": res}
    else:
        parser.print_help()
        return

    if args.output:
        output_path = Path(args.output)
        output_path.write_text(json.dumps({
            "timestamp": datetime.now().isoformat(),
            "url": args.url,
            "results": results,
        }, indent=2, default=str))
        print(f"\n  Results saved to {output_path}")


if __name__ == "__main__":
    main()
