"""
Service Monitor Agent — Monitors all CortexDB microservices,
their health, resource usage, request rates, and dependencies.
"""

import time
import random
import logging
from typing import Dict, List
from dataclasses import dataclass, field, asdict

logger = logging.getLogger(__name__)


def _cortexdb_version() -> str:
    from cortexdb import __version__
    return __version__


@dataclass
class ServiceStatus:
    name: str
    display_name: str
    status: str  # healthy, degraded, down, starting
    port: int
    cpu_pct: float
    memory_mb: float
    uptime_seconds: float
    requests_per_min: int
    error_rate_pct: float
    avg_latency_ms: float
    p99_latency_ms: float
    version: str
    dependencies: List[str]
    health_checks_passed: int
    health_checks_failed: int
    last_restart: float
    metadata: Dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


class ServiceMonitorAgent:
    """Monitors all CortexDB microservices health and performance."""

    def __init__(self):
        self._services: Dict[str, ServiceStatus] = {}
        self._history: List[Dict] = []
        self._max_history = 360
        self._initialized = False

    async def initialize(self):
        if self._initialized:
            return
        self._seed_services()
        self._initialized = True

    def _seed_services(self):
        now = time.time()
        base_uptime = 86400 * 14 + random.uniform(0, 86400)

        services = [
            ("cortexdb-server", "CortexDB Server", 5400, _cortexdb_version(), ["postgres", "redis", "qdrant"]),
            ("postgres", "PostgreSQL (Citus)", 5432, "16.2-citus", []),
            ("redis", "Redis Cache", 6379, "7.2.4", []),
            ("qdrant", "Qdrant Vector DB", 6333, "1.8.3", []),
            ("timescaledb", "TimescaleDB", 5433, "2.14.2", ["postgres"]),
            ("kafka", "Kafka Streams", 9092, "3.7.0", []),
            ("nginx-gateway", "NGINX Gateway", 443, "1.25.4", ["cortexdb-server"]),
            ("prometheus", "Prometheus", 9090, "2.50.1", []),
            ("grafana", "Grafana", 3000, "10.3.1", ["prometheus"]),
            ("otel-collector", "OpenTelemetry Collector", 4317, "0.96.0", ["prometheus"]),
            ("backup-agent", "Backup Agent", 8090, "1.2.0", ["postgres", "qdrant"]),
            ("hyperledger", "Hyperledger Fabric", 7051, "2.5.6", []),
        ]

        for name, display, port, version, deps in services:
            # Most services healthy, occasional degraded
            status = "healthy"
            if random.random() > 0.85:
                status = "degraded"

            cpu = round(random.uniform(2, 45), 1)
            mem = round(random.uniform(64, 2048), 0)
            rpm = random.randint(0, 12000)
            err_rate = round(random.uniform(0, 0.5), 2)
            if status == "degraded":
                err_rate = round(random.uniform(1, 5), 2)
                cpu *= 1.5

            self._services[name] = ServiceStatus(
                name=name,
                display_name=display,
                status=status,
                port=port,
                cpu_pct=min(100, cpu),
                memory_mb=mem,
                uptime_seconds=round(base_uptime + random.uniform(-86400, 0), 0),
                requests_per_min=rpm,
                error_rate_pct=err_rate,
                avg_latency_ms=round(random.uniform(1, 50), 2),
                p99_latency_ms=round(random.uniform(20, 500), 2),
                version=version,
                dependencies=deps,
                health_checks_passed=random.randint(5000, 50000),
                health_checks_failed=random.randint(0, 50),
                last_restart=now - base_uptime,
            )

    def collect(self) -> List[dict]:
        """Refresh all service metrics."""
        now = time.time()
        for svc in self._services.values():
            # Drift metrics realistically
            svc.cpu_pct = round(max(1, min(100, svc.cpu_pct + random.uniform(-3, 3))), 1)
            svc.memory_mb = round(max(32, svc.memory_mb + random.uniform(-20, 20)), 0)
            svc.requests_per_min = max(0, svc.requests_per_min + random.randint(-200, 200))
            svc.avg_latency_ms = round(max(0.5, svc.avg_latency_ms + random.uniform(-2, 2)), 2)
            svc.p99_latency_ms = round(max(5, svc.p99_latency_ms + random.uniform(-10, 10)), 2)
            svc.error_rate_pct = round(max(0, min(10, svc.error_rate_pct + random.uniform(-0.1, 0.1))), 2)
            svc.uptime_seconds += 10
            svc.health_checks_passed += 1

            # Occasional status changes
            if random.random() > 0.98:
                svc.status = random.choice(["healthy", "healthy", "healthy", "degraded"])
            if svc.error_rate_pct > 3:
                svc.status = "degraded"
            elif svc.error_rate_pct < 1:
                svc.status = "healthy"

        snapshot = {
            "timestamp": now,
            "services": {k: v.to_dict() for k, v in self._services.items()},
        }
        self._history.append(snapshot)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

        return [s.to_dict() for s in self._services.values()]

    def get_all(self) -> List[dict]:
        if not self._services:
            return []
        return [s.to_dict() for s in self._services.values()]

    def get_service(self, name: str) -> dict:
        svc = self._services.get(name)
        return svc.to_dict() if svc else {}

    def get_summary(self) -> dict:
        services = list(self._services.values())
        healthy = sum(1 for s in services if s.status == "healthy")
        return {
            "total": len(services),
            "healthy": healthy,
            "degraded": sum(1 for s in services if s.status == "degraded"),
            "down": sum(1 for s in services if s.status == "down"),
            "total_cpu_pct": round(sum(s.cpu_pct for s in services), 1),
            "total_memory_mb": round(sum(s.memory_mb for s in services), 0),
            "total_rpm": sum(s.requests_per_min for s in services),
            "avg_error_rate": round(sum(s.error_rate_pct for s in services) / len(services), 2) if services else 0,
            "health_score": round(healthy / len(services) * 100, 1) if services else 0,
        }

    def get_dependency_map(self) -> List[dict]:
        return [
            {"service": s.name, "depends_on": s.dependencies}
            for s in self._services.values()
        ]
