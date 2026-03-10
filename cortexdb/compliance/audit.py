"""Compliance Audit Trail

Enhanced audit logging for FedRAMP, SOC2, HIPAA, PCI-DSS evidence collection:
  - WHO accessed WHAT data, WHEN, from WHERE, and the OUTCOME
  - PHI access tracking (HIPAA 164.312(b))
  - Cardholder data access tracking (PCI-DSS 10.1)
  - Administrative action logging (FedRAMP AU-2)
  - Tamper-evident via ImmutableCore hash chain
"""

import time
import uuid
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger("cortexdb.compliance.audit")


class AuditEventType(Enum):
    # Access events
    DATA_READ = "DATA_READ"
    DATA_WRITE = "DATA_WRITE"
    DATA_DELETE = "DATA_DELETE"
    DATA_EXPORT = "DATA_EXPORT"

    # Authentication events
    AUTH_SUCCESS = "AUTH_SUCCESS"
    AUTH_FAILURE = "AUTH_FAILURE"
    AUTH_TOKEN_ISSUED = "AUTH_TOKEN_ISSUED"
    AUTH_TOKEN_REVOKED = "AUTH_TOKEN_REVOKED"

    # Administrative events
    TENANT_CREATED = "TENANT_CREATED"
    TENANT_SUSPENDED = "TENANT_SUSPENDED"
    TENANT_PURGED = "TENANT_PURGED"
    AGENT_REGISTERED = "AGENT_REGISTERED"
    AGENT_DEREGISTERED = "AGENT_DEREGISTERED"

    # Compliance-specific
    PHI_ACCESS = "PHI_ACCESS"           # HIPAA
    PCI_DATA_ACCESS = "PCI_DATA_ACCESS" # PCI-DSS
    ENCRYPTION_KEY_ROTATED = "ENCRYPTION_KEY_ROTATED"
    CUSTOMER_MERGED = "CUSTOMER_MERGED"
    COMPLIANCE_AUDIT_RUN = "COMPLIANCE_AUDIT_RUN"

    # Security events
    THREAT_DETECTED = "THREAT_DETECTED"
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"
    POLICY_VIOLATION = "POLICY_VIOLATION"


class AuditSeverity(Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class AuditEvent:
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    event_type: AuditEventType = AuditEventType.DATA_READ
    severity: AuditSeverity = AuditSeverity.INFO
    actor: str = ""                 # Who (tenant_id, agent_id, user)
    resource: str = ""              # What (table, endpoint, customer_id)
    action: str = ""                # Operation performed
    outcome: str = "success"        # success, failure, blocked
    ip_address: str = ""
    user_agent: str = ""
    tenant_id: Optional[str] = None
    details: Dict = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "severity": self.severity.value,
            "actor": self.actor,
            "resource": self.resource,
            "action": self.action,
            "outcome": self.outcome,
            "ip_address": self.ip_address,
            "tenant_id": self.tenant_id,
            "details": self.details,
            "timestamp": self.timestamp,
        }


# Compliance retention policies (in days)
RETENTION_POLICIES = {
    "fedramp": 365 * 3,    # 3 years (NIST 800-53 AU-11)
    "soc2": 365,            # 1 year minimum
    "hipaa": 365 * 6,       # 6 years (45 CFR 164.530(j))
    "pci_dss": 365,         # 1 year online, 1 year archived
    "pa_dss": 365,          # 1 year
    "default": 365 * 7,     # 7 years (maximum of all)
}


