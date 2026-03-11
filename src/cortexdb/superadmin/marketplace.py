"""
Marketplace Manager — Capability toggle system for CortexDB features.

Manages capabilities (features that can be toggled on/off) with dependency
resolution, tier-based access control, and persistent configuration.
Capabilities are stored in SQLite alongside other superadmin data.

Database: data/superadmin.db (shared with other superadmin modules)
Table: marketplace_capabilities
"""

import sqlite3
import json
import os
import logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, List, Dict, Any
from pathlib import Path

logger = logging.getLogger("cortexdb.marketplace")

DEFAULT_DB_PATH = os.path.join("data", "superadmin.db")


class CapabilityCategory(str, Enum):
    """Categories for marketplace capabilities."""
    core = "core"
    sdk = "sdk"
    integration = "integration"
    security = "security"
    analytics = "analytics"
    infrastructure = "infrastructure"


@dataclass
class Capability:
    """A toggleable feature/capability in the CortexDB marketplace."""
    id: str
    name: str
    description: str
    category: str
    icon: str
    version: str
    enabled: bool = False
    config: Dict[str, Any] = field(default_factory=dict)
    dependencies: List[str] = field(default_factory=list)
    tier: str = "free"  # free | pro | enterprise
    installed_at: Optional[str] = None
    updated_at: Optional[str] = None

    def to_dict(self) -> dict:
        """Serialize to a plain dict (JSON-safe)."""
        d = asdict(self)
        return d

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Capability":
        """Construct from a database row."""
        return cls(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            category=row["category"],
            icon=row["icon"],
            version=row["version"],
            enabled=bool(row["enabled"]),
            config=json.loads(row["config"]) if row["config"] else {},
            dependencies=json.loads(row["dependencies"]) if row["dependencies"] else [],
            tier=row["tier"],
            installed_at=row["installed_at"],
            updated_at=row["updated_at"],
        )


# ── Default capabilities seeded on first run ─────────────────────────

