"""Architecture Standards Authority (ASA) Enforcement (DOC-015 Section 9)

21 ASA Standards. Enforcement: HARD (blocks), SOFT (warns), ADVISORY (logs).
"""

import time
import logging
from collections import Counter
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional
from enum import Enum

logger = logging.getLogger("cortexdb.asa")


class EnforcementLevel(Enum):
    HARD = "HARD"
    SOFT = "SOFT"
    ADVISORY = "ADVISORY"


@dataclass
class ASAStandard:
    standard_id: str
    category: str
    title: str
    description: str
    enforcement: EnforcementLevel = EnforcementLevel.HARD
    source_document: str = ""
    version: str = "1.0.0"
    active: bool = True


@dataclass
class ASAViolation:
    standard_id: str
    enforcement: EnforcementLevel
    message: str
    context: Dict = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    blocked: bool = False


STANDARDS = [
    ASAStandard("NIRLAB-STD-001", "Block Architecture", "Universal Block Interface",
                "All blocks must have: block_id, version, input_schema, output_schema, dependencies, config_schema",
                EnforcementLevel.HARD, "DOC-013"),
    ASAStandard("NIRLAB-STD-002", "Communication", "Approved Protocols",
                "gRPC (internal), HTTP/2 (API), WebSocket (real-time), Redis Streams (events)",
                EnforcementLevel.HARD, "DOC-014"),
    ASAStandard("NIRLAB-STD-003", "Data Format", "Payload Standards",
                "JSON (REST), ISO 8601 (dates), ISO 4217 (currency)",
                EnforcementLevel.HARD, "DOC-010"),
    ASAStandard("NIRLAB-STD-004", "Naming", "Resource Naming",
                "Services: kebab-case. Agents: PascalCase. Tables: snake_case.",
                EnforcementLevel.SOFT, "DOC-015"),
    ASAStandard("NIRLAB-STD-005", "API", "API Versioning",
                "All APIs versioned /v1/. Breaking changes = new major version.",
                EnforcementLevel.HARD, "DOC-015"),
    ASAStandard("NIRLAB-STD-006", "Grid", "Packet Envelope",
                "All grid packets: packet_id, source, destination, priority, ttl",
                EnforcementLevel.HARD, "DOC-015"),
    ASAStandard("NIRLAB-STD-007", "Error Handling", "RFC 7807 Errors",
                "All errors: {type, title, status, detail, instance}",
                EnforcementLevel.SOFT, "DOC-015"),
    ASAStandard("NIRLAB-STD-008", "Logging", "Structured Logging",
                "All logs: {timestamp, level, service, trace_id, message, context}",
                EnforcementLevel.SOFT, "DOC-015"),
    ASAStandard("NIRLAB-STD-009", "Performance", "Service SLAs",
                "Liveness < 3s. API p95 < 500ms. Error rate < 2%.",
                EnforcementLevel.HARD, "DOC-014"),
    ASAStandard("NIRLAB-SEC-001", "Security", "Birth Certificate Enforcement",
                "Every agent must have valid Birth Certificate. Tools subset of parent.",
                EnforcementLevel.HARD, "DOC-003"),
    ASAStandard("NIRLAB-SEC-002", "Security", "Secret Management",
                "No plaintext secrets in env/config/code. Use Vault or encrypted config.",
                EnforcementLevel.HARD, "DOC-006"),
    ASAStandard("NIRLAB-GRID-001", "Grid", "Minimum Redundancy",
                "Every node type >= 2 instances (except PRIME). Removal blocked if violation.",
                EnforcementLevel.HARD, "DOC-015"),
    ASAStandard("NIRLAB-GRID-002", "Grid", "Dead Node Timeout",
                "Nodes MUST be declared DEAD within 3x heartbeat interval. No exceptions.",
                EnforcementLevel.HARD, "DOC-015"),
    ASAStandard("NIRLAB-GRID-003", "Grid", "Repair Level Escalation",
                "Total automated repair window: 10 minutes maximum.",
                EnforcementLevel.HARD, "DOC-015"),
    ASAStandard("NIRLAB-GRID-004", "Grid", "Tombstone Retention",
                "90 days hot + 7 years cold. Grid addresses locked 24hr after removal.",
                EnforcementLevel.HARD, "DOC-015"),
    ASAStandard("NIRLAB-GRID-005", "Grid", "Health Score Transparency",
                "CHRONIC/TERMINAL nodes generate investigation tickets within 24 hours.",
                EnforcementLevel.HARD, "DOC-015"),
]


class ASAEnforcer:
    def __init__(self):
        self._standards = {s.standard_id: s for s in STANDARDS}
        self._violations: List[ASAViolation] = []

    def get_standard(self, standard_id: str) -> Optional[ASAStandard]:
        return self._standards.get(standard_id)

    def get_all_standards(self, category: Optional[str] = None,
                          active_only: bool = True) -> List[ASAStandard]:
        standards = list(self._standards.values())
        if category:
            standards = [s for s in standards if s.category == category]
        if active_only:
            standards = [s for s in standards if s.active]
        return standards

    def check_and_enforce(self, standard_id: str, condition: bool,
                          message: str, context: Dict = None) -> Optional[ASAViolation]:
        standard = self._standards.get(standard_id)
        if not standard or not standard.active or condition:
            return None

        violation = ASAViolation(
            standard_id=standard_id, enforcement=standard.enforcement,
            message=message, context=context or {},
            blocked=standard.enforcement == EnforcementLevel.HARD,
        )
        self._violations.append(violation)

        if standard.enforcement == EnforcementLevel.HARD:
            logger.error(f"ASA VIOLATION (HARD): [{standard_id}] {message}")
        elif standard.enforcement == EnforcementLevel.SOFT:
            logger.warning(f"ASA VIOLATION (SOFT): [{standard_id}] {message}")
        else:
            logger.info(f"ASA ADVISORY: [{standard_id}] {message}")
        return violation

    def check_grid_removal(self, node_type: str, healthy_count: int,
                           is_prime: bool = False) -> Optional[ASAViolation]:
        if is_prime:
            return self.check_and_enforce("NIRLAB-GRID-001", healthy_count >= 1,
                                          f"Cannot remove PRIME: need >= 1 standby, have {healthy_count}")
        return self.check_and_enforce("NIRLAB-GRID-001", healthy_count >= 2,
                                      f"Need >= 2 healthy '{node_type}', would have {healthy_count}")

    def check_repair_window(self, elapsed_seconds: float) -> Optional[ASAViolation]:
        return self.check_and_enforce("NIRLAB-GRID-003", elapsed_seconds <= 600,
                                      f"Repair window exceeded: {elapsed_seconds:.0f}s > 600s")

    def get_violations(self, limit: int = 100) -> List[Dict]:
        return [{"standard_id": v.standard_id, "enforcement": v.enforcement.value,
                 "message": v.message, "timestamp": v.timestamp, "blocked": v.blocked}
                for v in self._violations[-limit:]]

    def get_violation_stats(self) -> Dict:
        by_std = Counter(v.standard_id for v in self._violations)
        return {"total": len(self._violations), "by_standard": dict(by_std),
                "blocked_count": sum(1 for v in self._violations if v.blocked)}
