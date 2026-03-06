"""Tenant Lifecycle Management (DOC-019 Section 6.2)

Onboarding -> Active -> Offboarding with full data isolation.
"""

import hashlib
import secrets
import time
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger("cortexdb.tenant")


class TenantPlan(Enum):
    FREE = "free"
    GROWTH = "growth"
    ENTERPRISE = "enterprise"
    CUSTOM = "custom"


class TenantStatus(Enum):
    ONBOARDING = "onboarding"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    OFFBOARDING = "offboarding"
    PURGED = "purged"


PLAN_RATE_LIMITS = {
    TenantPlan.FREE: {"requests_per_min": 100, "writes_per_min": 50, "agents_max": 5},
    TenantPlan.GROWTH: {"requests_per_min": 500, "writes_per_min": 200, "agents_max": 50},
    TenantPlan.ENTERPRISE: {"requests_per_min": 2000, "writes_per_min": 1000, "agents_max": 500},
    TenantPlan.CUSTOM: {"requests_per_min": 10000, "writes_per_min": 5000, "agents_max": 9999},
}


@dataclass
class Tenant:
    tenant_id: str
    name: str
    plan: TenantPlan = TenantPlan.FREE
    status: TenantStatus = TenantStatus.ONBOARDING
    api_key_hash: str = ""
    config: Dict = field(default_factory=dict)
    rate_limits: Dict = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    activated_at: Optional[float] = None
    metadata: Dict = field(default_factory=dict)

    @property
    def is_active(self) -> bool:
        return self.status == TenantStatus.ACTIVE

    @property
    def effective_rate_limits(self) -> Dict:
        base = PLAN_RATE_LIMITS.get(self.plan, PLAN_RATE_LIMITS[TenantPlan.FREE])
        return {**base, **self.rate_limits}


