"""
White-Label & Theming — Fully rebrandable dashboard with custom logos,
colors, domains, and email templates for SaaS resellers.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from cortexdb.superadmin.persistence import PersistenceStore

logger = logging.getLogger("cortexdb.white_label")

# ── Default Themes ──────────────────────────────────────────────────────

DEFAULT_THEMES = [
    {
        "name": "CortexDB Default",
        "description": "Dark glass-morphism theme with red and white accents",
        "colors": {
            "primary": "#DC2626",
            "secondary": "#1E1E2E",
            "accent": "#FFFFFF",
            "background": "#0A0A0F",
            "surface": "#1A1A2E",
            "text": "#FFFFFF",
            "textSecondary": "#A0A0B0",
            "border": "#2A2A3E",
            "success": "#22C55E",
            "warning": "#F59E0B",
            "error": "#EF4444",
            "info": "#3B82F6",
        },
        "typography": {
            "fontFamily": "'Inter', -apple-system, BlinkMacSystemFont, sans-serif",
            "headingFamily": "'Inter', sans-serif",
            "baseFontSize": "14px",
            "headingWeight": "600",
            "bodyWeight": "400",
            "lineHeight": "1.6",
        },
        "is_active": True,
    },
    {
        "name": "Light Mode",
        "description": "Clean white background with dark text and blue accents",
        "colors": {
            "primary": "#2563EB",
            "secondary": "#F1F5F9",
            "accent": "#1E40AF",
            "background": "#FFFFFF",
            "surface": "#F8FAFC",
            "text": "#0F172A",
            "textSecondary": "#64748B",
            "border": "#E2E8F0",
            "success": "#16A34A",
            "warning": "#D97706",
            "error": "#DC2626",
            "info": "#2563EB",
        },
        "typography": {
            "fontFamily": "'Inter', -apple-system, BlinkMacSystemFont, sans-serif",
            "headingFamily": "'Inter', sans-serif",
            "baseFontSize": "14px",
            "headingWeight": "700",
            "bodyWeight": "400",
            "lineHeight": "1.6",
        },
        "is_active": False,
    },
    {
        "name": "Midnight Blue",
        "description": "Deep navy theme with cyan and teal accents",
        "colors": {
            "primary": "#06B6D4",
            "secondary": "#0F172A",
            "accent": "#14B8A6",
            "background": "#020617",
            "surface": "#0F172A",
            "text": "#F0F9FF",
            "textSecondary": "#7DD3FC",
            "border": "#1E3A5F",
            "success": "#34D399",
            "warning": "#FBBF24",
            "error": "#F87171",
            "info": "#38BDF8",
        },
        "typography": {
            "fontFamily": "'JetBrains Mono', 'Fira Code', monospace",
            "headingFamily": "'Inter', sans-serif",
            "baseFontSize": "13px",
            "headingWeight": "600",
            "bodyWeight": "400",
            "lineHeight": "1.5",
        },
        "is_active": False,
    },
    {
        "name": "Forest",
        "description": "Dark green theme with emerald and lime accents",
        "colors": {
            "primary": "#10B981",
            "secondary": "#14332A",
            "accent": "#84CC16",
            "background": "#052E16",
            "surface": "#14332A",
            "text": "#ECFDF5",
            "textSecondary": "#6EE7B7",
            "border": "#1A4D3A",
            "success": "#22C55E",
            "warning": "#EAB308",
            "error": "#F43F5E",
            "info": "#06B6D4",
        },
        "typography": {
            "fontFamily": "'IBM Plex Sans', -apple-system, sans-serif",
            "headingFamily": "'IBM Plex Sans', sans-serif",
            "baseFontSize": "14px",
            "headingWeight": "600",
            "bodyWeight": "400",
            "lineHeight": "1.6",
        },
        "is_active": False,
    },
]

# Default email templates
DEFAULT_EMAIL_TEMPLATES = {
    "welcome": {
        "name": "welcome",
        "subject": "Welcome to {{company_name}}",
        "body_html": "<h1>Welcome to {{company_name}}</h1><p>Hi {{user_name}},</p><p>Your account is ready. Get started at <a href=\"{{dashboard_url}}\">your dashboard</a>.</p>",
    },
    "alert": {
        "name": "alert",
        "subject": "[{{company_name}}] Alert: {{alert_title}}",
        "body_html": "<h1>System Alert</h1><p><strong>{{alert_title}}</strong></p><p>{{alert_message}}</p><p>Severity: {{severity}}</p>",
    },
    "report": {
        "name": "report",
        "subject": "{{company_name}} — {{report_type}} Report",
        "body_html": "<h1>{{report_type}} Report</h1><p>Period: {{period}}</p><p>{{report_summary}}</p><p><a href=\"{{report_url}}\">View full report</a></p>",
    },
    "invite": {
        "name": "invite",
        "subject": "You've been invited to {{company_name}}",
        "body_html": "<h1>You're Invited</h1><p>{{inviter_name}} has invited you to join {{company_name}}.</p><p><a href=\"{{invite_url}}\">Accept Invitation</a></p>",
    },
}


class WhiteLabelManager:
    """Manages white-label theming, branding, and email templates for SaaS resellers."""

    def __init__(self, persistence_store: "PersistenceStore") -> None:
        self._store = persistence_store
        self._init_db()

    # ── Schema & Seeds ──────────────────────────────────────────────────

    def _init_db(self) -> None:
        """Seed defaults if empty. Tables 'wl_themes' and 'wl_branding' are managed
        by the SQLite migration system (see migrations.py v5)."""
        conn = self._store.conn

        # Seed default themes if none exist
        existing = conn.execute("SELECT COUNT(*) as cnt FROM wl_themes").fetchone()["cnt"]
        if existing == 0:
            self._seed_defaults()

        logger.info("White-label tables initialized")

    def _seed_defaults(self) -> None:
        """Seed the 4 default themes and initial branding config."""
        conn = self._store.conn
        now = time.time()

        for theme in DEFAULT_THEMES:
            theme_id = f"theme-{uuid.uuid4().hex[:12]}"
            conn.execute(
                """INSERT INTO wl_themes
                   (id, name, description, colors, typography, is_active, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    theme_id, theme["name"], theme["description"],
                    json.dumps(theme["colors"]),
                    json.dumps(theme.get("typography", {})),
                    1 if theme["is_active"] else 0,
                    now, now,
                ),
            )

        # Seed default branding
        branding_id = f"brand-{uuid.uuid4().hex[:12]}"
        conn.execute(
            """INSERT INTO wl_branding
               (id, company_name, tagline, support_email, email_templates, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                branding_id, "CortexDB",
                "The Intelligent Database Platform",
                "support@cortexdb.io",
                json.dumps(DEFAULT_EMAIL_TEMPLATES),
                now, now,
            ),
        )
        conn.commit()
        logger.info("Seeded %d default themes and initial branding", len(DEFAULT_THEMES))

    # ── Helpers ─────────────────────────────────────────────────────────

    def _row_to_dict(self, row) -> Optional[dict]:
        if row is None:
            return None
        d = dict(row)
        for key in ("colors", "typography", "email_templates"):
            if key in d and isinstance(d[key], str):
                try:
                    d[key] = json.loads(d[key])
                except (json.JSONDecodeError, TypeError):
                    pass
        # Convert is_active int to bool
        if "is_active" in d:
            d["is_active"] = bool(d["is_active"])
        return d

    # ── Theme CRUD ──────────────────────────────────────────────────────

    def list_themes(self) -> list:
        """List all available themes."""
        rows = self._store.conn.execute(
            "SELECT * FROM wl_themes ORDER BY is_active DESC, created_at ASC"
        ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def get_theme(self, theme_id: str) -> dict:
        """Get a single theme by ID."""
        row = self._store.conn.execute(
            "SELECT * FROM wl_themes WHERE id = ?", (theme_id,)
        ).fetchone()
        if not row:
            raise ValueError(f"Theme '{theme_id}' not found")
        return self._row_to_dict(row)

    def create_theme(
        self,
        name: str,
        colors: Dict[str, str],
        typography: Optional[Dict[str, str]] = None,
        logo_url: Optional[str] = None,
    ) -> dict:
        """Create a new custom theme."""
        theme_id = f"theme-{uuid.uuid4().hex[:12]}"
        now = time.time()

        self._store.conn.execute(
            """INSERT INTO wl_themes
               (id, name, colors, typography, logo_url, is_active, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, 0, ?, ?)""",
            (
                theme_id, name, json.dumps(colors),
                json.dumps(typography or {}), logo_url,
                now, now,
            ),
        )
        self._store.conn.commit()
        logger.info("Created theme %s: %s", theme_id, name)
        self._store.audit("create_theme", "wl_theme", theme_id, {"name": name})
        return self.get_theme(theme_id)

    def update_theme(self, theme_id: str, updates: Dict[str, Any]) -> dict:
        """Update a theme's properties."""
        self.get_theme(theme_id)  # Ensure exists
        now = time.time()

        allowed = {"name", "description", "colors", "typography", "logo_url", "favicon_url"}
        set_clauses = []
        params = []
        for key, value in updates.items():
            if key not in allowed:
                continue
            if key in ("colors", "typography"):
                value = json.dumps(value)
            set_clauses.append(f"{key} = ?")
            params.append(value)

        if not set_clauses:
            return self.get_theme(theme_id)

        set_clauses.append("updated_at = ?")
        params.append(now)
        params.append(theme_id)

        self._store.conn.execute(
            f"UPDATE wl_themes SET {', '.join(set_clauses)} WHERE id = ?", params
        )
        self._store.conn.commit()
        logger.info("Updated theme %s: %s", theme_id, list(updates.keys()))
        return self.get_theme(theme_id)

    def delete_theme(self, theme_id: str) -> dict:
        """Delete a theme. Cannot delete the active theme."""
        theme = self.get_theme(theme_id)
        if theme["is_active"]:
            raise ValueError("Cannot delete the active theme. Activate another theme first.")

        self._store.conn.execute("DELETE FROM wl_themes WHERE id = ?", (theme_id,))
        self._store.conn.commit()
        logger.info("Deleted theme %s (%s)", theme_id, theme["name"])
        self._store.audit("delete_theme", "wl_theme", theme_id, {"name": theme["name"]})
        return {"deleted": True, "theme_id": theme_id, "name": theme["name"]}

    def activate_theme(self, theme_id: str) -> dict:
        """Set a theme as active, deactivating all others."""
        theme = self.get_theme(theme_id)
        now = time.time()

        self._store.conn.execute(
            "UPDATE wl_themes SET is_active = 0, updated_at = ? WHERE is_active = 1",
            (now,),
        )
        self._store.conn.execute(
            "UPDATE wl_themes SET is_active = 1, updated_at = ? WHERE id = ?",
            (now, theme_id),
        )
        self._store.conn.commit()
        logger.info("Activated theme %s (%s)", theme_id, theme["name"])
        self._store.audit("activate_theme", "wl_theme", theme_id, {"name": theme["name"]})
        return self.get_theme(theme_id)

    def get_active_theme(self) -> dict:
        """Return the currently active theme."""
        row = self._store.conn.execute(
            "SELECT * FROM wl_themes WHERE is_active = 1 LIMIT 1"
        ).fetchone()
        if not row:
            # Fallback: return first theme
            row = self._store.conn.execute(
                "SELECT * FROM wl_themes ORDER BY created_at ASC LIMIT 1"
            ).fetchone()
        if not row:
            raise ValueError("No themes configured")
        return self._row_to_dict(row)

    # ── Theme Preview & Import/Export ───────────────────────────────────

    def preview_theme(self, theme_id: str) -> dict:
        """Generate CSS custom properties for theme preview."""
        theme = self.get_theme(theme_id)
        colors = theme.get("colors", {})
        typography = theme.get("typography", {})

        css_vars = []
        for key, value in colors.items():
            css_name = key.replace("_", "-")
            # Convert camelCase to kebab-case
            kebab = ""
            for ch in css_name:
                if ch.isupper():
                    kebab += f"-{ch.lower()}"
                else:
                    kebab += ch
            css_vars.append(f"  --color{kebab}: {value};")

        for key, value in typography.items():
            kebab = ""
            for ch in key:
                if ch.isupper():
                    kebab += f"-{ch.lower()}"
                else:
                    kebab += ch
            css_vars.append(f"  --typo-{kebab}: {value};")

        css_text = ":root {\n" + "\n".join(css_vars) + "\n}"

        return {
            "theme_id": theme_id,
            "theme_name": theme["name"],
            "css_variables": css_text,
            "colors": colors,
            "typography": typography,
        }

    def export_theme(self, theme_id: str) -> dict:
        """Export a theme as a portable JSON object."""
        theme = self.get_theme(theme_id)
        return {
            "format": "cortexdb-theme-v1",
            "exported_at": time.time(),
            "theme": {
                "name": theme["name"],
                "description": theme.get("description"),
                "colors": theme["colors"],
                "typography": theme.get("typography", {}),
                "logo_url": theme.get("logo_url"),
                "favicon_url": theme.get("favicon_url"),
            },
        }

    def import_theme(self, theme_data: Dict[str, Any]) -> dict:
        """Import a theme from a JSON export."""
        if "theme" not in theme_data:
            raise ValueError("Invalid theme data: missing 'theme' key")

        t = theme_data["theme"]
        name = t.get("name", "Imported Theme")
        colors = t.get("colors")
        if not colors:
            raise ValueError("Invalid theme data: missing 'colors'")

        return self.create_theme(
            name=name,
            colors=colors,
            typography=t.get("typography"),
            logo_url=t.get("logo_url"),
        )

    # ── Branding ────────────────────────────────────────────────────────

    def get_branding(self) -> dict:
        """Get the current branding configuration."""
        row = self._store.conn.execute(
            "SELECT * FROM wl_branding ORDER BY created_at LIMIT 1"
        ).fetchone()
        if not row:
            return {
                "company_name": "CortexDB",
                "tagline": None,
                "support_email": None,
                "support_url": None,
                "terms_url": None,
                "privacy_url": None,
                "custom_domain": None,
                "custom_css": None,
                "email_templates": DEFAULT_EMAIL_TEMPLATES,
            }
        return self._row_to_dict(row)

    def update_branding(self, updates: Dict[str, Any]) -> dict:
        """Update branding configuration (company name, logo, support info, etc.)."""
        branding = self.get_branding()
        now = time.time()

        allowed = {"company_name", "tagline", "support_email", "support_url",
                   "terms_url", "privacy_url", "custom_domain", "custom_css"}
        set_clauses = []
        params = []
        for key, value in updates.items():
            if key not in allowed:
                continue
            set_clauses.append(f"{key} = ?")
            params.append(value)

        if not set_clauses:
            return branding

        set_clauses.append("updated_at = ?")
        params.append(now)

        # Update the first (and only) branding row
        branding_id = branding.get("id")
        if branding_id:
            params.append(branding_id)
            self._store.conn.execute(
                f"UPDATE wl_branding SET {', '.join(set_clauses)} WHERE id = ?", params
            )
        else:
            # Create if somehow missing
            new_id = f"brand-{uuid.uuid4().hex[:12]}"
            self._store.conn.execute(
                """INSERT INTO wl_branding (id, company_name, created_at, updated_at)
                   VALUES (?, ?, ?, ?)""",
                (new_id, updates.get("company_name", "CortexDB"), now, now),
            )

        self._store.conn.commit()
        logger.info("Updated branding: %s", list(updates.keys()))
        self._store.audit("update_branding", "wl_branding", "global",
                          {"updated_fields": list(updates.keys())})
        return self.get_branding()

    # ── Email Templates ─────────────────────────────────────────────────

    def get_email_templates(self) -> list:
        """List all email templates."""
        branding = self.get_branding()
        templates = branding.get("email_templates", DEFAULT_EMAIL_TEMPLATES)
        return [
            {"name": name, "subject": tpl.get("subject", ""), "body_html": tpl.get("body_html", "")}
            for name, tpl in templates.items()
        ]

    def update_email_template(self, template_name: str, subject: str, body_html: str) -> dict:
        """Update a specific email template."""
        branding = self.get_branding()
        templates = branding.get("email_templates", {})

        templates[template_name] = {
            "name": template_name,
            "subject": subject,
            "body_html": body_html,
        }

        now = time.time()
        branding_id = branding.get("id")
        if branding_id:
            self._store.conn.execute(
                "UPDATE wl_branding SET email_templates = ?, updated_at = ? WHERE id = ?",
                (json.dumps(templates), now, branding_id),
            )
            self._store.conn.commit()

        logger.info("Updated email template: %s", template_name)
        return {"name": template_name, "subject": subject, "body_html": body_html}

    # ── Statistics ──────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        """Get white-label statistics."""
        conn = self._store.conn

        total_themes = conn.execute(
            "SELECT COUNT(*) as cnt FROM wl_themes"
        ).fetchone()["cnt"]

        custom_themes = conn.execute(
            "SELECT COUNT(*) as cnt FROM wl_themes WHERE name NOT IN (?, ?, ?, ?)",
            (DEFAULT_THEMES[0]["name"], DEFAULT_THEMES[1]["name"],
             DEFAULT_THEMES[2]["name"], DEFAULT_THEMES[3]["name"]),
        ).fetchone()["cnt"]

        active = self.get_active_theme()
        branding = self.get_branding()
        templates = branding.get("email_templates", {})

        return {
            "total_themes": total_themes,
            "custom_themes": custom_themes,
            "built_in_themes": total_themes - custom_themes,
            "active_theme": active["name"],
            "company_name": branding.get("company_name", "CortexDB"),
            "custom_domain_set": bool(branding.get("custom_domain")),
            "custom_css_set": bool(branding.get("custom_css")),
            "email_templates_count": len(templates),
        }