DEFAULT_CAPABILITIES: List[Capability] = [
    # Core
    Capability(
        id="agent-workforce",
        name="Agent Workforce Management",
        description="Manage agent teams, delegation, scheduling, and workforce orchestration.",
        category=CapabilityCategory.core.value,
        icon="users",
        version="1.0.0",
        enabled=True,
        tier="free",
    ),
    Capability(
        id="knowledge-graph",
        name="Knowledge Graph & Expert Discovery",
        description="Build and query a knowledge graph connecting agents, skills, topics, and expertise.",
        category=CapabilityCategory.core.value,
        icon="share-2",
        version="1.0.0",
        enabled=True,
        tier="free",
    ),
    Capability(
        id="autonomy-loop",
        name="Agent Autonomy & Self-Organization",
        description="Enable agents to self-organize, propose goals, and autonomously execute workflows.",
        category=CapabilityCategory.core.value,
        icon="refresh-cw",
        version="1.0.0",
        enabled=True,
        tier="free",
    ),

    # SDK
    Capability(
        id="sdk-python",
        name="Python SDK",
        description="Client library for Python apps. Install via pip install cortexdb-client.",
        category=CapabilityCategory.sdk.value,
        icon="code",
        version="0.9.0",
        tier="free",
    ),
    Capability(
        id="sdk-nodejs",
        name="Node.js SDK",
        description="Client library for Node.js apps. Install via npm install @cortexdb/client.",
        category=CapabilityCategory.sdk.value,
        icon="hexagon",
        version="0.9.0",
        tier="free",
    ),
    Capability(
        id="sdk-rest-api",
        name="REST API Templates",
        description="Ready-to-use API integration examples in 6 languages (Python, JS, Go, Rust, Java, C#).",
        category=CapabilityCategory.sdk.value,
        icon="file-code",
        version="1.0.0",
        tier="free",
    ),

    # Integration
    Capability(
        id="webhook-system",
        name="Webhook System",
        description="Outbound webhooks for agent events, task completions, and system alerts.",
        category=CapabilityCategory.integration.value,
        icon="link",
        version="1.0.0",
        tier="free",
    ),
    Capability(
        id="sso-saml",
        name="SSO/SAML Integration",
        description="Enterprise single sign-on via SAML 2.0 and OpenID Connect.",
        category=CapabilityCategory.integration.value,
        icon="shield",
        version="1.0.0",
        tier="enterprise",
    ),
    Capability(
        id="mobile-companion",
        name="Mobile Companion App",
        description="React Native admin app for monitoring agents and tasks on the go.",
        category=CapabilityCategory.integration.value,
        icon="smartphone",
        version="0.1.0",
        tier="pro",
    ),
    Capability(
        id="slack-integration",
        name="Slack Integration",
        description="Receive notifications and issue commands to agents via Slack.",
        category=CapabilityCategory.integration.value,
        icon="message-square",
        version="1.0.0",
        tier="free",
    ),

    # Security
    Capability(
        id="advanced-audit",
        name="Advanced Audit & Compliance Export",
        description="SOC2/HIPAA-ready audit log exports with tamper-proof checksums.",
        category=CapabilityCategory.security.value,
        icon="clipboard-check",
        version="1.0.0",
        tier="enterprise",
    ),
    Capability(
        id="field-encryption",
        name="Field-Level Encryption",
        description="Encrypt sensitive fields at rest using AES-256-GCM with per-field key management.",
        category=CapabilityCategory.security.value,
        icon="lock",
        version="1.0.0",
        tier="pro",
    ),

    # Analytics
    Capability(
        id="advanced-analytics",
        name="Advanced Analytics Dashboard",
        description="Custom metrics, trend analysis, forecasting, and drill-down reports.",
        category=CapabilityCategory.analytics.value,
        icon="bar-chart-2",
        version="1.0.0",
        tier="pro",
    ),
    Capability(
        id="cost-intelligence",
        name="Cost Intelligence",
        description="AI-powered cost optimization recommendations based on usage patterns.",
        category=CapabilityCategory.analytics.value,
        icon="dollar-sign",
        version="1.0.0",
        tier="pro",
    ),

    # Infrastructure
    Capability(
        id="multi-region",
        name="Multi-Region Replication",
        description="Cross-datacenter synchronization with conflict resolution and failover.",
        category=CapabilityCategory.infrastructure.value,
        icon="globe",
        version="0.1.0",
        config={},
        tier="enterprise",
    ),
    Capability(
        id="plugin-system",
        name="Custom Plugin System",
        description="Extend CortexDB with custom engines, hooks, and middleware plugins.",
        category=CapabilityCategory.infrastructure.value,
        icon="package",
        version="1.0.0",
        tier="pro",
    ),
    Capability(
        id="custom-engines",
        name="Custom Storage Engines",
        description="User-defined storage backends for specialized workloads.",
        category=CapabilityCategory.infrastructure.value,
        icon="database",
        version="1.0.0",
        dependencies=["plugin-system"],
        tier="enterprise",
    ),

    # ── Coming Soon ──────────────────────────────────────

    # Core
    Capability(
        id="ai-copilot",
        name="AI Copilot",
        description="In-dashboard conversational AI assistant that can answer questions about your data, generate queries, explain agent behavior, and suggest optimizations.",
        category=CapabilityCategory.core.value,
        icon="sparkles",
        version="0.1.0",
        config={},
        tier="pro",
    ),
    Capability(
        id="agent-marketplace",
        name="Agent Template Marketplace",
        description="Browse and install community-contributed agent templates, workflow blueprints, and pre-trained skill packs from a public marketplace.",
        category=CapabilityCategory.core.value,
        icon="shopping-bag",
        version="0.1.0",
        config={},
        tier="free",
    ),

    # SDK
    Capability(
        id="sdk-go",
        name="Go SDK",
        description="High-performance Go client library with connection pooling, retries, and streaming query support.",
        category=CapabilityCategory.sdk.value,
        icon="code",
        version="0.1.0",
        config={},
        tier="free",
    ),
    Capability(
        id="sdk-rust",
        name="Rust SDK",
        description="Zero-cost abstraction Rust client with async/await, compile-time query validation, and WASM support.",
        category=CapabilityCategory.sdk.value,
        icon="code",
        version="0.1.0",
        config={},
        tier="free",
    ),
    Capability(
        id="graphql-gateway",
        name="GraphQL API Gateway",
        description="Auto-generated GraphQL schema from your CortexDB data model with subscriptions, batching, and federation support.",
        category=CapabilityCategory.sdk.value,
        icon="git-branch",
        version="0.1.0",
        config={},
        tier="pro",
    ),

    # Integration
    Capability(
        id="teams-integration",
        name="Microsoft Teams Integration",
        description="Receive agent alerts, approve tasks, and chat with agents directly from Microsoft Teams channels.",
        category=CapabilityCategory.integration.value,
        icon="message-square",
        version="0.1.0",
        config={},
        tier="free",
    ),
    Capability(
        id="discord-integration",
        name="Discord Integration",
        description="Bot integration for Discord servers — real-time alerts, slash commands, and agent chat in channels.",
        category=CapabilityCategory.integration.value,
        icon="message-circle",
        version="0.1.0",
        config={},
        tier="free",
    ),
    Capability(
        id="zapier-connector",
        name="Zapier / n8n Connector",
        description="Connect CortexDB to 5,000+ apps via Zapier triggers and actions, or self-host with n8n workflows.",
        category=CapabilityCategory.integration.value,
        icon="zap",
        version="0.1.0",
        config={},
        tier="pro",
    ),
    Capability(
        id="voice-interface",
        name="Voice Interface",
        description="Control agents and query data using natural voice commands via browser, mobile, or smart speakers.",
        category=CapabilityCategory.integration.value,
        icon="mic",
        version="0.1.0",
        config={},
        tier="enterprise",
    ),

    # Security
    Capability(
        id="zero-trust",
        name="Zero-Trust Network Policies",
        description="Mutual TLS between all services, policy-based access control, and encrypted inter-agent communication by default.",
        category=CapabilityCategory.security.value,
        icon="shield-check",
        version="0.1.0",
        config={},
        tier="enterprise",
    ),
    Capability(
        id="secrets-vault",
        name="Integrated Secrets Vault",
        description="HashiCorp Vault-compatible secrets management with automatic rotation, lease tracking, and dynamic credentials.",
        category=CapabilityCategory.security.value,
        icon="key-round",
        version="0.1.0",
        config={},
        tier="enterprise",
    ),

    # Analytics
    Capability(
        id="data-pipeline-builder",
        name="Visual Data Pipeline Builder",
        description="Drag-and-drop ETL/ELT pipeline designer with scheduling, transformations, and cross-engine data flows.",
        category=CapabilityCategory.analytics.value,
        icon="workflow",
        version="0.1.0",
        config={},
        tier="pro",
    ),
    Capability(
        id="realtime-dashboards",
        name="Real-Time Custom Dashboards",
        description="Build personalized monitoring dashboards with live-updating charts, custom widgets, and shareable layouts.",
        category=CapabilityCategory.analytics.value,
        icon="layout-dashboard",
        version="0.1.0",
        config={},
        tier="pro",
    ),

    # Infrastructure
    Capability(
        id="edge-deployment",
        name="Edge Deployment",
        description="Deploy lightweight CortexDB nodes at the edge for low-latency reads, offline-capable sync, and IoT workloads.",
        category=CapabilityCategory.infrastructure.value,
        icon="radio-tower",
        version="0.1.0",
        config={},
        tier="enterprise",
    ),
    Capability(
        id="kubernetes-operator",
        name="Kubernetes Operator",
        description="Native K8s operator for automated scaling, rolling upgrades, backup CRDs, and self-healing CortexDB clusters.",
        category=CapabilityCategory.infrastructure.value,
        icon="container",
        version="0.1.0",
        config={},
        tier="enterprise",
    ),
    Capability(
        id="white-label",
        name="White-Label & Theming",
        description="Fully rebrandable dashboard with custom logos, colors, domains, and email templates for SaaS resellers.",
        category=CapabilityCategory.infrastructure.value,
        icon="palette",
        version="0.1.0",
        config={},
        tier="enterprise",
    ),
]