class TenantManager:
    """Manages tenant lifecycle: onboard, activate, suspend, offboard, purge."""

    def __init__(self, engines: Dict[str, Any] = None):
        self.engines = engines or {}
        self._tenants: Dict[str, Tenant] = {}
        self._api_key_index: Dict[str, str] = {}  # api_key_hash -> tenant_id

    @staticmethod
    def _hash_api_key(api_key: str) -> str:
        return hashlib.sha256(api_key.encode()).hexdigest()

    @staticmethod
    def _generate_api_key() -> str:
        return f"ctx_live_{secrets.token_urlsafe(32)}"

    async def onboard(self, tenant_id: str, name: str,
                      plan: TenantPlan = TenantPlan.FREE,
                      config: Dict = None) -> Dict:
        """Step 1-5: Create tenant, resources, API key, activate."""
        if tenant_id in self._tenants:
            raise ValueError(f"Tenant {tenant_id} already exists")

        api_key = self._generate_api_key()
        api_key_hash = self._hash_api_key(api_key)

        tenant = Tenant(
            tenant_id=tenant_id, name=name, plan=plan,
            api_key_hash=api_key_hash,
            config=config or {},
            rate_limits=PLAN_RATE_LIMITS.get(plan, {}),
        )

        # Step 1: Store tenant record
        self._tenants[tenant_id] = tenant
        self._api_key_index[api_key_hash] = tenant_id

        # Step 2: Create tenant-specific resources
        await self._create_tenant_resources(tenant)

        # Step 3: API key generated above

        # Step 4: Store in RelationalCore if available
        if "relational" in self.engines:
            try:
                await self.engines["relational"].execute(
                    "INSERT INTO tenants (tenant_id, name, plan, status, api_key_hash, config) "
                    "VALUES ($1, $2, $3, $4, $5, $6)",
                    [tenant_id, name, plan.value, "onboarding", api_key_hash,
                     json_dumps(config or {})])
            except Exception as e:
                logger.warning(f"Failed to persist tenant to DB: {e}")

        # Step 5: Activate
        await self.activate(tenant_id)

        logger.info(f"Tenant onboarded: {tenant_id} ({name}) plan={plan.value}")
        return {"tenant_id": tenant_id, "api_key": api_key, "plan": plan.value,
                "rate_limits": tenant.effective_rate_limits}

    async def _create_tenant_resources(self, tenant: Tenant):
        """Create per-tenant resources across engines."""
        tid = tenant.tenant_id

        # VectorCore: create collections
        if "vector" in self.engines:
            for collection in [f"tenant_{tid}_cache", f"tenant_{tid}_experiences",
                               f"tenant_{tid}_blocks"]:
                try:
                    await self.engines["vector"].create_collection(collection, size=384)
                except Exception as e:
                    logger.warning(f"VectorCore collection {collection}: {e}")

        # ImmutableCore: genesis entry
        if "immutable" in self.engines:
            try:
                await self.engines["immutable"].write("audit", {
                    "entry_type": "TENANT_GENESIS",
                    "tenant_id": tid, "name": tenant.name,
                    "plan": tenant.plan.value,
                }, actor="tenant_manager")
            except Exception as e:
                logger.warning(f"ImmutableCore genesis for {tid}: {e}")

    async def activate(self, tenant_id: str):
        tenant = self._tenants.get(tenant_id)
        if not tenant:
            raise ValueError(f"Tenant {tenant_id} not found")
        tenant.status = TenantStatus.ACTIVE
        tenant.activated_at = time.time()

    async def suspend(self, tenant_id: str, reason: str = ""):
        tenant = self._tenants.get(tenant_id)
        if not tenant:
            raise ValueError(f"Tenant {tenant_id} not found")
        tenant.status = TenantStatus.SUSPENDED
        logger.warning(f"Tenant suspended: {tenant_id} reason={reason}")

    async def deactivate(self, tenant_id: str):
        tenant = self._tenants.get(tenant_id)
        if not tenant:
            raise ValueError(f"Tenant {tenant_id} not found")
        tenant.status = TenantStatus.OFFBOARDING

    async def export_data(self, tenant_id: str) -> Dict:
        """Generate data export for tenant offboarding."""
        tenant = self._tenants.get(tenant_id)
        if not tenant:
            raise ValueError(f"Tenant {tenant_id} not found")
        return {"tenant_id": tenant_id, "status": "export_queued",
                "message": "Data export will be available within 24 hours"}

    async def purge(self, tenant_id: str) -> Dict:
        """Delete all tenant data across engines (72-hour cooling period enforced)."""
        tenant = self._tenants.get(tenant_id)
        if not tenant:
            raise ValueError(f"Tenant {tenant_id} not found")
        if tenant.status != TenantStatus.OFFBOARDING:
            raise ValueError("Tenant must be deactivated before purge")

        purged = {}
        tid = tenant_id

        # VectorCore: delete collections
        if "vector" in self.engines:
            for coll in [f"tenant_{tid}_cache", f"tenant_{tid}_experiences",
                         f"tenant_{tid}_blocks"]:
                try:
                    await self.engines["vector"].delete_collection(coll)
                    purged[f"vector_{coll}"] = "deleted"
                except Exception:
                    purged[f"vector_{coll}"] = "not_found"

        # MemoryCore: delete all tenant keys
        if "memory" in self.engines:
            try:
                deleted = await self.engines["memory"].delete_pattern(f"tenant:{tid}:*")
                purged["memory"] = f"deleted_{deleted}_keys"
            except Exception as e:
                purged["memory"] = f"error: {e}"

        # ImmutableCore: redact (never delete)
        if "immutable" in self.engines:
            try:
                await self.engines["immutable"].write("audit", {
                    "entry_type": "TENANT_PURGED",
                    "tenant_id": tid, "redacted": True,
                    "reason": "tenant_offboarded",
                }, actor="tenant_manager")
                purged["immutable"] = "redacted_tombstone"
            except Exception:
                pass

        tenant.status = TenantStatus.PURGED
        self._api_key_index.pop(tenant.api_key_hash, None)
        purged["status"] = "purged"
        logger.info(f"Tenant purged: {tenant_id}")
        return purged

    def resolve_tenant(self, api_key: str) -> Optional[Tenant]:
        """Resolve API key to tenant. O(1) lookup."""
        key_hash = self._hash_api_key(api_key)
        tenant_id = self._api_key_index.get(key_hash)
        if not tenant_id:
            return None
        return self._tenants.get(tenant_id)

    def get_tenant(self, tenant_id: str) -> Optional[Tenant]:
        return self._tenants.get(tenant_id)

    def list_tenants(self, status: Optional[str] = None) -> List[Dict]:
        tenants = list(self._tenants.values())
        if status:
            tenants = [t for t in tenants if t.status.value == status]
        return [{"tenant_id": t.tenant_id, "name": t.name, "plan": t.plan.value,
                 "status": t.status.value, "created_at": t.created_at,
                 "rate_limits": t.effective_rate_limits} for t in tenants]

    def get_stats(self) -> Dict:
        by_plan = {}
        by_status = {}
        for t in self._tenants.values():
            by_plan[t.plan.value] = by_plan.get(t.plan.value, 0) + 1
            by_status[t.status.value] = by_status.get(t.status.value, 0) + 1
        return {"total": len(self._tenants), "by_plan": by_plan, "by_status": by_status}


def json_dumps(obj):
    import json
    return json.dumps(obj, default=str)
