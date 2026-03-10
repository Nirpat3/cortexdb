"""Read Replica Routing and Connection Pool Management

Automatic read/write splitting:
  - Writes -> Primary (coordinator)
  - Reads  -> Round-robin across replicas
  - Sticky reads -> Same replica within a transaction (read-your-writes)

Connection pooling via PgBouncer integration:
  - Transaction pooling (default): connections reused after each transaction
  - Session pooling (for prepared statements): connection locked to session
  - Statement pooling (highest throughput): connection reused after each statement
"""

import logging
import time
import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger("cortexdb.scale.replication")


class ReadWriteSplit(Enum):
    PRIMARY = "primary"
    REPLICA = "replica"
    NEAREST = "nearest"   # Latency-based routing
    RANDOM = "random"


class PoolMode(Enum):
    TRANSACTION = "transaction"
    SESSION = "session"
    STATEMENT = "statement"


@dataclass
class ReplicaNode:
    host: str
    port: int = 5432
    role: str = "replica"           # "primary" or "replica"
    region: str = "us-east-1"
    latency_ms: float = 0.0
    connections_active: int = 0
    connections_max: int = 100
    lag_bytes: int = 0
    lag_ms: float = 0.0
    healthy: bool = True
    last_check: float = field(default_factory=time.time)

    @property
    def utilization(self) -> float:
        return self.connections_active / max(self.connections_max, 1) * 100

    @property
    def is_lagging(self) -> bool:
        return self.lag_ms > 1000  # 1s lag threshold


@dataclass
class PoolStats:
    total_connections: int = 0
    active_connections: int = 0
    idle_connections: int = 0
    waiting_clients: int = 0
    pool_mode: str = "transaction"
    avg_query_time_ms: float = 0


