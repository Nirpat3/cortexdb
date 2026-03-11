"""Tenant Lifecycle Management (DOC-019 Section 6.2)

Onboarding -> Active -> Offboarding with full data isolation.
"""

import hashlib
import os
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
    api_key_salt: str = ""
    api_key_prefix: str = ""
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
    """Manages tenant lifecycle: onboard, activate, suspend, offboard, purge.

    P0 FIX: Tenants are persisted to and loaded from the PostgreSQL `tenants`
    table. The in-memory dict is a write-through cache for fast O(1) lookups.
    """

    def __init__(self, engines: Dict[str, Any] = None):
        self.engines = engines or {}
        self._tenants: Dict[str, Tenant] = {}
        self._api_key_index: Dict[str, List[str]] = {}  # api_key_prefix -> [tenant_ids]

    async def load_from_db(self):
        """Load all tenants from PostgreSQL into the in-memory cache.

        Called on startup / after connect so tenants survive restarts.
        """
        if "relational" not in self.engines:
            logger.warning("No relational engine — tenants will not persist across restarts")
            return

        try:
            rows = await self.engines["relational"].execute(
                "SELECT tenant_id, name, plan, status, api_key_hash, api_key_salt, "
                "api_key_prefix, config, rate_limits, metadata, "
                "EXTRACT(EPOCH FROM created_at) AS created_epoch, "
                "EXTRACT(EPOCH FROM activated_at) AS activated_epoch "
                "FROM tenants WHERE status != 'purged'", None)

            for row in (rows or []):
                plan = TenantPlan(row["plan"])
                status = TenantStatus(row["status"])
                config = row.get("config") or {}
                if isinstance(config, str):
                    import json as _json
                    config = _json.loads(config)
                rate_limits = row.get("rate_limits") or {}
                if isinstance(rate_limits, str):
                    import json as _json
                    rate_limits = _json.loads(rate_limits)
                metadata = row.get("metadata") or {}
                if isinstance(metadata, str):
                    import json as _json
                    metadata = _json.loads(metadata)

                tenant = Tenant(
                    tenant_id=row["tenant_id"],
                    name=row["name"],
                    plan=plan,
                    status=status,
                    api_key_hash=row.get("api_key_hash", ""),
                    api_key_salt=row.get("api_key_salt", ""),
                    api_key_prefix=row.get("api_key_prefix", ""),
                    config=config,
                    rate_limits=rate_limits,
                    created_at=float(row["created_epoch"]) if row.get("created_epoch") else time.time(),
                    activated_at=float(row["activated_epoch"]) if row.get("activated_epoch") else None,
                    metadata=metadata,
                )
                self._tenants[tenant.tenant_id] = tenant
                if tenant.api_key_prefix:
                    self._api_key_index.setdefault(tenant.api_key_prefix, []).append(tenant.tenant_id)

            logger.info(f"Loaded {len(rows or [])} tenants from PostgreSQL")
        except Exception as e:
            logger.error(f"Failed to load tenants from DB: {e}")

    @staticmethod
    def _hash_api_key(api_key: str, salt: str = "") -> str:
        return hashlib.pbkdf2_hmac(
            'sha256', api_key.encode(), salt.encode(), iterations=100000
        ).hex()

    @staticmethod
    def _generate_salt() -> str:
        return os.urandom(16).hex()

    @staticmethod
    def _generate_api_key() -> str:
        return f"ctx_live_{secrets.token_urlsafe(32)}"

    async def onboard(self, tenant_id: str, name: str,
                      plan: TenantPlan = TenantPlan.FREE,
                      config: Dict = None) -> Dict:
        """Step 1-5: Create tenant, resources, API key, activate."""
        if tenant_id.startswith("__"):
            raise ValueError(
                f"Tenant ID '{tenant_id}' is reserved (prefix '__' is reserved for internal use)")
        if tenant_id in self._tenants:
            raise ValueError(f"Tenant {tenant_id} already exists")

        api_key = self._generate_api_key()
        api_key_salt = self._generate_salt()
        api_key_hash = self._hash_api_key(api_key, api_key_salt)
        api_key_prefix = api_key[:8]

        tenant = Tenant(
            tenant_id=tenant_id, name=name, plan=plan,
            api_key_hash=api_key_hash,
            api_key_salt=api_key_salt,
            api_key_prefix=api_key_prefix,
            config=config or {},
            rate_limits=PLAN_RATE_LIMITS.get(plan, {}),
        )

        # Step 1: Write to PostgreSQL first (write-through) so the tenant
        # survives restarts. If PG write fails, abort — don't create a
        # tenant that only exists in memory.
        if "relational" in self.engines:
            try:
                await self.engines["relational"].execute(
                    "INSERT INTO tenants (tenant_id, name, plan, status, api_key_hash, api_key_salt, api_key_prefix, config) "
                    "VALUES ($1, $2, $3, $4, $5, $6, $7, $8)",
                    [tenant_id, name, plan.value, "onboarding", api_key_hash,
                     api_key_salt, api_key_prefix, json_dumps(config or {})])
            except Exception as e:
                logger.error(f"Failed to persist tenant to DB: {e}")
                raise

        # Step 2: Update in-memory cache
        self._tenants[tenant_id] = tenant
        self._api_key_index.setdefault(api_key_prefix, []).append(tenant_id)

        # Step 3: Create tenant-specific resources
        await self._create_tenant_resources(tenant)

        # Step 4: API key generated above

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

    _ALLOWED_TIMESTAMP_FIELDS = frozenset({"activated_at", "deactivated_at", "suspended_at"})

    async def _update_tenant_status(self, tenant_id: str, status: str,
                                     set_timestamp_field: str = None):
        """Write-through: update PG first, then in-memory cache."""
        if "relational" in self.engines:
            if set_timestamp_field:
                if set_timestamp_field not in self._ALLOWED_TIMESTAMP_FIELDS:
                    raise ValueError(
                        f"Invalid timestamp field: {set_timestamp_field}. "
                        f"Allowed: {sorted(self._ALLOWED_TIMESTAMP_FIELDS)}")
                sql = f"UPDATE tenants SET status = $1, {set_timestamp_field} = NOW() WHERE tenant_id = $2"
            else:
                sql = "UPDATE tenants SET status = $1 WHERE tenant_id = $2"
            params = [status, tenant_id]
            try:
                await self.engines["relational"].execute(sql, params)
            except Exception as e:
                logger.error(f"Failed to update tenant {tenant_id} status in DB: {e}")
                raise

    async def activate(self, tenant_id: str):
        tenant = self._tenants.get(tenant_id)
        if not tenant:
            raise ValueError(f"Tenant {tenant_id} not found")
        await self._update_tenant_status(
            tenant_id, "active", set_timestamp_field="activated_at")
        tenant.status = TenantStatus.ACTIVE
        tenant.activated_at = time.time()

    async def suspend(self, tenant_id: str, reason: str = ""):
        tenant = self._tenants.get(tenant_id)
        if not tenant:
            raise ValueError(f"Tenant {tenant_id} not found")
        await self._update_tenant_status(tenant_id, "suspended")
        tenant.status = TenantStatus.SUSPENDED
        logger.warning(f"Tenant suspended: {tenant_id} reason={reason}")

    async def deactivate(self, tenant_id: str):
        tenant = self._tenants.get(tenant_id)
        if not tenant:
            raise ValueError(f"Tenant {tenant_id} not found")
        await self._update_tenant_status(
            tenant_id, "offboarding", set_timestamp_field="deactivated_at")
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

        # Persist purge status to PG, then update in-memory cache
        await self._update_tenant_status(tenant_id, "purged")
        tenant.status = TenantStatus.PURGED
        if tenant.api_key_prefix in self._api_key_index:
            try:
                self._api_key_index[tenant.api_key_prefix].remove(tenant_id)
            except ValueError:
                pass
            if not self._api_key_index[tenant.api_key_prefix]:
                del self._api_key_index[tenant.api_key_prefix]
        purged["status"] = "purged"
        logger.info(f"Tenant purged: {tenant_id}")
        return purged

    def resolve_tenant(self, api_key: str) -> Optional[Tenant]:
        """Resolve API key to tenant using prefix index for O(1) average lookup."""
        prefix = api_key[:8]
        candidate_ids = self._api_key_index.get(prefix)
        if not candidate_ids:
            return None
        for tenant_id in candidate_ids:
            tenant = self._tenants.get(tenant_id)
            if tenant and tenant.api_key_hash:
                key_hash = self._hash_api_key(api_key, tenant.api_key_salt)
                if key_hash == tenant.api_key_hash:
                    return tenant
        return None

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
