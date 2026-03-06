"""4-Tier Health Check Hierarchy (DOC-014 Section 2.2)

T1 Liveness (5s):  Process alive?
T2 Readiness (10s): Dependencies reachable?
T3 Deep Health (30s): Performance within SLA?
T4 Dependency Chain (5m): End-to-end path works?
"""

import asyncio
import time
import logging
from enum import IntEnum
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("cortexdb.heartbeat.health")


class HealthTier(IntEnum):
    T1_LIVENESS = 1
    T2_READINESS = 2
    T3_DEEP_HEALTH = 3
    T4_DEPENDENCY_CHAIN = 4


@dataclass
class HealthCheckResult:
    tier: HealthTier
    status: str
    timestamp: float = field(default_factory=time.time)
    latency_ms: float = 0
    checks: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    @property
    def is_healthy(self) -> bool:
        return self.status in ("healthy", "alive", "ready")


@dataclass
class SLAThresholds:
    db_latency_ms: float = 100
    redis_latency_ms: float = 50
    api_latency_ms: float = 500
    error_rate_pct: float = 2.0
    memory_pct: float = 85.0
    cpu_pct: float = 70.0


class HealthCheckRunner:
    def __init__(self, engines: Dict[str, Any] = None):
        self.engines = engines or {}
        self.sla = SLAThresholds()
        self._history: List[HealthCheckResult] = []

    async def check_liveness(self) -> HealthCheckResult:
        start = time.perf_counter()
        result = HealthCheckResult(tier=HealthTier.T1_LIVENESS, status="alive",
                                   checks={"event_loop": "responsive"})
        result.latency_ms = (time.perf_counter() - start) * 1000
        self._history.append(result)
        return result

    async def check_readiness(self) -> HealthCheckResult:
        start = time.perf_counter()
        checks, errors, warnings = {}, [], []

        for name, engine in self.engines.items():
            try:
                await asyncio.wait_for(engine.health(), timeout=3.0)
                checks[name] = "ok"
            except asyncio.TimeoutError:
                checks[name] = "TIMEOUT"
                warnings.append(f"{name}: timeout")
            except Exception as e:
                checks[name] = "FAIL"
                errors.append(f"{name}: {e}")

        status = "not_ready" if errors else ("degraded" if warnings else "ready")
        result = HealthCheckResult(tier=HealthTier.T2_READINESS, status=status,
                                   checks=checks, warnings=warnings, errors=errors)
        result.latency_ms = (time.perf_counter() - start) * 1000
        self._history.append(result)
        return result

    async def check_deep_health(self) -> HealthCheckResult:
        start = time.perf_counter()
        checks, warnings, errors = {}, [], []

        for name, engine in self.engines.items():
            try:
                health = await asyncio.wait_for(engine.health(), timeout=5.0)
                checks[name] = health
                if name == "memory":
                    used = health.get("used_memory_mb", 0)
                    max_mem = health.get("max_memory_mb", 1)
                    if max_mem > 0 and (used / max_mem * 100) > self.sla.memory_pct:
                        warnings.append(f"Redis memory > {self.sla.memory_pct}%")
            except asyncio.TimeoutError:
                checks[name] = {"status": "TIMEOUT"}
                errors.append(f"{name}: deep health timed out")
            except Exception as e:
                checks[name] = {"status": "ERROR", "error": str(e)}
                errors.append(f"{name}: {e}")

        status = "unhealthy" if errors else ("degraded" if warnings else "healthy")
        result = HealthCheckResult(tier=HealthTier.T3_DEEP_HEALTH, status=status,
                                   checks=checks, warnings=warnings, errors=errors)
        result.latency_ms = (time.perf_counter() - start) * 1000
        self._history.append(result)
        return result

    async def check_dependency_chain(self) -> HealthCheckResult:
        start = time.perf_counter()
        checks, errors = {}, []
        test_key = f"_health_{int(time.time())}"

        if "memory" in self.engines:
            try:
                await self.engines["memory"].set(test_key, "probe", ex=30)
                checks["write_memory"] = "ok"
                value = await self.engines["memory"].get(test_key)
                checks["read_memory"] = "ok" if value == "probe" else "MISMATCH"
                await self.engines["memory"].delete(test_key)
            except Exception as e:
                checks["memory_chain"] = "FAIL"
                errors.append(f"MemoryCore chain: {e}")

        if "relational" in self.engines:
            try:
                await self.engines["relational"].execute("SELECT 1 as probe")
                checks["relational_probe"] = "ok"
            except Exception as e:
                checks["relational_probe"] = "FAIL"
                errors.append(f"RelationalCore: {e}")

        status = "unhealthy" if errors else "healthy"
        result = HealthCheckResult(tier=HealthTier.T4_DEPENDENCY_CHAIN, status=status,
                                   checks=checks, errors=errors)
        result.latency_ms = (time.perf_counter() - start) * 1000
        self._history.append(result)
        return result

    def get_history(self, tier: Optional[HealthTier] = None, limit: int = 50) -> List[Dict]:
        results = self._history
        if tier:
            results = [r for r in results if r.tier == tier]
        return [{"tier": f"T{r.tier}", "status": r.status,
                 "latency_ms": round(r.latency_ms, 2), "timestamp": r.timestamp}
                for r in results[-limit:]]