class ReplicaRouter:
    """Routes queries to appropriate primary/replica based on operation type.

    Read-your-writes consistency:
      After a write, subsequent reads within the same session/request
      are routed to the primary for consistency.

    Lag-aware routing:
      Replicas with replication lag > threshold are deprioritized.
    """

    LAG_THRESHOLD_MS = 1000   # Max acceptable replication lag
    HEALTH_CHECK_INTERVAL = 5  # Seconds between health checks

    WRITER_STICKY_SEC = 5.0     # Read-your-writes window
    MAX_RECENT_WRITERS = 10000  # Bounded size for memory safety

    def __init__(self, engines: Dict[str, Any] = None, redis=None):
        self.engines = engines or {}
        self._redis = redis  # Shared Redis for cross-instance read-your-writes tracking
        self._primary: Optional[ReplicaNode] = None
        self._replicas: List[ReplicaNode] = []
        self._round_robin_idx = 0
        self._recent_writers: Dict[str, float] = {}  # tenant_id -> last_write_time (fallback)
        self._query_count = 0
        self._read_from_primary = 0
        self._read_from_replica = 0
        self._last_cleanup = time.time()

    async def configure(self, primary_url: str,
                        replica_urls: List[str] = None) -> Dict:
        """Configure primary and replica connections."""
        self._primary = self._parse_url(primary_url, role="primary")

        if replica_urls:
            for url in replica_urls:
                node = self._parse_url(url, role="replica")
                self._replicas.append(node)

        logger.info(f"Replica router configured: 1 primary + "
                    f"{len(self._replicas)} replicas")
        return {
            "primary": self._primary.host,
            "replicas": [r.host for r in self._replicas],
        }

    def _parse_url(self, url: str, role: str = "replica") -> ReplicaNode:
        """Parse PostgreSQL URL into ReplicaNode."""
        # postgresql://user:pass@host:port/db
        parts = url.replace("postgresql://", "").split("@")
        host_part = parts[-1].split("/")[0]
        host = host_part.split(":")[0]
        port = int(host_part.split(":")[1]) if ":" in host_part else 5432
        return ReplicaNode(host=host, port=port, role=role)

    async def record_write(self, tenant_id: str):
        """Record a write for read-your-writes tracking (Redis-backed)."""
        if self._redis:
            try:
                await self._redis.set(
                    f"ryw:{tenant_id}", "1",
                    ex=int(self.WRITER_STICKY_SEC))
                return
            except Exception as e:
                logger.warning(f"Redis record_write failed, using in-memory: {e}")
        # Fallback: in-memory
        now = time.time()
        if len(self._recent_writers) >= self.MAX_RECENT_WRITERS:
            self._cleanup_recent_writers(now)
            if len(self._recent_writers) >= self.MAX_RECENT_WRITERS:
                oldest = min(self._recent_writers, key=self._recent_writers.get)
                del self._recent_writers[oldest]
        self._recent_writers[tenant_id] = now

    async def should_route_to_primary(self, tenant_id: str) -> bool:
        """Check if a tenant's reads should go to primary (read-your-writes)."""
        if self._redis:
            try:
                return bool(await self._redis.exists(f"ryw:{tenant_id}"))
            except Exception as e:
                logger.warning(f"Redis should_route_to_primary failed, using in-memory: {e}")
        # Fallback: in-memory
        ts = self._recent_writers.get(tenant_id)
        if ts and (time.time() - ts) < self.WRITER_STICKY_SEC:
            return True
        if ts:
            del self._recent_writers[tenant_id]
        return False

    async def route(self, query: str, tenant_id: Optional[str] = None,
                    force: Optional[ReadWriteSplit] = None) -> ReplicaNode:
        """Route query to appropriate node.

        This is async because read-your-writes checks may hit Redis.
        """
        self._query_count += 1

        # Periodic cleanup of expired writer entries (every 30s)
        now = time.time()
        if now - self._last_cleanup > 30:
            self._cleanup_recent_writers(now)

        if force == ReadWriteSplit.PRIMARY or not self._replicas:
            self._read_from_primary += 1
            return self._primary

        # Writes always go to primary
        query_upper = query.strip().upper()
        if any(query_upper.startswith(kw) for kw in
               ("INSERT", "UPDATE", "DELETE", "CREATE", "ALTER", "DROP",
                "TRUNCATE", "GRANT", "REVOKE", "SET")):
            await self.record_write(tenant_id) if tenant_id else None
            self._read_from_primary += 1
            return self._primary

        # Read-your-writes: check Redis first, then in-memory fallback
        if tenant_id and await self.should_route_to_primary(tenant_id):
            self._read_from_primary += 1
            return self._primary

        # Select replica
        if force == ReadWriteSplit.NEAREST:
            node = self._nearest_replica()
        elif force == ReadWriteSplit.RANDOM:
            node = random.choice(self._replicas)
        else:
            node = self._round_robin_replica()

        self._read_from_replica += 1
        return node

    def _cleanup_recent_writers(self, now: float):
        """Remove expired entries from the recent writers dict."""
        expired = [tid for tid, ts in self._recent_writers.items()
                   if now - ts >= self.WRITER_STICKY_SEC]
        for tid in expired:
            del self._recent_writers[tid]
        self._last_cleanup = now

    def _round_robin_replica(self) -> ReplicaNode:
        """Round-robin across healthy, non-lagging replicas."""
        healthy = [r for r in self._replicas
                   if r.healthy and not r.is_lagging]
        if not healthy:
            healthy = [r for r in self._replicas if r.healthy]
        if not healthy:
            return self._primary

        # Modulo first, then increment — ensures we always pick a valid index
        # even when the healthy list size changes between calls.
        idx = self._round_robin_idx % len(healthy)
        self._round_robin_idx = idx + 1
        return healthy[idx]

    def _nearest_replica(self) -> ReplicaNode:
        """Select replica with lowest latency."""
        healthy = [r for r in self._replicas if r.healthy]
        if not healthy:
            return self._primary
        return min(healthy, key=lambda r: r.latency_ms)

    async def check_replica_lag(self) -> List[Dict]:
        """Check replication lag on all replicas."""
        engine = self.engines.get("relational")
        if not engine:
            return []

        results = []
        for replica in self._replicas:
            try:
                # This query runs on the replica to check its lag
                lag = await engine.execute(
                    "SELECT CASE WHEN pg_last_wal_receive_lsn() = pg_last_wal_replay_lsn() "
                    "THEN 0 ELSE EXTRACT(EPOCH FROM NOW() - pg_last_xact_replay_timestamp()) * 1000 "
                    "END AS lag_ms")
                if lag:
                    replica.lag_ms = float(lag[0].get("lag_ms", 0))
                    replica.healthy = replica.lag_ms < self.LAG_THRESHOLD_MS * 5
                results.append({
                    "host": replica.host, "lag_ms": replica.lag_ms,
                    "healthy": replica.healthy,
                })
            except Exception as e:
                replica.healthy = False
                results.append({
                    "host": replica.host, "error": str(e), "healthy": False,
                })

        return results

    async def get_pool_stats(self) -> Dict:
        """Get PgBouncer connection pool statistics."""
        engine = self.engines.get("relational")
        if not engine:
            return {}

        try:
            # PgBouncer admin interface
            pools = await engine.execute("SHOW POOLS")
            stats = await engine.execute("SHOW STATS")
            return {"pools": pools or [], "stats": stats or []}
        except Exception:
            # PgBouncer not available, return engine-level stats
            return {
                "primary": {
                    "host": self._primary.host if self._primary else "none",
                    "connections_active": self._primary.connections_active if self._primary else 0,
                },
                "replicas": [{
                    "host": r.host, "connections_active": r.connections_active,
                    "lag_ms": r.lag_ms, "healthy": r.healthy,
                } for r in self._replicas],
            }

    def get_stats(self) -> Dict:
        return {
            "total_queries": self._query_count,
            "reads_from_primary": self._read_from_primary,
            "reads_from_replica": self._read_from_replica,
            "replica_count": len(self._replicas),
            "healthy_replicas": sum(1 for r in self._replicas if r.healthy),
            "recent_writers": len(self._recent_writers),
        }
