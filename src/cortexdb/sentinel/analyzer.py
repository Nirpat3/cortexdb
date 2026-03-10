"""
Security Analyzer — Computes security posture scores, generates remediation plans, tracks trends.

Provides quantitative security assessment based on findings from attack campaigns,
with actionable remediation steps for each finding category.
"""

from __future__ import annotations

import json
import logging
import secrets
import time
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from cortexdb.superadmin.persistence import PersistenceStore

logger = logging.getLogger("cortexdb.sentinel.analyzer")

# Severity deduction weights for posture scoring
_SEVERITY_DEDUCTIONS = {
    "critical": 15,
    "high": 8,
    "medium": 3,
    "low": 1,
}

# Built-in remediation knowledge base — maps category to actionable steps
_REMEDIATION_TEMPLATES = {
    "sql_injection": {
        "title": "SQL Injection Remediation",
        "effort_estimate": "medium",
        "steps": [
            "Verify all queries use parameterized placeholders",
            "Add input validation for user-supplied values",
            "Review Amygdala bypass patterns",
            "Add WAF rules for detected payload pattern",
            "Implement stored procedures for complex queries",
            "Enable query logging to detect injection attempts",
        ],
    },
    "xss": {
        "title": "Cross-Site Scripting Remediation",
        "effort_estimate": "medium",
        "steps": [
            "Implement context-aware output encoding for all user input",
            "Enable Content-Security-Policy headers with strict directives",
            "Sanitize HTML input using a whitelist-based library",
            "Review and fix reflected XSS in query parameters",
            "Add HttpOnly and Secure flags to all session cookies",
            "Implement DOM purification for client-side rendering",
        ],
    },
    "auth_bypass": {
        "title": "Authentication Bypass Remediation",
        "effort_estimate": "high",
        "steps": [
            "Verify token validation on endpoint",
            "Add authentication middleware",
            "Implement constant-time comparison for secrets",
            "Add rate limiting for auth endpoints",
            "Review session fixation protections",
            "Enforce multi-factor authentication for sensitive operations",
        ],
    },
    "privilege_escalation": {
        "title": "Privilege Escalation Remediation",
        "effort_estimate": "high",
        "steps": [
            "Audit role-based access control assignments",
            "Implement least-privilege principle for all service accounts",
            "Add server-side authorization checks on every endpoint",
            "Review and restrict horizontal privilege paths",
            "Implement role hierarchy validation in middleware",
            "Add privilege change audit logging",
        ],
    },
    "path_traversal": {
        "title": "Path Traversal Remediation",
        "effort_estimate": "low",
        "steps": [
            "Canonicalize all file paths before access",
            "Implement allowlist for accessible directories",
            "Strip or reject path traversal sequences (../, ..\\)",
            "Use chroot or sandbox for file operations",
            "Validate file extensions against allowlist",
        ],
    },
    "command_injection": {
        "title": "Command Injection Remediation",
        "effort_estimate": "high",
        "steps": [
            "Replace shell command execution with native library calls",
            "Implement strict input validation with character allowlists",
            "Use parameterized command builders instead of string concatenation",
            "Sandbox command execution in restricted containers",
            "Add command audit logging with full argument capture",
        ],
    },
    "ssrf": {
        "title": "Server-Side Request Forgery Remediation",
        "effort_estimate": "medium",
        "steps": [
            "Implement URL allowlist for outbound requests",
            "Block requests to internal/private IP ranges",
            "Disable HTTP redirects in server-side HTTP clients",
            "Add DNS rebinding protections",
            "Validate and sanitize user-supplied URLs",
        ],
    },
    "idor": {
        "title": "Insecure Direct Object Reference Remediation",
        "effort_estimate": "medium",
        "steps": [
            "Replace sequential IDs with UUIDs or opaque references",
            "Add ownership verification before returning resources",
            "Implement per-user resource access scoping",
            "Add horizontal access control checks in data layer",
            "Log and alert on cross-tenant access attempts",
        ],
    },
    "csrf": {
        "title": "Cross-Site Request Forgery Remediation",
        "effort_estimate": "low",
        "steps": [
            "Implement anti-CSRF tokens on all state-changing endpoints",
            "Set SameSite=Strict on session cookies",
            "Validate Origin and Referer headers",
            "Use custom request headers for API calls",
        ],
    },
    "cryptographic": {
        "title": "Cryptographic Weakness Remediation",
        "effort_estimate": "high",
        "steps": [
            "Replace weak algorithms (MD5, SHA1, DES) with strong alternatives",
            "Rotate all compromised or weak encryption keys",
            "Enforce TLS 1.2+ with strong cipher suites",
            "Implement proper key management with hardware security modules",
            "Review and fix random number generation for security contexts",
            "Audit certificate validation and pinning",
        ],
    },
    "rate_limiting": {
        "title": "Rate Limiting Remediation",
        "effort_estimate": "low",
        "steps": [
            "Implement sliding window rate limiting on all public endpoints",
            "Add progressive backoff for repeated failures",
            "Configure per-IP and per-user rate limits",
            "Add CAPTCHA challenges after rate limit threshold",
        ],
    },
    "configuration": {
        "title": "Security Configuration Remediation",
        "effort_estimate": "low",
        "steps": [
            "Disable debug mode and verbose error messages in production",
            "Remove default credentials and sample data",
            "Harden HTTP security headers (HSTS, X-Frame-Options, etc.)",
            "Disable unnecessary HTTP methods (TRACE, OPTIONS)",
            "Review and restrict CORS configuration",
            "Remove server version disclosure from response headers",
        ],
    },
    "information_disclosure": {
        "title": "Information Disclosure Remediation",
        "effort_estimate": "low",
        "steps": [
            "Remove stack traces and debug info from error responses",
            "Implement generic error pages for production",
            "Audit API responses for excessive data exposure",
            "Remove sensitive files from web-accessible directories",
            "Disable directory listing on all servers",
        ],
    },
    "denial_of_service": {
        "title": "Denial of Service Remediation",
        "effort_estimate": "medium",
        "steps": [
            "Implement request size limits on all endpoints",
            "Add connection timeouts and idle session cleanup",
            "Configure rate limiting and throttling",
            "Add circuit breakers for downstream service calls",
            "Implement resource quotas per tenant",
        ],
    },
    "business_logic": {
        "title": "Business Logic Flaw Remediation",
        "effort_estimate": "high",
        "steps": [
            "Review and document expected state machine transitions",
            "Add server-side validation for all business rules",
            "Implement atomic transactions for multi-step operations",
            "Add integrity checks for financial and quantity calculations",
            "Create negative test cases for all business flows",
        ],
    },
}

