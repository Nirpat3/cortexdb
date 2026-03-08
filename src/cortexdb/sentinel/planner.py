"""
Campaign Planner — Plans and manages security attack campaigns.

Campaigns group sets of attack vectors into ordered test sequences
with configurable aggression levels, concurrency, and timeouts.
"""

from __future__ import annotations

import json
import logging
import secrets
import time
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from cortexdb.superadmin.persistence import PersistenceStore

logger = logging.getLogger("cortexdb.sentinel.planner")

# Phase ordering for campaign plans — tests run in this sequence
_PHASE_ORDER = [
    "reconnaissance",
    "authentication",
    "authorization",
    "injection",
    "business_logic",
    "cryptography",
    "configuration",
    "denial_of_service",
]

_DEFAULT_CONFIG = {
    "aggression_level": 2,
    "concurrency": 4,
    "timeout_per_test": 30,
    "max_duration": 3600,
}

# Estimated test counts per category
_CATEGORY_TEST_ESTIMATES = {
    "sql_injection": 18,
    "xss": 14,
    "auth_bypass": 12,
    "privilege_escalation": 10,
    "path_traversal": 8,
    "command_injection": 10,
    "ssrf": 8,
    "idor": 10,
    "csrf": 6,
    "cryptographic": 8,
    "rate_limiting": 6,
    "configuration": 10,
    "information_disclosure": 12,
    "denial_of_service": 8,
    "business_logic": 10,
}

# Map categories to phases
_CATEGORY_PHASE_MAP = {
    "sql_injection": "injection",
    "xss": "injection",
    "command_injection": "injection",
    "auth_bypass": "authentication",
    "privilege_escalation": "authorization",
    "idor": "authorization",
    "path_traversal": "injection",
    "ssrf": "injection",
    "csrf": "authentication",
    "cryptographic": "cryptography",
    "rate_limiting": "denial_of_service",
    "configuration": "configuration",
    "information_disclosure": "reconnaissance",
    "denial_of_service": "denial_of_service",
    "business_logic": "business_logic",
}


