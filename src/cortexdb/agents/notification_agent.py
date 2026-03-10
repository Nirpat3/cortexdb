"""
Notification Agent — Aggregates events from all agents and services
to produce real-time notifications with severity-based prioritization.
"""

import time
import random
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass, field, asdict

logger = logging.getLogger(__name__)


@dataclass
class Notification:
    notif_id: str
    timestamp: float
    severity: str  # critical, warning, info, success
    category: str  # system, security, performance, budget, compliance, agent
    title: str
    message: str
    source: str  # which agent/service generated it
    read: bool = False
    dismissed: bool = False
    action_url: str = ""
    metadata: Dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


class NotificationAgent:
    """Aggregates events from all agents into unified notification stream."""

    def __init__(self):
        self._notifications: List[Notification] = []
        self._max_notifications = 500
        self._counter = 0
        self._initialized = False

    async def initialize(self):
        if self._initialized:
            return
        self._seed_notifications()
        self._initialized = True

    def _seed_notifications(self):
        now = time.time()
        templates = [
            ("critical", "security", "Brute Force Attack Detected",
             "150 failed login attempts from 192.168.1.100 in 5 minutes. IP has been blocked.",
             "security-agent", "/security"),
            ("warning", "performance", "High CPU Usage Alert",
             "CPU usage has exceeded 85% for the last 10 minutes on cortexdb-server.",
             "system-metrics-agent", "/monitoring"),
            ("info", "system", "Daily Backup Completed",
             "Full backup completed successfully. Size: 42GB, Duration: 18 minutes.",
             "backup-agent", "/services"),
            ("success", "compliance", "SOC2 Audit Passed",
             "Annual SOC2 Type II compliance audit completed with zero findings.",
             "compliance-engine", "/compliance"),
            ("warning", "budget", "Budget Threshold Warning",
             "Compute resources at 82% of monthly budget with 10 days remaining.",
             "forecasting-agent", "/budgeting"),
            ("critical", "performance", "Database Connection Pool Exhausted",
             "All 200 connections in use. New requests are queuing. Consider scaling.",
             "db-monitor-agent", "/db-monitor"),
            ("info", "agent", "Forecasting Analysis Complete",
             "AI forecasting agent completed run #47. 6 predictions, 2 anomalies detected.",
             "forecasting-agent", "/budgeting"),
            ("warning", "security", "SSL Certificate Expiring",
             "TLS certificate for api.cortexdb.io expires in 28 days. Schedule renewal.",
             "security-agent", "/security"),
            ("success", "system", "Service Auto-Recovery",
             "Redis cache service recovered automatically after brief network partition.",
             "service-monitor-agent", "/services"),
            ("info", "performance", "Slow Query Detected",
             "Query on cortex_blocks took 8.5s. Consider adding index on tenant_id.",
             "db-monitor-agent", "/db-monitor"),
            ("warning", "system", "Disk Space Warning",
             "Primary storage at 78% capacity. Projected to reach 90% in 12 days.",
             "system-metrics-agent", "/hardware"),
            ("critical", "security", "Data Exfiltration Attempt",
             "Unusual bulk data export detected from tenant umbrella-corp. Quarantined.",
             "security-agent", "/security"),
            ("info", "agent", "Error Tracking Report",
             "12 errors tracked in last hour: 2 critical, 4 errors, 6 warnings.",
             "error-tracking-agent", "/errors"),
            ("success", "performance", "Index Optimization Applied",
             "AI-recommended index on vector_embeddings improved query time by 73%.",
             "db-monitor-agent", "/db-monitor"),
            ("warning", "budget", "Tenant Cost Anomaly",
             "Acme Corp usage spike: 40% above forecast. Investigating root cause.",
             "forecasting-agent", "/budgeting"),
            ("info", "compliance", "Encryption Keys Rotated",
             "Quarterly encryption key rotation completed for all 4 tenants.",
             "compliance-engine", "/compliance"),
            ("info", "system", "New Agent Registered",
             "Service Monitor Agent v1.0 registered and active. Monitoring 12 services.",
             "agent-registry", "/agents"),
            ("warning", "performance", "Replication Lag Spike",
             "PostgreSQL replica lag increased to 15ms. Threshold is 10ms.",
             "db-monitor-agent", "/scale"),
            ("success", "agent", "All Systems Operational",
             "All 7 agents reporting healthy. 12 services operational. No active incidents.",
             "agent-registry", "/agents"),
            ("info", "system", "Grid Node Resurrected",
             "Node worker-3 recovered after 45s downtime. Self-healing protocol engaged.",
             "grid-manager", "/grid"),
        ]

        for i, (sev, cat, title, msg, source, url) in enumerate(templates):
            self._counter += 1
            self._notifications.append(Notification(
                notif_id=f"NTF-{self._counter:04d}",
                timestamp=now - random.uniform(0, 86400),
                severity=sev, category=cat, title=title, message=msg,
                source=source, action_url=url,
                read=random.random() > 0.4,
            ))

        self._notifications.sort(key=lambda n: -n.timestamp)

    def generate(self) -> Optional[dict]:
        """Generate a new notification based on current system state."""
        now = time.time()

        # Generate with ~30% probability per call
        if random.random() > 0.3:
            return None

        templates = [
            ("info", "system", "Health Check Passed", "All services passed routine health check.", "system-metrics-agent"),
            ("warning", "performance", "Memory Pressure Detected", f"Memory usage at {random.randint(75, 92)}%. Consider scaling.", "system-metrics-agent"),
            ("info", "agent", "Agent Cycle Complete", f"Monitoring cycle completed in {random.randint(50, 500)}ms.", "service-monitor-agent"),
            ("warning", "security", "Suspicious Request Pattern", f"Unusual API pattern from {random.choice(['10.0.0', '172.16.0'])}.{random.randint(1, 254)}.", "security-agent"),
            ("success", "performance", "Cache Hit Ratio Optimal", f"Cache hit ratio at {round(random.uniform(95, 99.5), 1)}%.", "db-monitor-agent"),
            ("info", "budget", "Usage Snapshot Recorded", f"Hourly cost snapshot: ${random.randint(10, 50)} across all resources.", "forecasting-agent"),
        ]

        sev, cat, title, msg, source = random.choice(templates)
        self._counter += 1
        notif = Notification(
            notif_id=f"NTF-{self._counter:04d}",
            timestamp=now, severity=sev, category=cat,
            title=title, message=msg, source=source,
        )
        self._notifications.insert(0, notif)
        if len(self._notifications) > self._max_notifications:
            self._notifications = self._notifications[:self._max_notifications]

        return notif.to_dict()

    def get_all(self, severity: str = None, category: str = None,
                unread_only: bool = False, limit: int = 50) -> List[dict]:
        notifs = self._notifications
        if severity:
            notifs = [n for n in notifs if n.severity == severity]
        if category:
            notifs = [n for n in notifs if n.category == category]
        if unread_only:
            notifs = [n for n in notifs if not n.read]
        return [n.to_dict() for n in notifs[:limit]]

    def mark_read(self, notif_id: str) -> bool:
        for n in self._notifications:
            if n.notif_id == notif_id:
                n.read = True
                return True
        return False

    def mark_all_read(self):
        for n in self._notifications:
            n.read = True

    def dismiss(self, notif_id: str) -> bool:
        for n in self._notifications:
            if n.notif_id == notif_id:
                n.dismissed = True
                return True
        return False

    def get_summary(self) -> dict:
        unread = [n for n in self._notifications if not n.read]
        now = time.time()
        last_hour = [n for n in self._notifications if now - n.timestamp < 3600]
        by_severity = {}
        for n in unread:
            by_severity[n.severity] = by_severity.get(n.severity, 0) + 1
        by_category = {}
        for n in last_hour:
            by_category[n.category] = by_category.get(n.category, 0) + 1
        return {
            "total": len(self._notifications),
            "unread": len(unread),
            "last_hour": len(last_hour),
            "by_severity": by_severity,
            "by_category": by_category,
            "latest": self._notifications[0].to_dict() if self._notifications else None,
        }
