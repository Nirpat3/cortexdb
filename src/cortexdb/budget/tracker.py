"""
Budget Tracker — Tracks resource costs, tenant usage, and budget allocation.
Stores usage snapshots and provides real-time cost aggregation.
"""

import time
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass, field, asdict
from enum import Enum

logger = logging.getLogger(__name__)


class ResourceType(str, Enum):
    COMPUTE = "compute"
    STORAGE = "storage"
    NETWORK = "network"
    MEMORY = "memory"
    VECTOR_DB = "vector_db"
    BACKUP = "backup"


@dataclass
class ResourceBudget:
    resource: ResourceType
    allocated: float  # monthly budget in $
    used: float = 0.0
    unit_cost: float = 0.0  # cost per unit
    unit_name: str = "unit"

    @property
    def remaining(self) -> float:
        return max(0, self.allocated - self.used)

    @property
    def usage_pct(self) -> float:
        return (self.used / self.allocated * 100) if self.allocated > 0 else 0

    def to_dict(self) -> dict:
        return {**asdict(self), "remaining": self.remaining, "usage_pct": round(self.usage_pct, 1)}


@dataclass
class TenantCost:
    tenant_id: str
    tenant_name: str
    plan: str
    costs: Dict[str, float] = field(default_factory=dict)

    @property
    def total(self) -> float:
        return sum(self.costs.values())

    def to_dict(self) -> dict:
        return {"tenant_id": self.tenant_id, "tenant_name": self.tenant_name,
                "plan": self.plan, "costs": self.costs, "total": round(self.total, 2)}


@dataclass
class UsageSnapshot:
    timestamp: float
    resource: str
    value: float
    tenant_id: Optional[str] = None
    metadata: Dict = field(default_factory=dict)