# Default remediation for unknown categories
_DEFAULT_REMEDIATION = {
    "title": "General Security Remediation",
    "effort_estimate": "medium",
    "steps": [
        "Review the finding details and reproduce the vulnerability",
        "Identify the root cause in the affected component",
        "Implement a fix with appropriate input validation and access controls",
        "Add automated tests to prevent regression",
        "Conduct a follow-up scan to verify remediation",
    ],
}


class SecurityAnalyzer:
    """Computes security posture scores, generates remediation plans, tracks trends."""

    def __init__(self, persistence_store: "PersistenceStore"):
        self._persistence = persistence_store
        self._init_db()

    def _init_db(self) -> None:
        conn = self._persistence.conn
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS sentinel_posture (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_id TEXT NOT NULL UNIQUE,
                overall_score REAL NOT NULL,
                category_scores TEXT NOT NULL DEFAULT '{}',
                total_tests INTEGER NOT NULL DEFAULT 0,
                total_pass INTEGER NOT NULL DEFAULT 0,
                total_fail INTEGER NOT NULL DEFAULT 0,
                critical_findings INTEGER NOT NULL DEFAULT 0,
                high_findings INTEGER NOT NULL DEFAULT 0,
                medium_findings INTEGER NOT NULL DEFAULT 0,
                low_findings INTEGER NOT NULL DEFAULT 0,
                trend TEXT NOT NULL DEFAULT 'stable',
                created_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS sentinel_remediation (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plan_id TEXT NOT NULL UNIQUE,
                finding_id TEXT DEFAULT '',
                title TEXT NOT NULL,
                description TEXT DEFAULT '',
                priority TEXT NOT NULL DEFAULT 'medium'
                    CHECK(priority IN ('critical', 'high', 'medium', 'low')),
                effort_estimate TEXT NOT NULL DEFAULT 'medium'
                    CHECK(effort_estimate IN ('low', 'medium', 'high')),
                steps TEXT NOT NULL DEFAULT '[]',
                status TEXT NOT NULL DEFAULT 'open'
                    CHECK(status IN ('open', 'in_progress', 'completed', 'dismissed')),
                assigned_to TEXT DEFAULT '',
                created_at REAL NOT NULL,
                completed_at REAL
            );

            CREATE INDEX IF NOT EXISTS idx_sentinel_posture_created
                ON sentinel_posture(created_at);
            CREATE INDEX IF NOT EXISTS idx_sentinel_remediation_status
                ON sentinel_remediation(status);
            CREATE INDEX IF NOT EXISTS idx_sentinel_remediation_priority
                ON sentinel_remediation(priority);
        """)
        conn.commit()

    # ── Posture helpers ────────────────────────────────────────────────────

    _POSTURE_COLS = (
        "id, snapshot_id, overall_score, category_scores, total_tests, "
        "total_pass, total_fail, critical_findings, high_findings, "
        "medium_findings, low_findings, trend, created_at"
    )

    def _row_to_posture(self, row) -> dict:
        return {
            "id": row[0],
            "snapshot_id": row[1],
            "overall_score": row[2],
            "category_scores": json.loads(row[3]) if row[3] else {},
            "total_tests": row[4],
            "total_pass": row[5],
            "total_fail": row[6],
            "critical_findings": row[7],
            "high_findings": row[8],
            "medium_findings": row[9],
            "low_findings": row[10],
            "trend": row[11],
            "created_at": row[12],
        }

    _REMEDIATION_COLS = (
        "id, plan_id, finding_id, title, description, priority, "
        "effort_estimate, steps, status, assigned_to, created_at, completed_at"
    )

    def _row_to_remediation(self, row) -> dict:
        return {
            "id": row[0],
            "plan_id": row[1],
            "finding_id": row[2],
            "title": row[3],
            "description": row[4],
            "priority": row[5],
            "effort_estimate": row[6],
            "steps": json.loads(row[7]) if row[7] else [],
            "status": row[8],
            "assigned_to": row[9],
            "created_at": row[10],
            "completed_at": row[11],
        }

    # ── Posture Scoring ────────────────────────────────────────────────────

    def compute_posture_score(self, findings: Optional[List[Dict]] = None) -> dict:
        findings = findings or []

        severity_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        category_findings: Dict[str, List[Dict]] = {}

        for f in findings:
            sev = f.get("severity", "low").lower()
            if sev in severity_counts:
                severity_counts[sev] += 1
            cat = f.get("category", "unknown")
            category_findings.setdefault(cat, []).append(f)

        # Overall score: start at 100, deduct per finding
        overall = 100.0
        for sev, count in severity_counts.items():
            overall -= count * _SEVERITY_DEDUCTIONS.get(sev, 1)
        overall = max(0.0, round(overall, 1))

        # Per-category scores
        category_scores = {}
        for cat, cat_findings in category_findings.items():
            cat_score = 100.0
            for f in cat_findings:
                sev = f.get("severity", "low").lower()
                cat_score -= _SEVERITY_DEDUCTIONS.get(sev, 1)
            category_scores[cat] = max(0.0, round(cat_score, 1))

        total_tests = len(findings) + sum(
            1 for f in findings if f.get("result") == "pass"
        )
        total_pass = sum(1 for f in findings if f.get("result") == "pass")
        total_fail = sum(1 for f in findings if f.get("result") != "pass")

        # Determine trend from history
        trend = self._compute_trend(overall)

        return {
            "overall_score": overall,
            "category_scores": category_scores,
            "severity_counts": severity_counts,
            "total_tests": total_tests,
            "total_pass": total_pass,
            "total_fail": total_fail,
            "critical_findings": severity_counts["critical"],
            "high_findings": severity_counts["high"],
            "medium_findings": severity_counts["medium"],
            "low_findings": severity_counts["low"],
            "trend": trend,
            "finding_count": len(findings),
        }

    def _compute_trend(self, current_score: float) -> str:
        history = self.get_posture_history(limit=3)
        if len(history) < 2:
            return "stable"
        prev_score = history[0]["overall_score"]
        if current_score > prev_score + 2:
            return "improving"
        elif current_score < prev_score - 2:
            return "degrading"
        return "stable"

    def save_posture_snapshot(self, score_data: dict) -> dict:
        snapshot_id = f"SP-{secrets.token_hex(8)}"
        now = time.time()
        self._persistence.conn.execute(
            f"INSERT INTO sentinel_posture ({self._POSTURE_COLS}) "
            "VALUES (NULL,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                snapshot_id,
                score_data.get("overall_score", 0),
                json.dumps(score_data.get("category_scores", {})),
                score_data.get("total_tests", 0),
                score_data.get("total_pass", 0),
                score_data.get("total_fail", 0),
                score_data.get("critical_findings", 0),
                score_data.get("high_findings", 0),
                score_data.get("medium_findings", 0),
                score_data.get("low_findings", 0),
                score_data.get("trend", "stable"),
                now,
            ),
        )
        self._persistence.conn.commit()
        logger.info("Saved posture snapshot %s (score: %.1f)", snapshot_id, score_data.get("overall_score", 0))
        row = self._persistence.conn.execute(
            f"SELECT {self._POSTURE_COLS} FROM sentinel_posture WHERE snapshot_id = ?",
            (snapshot_id,),
        ).fetchone()
        return self._row_to_posture(row)

    def get_posture_history(self, limit: int = 30) -> list:
        rows = self._persistence.conn.execute(
            f"SELECT {self._POSTURE_COLS} FROM sentinel_posture "
            "ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [self._row_to_posture(r) for r in rows]

    def get_trend_analysis(self) -> dict:
        history = self.get_posture_history(limit=3)
        if not history:
            return {
                "trend": "unknown",
                "snapshots": 0,
                "message": "No posture snapshots available",
            }

        latest = history[0]
        if len(history) < 2:
            return {
                "trend": "stable",
                "snapshots": 1,
                "current_score": latest["overall_score"],
                "message": "Only one snapshot available, trend unknown",
            }

        scores = [h["overall_score"] for h in history]
        avg_change = (scores[0] - scores[-1]) / (len(scores) - 1)

        if avg_change > 2:
            trend = "improving"
            message = f"Score improving by ~{abs(avg_change):.1f} points per snapshot"
        elif avg_change < -2:
            trend = "degrading"
            message = f"Score degrading by ~{abs(avg_change):.1f} points per snapshot"
        else:
            trend = "stable"
            message = "Score is stable across recent snapshots"

        return {
            "trend": trend,
            "snapshots": len(history),
            "current_score": scores[0],
            "previous_score": scores[1] if len(scores) > 1 else None,
            "oldest_score": scores[-1],
            "average_change": round(avg_change, 1),
            "message": message,
            "history": [
                {"snapshot_id": h["snapshot_id"], "score": h["overall_score"], "created_at": h["created_at"]}
                for h in history
            ],
        }

    def get_top_risks(self, limit: int = 10) -> list:
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        plans = self.list_remediation_plans(status="open")
        plans.sort(key=lambda p: (severity_order.get(p["priority"], 99), -p["created_at"]))
        return plans[:limit]

    # ── Remediation Plans ──────────────────────────────────────────────────

    def generate_remediation_plan(self, finding: dict) -> dict:
        plan_id = f"RP-{secrets.token_hex(8)}"
        now = time.time()

        category = finding.get("category", "unknown")
        severity = finding.get("severity", "medium").lower()
        finding_id = finding.get("id", finding.get("finding_id", ""))

        template = _REMEDIATION_TEMPLATES.get(category, _DEFAULT_REMEDIATION)

        description_parts = []
        if finding.get("description"):
            description_parts.append(finding["description"])
        if finding.get("endpoint"):
            description_parts.append(f"Affected endpoint: {finding['endpoint']}")
        if finding.get("payload"):
            description_parts.append(f"Detected payload: {finding['payload']}")
        description = ". ".join(description_parts) if description_parts else f"Remediation for {category} finding"

        self._persistence.conn.execute(
            f"INSERT INTO sentinel_remediation ({self._REMEDIATION_COLS}) "
            "VALUES (NULL,?,?,?,?,?,?,?,?,?,?,NULL)",
            (
                plan_id,
                finding_id,
                template["title"],
                description,
                severity,
                template["effort_estimate"],
                json.dumps(template["steps"]),
                "open",
                "",
                now,
            ),
        )
        self._persistence.conn.commit()
        logger.info("Generated remediation plan %s for finding %s (%s)", plan_id, finding_id, category)

        row = self._persistence.conn.execute(
            f"SELECT {self._REMEDIATION_COLS} FROM sentinel_remediation WHERE plan_id = ?",
            (plan_id,),
        ).fetchone()
        return self._row_to_remediation(row)

    def list_remediation_plans(self, status: Optional[str] = None, limit: int = 50) -> list:
        sql = f"SELECT {self._REMEDIATION_COLS} FROM sentinel_remediation"
        params: list = []
        if status:
            sql += " WHERE status = ?"
            params.append(status)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        rows = self._persistence.conn.execute(sql, params).fetchall()
        return [self._row_to_remediation(r) for r in rows]

    def get_remediation(self, plan_id: str) -> dict:
        row = self._persistence.conn.execute(
            f"SELECT {self._REMEDIATION_COLS} FROM sentinel_remediation WHERE plan_id = ?",
            (plan_id,),
        ).fetchone()
        if not row:
            return {"error": "Remediation plan not found", "plan_id": plan_id}
        return self._row_to_remediation(row)

    def update_remediation(self, plan_id: str, updates: Dict[str, Any]) -> dict:
        existing = self.get_remediation(plan_id)
        if "error" in existing:
            return existing

        allowed = {"title", "description", "priority", "effort_estimate",
                    "steps", "status", "assigned_to", "completed_at"}
        sets, params = [], []
        for key, val in updates.items():
            if key not in allowed:
                continue
            if key == "steps":
                val = json.dumps(val)
            sets.append(f"{key} = ?")
            params.append(val)

        if not sets:
            return {"error": "No valid fields to update"}

        # Auto-set completed_at when status changes to completed
        if "status" in updates and updates["status"] == "completed" and "completed_at" not in updates:
            sets.append("completed_at = ?")
            params.append(time.time())

        params.append(plan_id)
        self._persistence.conn.execute(
            f"UPDATE sentinel_remediation SET {', '.join(sets)} WHERE plan_id = ?",
            params,
        )
        self._persistence.conn.commit()
        logger.info("Updated remediation plan %s", plan_id)
        return self.get_remediation(plan_id)

    # ── Category Breakdown ─────────────────────────────────────────────────

    def get_category_breakdown(self, findings: List[Dict]) -> dict:
        categories: Dict[str, Dict] = {}

        for f in findings:
            cat = f.get("category", "unknown")
            if cat not in categories:
                categories[cat] = {
                    "category": cat,
                    "tested": 0,
                    "passed": 0,
                    "failed": 0,
                    "score": 100.0,
                    "severities": {"critical": 0, "high": 0, "medium": 0, "low": 0},
                }
            entry = categories[cat]
            entry["tested"] += 1
            if f.get("result") == "pass":
                entry["passed"] += 1
            else:
                entry["failed"] += 1
                sev = f.get("severity", "low").lower()
                if sev in entry["severities"]:
                    entry["severities"][sev] += 1
                entry["score"] -= _SEVERITY_DEDUCTIONS.get(sev, 1)

        # Floor scores at 0
        for entry in categories.values():
            entry["score"] = max(0.0, round(entry["score"], 1))

        return {
            "categories": categories,
            "total_categories": len(categories),
            "weakest_category": min(categories.values(), key=lambda c: c["score"])["category"] if categories else None,
            "strongest_category": max(categories.values(), key=lambda c: c["score"])["category"] if categories else None,
        }
