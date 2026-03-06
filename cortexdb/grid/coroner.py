"""Grid Coroner - Post-Mortem Analysis for Dead Nodes (DOC-015 Section 7)

Every permanently removed node gets an automated post-mortem.
Report stored in Experience Ledger for platform learning.
"""

import time
import logging
from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from enum import Enum

from cortexdb.grid.state_machine import GridNode

logger = logging.getLogger("cortexdb.grid.coroner")


class CauseOfDeath(Enum):
    OOM_KILLED = "OOM_KILLED"
    CRASH_LOOP = "CRASH_LOOP"
    DEPENDENCY_FAILURE = "DEPENDENCY_FAILURE"
    NETWORK_PARTITION = "NETWORK_PARTITION"
    HARDWARE_FAILURE = "HARDWARE_FAILURE"
    SECURITY_INCIDENT = "SECURITY_INCIDENT"
    MANUAL_DECOMMISSION = "MANUAL_DECOMMISSION"
    SCALE_DOWN = "SCALE_DOWN"
    UNKNOWN = "UNKNOWN"


@dataclass
class CoronerReport:
    node_id: str
    grid_address: str
    node_type: str
    cause_of_death: CauseOfDeath
    lifetime_hours: float
    failure_timeline: List[Dict]
    repair_attempts: List[Dict]
    last_errors: List[str] = field(default_factory=list)
    resource_usage_at_death: Dict = field(default_factory=dict)
    similar_deaths: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    prevention_action: str = "monitored"
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict:
        return {
            "node_id": self.node_id, "grid_address": self.grid_address,
            "node_type": self.node_type, "cause_of_death": self.cause_of_death.value,
            "lifetime_hours": round(self.lifetime_hours, 2),
            "failure_timeline": self.failure_timeline,
            "repair_attempts": self.repair_attempts,
            "recommendations": self.recommendations,
            "similar_deaths": self.similar_deaths,
            "prevention_action": self.prevention_action,
            "created_at": self.created_at,
        }


class GridCoroner:
    def __init__(self):
        self._reports: List[CoronerReport] = []

    def conduct_postmortem(self, node: GridNode) -> CoronerReport:
        cause = self._determine_cause(node)
        timeline = [{"from": t.from_state.value, "to": t.to_state.value,
                      "timestamp": t.timestamp, "reason": t.reason}
                     for t in node.transition_history]
        recommendations = self._generate_recommendations(node, cause)

        report = CoronerReport(
            node_id=node.node_id, grid_address=node.grid_address,
            node_type=node.node_type, cause_of_death=cause,
            lifetime_hours=node.lifetime_hours, failure_timeline=timeline,
            repair_attempts=node.repair_attempts,
            recommendations=recommendations,
            similar_deaths=self._find_similar(cause, node.node_type),
        )
        self._reports.append(report)
        logger.info(f"Coroner: {node.grid_address} - {cause.value} after {node.lifetime_hours:.1f}h")
        return report

    def _determine_cause(self, node: GridNode) -> CauseOfDeath:
        if node.metadata.get("security_incident"): return CauseOfDeath.SECURITY_INCIDENT
        if node.metadata.get("manual_decommission"): return CauseOfDeath.MANUAL_DECOMMISSION
        if node.metadata.get("scale_down"): return CauseOfDeath.SCALE_DOWN

        if node.repair_attempts:
            errors = " ".join(a.get("error", "") for a in node.repair_attempts).lower()
            if "oom" in errors or "memory" in errors: return CauseOfDeath.OOM_KILLED
            if "crashloop" in errors or "restart" in errors: return CauseOfDeath.CRASH_LOOP
            if "dependency" in errors or "connection refused" in errors: return CauseOfDeath.DEPENDENCY_FAILURE
            if "network" in errors or "timeout" in errors: return CauseOfDeath.NETWORK_PARTITION
        return CauseOfDeath.UNKNOWN

    def _generate_recommendations(self, node: GridNode, cause: CauseOfDeath) -> List[str]:
        recs = {
            CauseOfDeath.OOM_KILLED: [f"Increase memory limit for {node.node_type}", "Review memory leak patterns"],
            CauseOfDeath.CRASH_LOOP: ["Review application logs for root cause", "Increase liveness probe timeout"],
            CauseOfDeath.DEPENDENCY_FAILURE: ["Add circuit breaker for failing dependency", "Increase timeout/retry"],
            CauseOfDeath.NETWORK_PARTITION: ["Review network config and DNS", "Add redundant network paths"],
            CauseOfDeath.SECURITY_INCIDENT: ["CRITICAL: Full security investigation required", "Do NOT reintroduce node"],
        }
        return recs.get(cause, ["Monitor for recurrence"])

    def _find_similar(self, cause: CauseOfDeath, node_type: str) -> List[str]:
        return [r.node_id for r in self._reports
                if r.cause_of_death == cause and r.node_type == node_type][-5:]

    def get_reports(self, limit: int = 50) -> List[Dict]:
        return [r.to_dict() for r in self._reports[-limit:]]

    def get_death_analytics(self) -> Dict:
        causes = Counter(r.cause_of_death.value for r in self._reports)
        return {
            "total_deaths": len(self._reports),
            "by_cause": dict(causes),
            "avg_lifetime_hours": sum(r.lifetime_hours for r in self._reports) / max(len(self._reports), 1),
        }
