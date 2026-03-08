"""
Error Tracking Agent — Collects, categorizes, and tracks errors across
all CortexDB services with stack traces and resolution status.
"""

import time
import random
import logging
import traceback
from typing import Dict, List, Optional
from dataclasses import dataclass, field, asdict

logger = logging.getLogger(__name__)


@dataclass
class TrackedError:
    error_id: str
    timestamp: float
    level: str  # critical, error, warning
    service: str
    message: str
    stack_trace: str
    count: int = 1
    first_seen: float = 0
    last_seen: float = 0
    resolved: bool = False
    resolution: str = ""
    affected_users: int = 0
    metadata: Dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


class ErrorTrackingAgent:
    """Collects and tracks errors from all CortexDB services."""

    def __init__(self):
        self._errors: Dict[str, TrackedError] = {}
        self._error_log: List[Dict] = []
        self._max_log = 1000
        self._initialized = False

    async def initialize(self):
        if self._initialized:
            return
        self._seed_data()
        self._initialized = True

    def _seed_data(self):
        now = time.time()

        errors = [
            ("ERR-001", "critical", "cortexdb-server", "Connection pool exhausted: max 200 connections reached",
             self._gen_stack("ConnectionPoolError", "pool.py", "acquire_connection", 142),
             5, 0, ""),
            ("ERR-002", "error", "qdrant", "Vector dimension mismatch: expected 1536, got 768",
             self._gen_stack("DimensionError", "vector_store.py", "upsert_vectors", 89),
             23, 0, ""),
            ("ERR-003", "warning", "redis", "Cache eviction rate exceeded threshold: 15% in last 5min",
             self._gen_stack("CacheWarning", "cache_manager.py", "check_eviction_rate", 201),
             8, 0, ""),
            ("ERR-004", "error", "cortexdb-server", "Tenant isolation breach attempt: cross-tenant query detected",
             self._gen_stack("TenantIsolationError", "rls_guard.py", "validate_query", 67),
             2, 0, ""),
            ("ERR-005", "critical", "kafka", "Consumer lag exceeded 10000 messages on partition 3",
             self._gen_stack("ConsumerLagError", "stream_processor.py", "check_lag", 155),
             1, 0, ""),
            ("ERR-006", "warning", "nginx-gateway", "Rate limit threshold approaching: 850/1000 RPS for tenant acme-corp",
             self._gen_stack("RateLimitWarning", "rate_limiter.py", "check_threshold", 88),
             12, 0, ""),
            ("ERR-007", "error", "postgres", "Deadlock detected between transactions 4521 and 4523",
             self._gen_stack("DeadlockError", "transaction_manager.py", "detect_deadlock", 234),
             3, True, "Automatic retry with exponential backoff resolved the deadlock"),
            ("ERR-008", "warning", "otel-collector", "Trace buffer 80% full, dropping low-priority spans",
             self._gen_stack("BufferWarning", "trace_collector.py", "check_buffer", 112),
             45, 0, ""),
            ("ERR-009", "error", "cortexdb-server", "MCP tool execution timeout after 30s: analyze_sentiment",
             self._gen_stack("ToolTimeoutError", "mcp_executor.py", "execute_tool", 178),
             7, True, "Increased timeout to 60s and added circuit breaker"),
            ("ERR-010", "critical", "hyperledger", "Ledger chain integrity verification failed at block 15234",
             self._gen_stack("IntegrityError", "ledger_verifier.py", "verify_chain", 92),
             1, 0, ""),
            ("ERR-011", "error", "backup-agent", "Incremental backup failed: insufficient disk space on /backup volume",
             self._gen_stack("BackupError", "backup_runner.py", "run_incremental", 156),
             2, 0, ""),
            ("ERR-012", "warning", "cortexdb-server", "Slow query detected: 8.5s on cortex_blocks full table scan",
             self._gen_stack("SlowQueryWarning", "query_executor.py", "execute", 245),
             18, True, "Added missing index on tenant_id column"),
        ]

        for eid, level, svc, msg, stack, count, resolved_flag, resolution in errors:
            first = now - random.uniform(3600, 172800)
            last = now - random.uniform(0, 3600)
            self._errors[eid] = TrackedError(
                error_id=eid, timestamp=last, level=level, service=svc,
                message=msg, stack_trace=stack, count=count,
                first_seen=first, last_seen=last,
                resolved=bool(resolved_flag), resolution=resolution,
                affected_users=random.randint(0, 50),
            )

    def _gen_stack(self, error_class: str, filename: str, func: str, line: int) -> str:
        return (
            f'Traceback (most recent call last):\n'
            f'  File "cortexdb/server.py", line 420, in handle_request\n'
            f'    result = await handler(request)\n'
            f'  File "cortexdb/{filename}", line {line}, in {func}\n'
            f'    raise {error_class}(message)\n'
            f'{error_class}: See error message above'
        )

    def collect(self) -> dict:
        """Run error collection cycle."""
        now = time.time()

        # Occasionally generate new errors
        if random.random() > 0.7:
            services = ["cortexdb-server", "postgres", "redis", "qdrant", "kafka", "nginx-gateway"]
            levels = ["warning", "warning", "error", "error", "critical"]
            svc = random.choice(services)
            level = random.choice(levels)
            templates = [
                f"Timeout waiting for {svc} response after 30s",
                f"Memory usage exceeded 85% threshold on {svc}",
                f"Connection reset by peer on {svc} port",
                f"Failed health check #{random.randint(1, 100)} on {svc}",
                f"Retry exhausted after 3 attempts on {svc}",
            ]
            eid = f"ERR-{random.randint(100, 9999)}"
            msg = random.choice(templates)

            if eid not in self._errors:
                self._errors[eid] = TrackedError(
                    error_id=eid, timestamp=now, level=level, service=svc,
                    message=msg,
                    stack_trace=self._gen_stack("RuntimeError", f"{svc.replace('-', '_')}.py", "handle", random.randint(50, 300)),
                    first_seen=now, last_seen=now,
                    affected_users=random.randint(0, 10),
                )
            # Keep max 50 errors
            if len(self._errors) > 50:
                oldest = sorted(self._errors.keys(), key=lambda k: self._errors[k].last_seen)
                for k in oldest[:len(self._errors) - 50]:
                    del self._errors[k]

        return self.get_summary()

    def get_all_errors(self, level: str = None, resolved: bool = None) -> List[dict]:
        errors = list(self._errors.values())
        if level:
            errors = [e for e in errors if e.level == level]
        if resolved is not None:
            errors = [e for e in errors if e.resolved == resolved]
        return [e.to_dict() for e in sorted(errors, key=lambda x: -x.last_seen)]

    def get_error(self, error_id: str) -> Optional[dict]:
        e = self._errors.get(error_id)
        return e.to_dict() if e else None

    def resolve_error(self, error_id: str, resolution: str) -> Optional[dict]:
        e = self._errors.get(error_id)
        if e:
            e.resolved = True
            e.resolution = resolution
            return e.to_dict()
        return None

    def get_summary(self) -> dict:
        errors = list(self._errors.values())
        unresolved = [e for e in errors if not e.resolved]
        now = time.time()
        last_hour = [e for e in errors if now - e.last_seen < 3600]

        by_level = {}
        by_service = {}
        for e in unresolved:
            by_level[e.level] = by_level.get(e.level, 0) + 1
            by_service[e.service] = by_service.get(e.service, 0) + 1

        return {
            "total_errors": len(errors),
            "unresolved": len(unresolved),
            "resolved": len(errors) - len(unresolved),
            "last_hour": len(last_hour),
            "by_level": by_level,
            "by_service": by_service,
            "total_occurrences": sum(e.count for e in errors),
            "affected_users": sum(e.affected_users for e in unresolved),
            "error_rate": round(len(last_hour) / max(1, len(errors)) * 100, 1),
            "most_frequent": [
                {"error_id": e.error_id, "message": e.message, "count": e.count, "service": e.service}
                for e in sorted(unresolved, key=lambda x: -x.count)[:5]
            ],
        }

    def get_stats_by_service(self) -> List[dict]:
        by_svc: Dict[str, Dict] = {}
        for e in self._errors.values():
            if e.service not in by_svc:
                by_svc[e.service] = {"service": e.service, "total": 0, "unresolved": 0, "critical": 0}
            by_svc[e.service]["total"] += 1
            if not e.resolved:
                by_svc[e.service]["unresolved"] += 1
            if e.level == "critical":
                by_svc[e.service]["critical"] += 1
        return list(by_svc.values())
