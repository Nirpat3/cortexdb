"""
Real-Time Custom Dashboards — Build personalized monitoring dashboards
with live-updating charts, custom widgets, and shareable layouts.

Supports grid-based layouts with draggable/resizable widgets. Each widget
has a type, data source, query, and position {x, y, w, h}. Dashboards
can be shared with specific users or made public.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from cortexdb.superadmin.persistence import PersistenceStore

logger = logging.getLogger("cortexdb.custom_dashboards")

# ── Widget type definitions ────────────────────────────────────────────────────

_WIDGET_TYPES = [
    {
        "type": "counter",
        "name": "Counter",
        "description": "Single numeric value with optional trend indicator",
        "config_schema": {
            "label": {"type": "string", "required": True},
            "unit": {"type": "string"},
            "trend_period": {"type": "string", "enum": ["1h", "24h", "7d"]},
            "thresholds": {"type": "object", "properties": {"warning": {"type": "number"}, "critical": {"type": "number"}}},
        },
        "default_size": {"w": 3, "h": 2},
    },
    {
        "type": "line_chart",
        "name": "Line Chart",
        "description": "Time-series line chart with multiple series support",
        "config_schema": {
            "series": {"type": "array", "items": {"type": "object", "properties": {"field": {"type": "string"}, "label": {"type": "string"}, "color": {"type": "string"}}}},
            "time_range": {"type": "string", "enum": ["1h", "6h", "24h", "7d", "30d"]},
            "y_axis_label": {"type": "string"},
        },
        "default_size": {"w": 6, "h": 4},
    },
    {
        "type": "bar_chart",
        "name": "Bar Chart",
        "description": "Vertical or horizontal bar chart for categorical data",
        "config_schema": {
            "orientation": {"type": "string", "enum": ["vertical", "horizontal"], "default": "vertical"},
            "category_field": {"type": "string", "required": True},
            "value_field": {"type": "string", "required": True},
            "color_field": {"type": "string"},
        },
        "default_size": {"w": 6, "h": 4},
    },
    {
        "type": "pie_chart",
        "name": "Pie Chart",
        "description": "Pie or donut chart for proportional data",
        "config_schema": {
            "label_field": {"type": "string", "required": True},
            "value_field": {"type": "string", "required": True},
            "donut": {"type": "boolean", "default": False},
        },
        "default_size": {"w": 4, "h": 4},
    },
    {
        "type": "gauge",
        "name": "Gauge",
        "description": "Circular gauge showing progress toward a target",
        "config_schema": {
            "min": {"type": "number", "default": 0},
            "max": {"type": "number", "default": 100},
            "thresholds": {"type": "array", "items": {"type": "object", "properties": {"value": {"type": "number"}, "color": {"type": "string"}}}},
            "unit": {"type": "string"},
        },
        "default_size": {"w": 3, "h": 3},
    },
    {
        "type": "table",
        "name": "Data Table",
        "description": "Tabular data with sorting, pagination, and row actions",
        "config_schema": {
            "columns": {"type": "array", "items": {"type": "object", "properties": {"field": {"type": "string"}, "label": {"type": "string"}, "sortable": {"type": "boolean"}}}},
            "page_size": {"type": "integer", "default": 10},
            "row_click_action": {"type": "string"},
        },
        "default_size": {"w": 12, "h": 6},
    },
    {
        "type": "list",
        "name": "List",
        "description": "Scrollable list of items with icons and status badges",
        "config_schema": {
            "title_field": {"type": "string", "required": True},
            "subtitle_field": {"type": "string"},
            "status_field": {"type": "string"},
            "max_items": {"type": "integer", "default": 10},
        },
        "default_size": {"w": 4, "h": 5},
    },
    {
        "type": "heatmap",
        "name": "Heatmap",
        "description": "2D heatmap grid for density or activity visualization",
        "config_schema": {
            "x_field": {"type": "string", "required": True},
            "y_field": {"type": "string", "required": True},
            "value_field": {"type": "string", "required": True},
            "color_scale": {"type": "string", "enum": ["viridis", "plasma", "inferno", "cool", "warm"]},
        },
        "default_size": {"w": 6, "h": 5},
    },
    {
        "type": "text",
        "name": "Text / Markdown",
        "description": "Static text or markdown content block",
        "config_schema": {
            "content": {"type": "string", "required": True},
            "format": {"type": "string", "enum": ["plain", "markdown"], "default": "markdown"},
        },
        "default_size": {"w": 4, "h": 2},
    },
    {
        "type": "status_grid",
        "name": "Status Grid",
        "description": "Grid of status indicators for service or agent health",
        "config_schema": {
            "id_field": {"type": "string", "required": True},
            "name_field": {"type": "string", "required": True},
            "status_field": {"type": "string", "required": True},
            "columns": {"type": "integer", "default": 4},
        },
        "default_size": {"w": 6, "h": 4},
    },
]

# ── Seed dashboards ────────────────────────────────────────────────────────────

_SEED_DASHBOARDS = [
    {
        "name": "Operations Overview",
        "description": "Real-time operational metrics for the agent workforce",
        "layout": {"columns": 12, "row_height": 60, "gap": 8},
        "theme": {"background": "#0f172a", "card_bg": "#1e293b", "accent": "#3b82f6"},
        "widgets": [
            {"widget_type": "pie_chart", "title": "Agent Status Distribution", "data_source": "agents", "query": "SELECT status, COUNT(*) FROM agents GROUP BY status", "config": {"label_field": "status", "value_field": "count", "donut": True}, "position": {"x": 0, "y": 0, "w": 4, "h": 4}},
            {"widget_type": "line_chart", "title": "Task Throughput", "data_source": "tasks", "query": "SELECT DATE(created_at) as date, COUNT(*) as tasks FROM tasks GROUP BY date", "config": {"series": [{"field": "tasks", "label": "Tasks/day", "color": "#3b82f6"}], "time_range": "7d"}, "position": {"x": 4, "y": 0, "w": 4, "h": 4}},
            {"widget_type": "gauge", "title": "Error Rate", "data_source": "tasks", "query": "SELECT ROUND(SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END)*100.0/COUNT(*),1) as rate FROM tasks", "config": {"min": 0, "max": 100, "unit": "%", "thresholds": [{"value": 5, "color": "#22c55e"}, {"value": 15, "color": "#eab308"}, {"value": 30, "color": "#ef4444"}]}, "position": {"x": 8, "y": 0, "w": 4, "h": 4}},
            {"widget_type": "counter", "title": "Active Agents", "data_source": "agents", "query": "SELECT COUNT(*) FROM agents WHERE status='active'", "config": {"label": "Active", "trend_period": "24h"}, "position": {"x": 0, "y": 4, "w": 3, "h": 2}},
            {"widget_type": "list", "title": "Recent Alerts", "data_source": "alerts", "query": "SELECT * FROM alerts ORDER BY created_at DESC LIMIT 10", "config": {"title_field": "title", "subtitle_field": "message", "status_field": "severity", "max_items": 10}, "position": {"x": 3, "y": 4, "w": 5, "h": 5}},
            {"widget_type": "gauge", "title": "System Health", "data_source": "health", "query": "SELECT overall_score FROM health_summary", "config": {"min": 0, "max": 100, "unit": "%", "thresholds": [{"value": 90, "color": "#22c55e"}, {"value": 70, "color": "#eab308"}, {"value": 50, "color": "#ef4444"}]}, "position": {"x": 8, "y": 4, "w": 4, "h": 3}},
        ],
    },
    {
        "name": "Cost Analytics",
        "description": "LLM spending, budget utilization, and cost optimization insights",
        "layout": {"columns": 12, "row_height": 60, "gap": 8},
        "theme": {"background": "#0f172a", "card_bg": "#1e293b", "accent": "#10b981"},
        "widgets": [
            {"widget_type": "bar_chart", "title": "Cost by Provider", "data_source": "cost_tracker", "query": "SELECT provider, SUM(cost) as total FROM llm_usage GROUP BY provider", "config": {"orientation": "horizontal", "category_field": "provider", "value_field": "total"}, "position": {"x": 0, "y": 0, "w": 6, "h": 4}},
            {"widget_type": "line_chart", "title": "Daily Spend", "data_source": "cost_tracker", "query": "SELECT DATE(timestamp) as date, SUM(cost) as spend FROM llm_usage GROUP BY date", "config": {"series": [{"field": "spend", "label": "Spend ($)", "color": "#10b981"}], "time_range": "30d"}, "position": {"x": 6, "y": 0, "w": 6, "h": 4}},
            {"widget_type": "gauge", "title": "Budget Utilization", "data_source": "budgets", "query": "SELECT ROUND(SUM(spent)/SUM(budget)*100, 1) as utilization FROM department_budgets", "config": {"min": 0, "max": 100, "unit": "%", "thresholds": [{"value": 60, "color": "#22c55e"}, {"value": 80, "color": "#eab308"}, {"value": 95, "color": "#ef4444"}]}, "position": {"x": 0, "y": 4, "w": 4, "h": 3}},
            {"widget_type": "table", "title": "Top Agents by Cost", "data_source": "cost_tracker", "query": "SELECT agent_id, SUM(cost) as total, COUNT(*) as calls FROM llm_usage GROUP BY agent_id ORDER BY total DESC LIMIT 10", "config": {"columns": [{"field": "agent_id", "label": "Agent", "sortable": True}, {"field": "total", "label": "Total Cost ($)", "sortable": True}, {"field": "calls", "label": "API Calls", "sortable": True}], "page_size": 10}, "position": {"x": 4, "y": 4, "w": 8, "h": 5}},
        ],
    },
    {
        "name": "Agent Performance",
        "description": "Individual and aggregate agent performance metrics",
        "layout": {"columns": 12, "row_height": 60, "gap": 8},
        "theme": {"background": "#0f172a", "card_bg": "#1e293b", "accent": "#8b5cf6"},
        "widgets": [
            {"widget_type": "gauge", "title": "Task Completion Rate", "data_source": "tasks", "query": "SELECT ROUND(SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END)*100.0/COUNT(*),1) as rate FROM tasks", "config": {"min": 0, "max": 100, "unit": "%", "thresholds": [{"value": 90, "color": "#22c55e"}, {"value": 70, "color": "#eab308"}, {"value": 50, "color": "#ef4444"}]}, "position": {"x": 0, "y": 0, "w": 3, "h": 3}},
            {"widget_type": "line_chart", "title": "Avg Response Time", "data_source": "agent_metrics", "query": "SELECT DATE(timestamp) as date, AVG(response_time_ms) as avg_ms FROM agent_metrics GROUP BY date", "config": {"series": [{"field": "avg_ms", "label": "Response Time (ms)", "color": "#8b5cf6"}], "time_range": "7d", "y_axis_label": "ms"}, "position": {"x": 3, "y": 0, "w": 5, "h": 4}},
            {"widget_type": "pie_chart", "title": "Skill Distribution", "data_source": "agent_skills", "query": "SELECT skill_category, COUNT(*) as count FROM agent_skills GROUP BY skill_category", "config": {"label_field": "skill_category", "value_field": "count", "donut": True}, "position": {"x": 8, "y": 0, "w": 4, "h": 4}},
            {"widget_type": "bar_chart", "title": "Reputation Scores", "data_source": "agent_reputation", "query": "SELECT agent_id, reputation_score FROM agents ORDER BY reputation_score DESC LIMIT 15", "config": {"orientation": "horizontal", "category_field": "agent_id", "value_field": "reputation_score"}, "position": {"x": 0, "y": 4, "w": 6, "h": 4}},
            {"widget_type": "gauge", "title": "Delegation Success Rate", "data_source": "delegations", "query": "SELECT ROUND(SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END)*100.0/COUNT(*),1) as rate FROM delegations", "config": {"min": 0, "max": 100, "unit": "%", "thresholds": [{"value": 85, "color": "#22c55e"}, {"value": 65, "color": "#eab308"}, {"value": 40, "color": "#ef4444"}]}, "position": {"x": 6, "y": 4, "w": 3, "h": 3}},
        ],
    },
]


class CustomDashboardManager:
    """Manages custom dashboards with grid-based widget layouts."""

    def __init__(self, persistence_store: "PersistenceStore"):
        self._persistence = persistence_store
        self._init_db()

    # ── Schema ──────────────────────────────────────────────────────────────

    def _init_db(self) -> None:
        conn = self._persistence.conn
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS custom_dashboards (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                layout TEXT NOT NULL DEFAULT '{}',
                widgets TEXT NOT NULL DEFAULT '[]',
                theme TEXT NOT NULL DEFAULT '{}',
                owner TEXT NOT NULL DEFAULT 'system',
                shared_with TEXT NOT NULL DEFAULT '[]',
                is_public INTEGER NOT NULL DEFAULT 0,
                refresh_interval INTEGER NOT NULL DEFAULT 30,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS dashboard_widgets (
                id TEXT PRIMARY KEY,
                dashboard_id TEXT NOT NULL,
                widget_type TEXT NOT NULL,
                title TEXT NOT NULL,
                data_source TEXT NOT NULL DEFAULT '',
                query TEXT NOT NULL DEFAULT '',
                config TEXT NOT NULL DEFAULT '{}',
                position TEXT NOT NULL DEFAULT '{}',
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                FOREIGN KEY (dashboard_id) REFERENCES custom_dashboards(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_dashboard_widgets_did ON dashboard_widgets(dashboard_id);
            CREATE INDEX IF NOT EXISTS idx_custom_dashboards_owner ON custom_dashboards(owner);
            CREATE INDEX IF NOT EXISTS idx_custom_dashboards_public ON custom_dashboards(is_public);
        """)
        conn.commit()
        self._seed_defaults()

    def _seed_defaults(self) -> None:
        existing = self._persistence.conn.execute(
            "SELECT COUNT(*) FROM custom_dashboards"
        ).fetchone()[0]
        if existing > 0:
            return

        now = time.time()
        for dash_def in _SEED_DASHBOARDS:
            did = f"DASH-{uuid.uuid4().hex[:8]}"
            self._persistence.conn.execute(
                "INSERT INTO custom_dashboards "
                "(id, name, description, layout, widgets, theme, owner, shared_with, "
                "is_public, refresh_interval, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,1,30,?,?)",
                (
                    did, dash_def["name"], dash_def["description"],
                    json.dumps(dash_def["layout"]), "[]",
                    json.dumps(dash_def["theme"]), "system", "[]", now, now,
                ),
            )
            # Insert widgets
            for widget_def in dash_def["widgets"]:
                wid = f"WGT-{uuid.uuid4().hex[:8]}"
                self._persistence.conn.execute(
                    "INSERT INTO dashboard_widgets "
                    "(id, dashboard_id, widget_type, title, data_source, query, config, position, "
                    "created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (
                        wid, did, widget_def["widget_type"], widget_def["title"],
                        widget_def.get("data_source", ""), widget_def.get("query", ""),
                        json.dumps(widget_def.get("config", {})),
                        json.dumps(widget_def.get("position", {})),
                        now, now,
                    ),
                )

        self._persistence.conn.commit()
        logger.info("Seeded %d default dashboards", len(_SEED_DASHBOARDS))

    # ── Helpers ─────────────────────────────────────────────────────────────

    def _row_to_dashboard(self, row, include_widgets: bool = False) -> dict:
        did = row[0]
        result = {
            "id": did,
            "name": row[1],
            "description": row[2],
            "layout": json.loads(row[3]) if row[3] else {},
            "theme": json.loads(row[5]) if row[5] else {},
            "owner": row[6],
            "shared_with": json.loads(row[7]) if row[7] else [],
            "is_public": bool(row[8]),
            "refresh_interval": row[9],
            "created_at": row[10],
            "updated_at": row[11],
        }
        if include_widgets:
            result["widgets"] = self._get_widgets(did)
        else:
            result["widget_count"] = self._persistence.conn.execute(
                "SELECT COUNT(*) FROM dashboard_widgets WHERE dashboard_id = ?", (did,)
            ).fetchone()[0]
        return result

    _DASHBOARD_COLS = (
        "id, name, description, layout, widgets, theme, owner, shared_with, "
        "is_public, refresh_interval, created_at, updated_at"
    )

    def _get_widgets(self, dashboard_id: str) -> list:
        rows = self._persistence.conn.execute(
            "SELECT id, dashboard_id, widget_type, title, data_source, query, "
            "config, position, created_at, updated_at "
            "FROM dashboard_widgets WHERE dashboard_id = ? ORDER BY created_at",
            (dashboard_id,),
        ).fetchall()
        return [self._row_to_widget(r) for r in rows]

    def _row_to_widget(self, row) -> dict:
        return {
            "id": row[0],
            "dashboard_id": row[1],
            "widget_type": row[2],
            "title": row[3],
            "data_source": row[4],
            "query": row[5],
            "config": json.loads(row[6]) if row[6] else {},
            "position": json.loads(row[7]) if row[7] else {},
            "created_at": row[8],
            "updated_at": row[9],
        }

    # ── Dashboard CRUD ──────────────────────────────────────────────────────

    def create_dashboard(
        self,
        name: str,
        description: Optional[str] = None,
        layout: Optional[Dict] = None,
    ) -> dict:
        did = f"DASH-{uuid.uuid4().hex[:8]}"
        now = time.time()
        default_layout = layout or {"columns": 12, "row_height": 60, "gap": 8}
        self._persistence.conn.execute(
            f"INSERT INTO custom_dashboards ({self._DASHBOARD_COLS}) "
            "VALUES (?,?,?,?,?,?,?,?,0,30,?,?)",
            (
                did, name, description or "", json.dumps(default_layout),
                "[]", "{}", "system", "[]", now, now,
            ),
        )
        self._persistence.conn.commit()
        logger.info("Created dashboard %s: %s", did, name)
        return self.get_dashboard(did)

    def list_dashboards(self, owner: Optional[str] = None, include_public: bool = True) -> list:
        conditions = []
        params: list = []
        if owner:
            conditions.append("owner = ?")
            params.append(owner)
        if include_public and owner:
            # Include public dashboards OR owned by the user
            sql = (
                f"SELECT {self._DASHBOARD_COLS} FROM custom_dashboards "
                "WHERE owner = ? OR is_public = 1 ORDER BY created_at DESC"
            )
            params = [owner]
        elif owner:
            sql = (
                f"SELECT {self._DASHBOARD_COLS} FROM custom_dashboards "
                "WHERE owner = ? ORDER BY created_at DESC"
            )
            params = [owner]
        else:
            sql = f"SELECT {self._DASHBOARD_COLS} FROM custom_dashboards ORDER BY created_at DESC"
            params = []

        rows = self._persistence.conn.execute(sql, params).fetchall()
        return [self._row_to_dashboard(r) for r in rows]

    def get_dashboard(self, dashboard_id: str) -> dict:
        row = self._persistence.conn.execute(
            f"SELECT {self._DASHBOARD_COLS} FROM custom_dashboards WHERE id = ?",
            (dashboard_id,),
        ).fetchone()
        if not row:
            return {"error": "Dashboard not found", "dashboard_id": dashboard_id}
        return self._row_to_dashboard(row, include_widgets=True)

    def update_dashboard(self, dashboard_id: str, updates: Dict[str, Any]) -> dict:
        existing = self.get_dashboard(dashboard_id)
        if "error" in existing:
            return existing
        allowed = {"name", "description", "layout", "theme", "refresh_interval"}
        sets, params = [], []
        for key, val in updates.items():
            if key not in allowed:
                continue
            if key in ("layout", "theme"):
                val = json.dumps(val)
            sets.append(f"{key} = ?")
            params.append(val)
        if not sets:
            return {"error": "No valid fields to update"}
        sets.append("updated_at = ?")
        params.append(time.time())
        params.append(dashboard_id)
        self._persistence.conn.execute(
            f"UPDATE custom_dashboards SET {', '.join(sets)} WHERE id = ?", params
        )
        self._persistence.conn.commit()
        logger.info("Updated dashboard %s", dashboard_id)
        return self.get_dashboard(dashboard_id)

    def delete_dashboard(self, dashboard_id: str) -> dict:
        existing = self.get_dashboard(dashboard_id)
        if "error" in existing:
            return existing
        self._persistence.conn.execute(
            "DELETE FROM dashboard_widgets WHERE dashboard_id = ?", (dashboard_id,)
        )
        self._persistence.conn.execute(
            "DELETE FROM custom_dashboards WHERE id = ?", (dashboard_id,)
        )
        self._persistence.conn.commit()
        logger.info("Deleted dashboard %s", dashboard_id)
        return {"deleted": True, "dashboard_id": dashboard_id}

    def duplicate_dashboard(self, dashboard_id: str, new_name: str) -> dict:
        """Clone a dashboard with all its widgets under a new name."""
        source = self.get_dashboard(dashboard_id)
        if "error" in source:
            return source

        new_id = f"DASH-{uuid.uuid4().hex[:8]}"
        now = time.time()
        self._persistence.conn.execute(
            f"INSERT INTO custom_dashboards ({self._DASHBOARD_COLS}) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                new_id, new_name, source["description"],
                json.dumps(source["layout"]), "[]",
                json.dumps(source["theme"]), source["owner"],
                json.dumps(source["shared_with"]),
                1 if source["is_public"] else 0,
                source["refresh_interval"], now, now,
            ),
        )

        # Duplicate widgets
        for widget in source.get("widgets", []):
            wid = f"WGT-{uuid.uuid4().hex[:8]}"
            self._persistence.conn.execute(
                "INSERT INTO dashboard_widgets "
                "(id, dashboard_id, widget_type, title, data_source, query, config, position, "
                "created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    wid, new_id, widget["widget_type"], widget["title"],
                    widget.get("data_source", ""), widget.get("query", ""),
                    json.dumps(widget.get("config", {})),
                    json.dumps(widget.get("position", {})),
                    now, now,
                ),
            )

        self._persistence.conn.commit()
        logger.info("Duplicated dashboard %s -> %s as '%s'", dashboard_id, new_id, new_name)
        return self.get_dashboard(new_id)

    # ── Widget CRUD ─────────────────────────────────────────────────────────

    def add_widget(
        self,
        dashboard_id: str,
        widget_type: str,
        title: str,
        data_source: str,
        config: Optional[Dict] = None,
        position: Optional[Dict] = None,
    ) -> dict:
        """Add a widget to a dashboard."""
        # Verify dashboard exists
        dash = self.get_dashboard(dashboard_id)
        if "error" in dash:
            return dash

        # Validate widget type
        valid_types = {wt["type"] for wt in _WIDGET_TYPES}
        if widget_type not in valid_types:
            return {"error": f"Unknown widget type '{widget_type}'"}

        # Auto-assign position if not given
        if position is None:
            type_def = next((wt for wt in _WIDGET_TYPES if wt["type"] == widget_type), None)
            default_size = type_def["default_size"] if type_def else {"w": 4, "h": 3}
            existing_widgets = self._get_widgets(dashboard_id)
            max_y = 0
            for w in existing_widgets:
                wp = w.get("position", {})
                bottom = wp.get("y", 0) + wp.get("h", 0)
                if bottom > max_y:
                    max_y = bottom
            position = {"x": 0, "y": max_y, **default_size}

        wid = f"WGT-{uuid.uuid4().hex[:8]}"
        now = time.time()
        self._persistence.conn.execute(
            "INSERT INTO dashboard_widgets "
            "(id, dashboard_id, widget_type, title, data_source, query, config, position, "
            "created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                wid, dashboard_id, widget_type, title, data_source, "",
                json.dumps(config or {}), json.dumps(position), now, now,
            ),
        )
        self._persistence.conn.commit()
        logger.info("Added widget %s (%s) to dashboard %s", wid, widget_type, dashboard_id)
        return self.get_dashboard(dashboard_id)

    def update_widget(self, widget_id: str, updates: Dict[str, Any]) -> dict:
        """Update a widget's properties."""
        row = self._persistence.conn.execute(
            "SELECT id, dashboard_id FROM dashboard_widgets WHERE id = ?", (widget_id,)
        ).fetchone()
        if not row:
            return {"error": "Widget not found", "widget_id": widget_id}

        allowed = {"widget_type", "title", "data_source", "query", "config", "position"}
        sets, params = [], []
        for key, val in updates.items():
            if key not in allowed:
                continue
            if key in ("config", "position"):
                val = json.dumps(val)
            sets.append(f"{key} = ?")
            params.append(val)
        if not sets:
            return {"error": "No valid fields to update"}
        sets.append("updated_at = ?")
        params.append(time.time())
        params.append(widget_id)
        self._persistence.conn.execute(
            f"UPDATE dashboard_widgets SET {', '.join(sets)} WHERE id = ?", params
        )
        self._persistence.conn.commit()
        logger.info("Updated widget %s", widget_id)
        return self.get_dashboard(row[1])

    def remove_widget(self, widget_id: str) -> dict:
        """Remove a widget from its dashboard."""
        row = self._persistence.conn.execute(
            "SELECT id, dashboard_id FROM dashboard_widgets WHERE id = ?", (widget_id,)
        ).fetchone()
        if not row:
            return {"error": "Widget not found", "widget_id": widget_id}
        dashboard_id = row[1]
        self._persistence.conn.execute(
            "DELETE FROM dashboard_widgets WHERE id = ?", (widget_id,)
        )
        self._persistence.conn.commit()
        logger.info("Removed widget %s from dashboard %s", widget_id, dashboard_id)
        return {"deleted": True, "widget_id": widget_id, "dashboard_id": dashboard_id}

    def reorder_widgets(self, dashboard_id: str, widget_positions: list) -> dict:
        """
        Update positions for multiple widgets at once.
        widget_positions: list of {"widget_id": str, "position": {x, y, w, h}}
        """
        dash = self.get_dashboard(dashboard_id)
        if "error" in dash:
            return dash

        now = time.time()
        for wp in widget_positions:
            wid = wp.get("widget_id")
            pos = wp.get("position", {})
            if not wid:
                continue
            self._persistence.conn.execute(
                "UPDATE dashboard_widgets SET position = ?, updated_at = ? "
                "WHERE id = ? AND dashboard_id = ?",
                (json.dumps(pos), now, wid, dashboard_id),
            )
        self._persistence.conn.commit()
        logger.info("Reordered %d widgets in dashboard %s", len(widget_positions), dashboard_id)
        return self.get_dashboard(dashboard_id)

    # ── Sharing ─────────────────────────────────────────────────────────────

    def share_dashboard(
        self,
        dashboard_id: str,
        user_ids: Optional[List[str]] = None,
        is_public: bool = False,
    ) -> dict:
        """Share a dashboard with specific users or make it public."""
        dash = self.get_dashboard(dashboard_id)
        if "error" in dash:
            return dash

        now = time.time()
        updates: Dict[str, Any] = {"updated_at": now}

        if user_ids is not None:
            current = dash.get("shared_with", [])
            merged = list(set(current + user_ids))
            self._persistence.conn.execute(
                "UPDATE custom_dashboards SET shared_with = ?, updated_at = ? WHERE id = ?",
                (json.dumps(merged), now, dashboard_id),
            )

        self._persistence.conn.execute(
            "UPDATE custom_dashboards SET is_public = ?, updated_at = ? WHERE id = ?",
            (1 if is_public else 0, now, dashboard_id),
        )
        self._persistence.conn.commit()
        logger.info("Shared dashboard %s (public=%s, users=%s)", dashboard_id, is_public, user_ids)
        return self.get_dashboard(dashboard_id)

    # ── Widget Types ────────────────────────────────────────────────────────

    def get_widget_types(self) -> list:
        """Return all available widget types with their config schemas."""
        return [
            {
                "type": wt["type"],
                "name": wt["name"],
                "description": wt["description"],
                "config_schema": wt["config_schema"],
                "default_size": wt["default_size"],
            }
            for wt in _WIDGET_TYPES
        ]

    # ── Stats ───────────────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        conn = self._persistence.conn
        total_dashboards = conn.execute("SELECT COUNT(*) FROM custom_dashboards").fetchone()[0]
        public_dashboards = conn.execute(
            "SELECT COUNT(*) FROM custom_dashboards WHERE is_public = 1"
        ).fetchone()[0]
        total_widgets = conn.execute("SELECT COUNT(*) FROM dashboard_widgets").fetchone()[0]

        widget_type_counts = {}
        for row in conn.execute(
            "SELECT widget_type, COUNT(*) FROM dashboard_widgets GROUP BY widget_type"
        ).fetchall():
            widget_type_counts[row[0]] = row[1]

        return {
            "total_dashboards": total_dashboards,
            "public_dashboards": public_dashboards,
            "private_dashboards": total_dashboards - public_dashboards,
            "total_widgets": total_widgets,
            "avg_widgets_per_dashboard": round(total_widgets / total_dashboards, 1) if total_dashboards else 0.0,
            "widget_type_distribution": widget_type_counts,
        }
