"""
Sentinel Manager — Facade coordinating all sentinel sub-components.

Provides a unified API for security scanning, campaign management,
posture analysis, and remediation tracking.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from cortexdb.superadmin.persistence import PersistenceStore

from cortexdb.sentinel.knowledge_base import AttackKnowledgeBase
from cortexdb.sentinel.planner import CampaignPlanner
from cortexdb.sentinel.executor import AttackExecutor
from cortexdb.sentinel.analyzer import SecurityAnalyzer

logger = logging.getLogger("cortexdb.sentinel.manager")


class SentinelManager:
    """Facade that coordinates all sentinel sub-components."""

    def __init__(self, persistence_store: "PersistenceStore", llm_router=None):
        self._persistence = persistence_store
        self._llm_router = llm_router

        self.knowledge_base = AttackKnowledgeBase(persistence_store)
        self.planner = CampaignPlanner(persistence_store)
        self.executor = AttackExecutor(persistence_store, self.knowledge_base)
        self.analyzer = SecurityAnalyzer(persistence_store)

        self.knowledge_base.seed_knowledge_base()
        logger.info("SentinelManager initialized with all sub-components")

    # ── Quick / Targeted Scans ─────────────────────────────────────────────

    async def run_quick_scan(self) -> dict:
        all_categories = self.knowledge_base.list_categories()
        campaign = self.planner.create_campaign(
            name=f"Quick Scan {int(time.time())}",
            description="Automated full-spectrum quick scan",
            categories=all_categories,
            config={"aggression_level": 2, "concurrency": 8, "timeout_per_test": 15, "max_duration": 1800},
        )
        campaign_id = campaign["campaign_id"]

        self.planner.plan_campaign(campaign_id)
        self.planner.start_campaign(campaign_id)

        results = await self.executor.execute_campaign(campaign_id, all_categories)
        findings = results.get("findings", [])

        posture = self.analyzer.compute_posture_score(findings)
        snapshot = self.analyzer.save_posture_snapshot(posture)

        for f in findings:
            if f.get("result") != "pass":
                self.analyzer.generate_remediation_plan(f)

        self.planner.complete_campaign(campaign_id, summary={
            "total_tests": results.get("total_tests", 0),
            "total_findings": len(findings),
            "posture_score": posture["overall_score"],
            "snapshot_id": snapshot["snapshot_id"],
        })

        return {
            "campaign_id": campaign_id,
            "posture": posture,
            "snapshot_id": snapshot["snapshot_id"],
            "total_findings": len(findings),
            "results": results,
        }

    async def run_targeted_scan(
        self,
        categories: List[str],
        endpoints: Optional[List[str]] = None,
    ) -> dict:
        campaign = self.planner.create_campaign(
            name=f"Targeted Scan {int(time.time())}",
            description=f"Targeted scan: {', '.join(categories)}",
            categories=categories,
            endpoints=endpoints,
            config={"aggression_level": 3, "concurrency": 4, "timeout_per_test": 30, "max_duration": 3600},
        )
        campaign_id = campaign["campaign_id"]

        self.planner.plan_campaign(campaign_id)
        self.planner.start_campaign(campaign_id)

        results = await self.executor.execute_campaign(campaign_id, categories, endpoints=endpoints)
        findings = results.get("findings", [])

        posture = self.analyzer.compute_posture_score(findings)
        snapshot = self.analyzer.save_posture_snapshot(posture)

        for f in findings:
            if f.get("result") != "pass":
                self.analyzer.generate_remediation_plan(f)

        self.planner.complete_campaign(campaign_id, summary={
            "total_tests": results.get("total_tests", 0),
            "total_findings": len(findings),
            "posture_score": posture["overall_score"],
            "snapshot_id": snapshot["snapshot_id"],
            "categories": categories,
        })

        return {
            "campaign_id": campaign_id,
            "posture": posture,
            "snapshot_id": snapshot["snapshot_id"],
            "total_findings": len(findings),
            "results": results,
        }

    # ── Dashboard ──────────────────────────────────────────────────────────

    def get_dashboard_summary(self) -> dict:
        history = self.analyzer.get_posture_history(limit=1)
        latest_posture = history[0] if history else None

        recent_plans = self.analyzer.list_remediation_plans(status="open", limit=100)
        severity_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        for plan in recent_plans:
            sev = plan.get("priority", "low")
            if sev in severity_counts:
                severity_counts[sev] += 1

        active_campaigns = self.planner.list_campaigns(status="running")
        kb_stats = self.knowledge_base.get_stats()

        return {
            "posture": {
                "score": latest_posture["overall_score"] if latest_posture else None,
                "trend": latest_posture["trend"] if latest_posture else "unknown",
                "last_scan": latest_posture["created_at"] if latest_posture else None,
            },
            "findings": {
                "open_count": len(recent_plans),
                "critical": severity_counts["critical"],
                "high": severity_counts["high"],
                "medium": severity_counts["medium"],
                "low": severity_counts["low"],
            },
            "campaigns": {
                "active": len(active_campaigns),
                "total": len(self.planner.list_campaigns()),
            },
            "knowledge_base": {
                "total_vectors": kb_stats.get("total_vectors", 0),
                "total_categories": kb_stats.get("total_categories", 0),
                "threat_intel_count": kb_stats.get("threat_intel_count", 0),
            },
        }

    # ── Campaign CRUD (delegates to planner) ───────────────────────────────

    def create_campaign(self, name: str, description: str, categories: List[str],
                        endpoints: Optional[List[str]] = None, config: Optional[Dict] = None) -> dict:
        return self.planner.create_campaign(name, description, categories, endpoints, config)

    def plan_campaign(self, campaign_id: str) -> dict:
        return self.planner.plan_campaign(campaign_id)

    def list_campaigns(self, status: Optional[str] = None, limit: int = 50) -> list:
        return self.planner.list_campaigns(status, limit)

    def get_campaign(self, campaign_id: str) -> dict:
        return self.planner.get_campaign(campaign_id)

    def update_campaign(self, campaign_id: str, updates: Dict[str, Any]) -> dict:
        return self.planner.update_campaign(campaign_id, updates)

    def delete_campaign(self, campaign_id: str) -> bool:
        return self.planner.delete_campaign(campaign_id)

    # ── Campaign Execution ─────────────────────────────────────────────────

    async def execute_campaign(self, campaign_id: str) -> dict:
        campaign = self.planner.get_campaign(campaign_id)
        if "error" in campaign:
            return campaign

        self.planner.start_campaign(campaign_id)
        categories = campaign.get("target_categories", [])
        endpoints = campaign.get("target_endpoints", None)

        results = await self.executor.execute_campaign(campaign_id, categories, endpoints=endpoints)
        findings = results.get("findings", [])

        posture = self.analyzer.compute_posture_score(findings)
        snapshot = self.analyzer.save_posture_snapshot(posture)

        for f in findings:
            if f.get("result") != "pass":
                self.analyzer.generate_remediation_plan(f)

        self.planner.complete_campaign(campaign_id, summary={
            "total_tests": results.get("total_tests", 0),
            "total_findings": len(findings),
            "posture_score": posture["overall_score"],
            "snapshot_id": snapshot["snapshot_id"],
        })

        return {
            "campaign_id": campaign_id,
            "posture": posture,
            "snapshot_id": snapshot["snapshot_id"],
            "total_findings": len(findings),
            "results": results,
        }

    # ── Run / Finding queries (delegates to executor) ──────────────────────

    def list_runs(self, campaign_id: Optional[str] = None, limit: int = 50) -> list:
        return self.executor.list_runs(campaign_id=campaign_id, limit=limit)

    def get_run(self, run_id: str) -> dict:
        return self.executor.get_run(run_id)

    def list_findings(self, run_id: Optional[str] = None, severity: Optional[str] = None,
                      limit: int = 100) -> list:
        return self.executor.list_findings(run_id=run_id, severity=severity, limit=limit)

    def get_finding(self, finding_id: str) -> dict:
        return self.executor.get_finding(finding_id)

    # ── Posture / Remediation (delegates to analyzer) ──────────────────────

    def get_posture_history(self, limit: int = 30) -> list:
        return self.analyzer.get_posture_history(limit)

    def get_trend_analysis(self) -> dict:
        return self.analyzer.get_trend_analysis()

    def get_top_risks(self, limit: int = 10) -> list:
        return self.analyzer.get_top_risks(limit)

    def list_remediation_plans(self, status: Optional[str] = None, limit: int = 50) -> list:
        return self.analyzer.list_remediation_plans(status, limit)

    def get_remediation(self, plan_id: str) -> dict:
        return self.analyzer.get_remediation(plan_id)

    def update_remediation(self, plan_id: str, updates: Dict[str, Any]) -> dict:
        return self.analyzer.update_remediation(plan_id, updates)

    # ── Knowledge Base (delegates) ─────────────────────────────────────────

    def list_vectors(self, category: Optional[str] = None, limit: int = 50) -> list:
        return self.knowledge_base.list_vectors(category=category, limit=limit)

    def get_vector(self, vector_id: str) -> dict:
        return self.knowledge_base.get_vector(vector_id)

    def add_vector(self, vector_data: dict) -> dict:
        return self.knowledge_base.add_vector(vector_data)

    def list_categories(self) -> list:
        return self.knowledge_base.list_categories()

    # ── Stats ──────────────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        conn = self._persistence.conn

        total_campaigns = conn.execute("SELECT COUNT(*) FROM sentinel_campaigns").fetchone()[0]
        active_campaigns = conn.execute(
            "SELECT COUNT(*) FROM sentinel_campaigns WHERE status = 'running'"
        ).fetchone()[0]
        completed_campaigns = conn.execute(
            "SELECT COUNT(*) FROM sentinel_campaigns WHERE status = 'completed'"
        ).fetchone()[0]

        total_snapshots = conn.execute("SELECT COUNT(*) FROM sentinel_posture").fetchone()[0]
        latest_score_row = conn.execute(
            "SELECT overall_score FROM sentinel_posture ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        latest_score = latest_score_row[0] if latest_score_row else None

        total_remediation = conn.execute("SELECT COUNT(*) FROM sentinel_remediation").fetchone()[0]
        open_remediation = conn.execute(
            "SELECT COUNT(*) FROM sentinel_remediation WHERE status = 'open'"
        ).fetchone()[0]
        completed_remediation = conn.execute(
            "SELECT COUNT(*) FROM sentinel_remediation WHERE status = 'completed'"
        ).fetchone()[0]

        kb_stats = self.knowledge_base.get_stats()

        return {
            "campaigns": {
                "total": total_campaigns,
                "active": active_campaigns,
                "completed": completed_campaigns,
            },
            "posture": {
                "snapshots": total_snapshots,
                "latest_score": latest_score,
            },
            "remediation": {
                "total": total_remediation,
                "open": open_remediation,
                "completed": completed_remediation,
                "in_progress": total_remediation - open_remediation - completed_remediation,
            },
            "knowledge_base": kb_stats,
        }
