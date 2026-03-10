"""Citus-Based Horizontal Sharding at Petabyte Scale

Citus transforms PostgreSQL into a distributed database by:
  1. Distributing tables across worker nodes using a distribution column
  2. Co-locating related tables on the same shard (no cross-shard joins)
  3. Reference tables replicated to all nodes (small lookup tables)
  4. Transparent query routing - SQL just works

CortexDB sharding strategy:
  - Distribution column: tenant_id (multi-tenant isolation + performance)
  - Co-located tables: customers, customer_identifiers, customer_events,
    customer_profiles, blocks, agents, tasks (all on same tenant shard)
  - Reference tables: tenants, asa_standards (small, replicated everywhere)
  - Shard count: 128 default (supports up to 128 worker nodes)
"""

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger("cortexdb.scale.sharding")


class ShardStrategy(Enum):
    HASH = "hash"           # Hash-based distribution (default, even spread)
    RANGE = "range"         # Range-based (time-series, geo-partitioning)
    APPEND = "append"       # Append-only (immutable ledger, logs)
    REFERENCE = "reference" # Replicated to all nodes (small lookup tables)


@dataclass
class ShardInfo:
    shard_id: int
    table_name: str
    node_name: str
    node_port: int
    row_count: int = 0
    size_bytes: int = 0
    tenant_id: Optional[str] = None


@dataclass
class RebalanceResult:
    moved: int = 0
    skipped: int = 0
    errors: int = 0
    duration_ms: float = 0
    details: List[Dict] = field(default_factory=list)


# Tables and their sharding configuration
DISTRIBUTED_TABLES = {
    # CortexGraph tables (DOC-020)
    "customers": {"column": "tenant_id", "colocate": "cortexgraph"},
    "customer_identifiers": {"column": "tenant_id", "colocate": "cortexgraph"},
    "customer_events": {"column": "tenant_id", "colocate": "cortexgraph"},
    "customer_profiles": {"column": "tenant_id", "colocate": "cortexgraph"},
    "customer_merges": {"column": "tenant_id", "colocate": "cortexgraph"},
    # Core tables
    "blocks": {"column": "tenant_id", "colocate": "core"},
    "agents": {"column": "tenant_id", "colocate": "core"},
    "tasks": {"column": "tenant_id", "colocate": "core"},
    "experience_ledger": {"column": "tenant_id", "colocate": "core"},
    # A2A tables
    "a2a_agent_cards": {"column": "tenant_id", "colocate": "a2a"},
    "a2a_tasks": {"column": "tenant_id", "colocate": "a2a"},
    # Observability
    "heartbeats": {"column": "node_id", "colocate": None, "strategy": "append"},
    "agent_metrics": {"column": "agent_id", "colocate": None, "strategy": "append"},
    "query_metrics": {"column": "query_hash", "colocate": None, "strategy": "append"},
    # Immutable
    "immutable_ledger": {"column": "entry_type", "colocate": None, "strategy": "append"},
}

REFERENCE_TABLES = [
    "tenants",
    "asa_standards",
    "grid_nodes",
    "grid_links",
    "query_paths",
    "response_cache_meta",
    "rate_limit_log",
]


