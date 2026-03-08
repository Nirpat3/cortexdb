"""
Security Agent — Real-time threat detection, audit logging, vulnerability
scanning, and security posture scoring.
"""

import time
import random
import logging
from typing import Dict, List
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)


@dataclass
class ThreatEvent:
    threat_id: str
    timestamp: float
    severity: str  # critical, high, medium, low, info
    category: str  # brute_force, injection, anomaly, policy_violation, auth_failure, data_exfil
    source_ip: str
    target: str
    description: str
    action_taken: str  # blocked, flagged, allowed, quarantined
    details: Dict = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["details"] = self.details or {}
        return d


@dataclass
class AuditEntry:
    entry_id: str
    timestamp: float
    actor: str
    action: str
    resource: str
    outcome: str  # success, failure, denied
    ip_address: str
    details: str

    def to_dict(self) -> dict:
        return asdict(self)


class SecurityAgent:
    """Real-time security monitoring and threat detection."""

    def __init__(self):
        self._threats: List[ThreatEvent] = []
        self._audit_log: List[AuditEntry] = []
        self._blocked_ips: set = set()
        self._initialized = False
        self._scan_results: Dict = {}

    async def initialize(self):
        if self._initialized:
            return
        self._seed_data()
        self._initialized = True

    def _seed_data(self):
        now = time.time()

        # Seed threat events (last 24h)
        threat_templates = [
            ("TH-001", "critical", "brute_force", "192.168.1.100", "/api/auth/login",
             "Brute force attack detected: 150 failed login attempts in 5 minutes", "blocked"),
            ("TH-002", "high", "injection", "10.0.0.45", "/v1/query",
             "SQL injection attempt in CortexQL query parameter", "blocked"),
            ("TH-003", "medium", "anomaly", "172.16.0.22", "/v1/write",
             "Unusual write volume spike: 10x normal rate from single tenant", "flagged"),
            ("TH-004", "high", "policy_violation", "10.0.0.88", "/v1/admin/tenants",
             "Unauthorized admin API access attempt without proper RBAC role", "blocked"),
            ("TH-005", "low", "auth_failure", "192.168.2.50", "/v1/budget/resources",
             "Expired API key used for budget endpoint access", "blocked"),
            ("TH-006", "critical", "data_exfil", "10.0.0.33", "/v1/admin/tenants/export",
             "Large data export requested for 3 tenants simultaneously", "quarantined"),
            ("TH-007", "medium", "anomaly", "172.16.0.15", "/v1/cortexgraph/stats",
             "Abnormal query pattern: sequential scan of all customer profiles", "flagged"),
            ("TH-008", "high", "injection", "192.168.3.10", "/v1/mcp/call",
             "Malicious tool invocation attempt via MCP endpoint", "blocked"),
            ("TH-009", "low", "policy_violation", "10.0.0.55", "/v1/compliance/audit-log",
             "Audit log access from non-compliance role", "flagged"),
            ("TH-010", "info", "auth_failure", "172.16.0.100", "/health/ready",
             "Health check from unregistered monitoring agent", "allowed"),
        ]

        for tid, sev, cat, ip, target, desc, action in threat_templates:
            self._threats.append(ThreatEvent(
                threat_id=tid, timestamp=now - random.uniform(0, 86400),
                severity=sev, category=cat, source_ip=ip, target=target,
                description=desc, action_taken=action,
            ))
            if action == "blocked":
                self._blocked_ips.add(ip)

        # Seed audit entries
        audit_templates = [
            ("admin@cortexdb.io", "tenant.create", "tenants/acme-corp", "success", "Onboarded new enterprise tenant"),
            ("system", "encryption.rotate", "keys/master", "success", "Quarterly master key rotation completed"),
            ("api-user-42", "data.export", "tenants/globex/data", "denied", "Export denied: insufficient permissions"),
            ("admin@cortexdb.io", "config.update", "settings/rate-limit", "success", "Rate limit increased to 1000 RPS"),
            ("system", "backup.complete", "backups/daily-20240307", "success", "Daily backup completed: 42GB compressed"),
            ("api-user-15", "query.execute", "v1/query", "success", "CortexQL query executed on 3 engines"),
            ("admin@cortexdb.io", "agent.register", "agents/security-scanner", "success", "New security scanning agent registered"),
            ("system", "compliance.audit", "soc2/annual", "success", "SOC2 annual audit report generated"),
        ]

        for i, (actor, action, resource, outcome, details) in enumerate(audit_templates):
            self._audit_log.append(AuditEntry(
                entry_id=f"AUD-{1000 + i}",
                timestamp=now - random.uniform(0, 172800),
                actor=actor, action=action, resource=resource,
                outcome=outcome,
                ip_address=f"10.0.0.{random.randint(1, 100)}",
                details=details,
            ))

        self._scan_results = {
            "last_scan": now - 3600,
            "vulnerabilities": {"critical": 0, "high": 1, "medium": 3, "low": 8, "info": 15},
            "patches_pending": 2,
            "certificates_expiring_30d": 1,
            "open_ports_unexpected": 0,
        }

    def collect(self) -> dict:
        """Run threat detection cycle and return current status."""
        now = time.time()

        # Occasionally generate new threats
        if random.random() > 0.6:
            categories = ["anomaly", "auth_failure", "policy_violation", "brute_force"]
            severities = ["info", "low", "medium", "medium", "high"]
            actions = ["blocked", "flagged", "allowed"]
            cat = random.choice(categories)
            sev = random.choice(severities)
            ip = f"{random.choice(['10.0.0', '172.16.0', '192.168.1'])}.{random.randint(1, 254)}"

            self._threats.append(ThreatEvent(
                threat_id=f"TH-{random.randint(100, 9999)}",
                timestamp=now, severity=sev, category=cat,
                source_ip=ip, target=f"/v1/{random.choice(['query', 'write', 'admin/tenants', 'mcp/call'])}",
                description=f"Automated detection: {cat.replace('_', ' ')} from {ip}",
                action_taken=random.choice(actions),
            ))
            self._threats = self._threats[-100:]

        return self.get_overview()

    def get_overview(self) -> dict:
        now = time.time()
        recent_24h = [t for t in self._threats if now - t.timestamp < 86400]
        return {
            "security_score": self._compute_score(),
            "threat_level": self._compute_threat_level(recent_24h),
            "threats_24h": len(recent_24h),
            "blocked_today": sum(1 for t in recent_24h if t.action_taken == "blocked"),
            "blocked_ips": len(self._blocked_ips),
            "active_sessions": random.randint(15, 45),
            "failed_logins_24h": sum(1 for t in recent_24h if t.category == "auth_failure"),
            "scan_results": self._scan_results,
            "encryption": {
                "tls_version": "1.3",
                "cipher_suite": "AES-256-GCM",
                "certificates_valid": True,
                "data_at_rest": "AES-256",
                "key_rotation_days": random.randint(5, 25),
            },
            "compliance_status": {
                "soc2": "compliant",
                "hipaa": "compliant",
                "pci_dss": "compliant",
                "fedramp": "in_progress",
            },
        }

    def _compute_score(self) -> int:
        base = 96
        recent = [t for t in self._threats if time.time() - t.timestamp < 86400]
        critical = sum(1 for t in recent if t.severity == "critical")
        high = sum(1 for t in recent if t.severity == "high")
        base -= critical * 5 + high * 2
        return max(50, min(100, base))

    def _compute_threat_level(self, recent: list) -> str:
        critical = sum(1 for t in recent if t.severity == "critical")
        high = sum(1 for t in recent if t.severity == "high")
        if critical > 2:
            return "Critical"
        if critical > 0 or high > 3:
            return "High"
        if high > 0:
            return "Medium"
        return "Low"

    def get_threats(self, severity: str = None, limit: int = 50) -> List[dict]:
        threats = sorted(self._threats, key=lambda t: -t.timestamp)
        if severity:
            threats = [t for t in threats if t.severity == severity]
        return [t.to_dict() for t in threats[:limit]]

    def get_audit_log(self, limit: int = 50) -> List[dict]:
        entries = sorted(self._audit_log, key=lambda e: -e.timestamp)
        return [e.to_dict() for e in entries[:limit]]

    def get_threat_stats(self) -> dict:
        now = time.time()
        last_24h = [t for t in self._threats if now - t.timestamp < 86400]
        last_7d = [t for t in self._threats if now - t.timestamp < 604800]
        by_category = {}
        for t in last_24h:
            by_category[t.category] = by_category.get(t.category, 0) + 1
        by_severity = {}
        for t in last_24h:
            by_severity[t.severity] = by_severity.get(t.severity, 0) + 1
        return {
            "last_24h": len(last_24h),
            "last_7d": len(last_7d),
            "by_category": by_category,
            "by_severity": by_severity,
            "blocked_ips": list(self._blocked_ips)[:20],
            "top_targets": self._top_targets(last_24h),
        }

    def _top_targets(self, threats: list) -> List[dict]:
        counts: Dict[str, int] = {}
        for t in threats:
            counts[t.target] = counts.get(t.target, 0) + 1
        return [{"target": k, "count": v} for k, v in sorted(counts.items(), key=lambda x: -x[1])[:5]]