class CampaignPlanner:
    """Plans and manages attack campaigns."""

    def __init__(self, persistence_store: "PersistenceStore"):
        self._persistence = persistence_store
        self._init_db()

    def _init_db(self) -> None:
        conn = self._persistence.conn
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS sentinel_campaigns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                campaign_id TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                status TEXT NOT NULL DEFAULT 'draft'
                    CHECK(status IN ('draft', 'planned', 'running', 'completed', 'cancelled', 'failed')),
                target_categories TEXT NOT NULL DEFAULT '[]',
                target_endpoints TEXT NOT NULL DEFAULT '[]',
                schedule TEXT NOT NULL DEFAULT '{}',
                config TEXT NOT NULL DEFAULT '{}',
                created_at REAL NOT NULL,
                started_at REAL,
                completed_at REAL,
                created_by TEXT DEFAULT 'system'
            );

            CREATE INDEX IF NOT EXISTS idx_sentinel_campaigns_status
                ON sentinel_campaigns(status);
            CREATE INDEX IF NOT EXISTS idx_sentinel_campaigns_created
                ON sentinel_campaigns(created_at);
        """)
        conn.commit()

    # ── Helpers ─────────────────────────────────────────────────────────────

    _COLS = (
        "id, campaign_id, name, description, status, target_categories, "
        "target_endpoints, schedule, config, created_at, started_at, "
        "completed_at, created_by"
    )

    def _row_to_dict(self, row) -> dict:
        return {
            "id": row[0],
            "campaign_id": row[1],
            "name": row[2],
            "description": row[3],
            "status": row[4],
            "target_categories": json.loads(row[5]) if row[5] else [],
            "target_endpoints": json.loads(row[6]) if row[6] else [],
            "schedule": json.loads(row[7]) if row[7] else {},
            "config": json.loads(row[8]) if row[8] else {},
            "created_at": row[9],
            "started_at": row[10],
            "completed_at": row[11],
            "created_by": row[12],
        }

    # ── CRUD ────────────────────────────────────────────────────────────────

    def create_campaign(
        self,
        name: str,
        description: str,
        categories: List[str],
        endpoints: Optional[List[str]] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> dict:
        campaign_id = f"SC-{secrets.token_hex(8)}"
        now = time.time()
        merged_config = {**_DEFAULT_CONFIG, **(config or {})}
        merged_config["aggression_level"] = max(1, min(5, merged_config["aggression_level"]))

        self._persistence.conn.execute(
            f"INSERT INTO sentinel_campaigns ({self._COLS}) "
            "VALUES (NULL,?,?,?,'draft',?,?,?,?,?,NULL,NULL,?)",
            (
                campaign_id, name, description,
                json.dumps(categories),
                json.dumps(endpoints or []),
                json.dumps({}),
                json.dumps(merged_config),
                now,
                "system",
            ),
        )
        self._persistence.conn.commit()
        logger.info("Created campaign %s: %s", campaign_id, name)
        return self.get_campaign(campaign_id)

    def plan_campaign(self, campaign_id: str) -> dict:
        campaign = self.get_campaign(campaign_id)
        if "error" in campaign:
            return campaign

        categories = campaign["target_categories"]
        if not categories:
            return {"error": "Campaign has no target categories", "campaign_id": campaign_id}

        # Build phases from categories
        phases: Dict[str, Dict] = {}
        for cat in categories:
            phase_name = _CATEGORY_PHASE_MAP.get(cat, "business_logic")
            if phase_name not in phases:
                phases[phase_name] = {
                    "phase": phase_name,
                    "categories": [],
                    "estimated_tests": 0,
                    "order": _PHASE_ORDER.index(phase_name) if phase_name in _PHASE_ORDER else 99,
                }
            phases[phase_name]["categories"].append(cat)
            phases[phase_name]["estimated_tests"] += _CATEGORY_TEST_ESTIMATES.get(cat, 8)

        ordered_phases = sorted(phases.values(), key=lambda p: p["order"])
        for i, phase in enumerate(ordered_phases):
            phase["sequence"] = i + 1
            del phase["order"]

        total_tests = sum(p["estimated_tests"] for p in ordered_phases)
        config = campaign["config"]
        estimated_duration = (total_tests * config.get("timeout_per_test", 30)) / max(
            config.get("concurrency", 4), 1
        )

        plan = {
            "campaign_id": campaign_id,
            "phases": ordered_phases,
            "total_phases": len(ordered_phases),
            "estimated_total_tests": total_tests,
            "estimated_duration_seconds": round(estimated_duration),
            "config": config,
        }

        # Update campaign status to planned
        self.update_campaign(campaign_id, {"status": "planned", "schedule": plan})
        logger.info("Planned campaign %s: %d phases, ~%d tests", campaign_id, len(ordered_phases), total_tests)
        return plan

    def list_campaigns(self, status: Optional[str] = None, limit: int = 50) -> list:
        sql = f"SELECT {self._COLS} FROM sentinel_campaigns"
        params: list = []
        if status:
            sql += " WHERE status = ?"
            params.append(status)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        rows = self._persistence.conn.execute(sql, params).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def get_campaign(self, campaign_id: str) -> dict:
        row = self._persistence.conn.execute(
            f"SELECT {self._COLS} FROM sentinel_campaigns WHERE campaign_id = ?",
            (campaign_id,),
        ).fetchone()
        if not row:
            return {"error": "Campaign not found", "campaign_id": campaign_id}
        return self._row_to_dict(row)

    def update_campaign(self, campaign_id: str, updates: Dict[str, Any]) -> dict:
        existing = self.get_campaign(campaign_id)
        if "error" in existing:
            return existing

        allowed = {"name", "description", "status", "target_categories",
                    "target_endpoints", "schedule", "config", "started_at",
                    "completed_at", "created_by"}
        sets, params = [], []
        for key, val in updates.items():
            if key not in allowed:
                continue
            if key in ("target_categories", "target_endpoints", "schedule", "config"):
                val = json.dumps(val)
            sets.append(f"{key} = ?")
            params.append(val)

        if not sets:
            return {"error": "No valid fields to update"}

        params.append(campaign_id)
        self._persistence.conn.execute(
            f"UPDATE sentinel_campaigns SET {', '.join(sets)} WHERE campaign_id = ?",
            params,
        )
        self._persistence.conn.commit()
        logger.info("Updated campaign %s", campaign_id)
        return self.get_campaign(campaign_id)

    def delete_campaign(self, campaign_id: str) -> bool:
        existing = self.get_campaign(campaign_id)
        if "error" in existing:
            return False
        self._persistence.conn.execute(
            "DELETE FROM sentinel_campaigns WHERE campaign_id = ?", (campaign_id,)
        )
        self._persistence.conn.commit()
        logger.info("Deleted campaign %s", campaign_id)
        return True

    def start_campaign(self, campaign_id: str) -> dict:
        campaign = self.get_campaign(campaign_id)
        if "error" in campaign:
            return campaign
        if campaign["status"] not in ("draft", "planned"):
            return {"error": f"Cannot start campaign in '{campaign['status']}' status"}
        return self.update_campaign(campaign_id, {
            "status": "running",
            "started_at": time.time(),
        })

    def complete_campaign(self, campaign_id: str, summary: Optional[Dict] = None) -> dict:
        campaign = self.get_campaign(campaign_id)
        if "error" in campaign:
            return campaign
        updates: Dict[str, Any] = {
            "status": "completed",
            "completed_at": time.time(),
        }
        if summary:
            schedule = campaign.get("schedule", {})
            if isinstance(schedule, dict):
                schedule["summary"] = summary
            else:
                schedule = {"summary": summary}
            updates["schedule"] = schedule
        return self.update_campaign(campaign_id, updates)