class CitusShardManager:
    """Manages Citus distributed tables, shard placement, and rebalancing.

    Architecture:
      Coordinator (1 node) -> Workers (N nodes)
      - Coordinator: receives queries, plans distribution, merges results
      - Workers: store shard data, execute shard-local queries
      - Each tenant's data co-located on same worker (no cross-shard joins)

    Scaling:
      - Add workers dynamically: add_worker()
      - Rebalance shards: rebalance()
      - Monitor shard health: get_shard_stats()
    """

    DEFAULT_SHARD_COUNT = 128
    MAX_SHARD_REPLICATION = 2

    def __init__(self, engines: Dict[str, Any] = None):
        self.engines = engines or {}
        self._initialized = False
        self._workers: List[Dict] = []
        self._shard_count = self.DEFAULT_SHARD_COUNT

    async def initialize(self) -> Dict:
        """Initialize Citus extension and configure sharding."""
        if "relational" not in self.engines:
            return {"status": "error", "error": "RelationalCore not available"}

        results = {"status": "initializing", "steps": []}
        engine = self.engines["relational"]

        # Step 1: Create Citus extension
        try:
            await engine.execute("CREATE EXTENSION IF NOT EXISTS citus")
            results["steps"].append({"step": "create_extension", "status": "ok"})
        except Exception as e:
            results["status"] = "error"
            results["error"] = f"Citus extension not available: {e}"
            logger.warning(f"Citus not available: {e}. Sharding disabled.")
            return results

        # Step 2: Set coordinator
        try:
            await engine.execute(
                "SELECT citus_set_coordinator_host('localhost', 5432)")
            results["steps"].append({"step": "set_coordinator", "status": "ok"})
        except Exception as e:
            logger.warning(f"Coordinator setup: {e}")

        # Step 3: Configure shard settings
        try:
            await engine.execute(
                f"SET citus.shard_count = {self._shard_count}")
            await engine.execute(
                f"SET citus.shard_replication_factor = {self.MAX_SHARD_REPLICATION}")
            results["steps"].append({"step": "configure_shards", "status": "ok",
                                     "shard_count": self._shard_count})
        except Exception as e:
            logger.warning(f"Shard config: {e}")

        self._initialized = True
        results["status"] = "initialized"
        logger.info(f"Citus sharding initialized: {self._shard_count} shards")
        return results

    async def distribute_tables(self) -> Dict:
        """Distribute all CortexDB tables across workers."""
        if not self._initialized:
            await self.initialize()

        engine = self.engines.get("relational")
        if not engine:
            return {"error": "RelationalCore not available"}

        results = {"distributed": [], "reference": [], "errors": []}

        # Reference tables first (replicated to all nodes)
        for table in REFERENCE_TABLES:
            try:
                await engine.execute(
                    f"SELECT create_reference_table('{table}')")
                results["reference"].append(table)
            except Exception as e:
                if "already distributed" not in str(e).lower():
                    results["errors"].append({"table": table, "error": str(e)})

        # Distributed tables with co-location groups
        colocation_groups = {}
        for table, config in DISTRIBUTED_TABLES.items():
            col = config["column"]
            colocate = config.get("colocate")
            strategy = config.get("strategy", "hash")

            try:
                if strategy == "append":
                    await engine.execute(
                        f"SELECT create_distributed_table('{table}', '{col}', "
                        f"colocate_with => 'none', distribution_type => 'append')")
                elif colocate and colocate in colocation_groups:
                    # Co-locate with existing group
                    ref_table = colocation_groups[colocate]
                    await engine.execute(
                        f"SELECT create_distributed_table('{table}', '{col}', "
                        f"colocate_with => '{ref_table}')")
                else:
                    await engine.execute(
                        f"SELECT create_distributed_table('{table}', '{col}')")
                    if colocate:
                        colocation_groups[colocate] = table

                results["distributed"].append({"table": table, "column": col,
                                                "colocate": colocate})
            except Exception as e:
                if "already distributed" not in str(e).lower():
                    results["errors"].append({"table": table, "error": str(e)})

        logger.info(f"Distributed {len(results['distributed'])} tables, "
                    f"{len(results['reference'])} reference tables")
        return results

    async def add_worker(self, host: str, port: int = 5432) -> Dict:
        """Add a Citus worker node to the cluster."""
        engine = self.engines.get("relational")
        if not engine:
            return {"error": "RelationalCore not available"}

        try:
            await engine.execute(
                "SELECT citus_add_node($1, $2)", [host, port])
            worker = {"host": host, "port": port, "added_at": time.time()}
            self._workers.append(worker)
            logger.info(f"Worker added: {host}:{port}")
            return {"status": "added", "worker": worker}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    async def remove_worker(self, host: str, port: int = 5432) -> Dict:
        """Remove a worker node (drains shards first)."""
        engine = self.engines.get("relational")
        if not engine:
            return {"error": "RelationalCore not available"}

        try:
            # Drain shards before removal
            await engine.execute(
                "SELECT citus_drain_node($1, $2)", [host, port])
            await engine.execute(
                "SELECT citus_remove_node($1, $2)", [host, port])
            self._workers = [w for w in self._workers
                             if not (w["host"] == host and w["port"] == port)]
            return {"status": "removed", "host": host, "port": port}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    async def rebalance(self) -> RebalanceResult:
        """Rebalance shards across workers for even distribution."""
        engine = self.engines.get("relational")
        result = RebalanceResult()
        start = time.perf_counter()

        if not engine:
            result.errors = 1
            return result

        try:
            await engine.execute("SELECT citus_rebalance_start()")
            # Poll for completion
            for _ in range(300):  # 5 min max
                status = await engine.execute(
                    "SELECT * FROM citus_rebalance_status()")
                if not status or status[0].get("status") == "completed":
                    break
                await __import__("asyncio").sleep(1)

            result.duration_ms = (time.perf_counter() - start) * 1000
            logger.info(f"Rebalance completed in {result.duration_ms:.0f}ms")
        except Exception as e:
            result.errors = 1
            result.details.append({"error": str(e)})

        return result

    async def get_shard_stats(self) -> Dict:
        """Get shard distribution statistics."""
        engine = self.engines.get("relational")
        if not engine:
            return {"error": "RelationalCore not available"}

        try:
            # Shard sizes per table
            table_stats = await engine.execute("""
                SELECT logicalrelid::text AS table_name,
                       COUNT(*) AS shard_count,
                       SUM(pg_total_relation_size(shardid::text || '_' ||
                           logicalrelid::text)) AS total_bytes
                FROM pg_dist_shard
                GROUP BY logicalrelid
                ORDER BY total_bytes DESC
            """) or []

            # Worker utilization
            worker_stats = await engine.execute("""
                SELECT nodename, nodeport,
                       COUNT(*) AS shard_count,
                       SUM(pg_total_relation_size(shardid::text || '_' ||
                           logicalrelid::text)) AS total_bytes
                FROM pg_dist_shard_placement
                JOIN pg_dist_shard USING (shardid)
                GROUP BY nodename, nodeport
            """) or []

            # Node health
            nodes = await engine.execute(
                "SELECT * FROM citus_get_active_worker_nodes()") or []

            return {
                "tables": table_stats,
                "workers": worker_stats,
                "active_nodes": len(nodes),
                "total_shards": self._shard_count,
                "colocation_groups": len(set(
                    c.get("colocate") for c in DISTRIBUTED_TABLES.values() if c.get("colocate")
                )),
            }
        except Exception as e:
            return {"error": str(e)}

    async def get_tenant_placement(self, tenant_id: str) -> Dict:
        """Find which worker node hosts a specific tenant's data."""
        engine = self.engines.get("relational")
        if not engine:
            return {"error": "RelationalCore not available"}

        try:
            result = await engine.execute("""
                SELECT nodename, nodeport, shardid
                FROM citus_find_shard_interval_minimum('customers', $1::text)
            """, [tenant_id])
            return {"tenant_id": tenant_id, "placement": result}
        except Exception as e:
            return {"tenant_id": tenant_id, "error": str(e)}

    async def isolate_tenant(self, tenant_id: str) -> Dict:
        """Isolate a tenant onto dedicated shard(s) for premium performance."""
        engine = self.engines.get("relational")
        if not engine:
            return {"error": "RelationalCore not available"}

        try:
            await engine.execute(
                "SELECT citus_move_shard_placement("
                "  (SELECT shardid FROM pg_dist_shard WHERE logicalrelid = 'customers'::regclass "
                "   AND shardminvalue <= hashtext($1)::text AND shardmaxvalue >= hashtext($1)::text "
                "   LIMIT 1), "
                "  source_node_name := (SELECT nodename FROM pg_dist_shard_placement LIMIT 1), "
                "  target_node_name := $2"
                ")", [tenant_id, f"dedicated-{tenant_id}"])
            return {"status": "isolated", "tenant_id": tenant_id}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    async def enable_columnar(self, table_name: str) -> Dict:
        """Convert a table to Citus columnar storage for analytics."""
        engine = self.engines.get("relational")
        if not engine:
            return {"error": "RelationalCore not available"}

        try:
            await engine.execute(
                f"SELECT alter_table_set_access_method('{table_name}', 'columnar')")
            return {"status": "converted", "table": table_name, "storage": "columnar"}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def get_stats(self) -> Dict:
        return {
            "initialized": self._initialized,
            "shard_count": self._shard_count,
            "workers": len(self._workers),
            "distributed_tables": len(DISTRIBUTED_TABLES),
            "reference_tables": len(REFERENCE_TABLES),
        }
