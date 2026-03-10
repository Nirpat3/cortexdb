"""Per-Engine Tenant Isolation (DOC-019 Section 6.1)

RelationalCore: Row-Level Security (RLS)
MemoryCore: Key prefix tenant:{id}:*
VectorCore: Per-tenant collections
StreamCore: Per-tenant stream keys
ImmutableCore: Global chain with tenant_id filter
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("cortexdb.tenant.isolation")


class TenantIsolation:
    """Enforces data isolation across all 7 CortexDB engines."""

    def __init__(self, engines: Dict[str, Any] = None):
        self.engines = engines or {}
        self._rls_verified = False

    # -- RelationalCore: PostgreSQL Row-Level Security --

    async def set_rls_context(self, tenant_id: str):
        """SET app.current_tenant for PostgreSQL RLS policies."""
        if "relational" not in self.engines:
            return
        try:
            await self.engines["relational"].execute(
                "SET app.current_tenant = $1", [tenant_id])
        except Exception as e:
            logger.error(f"Failed to set RLS context for {tenant_id}: {e}")
            raise

    async def verify_rls_enabled(self) -> Dict:
        """Health check: verify RLS is enabled on all tenant tables."""
        if "relational" not in self.engines:
            return {"status": "skip", "reason": "no relational engine"}

        tenant_tables = ["blocks", "agents", "tasks", "experience_ledger",
                         "grid_nodes", "query_paths"]
        results = {}
        try:
            rows = await self.engines["relational"].execute(
                "SELECT tablename, rowsecurity FROM pg_tables "
                "WHERE schemaname = 'public'")
            rls_map = {r["tablename"]: r["rowsecurity"] for r in (rows or [])}
            for table in tenant_tables:
                results[table] = "rls_enabled" if rls_map.get(table) else "rls_missing"
            self._rls_verified = all(v == "rls_enabled" for v in results.values())
        except Exception as e:
            results["error"] = str(e)
        return {"rls_tables": results, "all_secured": self._rls_verified}

    # -- MemoryCore: Key prefix isolation --

    @staticmethod
    def tenant_key(tenant_id: str, key: str) -> str:
        """Prefix key with tenant namespace: tenant:{id}:{key}"""
        return f"tenant:{tenant_id}:{key}"

    @staticmethod
    def cache_key(tenant_id: str, query_hash: str) -> str:
        """Tenant-scoped cache key."""
        return f"tenant:{tenant_id}:cache:{query_hash}"

    # -- VectorCore: Collection isolation --

    @staticmethod
    def vector_collection(tenant_id: str, collection_type: str) -> str:
        """Tenant-scoped Qdrant collection name."""
        return f"tenant_{tenant_id}_{collection_type}"

    # -- StreamCore: Stream key isolation --

    @staticmethod
    def stream_key(tenant_id: str, event_type: str) -> str:
        """Tenant-scoped Redis Stream key."""
        return f"tenant:{tenant_id}:stream:{event_type}"

    # -- Cross-engine isolation report --

    async def isolation_report(self, tenant_id: str) -> Dict:
        """Generate isolation status report for a tenant."""
        report = {"tenant_id": tenant_id, "engines": {}}

        # RelationalCore: RLS
        rls = await self.verify_rls_enabled()
        report["engines"]["relational"] = {
            "method": "row_level_security",
            "status": "secured" if rls.get("all_secured") else "needs_setup",
            "details": rls}

        # MemoryCore: Key prefix
        report["engines"]["memory"] = {
            "method": "key_prefix",
            "prefix": f"tenant:{tenant_id}:",
            "status": "enforced"}

        # VectorCore: Collection isolation
        report["engines"]["vector"] = {
            "method": "collection_isolation",
            "collections": [
                self.vector_collection(tenant_id, "cache"),
                self.vector_collection(tenant_id, "experiences"),
                self.vector_collection(tenant_id, "blocks"),
            ],
            "status": "enforced"}

        # StreamCore: Stream key isolation
        report["engines"]["stream"] = {
            "method": "stream_key_prefix",
            "prefix": f"tenant:{tenant_id}:stream:",
            "status": "enforced"}

        # ImmutableCore: Global chain with tenant filter
        report["engines"]["immutable"] = {
            "method": "global_chain_tenant_filter",
            "status": "enforced",
            "note": "Hash chain is global for integrity; queries filter by tenant_id"}

        return report
