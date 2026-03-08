"""
Alert System — Notifications for level-ups, failures, budget breaches, skill gaps.

Alert types: level_up, task_failed, budget_breach, reputation_drop,
             skill_gap, delegation_rejected, agent_idle
Severities: info, warning, critical
"""

import time
import uuid
import logging
from typing import List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from cortexdb.superadmin.persistence import PersistenceStore

logger = logging.getLogger(__name__)


class AlertSystem:
    """Manages alerts and notifications for the agent workforce."""

    def __init__(self, persistence: "PersistenceStore"):
        self._persistence = persistence
        self._push_event = None  # Set externally to wire WebSocket

    def create_alert(self, alert_type: str, severity: str, title: str,
                     message: str, agent_id: str = None, data: dict = None) -> dict:
        """Create and store an alert."""
        alert = {
            "alert_id": f"ALT-{uuid.uuid4().hex[:8]}",
            "alert_type": alert_type,
            "severity": severity,
            "title": title,
            "message": message,
            "agent_id": agent_id,
            "data": data or {},
            "acknowledged": False,
            "created_at": time.time(),
        }

        alerts = self._persistence.kv_get("alerts", [])
        alerts.append(alert)
        if len(alerts) > 500:
            alerts = alerts[-500:]
        self._persistence.kv_set("alerts", alerts)

        logger.info("Alert [%s] %s: %s", severity, alert_type, title)
        return alert

    def get_alerts(self, severity: str = None, alert_type: str = None,
                   acknowledged: bool = None, limit: int = 50) -> List[dict]:
        alerts = self._persistence.kv_get("alerts", [])
        if severity:
            alerts = [a for a in alerts if a.get("severity") == severity]
        if alert_type:
            alerts = [a for a in alerts if a.get("alert_type") == alert_type]
        if acknowledged is not None:
            alerts = [a for a in alerts if a.get("acknowledged") == acknowledged]
        return alerts[-limit:]

    def get_unread_count(self) -> int:
        alerts = self._persistence.kv_get("alerts", [])
        return sum(1 for a in alerts if not a.get("acknowledged"))

    def acknowledge(self, alert_id: str) -> dict:
        alerts = self._persistence.kv_get("alerts", [])
        for a in alerts:
            if a.get("alert_id") == alert_id:
                a["acknowledged"] = True
                self._persistence.kv_set("alerts", alerts)
                return a
        return {"error": "Alert not found"}

    def acknowledge_all(self) -> dict:
        alerts = self._persistence.kv_get("alerts", [])
        count = 0
        for a in alerts:
            if not a.get("acknowledged"):
                a["acknowledged"] = True
                count += 1
        self._persistence.kv_set("alerts", alerts)
        return {"acknowledged": count}

    # ── Alert generators (called from hooks) ──

    def on_level_up(self, agent_id: str, skill: str, new_level: int, level_name: str):
        self.create_alert(
            "level_up", "info",
            f"{skill} leveled up to {level_name}",
            f"Agent {agent_id} reached {level_name} (lv.{new_level}) in {skill}",
            agent_id=agent_id,
            data={"skill": skill, "level": new_level, "level_name": level_name},
        )

    def on_task_failed(self, agent_id: str, task_id: str, task_title: str):
        self.create_alert(
            "task_failed", "warning",
            f"Task failed: {task_title}",
            f"Agent {agent_id} failed task {task_id}",
            agent_id=agent_id,
            data={"task_id": task_id},
        )

    def on_low_grade(self, agent_id: str, task_id: str, grade: int):
        if grade <= 3:
            self.create_alert(
                "low_quality", "warning",
                f"Low quality output (grade {grade}/10)",
                f"Agent {agent_id} produced low-quality output on task {task_id}",
                agent_id=agent_id,
                data={"task_id": task_id, "grade": grade},
            )