class BudgetTracker:
    """Tracks resource budgets, tenant costs, and usage history."""

    def __init__(self):
        self._budgets: Dict[str, ResourceBudget] = {}
        self._tenant_costs: Dict[str, TenantCost] = {}
        self._usage_history: List[UsageSnapshot] = []
        self._monthly_totals: List[Dict] = []
        self._initialized = False

    async def initialize(self):
        """Initialize with default budgets and seed data."""
        if self._initialized:
            return

        # Default resource budgets
        defaults = [
            (ResourceType.COMPUTE, 5000, 0.05, "vCPU-hour"),
            (ResourceType.STORAGE, 2000, 0.023, "GB-month"),
            (ResourceType.NETWORK, 1500, 0.09, "GB-transfer"),
            (ResourceType.MEMORY, 1200, 0.01, "GB-hour"),
            (ResourceType.VECTOR_DB, 800, 0.10, "million-vectors"),
            (ResourceType.BACKUP, 600, 0.025, "GB-month"),
        ]
        for rt, allocated, unit_cost, unit_name in defaults:
            self._budgets[rt.value] = ResourceBudget(
                resource=rt, allocated=allocated, unit_cost=unit_cost, unit_name=unit_name
            )

        # Seed usage from simulated history
        self._seed_usage()
        self._initialized = True
        logger.info("BudgetTracker initialized with %d resource budgets", len(self._budgets))

    def _seed_usage(self):
        """Generate realistic historical usage data."""
        import random
        now = time.time()

        # Monthly totals (last 6 months)
        months = ["Oct", "Nov", "Dec", "Jan", "Feb", "Mar"]
        base_costs = [7200, 7800, 8100, 7600, 8310, 0]
        for i, (month, cost) in enumerate(zip(months, base_costs)):
            if month == "Mar":
                # Current month — partial, computed from actual usage
                continue
            self._monthly_totals.append({
                "month": month, "cost": cost,
                "breakdown": {
                    "compute": cost * 0.42,
                    "storage": cost * 0.18,
                    "network": cost * 0.12,
                    "memory": cost * 0.13,
                    "vector_db": cost * 0.08,
                    "backup": cost * 0.07,
                }
            })

        # Current month usage per resource
        usage_pcts = {"compute": 0.82, "storage": 0.67, "network": 0.59,
                      "memory": 0.82, "vector_db": 0.70, "backup": 0.70}
        for resource_key, pct in usage_pcts.items():
            if resource_key in self._budgets:
                self._budgets[resource_key].used = round(self._budgets[resource_key].allocated * pct, 2)

        # Tenant costs
        tenants = [
            ("acme-corp", "Acme Corp", "Enterprise", {"compute": 1200, "storage": 480, "network": 340, "memory": 420, "vector_db": 240, "backup": 160}),
            ("globex", "Globex Inc", "Business", {"compute": 680, "storage": 290, "network": 180, "memory": 240, "vector_db": 120, "backup": 110}),
            ("initech", "Initech", "Starter", {"compute": 180, "storage": 85, "network": 60, "memory": 80, "vector_db": 40, "backup": 35}),
            ("umbrella", "Umbrella Corp", "Enterprise", {"compute": 1400, "storage": 540, "network": 380, "memory": 460, "vector_db": 250, "backup": 150}),
        ]
        for tid, name, plan, costs in tenants:
            self._tenant_costs[tid] = TenantCost(tid, name, plan, costs)

        # Usage snapshots (last 30 days, daily)
        for day in range(30):
            ts = now - (30 - day) * 86400
            for rt in ResourceType:
                base = self._budgets[rt.value].allocated / 30
                noise = random.uniform(0.7, 1.3)
                trend = 1.0 + (day / 30) * 0.15  # slight upward trend
                self._usage_history.append(UsageSnapshot(
                    timestamp=ts, resource=rt.value,
                    value=round(base * noise * trend, 2)
                ))

    def get_budgets(self) -> List[dict]:
        return [b.to_dict() for b in self._budgets.values()]

    def get_budget(self, resource: str) -> Optional[dict]:
        b = self._budgets.get(resource)
        return b.to_dict() if b else None

    def set_budget(self, resource: str, allocated: float) -> dict:
        if resource in self._budgets:
            self._budgets[resource].allocated = allocated
        return self._budgets[resource].to_dict()

    def get_tenant_costs(self) -> List[dict]:
        return [t.to_dict() for t in self._tenant_costs.values()]

    def get_tenant_cost(self, tenant_id: str) -> Optional[dict]:
        t = self._tenant_costs.get(tenant_id)
        return t.to_dict() if t else None

    def get_monthly_totals(self) -> List[dict]:
        # Include current month from live budgets
        current_total = sum(b.used for b in self._budgets.values())
        current = {
            "month": "Mar", "cost": round(current_total, 2), "partial": True,
            "breakdown": {k: round(b.used, 2) for k, b in self._budgets.items()}
        }
        return self._monthly_totals + [current]

    def get_usage_history(self, resource: Optional[str] = None, days: int = 30) -> List[dict]:
        cutoff = time.time() - days * 86400
        snapshots = [s for s in self._usage_history if s.timestamp >= cutoff]
        if resource:
            snapshots = [s for s in snapshots if s.resource == resource]
        return [asdict(s) for s in snapshots]

    def get_summary(self) -> dict:
        total_budget = sum(b.allocated for b in self._budgets.values())
        total_used = sum(b.used for b in self._budgets.values())
        return {
            "total_budget": total_budget,
            "total_used": round(total_used, 2),
            "remaining": round(total_budget - total_used, 2),
            "usage_pct": round(total_used / total_budget * 100, 1) if total_budget > 0 else 0,
            "resource_count": len(self._budgets),
            "tenant_count": len(self._tenant_costs),
            "alerts": [
                {"resource": k, "message": f"{b.resource.value} at {b.usage_pct:.0f}% of budget",
                 "severity": "critical" if b.usage_pct > 90 else "warning"}
                for k, b in self._budgets.items() if b.usage_pct > 80
            ],
        }

    def record_usage(self, resource: str, value: float, tenant_id: Optional[str] = None):
        """Record a usage data point."""
        self._usage_history.append(UsageSnapshot(
            timestamp=time.time(), resource=resource, value=value, tenant_id=tenant_id
        ))
        if resource in self._budgets:
            self._budgets[resource].used += value * self._budgets[resource].unit_cost