class ComplianceAudit:
    """Compliance audit trail with framework-specific logging.

    Every access to sensitive data generates an audit event that is:
      1. Logged in-memory for real-time queries
      2. Written to ImmutableCore for tamper-evident persistence
      3. Classified by compliance framework relevance
    """

    def __init__(self, engines: Dict[str, Any] = None):
        self.engines = engines or {}
        self._events: List[AuditEvent] = []
        self._event_count = 0
        self._max_memory_events = 50000

    async def log(self, event_type: AuditEventType, actor: str,
                  resource: str, action: str = "",
                  outcome: str = "success",
                  tenant_id: Optional[str] = None,
                  details: Dict = None,
                  ip_address: str = "",
                  severity: AuditSeverity = None) -> AuditEvent:
        """Log a compliance audit event."""
        self._event_count += 1

        # Auto-determine severity
        if severity is None:
            severity = self._auto_severity(event_type, outcome)

        event = AuditEvent(
            event_type=event_type, severity=severity,
            actor=actor, resource=resource, action=action,
            outcome=outcome, tenant_id=tenant_id,
            details=details or {}, ip_address=ip_address)

        # Store in memory (ring buffer)
        self._events.append(event)
        if len(self._events) > self._max_memory_events:
            self._events = self._events[-self._max_memory_events:]

        # Persist to ImmutableCore
        if "immutable" in self.engines:
            try:
                await self.engines["immutable"].write("audit", {
                    "entry_type": f"COMPLIANCE_{event_type.value}",
                    **event.to_dict(),
                }, actor=actor)
            except Exception as e:
                logger.warning(f"Audit persistence error: {e}")

        # Log critical events
        if severity == AuditSeverity.CRITICAL:
            logger.warning(f"CRITICAL AUDIT: {event_type.value} by {actor} "
                           f"on {resource}: {outcome}")

        return event

    async def log_phi_access(self, actor: str, patient_id: str,
                              fields_accessed: List[str],
                              purpose: str = "",
                              tenant_id: Optional[str] = None) -> AuditEvent:
        """HIPAA-specific: log access to Protected Health Information."""
        return await self.log(
            event_type=AuditEventType.PHI_ACCESS,
            actor=actor, resource=f"patient:{patient_id}",
            action="phi_access",
            details={
                "fields_accessed": fields_accessed,
                "purpose": purpose,
                "phi_categories": [f for f in fields_accessed
                                   if f in {"diagnosis", "medication",
                                            "lab_result", "ssn", "date_of_birth"}],
            },
            tenant_id=tenant_id)

    async def log_pci_access(self, actor: str, resource_id: str,
                              data_type: str = "cardholder",
                              tenant_id: Optional[str] = None) -> AuditEvent:
        """PCI-DSS specific: log access to cardholder data."""
        return await self.log(
            event_type=AuditEventType.PCI_DATA_ACCESS,
            actor=actor, resource=f"pci:{resource_id}",
            action="pci_data_access",
            details={"data_type": data_type},
            tenant_id=tenant_id,
            severity=AuditSeverity.WARNING)

    async def log_threat(self, actor: str, threat_type: str,
                          threat_details: Dict,
                          ip_address: str = "",
                          tenant_id: Optional[str] = None) -> AuditEvent:
        """Log a security threat detection."""
        return await self.log(
            event_type=AuditEventType.THREAT_DETECTED,
            actor=actor, resource="security",
            action=threat_type, outcome="blocked",
            details=threat_details,
            ip_address=ip_address,
            tenant_id=tenant_id,
            severity=AuditSeverity.CRITICAL)

    def query_events(self, event_type: Optional[AuditEventType] = None,
                     actor: Optional[str] = None,
                     tenant_id: Optional[str] = None,
                     since: Optional[float] = None,
                     severity: Optional[AuditSeverity] = None,
                     limit: int = 100) -> List[Dict]:
        """Query audit events from memory."""
        results = []
        for event in reversed(self._events):
            if event_type and event.event_type != event_type:
                continue
            if actor and event.actor != actor:
                continue
            if tenant_id and event.tenant_id != tenant_id:
                continue
            if since and event.timestamp < since:
                continue
            if severity and event.severity != severity:
                continue
            results.append(event.to_dict())
            if len(results) >= limit:
                break
        return results

    async def generate_evidence_report(self, framework: str,
                                        start_time: float = None,
                                        end_time: float = None) -> Dict:
        """Generate compliance evidence report for auditors."""
        start = start_time or (time.time() - 86400 * 90)  # Last 90 days
        end = end_time or time.time()

        relevant_events = [
            e for e in self._events
            if start <= e.timestamp <= end
        ]

        # Framework-specific event types
        framework_types = {
            "fedramp": {AuditEventType.AUTH_SUCCESS, AuditEventType.AUTH_FAILURE,
                        AuditEventType.THREAT_DETECTED, AuditEventType.DATA_WRITE,
                        AuditEventType.TENANT_CREATED, AuditEventType.POLICY_VIOLATION},
            "soc2": {AuditEventType.DATA_READ, AuditEventType.DATA_WRITE,
                     AuditEventType.AUTH_SUCCESS, AuditEventType.AUTH_FAILURE,
                     AuditEventType.TENANT_CREATED, AuditEventType.COMPLIANCE_AUDIT_RUN},
            "hipaa": {AuditEventType.PHI_ACCESS, AuditEventType.DATA_EXPORT,
                      AuditEventType.AUTH_FAILURE, AuditEventType.ENCRYPTION_KEY_ROTATED,
                      AuditEventType.DATA_DELETE},
            "pci_dss": {AuditEventType.PCI_DATA_ACCESS, AuditEventType.AUTH_FAILURE,
                        AuditEventType.THREAT_DETECTED, AuditEventType.ENCRYPTION_KEY_ROTATED,
                        AuditEventType.RATE_LIMIT_EXCEEDED},
            "pa_dss": {AuditEventType.PCI_DATA_ACCESS, AuditEventType.AUTH_FAILURE,
                       AuditEventType.THREAT_DETECTED},
        }

        types = framework_types.get(framework, set())
        filtered = [e for e in relevant_events if e.event_type in types]

        # Statistics
        by_type = {}
        by_severity = {"info": 0, "warning": 0, "critical": 0}
        by_outcome = {"success": 0, "failure": 0, "blocked": 0}

        for e in filtered:
            by_type[e.event_type.value] = by_type.get(e.event_type.value, 0) + 1
            by_severity[e.severity.value] = by_severity.get(e.severity.value, 0) + 1
            by_outcome[e.outcome] = by_outcome.get(e.outcome, 0) + 1

        return {
            "framework": framework,
            "period": {"start": start, "end": end},
            "total_events": len(filtered),
            "retention_days": RETENTION_POLICIES.get(framework, 365),
            "by_type": by_type,
            "by_severity": by_severity,
            "by_outcome": by_outcome,
            "sample_events": [e.to_dict() for e in filtered[:20]],
        }

    @staticmethod
    def _auto_severity(event_type: AuditEventType,
                       outcome: str) -> AuditSeverity:
        """Auto-assign severity based on event type and outcome."""
        if event_type in (AuditEventType.THREAT_DETECTED,
                          AuditEventType.POLICY_VIOLATION,
                          AuditEventType.TENANT_PURGED):
            return AuditSeverity.CRITICAL
        if event_type in (AuditEventType.AUTH_FAILURE,
                          AuditEventType.RATE_LIMIT_EXCEEDED,
                          AuditEventType.PCI_DATA_ACCESS):
            return AuditSeverity.WARNING
        if outcome in ("failure", "blocked"):
            return AuditSeverity.WARNING
        return AuditSeverity.INFO

    def get_stats(self) -> Dict:
        return {
            "total_events": self._event_count,
            "events_in_memory": len(self._events),
            "max_memory_events": self._max_memory_events,
        }
