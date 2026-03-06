"""Grid Health Score - Chronic Failure Classification (DOC-015 Section 6)

PRISTINE (95-100) | STABLE (80-94) | FLAKY (60-79) | CHRONIC (30-59) | TERMINAL (0-29)

Score = Uptime(35%) + Failure Freq(25%) + Repair Rate(15%) + SLA(15%) + MTTR(10%)
"""

import time
import logging
from enum import Enum
from dataclasses import dataclass
from typing import Dict, List

from cortexdb.grid.state_machine import GridNode, NodeState

logger = logging.getLogger("cortexdb.grid.health")


class HealthClassification(Enum):
    PRISTINE = "PRISTINE"
    STABLE = "STABLE"
    FLAKY = "FLAKY"
    CHRONIC = "CHRONIC"
    TERMINAL = "TERMINAL"


CLASSIFICATION_THRESHOLDS = [
    (95, HealthClassification.PRISTINE),
    (80, HealthClassification.STABLE),
    (60, HealthClassification.FLAKY),
    (30, HealthClassification.CHRONIC),
    (0, HealthClassification.TERMINAL),
]

ROUTING_WEIGHTS = {
    HealthClassification.PRISTINE: 1.0,
    HealthClassification.STABLE: 1.0,
    HealthClassification.FLAKY: 0.75,
    HealthClassification.CHRONIC: 0.25,
    HealthClassification.TERMINAL: 0.0,
}


@dataclass
class HealthScoreBreakdown:
    uptime_score: float = 0
    failure_score: float = 0
    repair_rate_score: float = 0
    sla_score: float = 0
    mttr_score: float = 0
    total: float = 0
    classification: HealthClassification = HealthClassification.PRISTINE


class GridHealthScorer:
    SEVERITY_WEIGHTS = {1: 0.5, 2: 1.0, 3: 2.0, 4: 3.0, 5: 5.0}

    def calculate(self, node: GridNode, window_days: int = 30) -> HealthScoreBreakdown:
        window_start = time.time() - (window_days * 86400)
        breakdown = HealthScoreBreakdown()

        # Uptime (35%)
        total_minutes = window_days * 24 * 60
        downtime_minutes = self._estimate_downtime(node, window_start)
        uptime_pct = max(0, (total_minutes - downtime_minutes) / total_minutes * 100)

        if uptime_pct >= 99.9: breakdown.uptime_score = 35
        elif uptime_pct >= 99.5: breakdown.uptime_score = 30
        elif uptime_pct >= 99.0: breakdown.uptime_score = 25
        elif uptime_pct >= 98.0: breakdown.uptime_score = 15
        else: breakdown.uptime_score = 0

        # Failure Frequency (25%)
        recent = [a for a in node.repair_attempts if a.get("started_at", 0) > window_start]
        weighted = sum(self.SEVERITY_WEIGHTS.get(a.get("level", 1), 1.0) for a in recent)

        if weighted == 0: breakdown.failure_score = 25
        elif weighted <= 0.5: breakdown.failure_score = 22
        elif weighted <= 2: breakdown.failure_score = 18
        elif weighted <= 5: breakdown.failure_score = 10
        else: breakdown.failure_score = 0

        # Repair Success Rate (15%)
        if recent:
            rate = sum(1 for a in recent if a.get("success")) / len(recent) * 100
            if rate >= 100: breakdown.repair_rate_score = 15
            elif rate >= 90: breakdown.repair_rate_score = 12
            elif rate >= 75: breakdown.repair_rate_score = 8
            elif rate >= 50: breakdown.repair_rate_score = 4
            else: breakdown.repair_rate_score = 0
        else:
            breakdown.repair_rate_score = 15

        # SLA Compliance (15%)
        if uptime_pct >= 100: breakdown.sla_score = 15
        elif uptime_pct >= 99: breakdown.sla_score = 13
        elif uptime_pct >= 95: breakdown.sla_score = 10
        elif uptime_pct >= 90: breakdown.sla_score = 5
        else: breakdown.sla_score = 0

        # MTTR (10%)
        if recent:
            avg_dur = sum(a.get("duration", 60) for a in recent) / len(recent)
            if avg_dur < 30: breakdown.mttr_score = 10
            elif avg_dur < 60: breakdown.mttr_score = 8
            elif avg_dur < 300: breakdown.mttr_score = 5
            elif avg_dur < 900: breakdown.mttr_score = 3
            else: breakdown.mttr_score = 0
        else:
            breakdown.mttr_score = 10

        breakdown.total = (breakdown.uptime_score + breakdown.failure_score +
                          breakdown.repair_rate_score + breakdown.sla_score +
                          breakdown.mttr_score)

        for threshold, classification in CLASSIFICATION_THRESHOLDS:
            if breakdown.total >= threshold:
                breakdown.classification = classification
                break

        return breakdown

    def _estimate_downtime(self, node: GridNode, since: float) -> float:
        down_states = {NodeState.DEAD, NodeState.QUARANTINE, NodeState.REPAIRING,
                       NodeState.DRAINING, NodeState.REMOVED}
        downtime = 0
        in_downtime = False
        start = 0
        for t in node.transition_history:
            if t.timestamp < since:
                continue
            if t.to_state in down_states and not in_downtime:
                in_downtime = True
                start = t.timestamp
            elif t.to_state not in down_states and in_downtime:
                in_downtime = False
                downtime += (t.timestamp - start)
        if in_downtime:
            downtime += (time.time() - start)
        return downtime / 60

    def get_routing_weight(self, classification: HealthClassification) -> float:
        return ROUTING_WEIGHTS.get(classification, 1.0)