class MarketplaceManager:
    """Manages marketplace capabilities with SQLite persistence.

    Capabilities can be enabled/disabled, configured, and queried.
    Dependency resolution ensures capabilities are only enabled when
    their prerequisites are met, and disabled only when no dependents
    rely on them.
    """

    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        self.db: Optional[sqlite3.Connection] = None
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """Get or create a SQLite connection with row factory."""
        if self.db is None or not self._connection_alive():
            db_dir = os.path.dirname(self.db_path)
            if db_dir:
                os.makedirs(db_dir, exist_ok=True)
            self.db = sqlite3.connect(self.db_path, timeout=10.0)
            self.db.row_factory = sqlite3.Row
            self.db.execute("PRAGMA journal_mode=WAL")
            self.db.execute("PRAGMA foreign_keys=ON")
        return self.db

    def _connection_alive(self) -> bool:
        """Check if the current connection is still usable."""
        try:
            self.db.execute("SELECT 1")
            return True
        except Exception:
            return False

    def _init_db(self) -> None:
        """Seed defaults. Table 'marketplace_capabilities' is managed by the
        SQLite migration system (see migrations.py v5)."""
        conn = self._get_connection()

        # Seed defaults if table is empty, or add missing capabilities
        row = conn.execute(
            "SELECT COUNT(*) AS cnt FROM marketplace_capabilities"
        ).fetchone()
        if row["cnt"] == 0:
            self._seed_defaults(conn)
        else:
            self._seed_missing(conn)

    def _seed_defaults(self, conn: sqlite3.Connection) -> None:
        """Insert the default capability set."""
        now = datetime.now(timezone.utc).isoformat()
        for cap in DEFAULT_CAPABILITIES:
            conn.execute(
                """
                INSERT OR IGNORE INTO marketplace_capabilities
                    (id, name, description, category, icon, version,
                     enabled, config, dependencies, tier, installed_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    cap.id,
                    cap.name,
                    cap.description,
                    cap.category,
                    cap.icon,
                    cap.version,
                    1 if cap.enabled else 0,
                    json.dumps(cap.config),
                    json.dumps(cap.dependencies),
                    cap.tier,
                    now,
                    now,
                ),
            )
        conn.commit()
        logger.info("Seeded %d default marketplace capabilities", len(DEFAULT_CAPABILITIES))

    def _seed_missing(self, conn: sqlite3.Connection) -> None:
        """Insert any new capabilities that don't yet exist in the database."""
        now = datetime.now(timezone.utc).isoformat()
        added = 0
        for cap in DEFAULT_CAPABILITIES:
            existing = conn.execute(
                "SELECT 1 FROM marketplace_capabilities WHERE id = ?", (cap.id,)
            ).fetchone()
            if existing is None:
                conn.execute(
                    """
                    INSERT INTO marketplace_capabilities
                        (id, name, description, category, icon, version,
                         enabled, config, dependencies, tier, installed_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        cap.id, cap.name, cap.description, cap.category,
                        cap.icon, cap.version, 1 if cap.enabled else 0,
                        json.dumps(cap.config), json.dumps(cap.dependencies),
                        cap.tier, now, now,
                    ),
                )
                added += 1
        if added:
            conn.commit()
            logger.info("Added %d new marketplace capabilities", added)

    # ── Query methods ─────────────────────────────────────────────────

    def list_capabilities(
        self,
        category: Optional[str] = None,
        enabled_only: bool = False,
    ) -> List[Capability]:
        """List capabilities with optional filters.

        Args:
            category: Filter by CapabilityCategory value (e.g. 'core', 'sdk').
            enabled_only: If True, return only enabled capabilities.

        Returns:
            List of Capability objects sorted by category then name.
        """
        conn = self._get_connection()
        clauses: List[str] = []
        params: List[Any] = []

        if category is not None:
            clauses.append("category = ?")
            params.append(category)
        if enabled_only:
            clauses.append("enabled = 1")

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        query = f"SELECT * FROM marketplace_capabilities {where} ORDER BY category, name"

        rows = conn.execute(query, params).fetchall()
        return [Capability.from_row(r) for r in rows]

    def get_capability(self, capability_id: str) -> Optional[Capability]:
        """Get a single capability by ID.

        Args:
            capability_id: The unique capability identifier.

        Returns:
            Capability object or None if not found.
        """
        conn = self._get_connection()
        row = conn.execute(
            "SELECT * FROM marketplace_capabilities WHERE id = ?",
            (capability_id,),
        ).fetchone()
        if row is None:
            return None
        return Capability.from_row(row)

    def search_capabilities(self, query: str) -> List[Capability]:
        """Search capabilities by name or description (case-insensitive).

        Args:
            query: Search term to match against name and description.

        Returns:
            List of matching Capability objects.
        """
        conn = self._get_connection()
        pattern = f"%{query}%"
        rows = conn.execute(
            """
            SELECT * FROM marketplace_capabilities
            WHERE name LIKE ? OR description LIKE ?
            ORDER BY category, name
            """,
            (pattern, pattern),
        ).fetchall()
        return [Capability.from_row(r) for r in rows]

    # ── Dependency resolution ─────────────────────────────────────────

    def check_dependencies(self, capability_id: str) -> Dict[str, Any]:
        """Check whether all dependencies for a capability are enabled.

        Args:
            capability_id: The capability to check.

        Returns:
            Dict with 'satisfied' (bool), 'missing' (list of unmet dep IDs),
            and 'deps' (list of all dependency IDs).
        """
        cap = self.get_capability(capability_id)
        if cap is None:
            return {"satisfied": False, "missing": [], "deps": [], "error": "Capability not found"}

        if not cap.dependencies:
            return {"satisfied": True, "missing": [], "deps": []}

        missing = []
        for dep_id in cap.dependencies:
            dep = self.get_capability(dep_id)
            if dep is None or not dep.enabled:
                missing.append(dep_id)

        return {
            "satisfied": len(missing) == 0,
            "missing": missing,
            "deps": list(cap.dependencies),
        }

    def get_dependents(self, capability_id: str) -> List[Capability]:
        """Get capabilities that depend on the given capability.

        Args:
            capability_id: The capability to find dependents of.

        Returns:
            List of Capability objects that list this ID in their dependencies.
        """
        conn = self._get_connection()
        # SQLite JSON: check if dependencies array contains the id
        rows = conn.execute(
            """
            SELECT * FROM marketplace_capabilities
            WHERE dependencies LIKE ?
            ORDER BY category, name
            """,
            (f'%"{capability_id}"%',),
        ).fetchall()
        return [Capability.from_row(r) for r in rows]

    # ── Enable / Disable ──────────────────────────────────────────────

    def enable_capability(self, capability_id: str) -> Dict[str, Any]:
        """Enable a capability after verifying its dependencies are met.

        Args:
            capability_id: The capability to enable.

        Returns:
            Dict with 'success' (bool) and 'message' or 'error'.
        """
        cap = self.get_capability(capability_id)
        if cap is None:
            logger.warning("enable_capability: '%s' not found", capability_id)
            return {"success": False, "error": f"Capability '{capability_id}' not found"}

        if cap.enabled:
            return {"success": True, "message": f"'{capability_id}' is already enabled"}

        # Check for coming_soon status
        if cap.config.get("status") == "coming_soon":
            logger.info("enable_capability: '%s' is coming soon, cannot enable", capability_id)
            return {"success": False, "error": f"'{capability_id}' is not yet available (coming soon)"}

        # Verify dependencies
        dep_check = self.check_dependencies(capability_id)
        if not dep_check["satisfied"]:
            missing = ", ".join(dep_check["missing"])
            logger.warning(
                "enable_capability: '%s' has unmet dependencies: %s",
                capability_id, missing,
            )
            return {
                "success": False,
                "error": f"Unmet dependencies: {missing}",
                "missing_dependencies": dep_check["missing"],
            }

        now = datetime.now(timezone.utc).isoformat()
        conn = self._get_connection()
        conn.execute(
            "UPDATE marketplace_capabilities SET enabled = 1, updated_at = ? WHERE id = ?",
            (now, capability_id),
        )
        conn.commit()
        logger.info("Enabled capability '%s'", capability_id)
        return {"success": True, "message": f"'{capability_id}' enabled successfully"}

    def disable_capability(self, capability_id: str) -> Dict[str, Any]:
        """Disable a capability after verifying no enabled dependents exist.

        Args:
            capability_id: The capability to disable.

        Returns:
            Dict with 'success' (bool) and 'message' or 'error'.
        """
        cap = self.get_capability(capability_id)
        if cap is None:
            logger.warning("disable_capability: '%s' not found", capability_id)
            return {"success": False, "error": f"Capability '{capability_id}' not found"}

        if not cap.enabled:
            return {"success": True, "message": f"'{capability_id}' is already disabled"}

        # Check for enabled dependents
        dependents = self.get_dependents(capability_id)
        enabled_dependents = [d for d in dependents if d.enabled]
        if enabled_dependents:
            dep_ids = ", ".join(d.id for d in enabled_dependents)
            logger.warning(
                "disable_capability: '%s' has enabled dependents: %s",
                capability_id, dep_ids,
            )
            return {
                "success": False,
                "error": f"Cannot disable: the following enabled capabilities depend on it: {dep_ids}",
                "enabled_dependents": [d.id for d in enabled_dependents],
            }

        now = datetime.now(timezone.utc).isoformat()
        conn = self._get_connection()
        conn.execute(
            "UPDATE marketplace_capabilities SET enabled = 0, updated_at = ? WHERE id = ?",
            (now, capability_id),
        )
        conn.commit()
        logger.info("Disabled capability '%s'", capability_id)
        return {"success": True, "message": f"'{capability_id}' disabled successfully"}

    # ── Configuration ─────────────────────────────────────────────────

    def update_capability_config(
        self, capability_id: str, config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Update the configuration dict for a capability.

        Performs a shallow merge: new keys are added, existing keys are
        overwritten, keys not present in `config` are preserved.

        Args:
            capability_id: The capability to update.
            config: Dict of configuration values to merge.

        Returns:
            Dict with 'success' (bool) and the merged 'config' or 'error'.
        """
        cap = self.get_capability(capability_id)
        if cap is None:
            logger.warning("update_capability_config: '%s' not found", capability_id)
            return {"success": False, "error": f"Capability '{capability_id}' not found"}

        merged = {**cap.config, **config}
        now = datetime.now(timezone.utc).isoformat()
        conn = self._get_connection()
        conn.execute(
            "UPDATE marketplace_capabilities SET config = ?, updated_at = ? WHERE id = ?",
            (json.dumps(merged), now, capability_id),
        )
        conn.commit()
        logger.info("Updated config for capability '%s'", capability_id)
        return {"success": True, "config": merged}

    # ── Stats ─────────────────────────────────────────────────────────

    def get_marketplace_stats(self) -> Dict[str, Any]:
        """Get summary statistics for the marketplace.

        Returns:
            Dict with total, enabled, disabled counts, breakdown by category
            and tier, and lists of coming_soon capabilities.
        """
        conn = self._get_connection()

        total_row = conn.execute(
            "SELECT COUNT(*) AS cnt FROM marketplace_capabilities"
        ).fetchone()
        total = total_row["cnt"]

        enabled_row = conn.execute(
            "SELECT COUNT(*) AS cnt FROM marketplace_capabilities WHERE enabled = 1"
        ).fetchone()
        enabled = enabled_row["cnt"]

        # Breakdown by category
        cat_rows = conn.execute(
            """
            SELECT category,
                   COUNT(*) AS total,
                   SUM(enabled) AS enabled
            FROM marketplace_capabilities
            GROUP BY category
            ORDER BY category
            """
        ).fetchall()
        by_category = {
            r["category"]: {"total": r["total"], "enabled": r["enabled"]}
            for r in cat_rows
        }

        # Breakdown by tier
        tier_rows = conn.execute(
            """
            SELECT tier,
                   COUNT(*) AS total,
                   SUM(enabled) AS enabled
            FROM marketplace_capabilities
            GROUP BY tier
            ORDER BY tier
            """
        ).fetchall()
        by_tier = {
            r["tier"]: {"total": r["total"], "enabled": r["enabled"]}
            for r in tier_rows
        }

        # Coming soon
        coming_rows = conn.execute(
            "SELECT id, name FROM marketplace_capabilities WHERE config LIKE '%coming_soon%'"
        ).fetchall()
        coming_soon = [{"id": r["id"], "name": r["name"]} for r in coming_rows]

        return {
            "total": total,
            "enabled": enabled,
            "disabled": total - enabled,
            "by_category": by_category,
            "by_tier": by_tier,
            "coming_soon": coming_soon,
        }

    # ── Cleanup ───────────────────────────────────────────────────────

    def close(self) -> None:
        """Close the database connection."""
        if self.db is not None:
            try:
                self.db.close()
            except Exception:
                pass
            self.db = None
