"""
Audit & Compliance Reports — Exportable reports of agent actions, costs, quality.

Report types:
  - agent_actions: task executions, delegations, state changes
  - cost_summary: spending breakdown by provider/agent/department
  - quality_audit: outcome grades, failure analysis, quality trends
  - delegation_audit: delegation decisions and outcomes
"""

import time
import uuid
import json
import logging
from typing import List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from cortexdb.superadmin.agent_team import AgentTeamManager
    from cortexdb.superadmin.persistence import PersistenceStore

logger = logging.getLogger(__name__)

REPORT_TYPES = ["agent_actions", "cost_summary", "quality_audit", "delegation_audit"]


class ComplianceReporter:
    """Generates exportable audit and compliance reports."""

    def __init__(self, team: "AgentTeamManager", persistence: "PersistenceStore"):
        self._team = team
        self._persistence = persistence

    def generate(self, report_type: str, from_date: float = None,
                 to_date: float = None) -> dict:
        """Generate a report of the specified type."""
        if report_type not in REPORT_TYPES:
            return {"error": f"Unknown report type. Options: {REPORT_TYPES}"}

        report_id = f"RPT-{uuid.uuid4().hex[:8]}"
        now = time.time()
        from_date = from_date or (now - 86400 * 30)  # default last 30 days
        to_date = to_date or now

        if report_type == "agent_actions":
            data = self._agent_actions_report(from_date, to_date)
        elif report_type == "cost_summary":
            data = self._cost_summary_report(from_date, to_date)
        elif report_type == "quality_audit":
            data = self._quality_audit_report(from_date, to_date)
        elif report_type == "delegation_audit":
            data = self._delegation_audit_report(from_date, to_date)
        else:
            data = {}

        report = {
            "report_id": report_id,
            "report_type": report_type,
            "from_date": from_date,
            "to_date": to_date,
            "generated_at": now,
            "data": data,
        }

        # Store
        reports = self._persistence.kv_get("compliance_reports", [])
        reports.append({k: v for k, v in report.items() if k != "data"})
        if len(reports) > 100:
            reports = reports[-100:]
        self._persistence.kv_set("compliance_reports", reports)
        self._persistence.kv_set(f"report:{report_id}", report)

        return report

    def _agent_actions_report(self, from_d: float, to_d: float) -> dict:
        audit = self._persistence.get_audit_log(limit=1000)
        filtered = [a for a in audit if from_d <= a.get("timestamp", 0) <= to_d]

        by_agent = {}
        for entry in filtered:
            agent = entry.get("details", {}).get("agent", entry.get("entity_id", "system"))
            if agent not in by_agent:
                by_agent[agent] = []
            by_agent[agent].append(entry)

        return {
            "total_actions": len(filtered),
            "by_agent": {k: len(v) for k, v in by_agent.items()},
            "action_types": self._count_field(filtered, "action"),
            "entries": filtered[-100:],
        }

    def _cost_summary_report(self, from_d: float, to_d: float) -> dict:
        costs = self._persistence.kv_get("cost_log", [])
        if isinstance(costs, dict):
            costs = costs.get("entries", [])
        filtered = [c for c in costs if from_d <= c.get("timestamp", 0) <= to_d]

        by_provider = {}
        by_department = {}
        total = 0
        for c in filtered:
            cost = c.get("cost_usd", 0)
            total += cost
            prov = c.get("provider", "unknown")
            by_provider[prov] = by_provider.get(prov, 0) + cost
            dept = c.get("department", "unknown")
            by_department[dept] = by_department.get(dept, 0) + cost

        return {
            "total_cost_usd": round(total, 4),
            "total_calls": len(filtered),
            "by_provider": {k: round(v, 4) for k, v in by_provider.items()},
            "by_department": {k: round(v, 4) for k, v in by_department.items()},
        }

    def _quality_audit_report(self, from_d: float, to_d: float) -> dict:
        analyses = self._persistence.kv_get("outcome_analyses", [])
        filtered = [a for a in analyses if from_d <= a.get("timestamp", 0) <= to_d]
        grades = [a.get("grade", 5) for a in filtered]

        return {
            "total_analyzed": len(filtered),
            "avg_grade": round(sum(grades) / max(len(grades), 1), 2),
            "grade_distribution": {
                "poor (1-3)": sum(1 for g in grades if g <= 3),
                "fair (4-6)": sum(1 for g in grades if 4 <= g <= 6),
                "good (7-8)": sum(1 for g in grades if 7 <= g <= 8),
                "excellent (9-10)": sum(1 for g in grades if g >= 9),
            },
            "by_category": self._grades_by_field(filtered, "category"),
            "by_agent": self._grades_by_field(filtered, "agent_id"),
        }

    def _delegation_audit_report(self, from_d: float, to_d: float) -> dict:
        delegations = self._persistence.kv_get("delegation_log", [])
        filtered = [d for d in delegations if from_d <= d.get("created_at", 0) <= to_d]

        return {
            "total_delegations": len(filtered),
            "outcomes": self._count_field(filtered, "outcome"),
            "top_delegators": self._count_field(filtered, "from_agent"),
            "top_delegates": self._count_field(filtered, "to_agent"),
            "entries": filtered[-50:],
        }

    def _count_field(self, items: list, field: str) -> dict:
        counts = {}
        for item in items:
            val = item.get(field, "unknown")
            counts[val] = counts.get(val, 0) + 1
        return counts

    def _grades_by_field(self, analyses: list, field: str) -> dict:
        groups = {}
        for a in analyses:
            key = a.get(field, "unknown")
            if key not in groups:
                groups[key] = []
            groups[key].append(a.get("grade", 5))
        return {k: round(sum(v)/len(v), 2) for k, v in groups.items()}

    def get_reports(self) -> List[dict]:
        return self._persistence.kv_get("compliance_reports", [])

    def get_report(self, report_id: str) -> Optional[dict]:
        return self._persistence.kv_get(f"report:{report_id}")

    def get_types(self) -> List[str]:
        return REPORT_TYPES
