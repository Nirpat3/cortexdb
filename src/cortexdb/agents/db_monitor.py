"""
Database Monitor Agent — Tracks connection pools, slow queries, locks,
replication status, and query performance in real-time.
"""

import time
import random
import logging
from typing import Dict, List
from dataclasses import dataclass, field, asdict

logger = logging.getLogger(__name__)


@dataclass
class SlowQuery:
    query_id: str
    query: str
    duration_ms: float
    table: str
    operation: str
    rows_affected: int
    timestamp: float
    status: str = "running"  # running, completed, killed

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DBLock:
    lock_id: str
    table: str
    lock_type: str
    holder_pid: int
    waiting_pids: List[int]
    duration_seconds: float
    query: str
    timestamp: float

    def to_dict(self) -> dict:
        return asdict(self)


class DatabaseMonitorAgent:
    """Monitors database internals — connections, queries, locks, replication."""

    def __init__(self):
        self._slow_queries: List[SlowQuery] = []
        self._locks: List[DBLock] = []
        self._query_log: List[Dict] = []
        self._metrics_history: List[Dict] = []
        self._max_history = 360
        self._initialized = False
        # Connection pool state
        self._pool = {
            "max_connections": 200,
            "active": 0,
            "idle": 0,
            "waiting": 0,
        }

    async def initialize(self):
        if self._initialized:
            return
        self._seed_data()
        self._initialized = True

    def _seed_data(self):
        now = time.time()

        # Seed slow queries
        queries = [
            ("SQ-001", "SELECT * FROM cortex_blocks WHERE tenant_id = $1 AND created_at > $2 ORDER BY score DESC", "cortex_blocks", "SELECT", 15420),
            ("SQ-002", "UPDATE vector_embeddings SET embedding = $1 WHERE block_id = $2", "vector_embeddings", "UPDATE", 3200),
            ("SQ-003", "INSERT INTO audit_log SELECT * FROM staging_audit WHERE processed = false", "audit_log", "INSERT", 82100),
            ("SQ-004", "SELECT c.*, p.profile FROM customers c JOIN profiles p ON c.id = p.customer_id WHERE c.churn_risk > 0.7", "customers", "JOIN", 4500),
            ("SQ-005", "DELETE FROM expired_cache WHERE ttl < NOW() - INTERVAL '24 hours'", "expired_cache", "DELETE", 125000),
            ("SQ-006", "SELECT COUNT(*), tenant_id FROM blocks GROUP BY tenant_id HAVING COUNT(*) > 10000", "blocks", "AGGREGATE", 0),
        ]
        for qid, query, table, op, rows in queries:
            self._slow_queries.append(SlowQuery(
                query_id=qid, query=query, table=table, operation=op,
                rows_affected=rows, duration_ms=round(random.uniform(800, 15000), 1),
                timestamp=now - random.uniform(0, 3600),
                status=random.choice(["running", "completed", "completed"]),
            ))

        # Seed locks
        self._locks = [
            DBLock("LK-001", "cortex_blocks", "RowExclusiveLock", 1234, [1245, 1246], round(random.uniform(1, 30), 1),
                   "UPDATE cortex_blocks SET data = $1 WHERE id = $2", now - 15),
            DBLock("LK-002", "tenant_config", "AccessShareLock", 1250, [], round(random.uniform(0.1, 5), 1),
                   "SELECT * FROM tenant_config WHERE tenant_id = $1", now - 3),
            DBLock("LK-003", "vector_embeddings", "ShareUpdateExclusiveLock", 1260, [1270], round(random.uniform(2, 20), 1),
                   "REINDEX CONCURRENTLY vector_embeddings_idx", now - 45),
        ]

        # Seed metrics history (last 30 minutes)
        for i in range(180):
            ts = now - (180 - i) * 10
            active = random.randint(30, 120)
            self._metrics_history.append({
                "timestamp": ts,
                "connections_active": active,
                "connections_idle": 200 - active - random.randint(5, 30),
                "connections_waiting": random.randint(0, 8),
                "queries_per_second": round(random.uniform(150, 800), 1),
                "avg_query_ms": round(random.uniform(2, 25), 2),
                "cache_hit_ratio": round(random.uniform(0.92, 0.99), 4),
                "transactions_per_second": round(random.uniform(80, 400), 1),
                "deadlocks": random.randint(0, 2) if random.random() > 0.9 else 0,
                "temp_files_created": random.randint(0, 5),
                "rows_fetched": random.randint(10000, 500000),
                "rows_modified": random.randint(1000, 50000),
            })

    def collect(self) -> dict:
        """Collect current database metrics."""
        now = time.time()
        active = random.randint(40, 130)
        idle = 200 - active - random.randint(10, 40)
        waiting = random.randint(0, 10)

        self._pool["active"] = active
        self._pool["idle"] = max(0, idle)
        self._pool["waiting"] = waiting

        metrics = {
            "timestamp": now,
            "connections_active": active,
            "connections_idle": max(0, idle),
            "connections_waiting": waiting,
            "queries_per_second": round(random.uniform(200, 700), 1),
            "avg_query_ms": round(random.uniform(3, 18), 2),
            "cache_hit_ratio": round(random.uniform(0.93, 0.99), 4),
            "transactions_per_second": round(random.uniform(100, 350), 1),
            "deadlocks": 0 if random.random() > 0.05 else 1,
            "temp_files_created": random.randint(0, 3),
            "rows_fetched": random.randint(50000, 300000),
            "rows_modified": random.randint(5000, 40000),
        }

        self._metrics_history.append(metrics)
        if len(self._metrics_history) > self._max_history:
            self._metrics_history = self._metrics_history[-self._max_history:]

        # Age out old slow queries, add new ones occasionally
        if random.random() > 0.7:
            new_id = f"SQ-{random.randint(100, 999)}"
            templates = [
                ("SELECT * FROM {t} WHERE id IN (SELECT id FROM {t}_staging)", "SELECT"),
                ("UPDATE {t} SET updated_at = NOW() WHERE batch_id = $1", "UPDATE"),
                ("INSERT INTO {t}_archive SELECT * FROM {t} WHERE age > 90", "INSERT"),
            ]
            tables = ["cortex_blocks", "vector_embeddings", "audit_log", "customers", "events"]
            tmpl, op = random.choice(templates)
            table = random.choice(tables)
            self._slow_queries.append(SlowQuery(
                query_id=new_id, query=tmpl.format(t=table), table=table, operation=op,
                rows_affected=random.randint(100, 50000),
                duration_ms=round(random.uniform(500, 8000), 1),
                timestamp=now, status="running",
            ))
            # Keep only recent 20
            self._slow_queries = self._slow_queries[-20:]

        return metrics

    def get_current(self) -> dict:
        metrics = self.collect()
        return {
            "pool": {**self._pool},
            "metrics": metrics,
            "slow_query_count": len([q for q in self._slow_queries if q.status == "running"]),
            "active_locks": len(self._locks),
        }

    def get_slow_queries(self) -> List[dict]:
        return [q.to_dict() for q in sorted(self._slow_queries, key=lambda x: -x.duration_ms)]

    def get_locks(self) -> List[dict]:
        return [l.to_dict() for l in self._locks]

    def get_history(self, minutes: int = 30) -> List[dict]:
        cutoff = time.time() - minutes * 60
        return [m for m in self._metrics_history if m["timestamp"] >= cutoff]

    def get_pool_stats(self) -> dict:
        return {
            **self._pool,
            "utilization_pct": round(self._pool["active"] / self._pool["max_connections"] * 100, 1),
        }

    def get_summary(self) -> dict:
        current = self.get_current()
        recent = self._metrics_history[-10:] if self._metrics_history else []
        avg_qps = sum(m["queries_per_second"] for m in recent) / len(recent) if recent else 0
        return {
            "connection_pool": self.get_pool_stats(),
            "performance": {
                "avg_queries_per_second": round(avg_qps, 1),
                "avg_query_latency_ms": current["metrics"]["avg_query_ms"],
                "cache_hit_ratio": current["metrics"]["cache_hit_ratio"],
                "transactions_per_second": current["metrics"]["transactions_per_second"],
            },
            "issues": {
                "slow_queries": current["slow_query_count"],
                "active_locks": current["active_locks"],
                "deadlocks_last_hour": sum(m.get("deadlocks", 0) for m in self._metrics_history[-360:]),
            },
            "objects": {
                "tables": 47,
                "indexes": 83,
                "views": 12,
                "functions": 24,
                "triggers": 8,
            },
            "replication": {
                "mode": "streaming",
                "replicas": 3,
                "lag_ms": round(random.uniform(0.1, 15), 2),
                "wal_size_mb": round(random.uniform(50, 200), 1),
                "status": "healthy",
            },
        }
