"""
Zero-Trust Network Policies — mTLS, policy-based access control, encrypted inter-agent communication.

Evaluates every request against ordered priority-based allow/deny/require_auth policies.
Manages certificate lifecycle (issue, revoke, expire) and maintains a full audit trail
of policy evaluation decisions.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from cortexdb.superadmin.persistence import PersistenceStore

logger = logging.getLogger("cortexdb.zero_trust")

# ── Default seed policies ──────────────────────────────────────────────────────

_DEFAULT_POLICIES = [
    {
        "name": "Require auth for superadmin routes",
        "description": "All /superadmin/* endpoints require authenticated sessions",
        "policy_type": "require_auth",
        "source_pattern": "*",
        "destination_pattern": "/superadmin/*",
        "conditions": {"require_session": True},
        "priority": 10,
    },
    {
        "name": "Allow health checks without auth",
        "description": "Health and readiness probes are accessible without credentials",
        "policy_type": "allow",
        "source_pattern": "*",
        "destination_pattern": "/health/*",
        "conditions": {"methods": ["GET", "HEAD"]},
        "priority": 5,
    },
    {
        "name": "Require mTLS for inter-agent communication",
        "description": "Agent-to-agent messages must present valid client certificates",
        "policy_type": "require_auth",
        "source_pattern": "agent:*",
        "destination_pattern": "agent:*",
        "conditions": {"require_mtls": True, "require_valid_cert": True},
        "priority": 15,
    },
    {
        "name": "Deny external access to internal APIs",
        "description": "Block requests from external sources to internal-only endpoints",
        "policy_type": "deny",
        "source_pattern": "external:*",
        "destination_pattern": "/internal/*",
        "conditions": {"log_violation": True},
        "priority": 1,
    },
    {
        "name": "Allow webhook endpoints",
        "description": "Inbound webhooks are allowed with signature verification",
        "policy_type": "allow",
        "source_pattern": "*",
        "destination_pattern": "/webhooks/*",
        "conditions": {"require_signature": True},
        "priority": 20,
    },
    {
        "name": "Require encryption for data-at-rest operations",
        "description": "Any write to persistent storage must use encrypted channels",
        "policy_type": "require_auth",
        "source_pattern": "*",
        "destination_pattern": "storage:*",
        "conditions": {"require_encryption": True, "min_key_bits": 256},
        "priority": 12,
    },
]


def _match_pattern(pattern: str, value: str) -> bool:
    """Simple glob-style matching: '*' matches any sequence of characters."""
    if pattern == "*":
        return True
    if "*" not in pattern:
        return pattern == value
    # Split on '*' and match segments in order
    parts = pattern.split("*")
    idx = 0
    for i, part in enumerate(parts):
        if not part:
            continue
        pos = value.find(part, idx)
        if pos == -1:
            return False
        if i == 0 and pos != 0:
            return False
        idx = pos + len(part)
    if parts[-1] and not value.endswith(parts[-1]):
        return False
    return True


class ZeroTrustManager:
    """Policy-based zero-trust access control with certificate management."""

    def __init__(self, persistence_store: "PersistenceStore"):
        self._persistence = persistence_store
        self._init_db()

    # ── Schema ──────────────────────────────────────────────────────────────

    def _init_db(self) -> None:
        conn = self._persistence.conn
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS zt_policies (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                policy_type TEXT NOT NULL CHECK(policy_type IN ('allow', 'deny', 'require_auth')),
                source_pattern TEXT NOT NULL DEFAULT '*',
                destination_pattern TEXT NOT NULL DEFAULT '*',
                conditions TEXT NOT NULL DEFAULT '{}',
                priority INTEGER NOT NULL DEFAULT 100,
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS zt_certificates (
                id TEXT PRIMARY KEY,
                subject TEXT NOT NULL,
                issuer TEXT NOT NULL DEFAULT 'CortexDB-CA',
                serial TEXT NOT NULL UNIQUE,
                fingerprint TEXT NOT NULL UNIQUE,
                not_before REAL NOT NULL,
                not_after REAL NOT NULL,
                status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active', 'revoked', 'expired')),
                created_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS zt_audit_log (
                id TEXT PRIMARY KEY,
                policy_id TEXT,
                source TEXT NOT NULL,
                destination TEXT NOT NULL,
                action TEXT NOT NULL CHECK(action IN ('allow', 'deny')),
                reason TEXT DEFAULT '',
                timestamp REAL NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_zt_policies_priority ON zt_policies(priority);
            CREATE INDEX IF NOT EXISTS idx_zt_policies_enabled ON zt_policies(enabled);
            CREATE INDEX IF NOT EXISTS idx_zt_certs_status ON zt_certificates(status);
            CREATE INDEX IF NOT EXISTS idx_zt_audit_ts ON zt_audit_log(timestamp);
        """)
        conn.commit()
        self._seed_defaults()

    def _seed_defaults(self) -> None:
        existing = self._persistence.conn.execute(
            "SELECT COUNT(*) FROM zt_policies"
        ).fetchone()[0]
        if existing > 0:
            return
        now = time.time()
        for pol in _DEFAULT_POLICIES:
            pid = f"ZTP-{uuid.uuid4().hex[:8]}"
            self._persistence.conn.execute(
                "INSERT INTO zt_policies "
                "(id, name, description, policy_type, source_pattern, destination_pattern, "
                "conditions, priority, enabled, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,1,?,?)",
                (
                    pid, pol["name"], pol["description"], pol["policy_type"],
                    pol["source_pattern"], pol["destination_pattern"],
                    json.dumps(pol["conditions"]), pol["priority"], now, now,
                ),
            )
        self._persistence.conn.commit()
        logger.info("Seeded %d default zero-trust policies", len(_DEFAULT_POLICIES))

    # ── Helpers ─────────────────────────────────────────────────────────────

    def _row_to_policy(self, row) -> dict:
        return {
            "id": row[0],
            "name": row[1],
            "description": row[2],
            "policy_type": row[3],
            "source_pattern": row[4],
            "destination_pattern": row[5],
            "conditions": json.loads(row[6]) if row[6] else {},
            "priority": row[7],
            "enabled": bool(row[8]),
            "created_at": row[9],
            "updated_at": row[10],
        }

    _POLICY_COLS = (
        "id, name, description, policy_type, source_pattern, destination_pattern, "
        "conditions, priority, enabled, created_at, updated_at"
    )

    def _row_to_cert(self, row) -> dict:
        return {
            "id": row[0],
            "subject": row[1],
            "issuer": row[2],
            "serial": row[3],
            "fingerprint": row[4],
            "not_before": row[5],
            "not_after": row[6],
            "status": row[7],
            "created_at": row[8],
        }

    _CERT_COLS = "id, subject, issuer, serial, fingerprint, not_before, not_after, status, created_at"

    # ── Policy CRUD ─────────────────────────────────────────────────────────

    def list_policies(self, enabled_only: bool = False) -> list:
        """Return all policies ordered by priority (ascending = highest priority first)."""
        sql = f"SELECT {self._POLICY_COLS} FROM zt_policies"
        if enabled_only:
            sql += " WHERE enabled = 1"
        sql += " ORDER BY priority ASC, created_at ASC"
        rows = self._persistence.conn.execute(sql).fetchall()
        return [self._row_to_policy(r) for r in rows]

    def get_policy(self, policy_id: str) -> dict:
        row = self._persistence.conn.execute(
            f"SELECT {self._POLICY_COLS} FROM zt_policies WHERE id = ?", (policy_id,)
        ).fetchone()
        if not row:
            return {"error": "Policy not found", "policy_id": policy_id}
        return self._row_to_policy(row)

    def create_policy(
        self,
        name: str,
        policy_type: str,
        source_pattern: str,
        destination_pattern: str,
        conditions: Optional[Dict] = None,
        priority: int = 100,
    ) -> dict:
        if policy_type not in ("allow", "deny", "require_auth"):
            return {"error": f"Invalid policy_type '{policy_type}'"}
        pid = f"ZTP-{uuid.uuid4().hex[:8]}"
        now = time.time()
        self._persistence.conn.execute(
            "INSERT INTO zt_policies "
            "(id, name, description, policy_type, source_pattern, destination_pattern, "
            "conditions, priority, enabled, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,1,?,?)",
            (
                pid, name, "", policy_type, source_pattern, destination_pattern,
                json.dumps(conditions or {}), priority, now, now,
            ),
        )
        self._persistence.conn.commit()
        logger.info("Created zero-trust policy %s: %s", pid, name)
        return self.get_policy(pid)

    def update_policy(self, policy_id: str, updates: Dict[str, Any]) -> dict:
        existing = self.get_policy(policy_id)
        if "error" in existing:
            return existing
        allowed = {"name", "description", "policy_type", "source_pattern",
                    "destination_pattern", "conditions", "priority", "enabled"}
        sets, params = [], []
        for key, val in updates.items():
            if key not in allowed:
                continue
            if key == "conditions":
                val = json.dumps(val)
            if key == "enabled":
                val = 1 if val else 0
            sets.append(f"{key} = ?")
            params.append(val)
        if not sets:
            return {"error": "No valid fields to update"}
        sets.append("updated_at = ?")
        params.append(time.time())
        params.append(policy_id)
        self._persistence.conn.execute(
            f"UPDATE zt_policies SET {', '.join(sets)} WHERE id = ?", params
        )
        self._persistence.conn.commit()
        logger.info("Updated zero-trust policy %s", policy_id)
        return self.get_policy(policy_id)

    def delete_policy(self, policy_id: str) -> dict:
        existing = self.get_policy(policy_id)
        if "error" in existing:
            return existing
        self._persistence.conn.execute("DELETE FROM zt_policies WHERE id = ?", (policy_id,))
        self._persistence.conn.commit()
        logger.info("Deleted zero-trust policy %s", policy_id)
        return {"deleted": True, "policy_id": policy_id}

    def enable_policy(self, policy_id: str) -> dict:
        return self.update_policy(policy_id, {"enabled": True})

    def disable_policy(self, policy_id: str) -> dict:
        return self.update_policy(policy_id, {"enabled": False})

    # ── Policy Evaluation ───────────────────────────────────────────────────

    def evaluate_request(
        self,
        source: str,
        destination: str,
        context: Optional[Dict] = None,
    ) -> dict:
        """
        Evaluate all enabled policies against a request.

        Policies are checked in priority order (lowest number = highest priority).
        The first matching policy determines the outcome. If no policy matches
        the request is denied by default (zero-trust).
        """
        context = context or {}
        policies = self.list_policies(enabled_only=True)

        for pol in policies:
            src_match = _match_pattern(pol["source_pattern"], source)
            dst_match = _match_pattern(pol["destination_pattern"], destination)
            if not (src_match and dst_match):
                continue

            # Matched — determine action
            if pol["policy_type"] == "deny":
                action = "deny"
                reason = f"Denied by policy '{pol['name']}'"
            elif pol["policy_type"] == "require_auth":
                # Check if context satisfies auth conditions
                conditions = pol.get("conditions", {})
                authenticated = context.get("authenticated", False)
                has_mtls = context.get("mtls", False)
                if conditions.get("require_mtls") and not has_mtls:
                    action = "deny"
                    reason = f"mTLS required by policy '{pol['name']}'"
                elif conditions.get("require_session") and not authenticated:
                    action = "deny"
                    reason = f"Authentication required by policy '{pol['name']}'"
                elif conditions.get("require_encryption") and not context.get("encrypted", False):
                    action = "deny"
                    reason = f"Encryption required by policy '{pol['name']}'"
                else:
                    action = "allow"
                    reason = f"Auth conditions satisfied for policy '{pol['name']}'"
            else:  # allow
                action = "allow"
                reason = f"Allowed by policy '{pol['name']}'"

            # Audit the decision
            self._log_audit(pol["id"], source, destination, action, reason)
            return {
                "action": action,
                "reason": reason,
                "matched_policy": pol["id"],
                "policy_name": pol["name"],
                "source": source,
                "destination": destination,
            }

        # No policy matched — default deny (zero-trust)
        reason = "No matching policy — default deny"
        self._log_audit(None, source, destination, "deny", reason)
        return {
            "action": "deny",
            "reason": reason,
            "matched_policy": None,
            "policy_name": None,
            "source": source,
            "destination": destination,
        }

    def _log_audit(
        self,
        policy_id: Optional[str],
        source: str,
        destination: str,
        action: str,
        reason: str,
    ) -> None:
        aid = f"ZTA-{uuid.uuid4().hex[:8]}"
        self._persistence.conn.execute(
            "INSERT INTO zt_audit_log (id, policy_id, source, destination, action, reason, timestamp) "
            "VALUES (?,?,?,?,?,?,?)",
            (aid, policy_id, source, destination, action, reason, time.time()),
        )
        self._persistence.conn.commit()

    # ── Certificate Management ──────────────────────────────────────────────

    def list_certificates(self, status: Optional[str] = None) -> list:
        self._expire_certificates()
        sql = f"SELECT {self._CERT_COLS} FROM zt_certificates"
        params: list = []
        if status:
            sql += " WHERE status = ?"
            params.append(status)
        sql += " ORDER BY created_at DESC"
        rows = self._persistence.conn.execute(sql, params).fetchall()
        return [self._row_to_cert(r) for r in rows]

    def issue_certificate(self, subject: str, validity_days: int = 365) -> dict:
        """Issue a self-signed certificate (metadata stored, no real PKI)."""
        cid = f"ZTC-{uuid.uuid4().hex[:8]}"
        serial = secrets.token_hex(16)
        fingerprint = hashlib.sha256(f"{subject}:{serial}:{time.time()}".encode()).hexdigest()
        now = time.time()
        not_after = now + (validity_days * 86400)

        self._persistence.conn.execute(
            f"INSERT INTO zt_certificates ({self._CERT_COLS}) VALUES (?,?,?,?,?,?,?,?,?)",
            (cid, subject, "CortexDB-CA", serial, fingerprint, now, not_after, "active", now),
        )
        self._persistence.conn.commit()
        logger.info("Issued certificate %s for subject '%s' (valid %d days)", cid, subject, validity_days)
        return self._row_to_cert(
            self._persistence.conn.execute(
                f"SELECT {self._CERT_COLS} FROM zt_certificates WHERE id = ?", (cid,)
            ).fetchone()
        )

    def revoke_certificate(self, cert_id: str) -> dict:
        row = self._persistence.conn.execute(
            f"SELECT {self._CERT_COLS} FROM zt_certificates WHERE id = ?", (cert_id,)
        ).fetchone()
        if not row:
            return {"error": "Certificate not found", "cert_id": cert_id}
        self._persistence.conn.execute(
            "UPDATE zt_certificates SET status = 'revoked' WHERE id = ?", (cert_id,)
        )
        self._persistence.conn.commit()
        logger.info("Revoked certificate %s", cert_id)
        return {**self._row_to_cert(row), "status": "revoked"}

    def _expire_certificates(self) -> None:
        """Mark active certificates past their not_after as expired."""
        now = time.time()
        self._persistence.conn.execute(
            "UPDATE zt_certificates SET status = 'expired' "
            "WHERE status = 'active' AND not_after < ?",
            (now,),
        )
        self._persistence.conn.commit()

    # ── Audit Log ───────────────────────────────────────────────────────────

    def get_audit_log(self, limit: int = 100) -> list:
        rows = self._persistence.conn.execute(
            "SELECT id, policy_id, source, destination, action, reason, timestamp "
            "FROM zt_audit_log ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [
            {
                "id": r[0], "policy_id": r[1], "source": r[2],
                "destination": r[3], "action": r[4], "reason": r[5],
                "timestamp": r[6],
            }
            for r in rows
        ]

    # ── Stats ───────────────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        conn = self._persistence.conn
        total_policies = conn.execute("SELECT COUNT(*) FROM zt_policies").fetchone()[0]
        enabled_policies = conn.execute(
            "SELECT COUNT(*) FROM zt_policies WHERE enabled = 1"
        ).fetchone()[0]

        self._expire_certificates()
        total_certs = conn.execute("SELECT COUNT(*) FROM zt_certificates").fetchone()[0]
        active_certs = conn.execute(
            "SELECT COUNT(*) FROM zt_certificates WHERE status = 'active'"
        ).fetchone()[0]
        revoked_certs = conn.execute(
            "SELECT COUNT(*) FROM zt_certificates WHERE status = 'revoked'"
        ).fetchone()[0]

        total_requests = conn.execute("SELECT COUNT(*) FROM zt_audit_log").fetchone()[0]
        allowed = conn.execute(
            "SELECT COUNT(*) FROM zt_audit_log WHERE action = 'allow'"
        ).fetchone()[0]
        denied = conn.execute(
            "SELECT COUNT(*) FROM zt_audit_log WHERE action = 'deny'"
        ).fetchone()[0]

        return {
            "policies": {
                "total": total_policies,
                "enabled": enabled_policies,
                "disabled": total_policies - enabled_policies,
            },
            "certificates": {
                "total": total_certs,
                "active": active_certs,
                "revoked": revoked_certs,
                "expired": total_certs - active_certs - revoked_certs,
            },
            "requests": {
                "total": total_requests,
                "allowed": allowed,
                "denied": denied,
                "deny_rate": round(denied / total_requests * 100, 1) if total_requests else 0.0,
            },
        }
