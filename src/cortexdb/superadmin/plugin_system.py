"""
Plugin System — Allows extending CortexDB with custom engines, hooks, and middleware.

Plugins are loaded from the ``data/plugins/`` directory. Each plugin must contain
a ``manifest.json`` that describes its metadata, type, entry point, and
configuration schema. The PluginManager persists installation state in
``data/superadmin.db`` (SQLite).

Supported plugin types:
    - **engine**: Custom storage/query engine extension
    - **hook**: Lifecycle hook (pre-query, post-write, on-connect, etc.)
    - **middleware**: Request/response middleware layer

Usage::

    from cortexdb.superadmin.plugin_system import PluginManager

    pm = PluginManager()
    pm.register_plugin({
        "id": "vector-search",
        "name": "Vector Search Engine",
        "version": "1.0.0",
        "description": "Adds pgvector-compatible similarity search",
        "author": "Nirlab",
        "type": "engine",
        "entry_point": "vector_search.main",
        "config": {"dimensions": 1536},
        "dependencies": [],
    })
    pm.enable_plugin("vector-search")
    plugins = pm.list_plugins(enabled_only=True)
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("cortexdb.plugin_system")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_PLUGIN_TYPES = {"engine", "hook", "middleware"}

_REQUIRED_MANIFEST_KEYS = {"id", "name", "version", "type", "entry_point"}

_DB_DIR = Path(os.environ.get("CORTEXDB_DATA_DIR", os.path.join("data", "superadmin")))
_DB_PATH = _DB_DIR / "cortexdb_admin.db"

# Table 'installed_plugins' is managed by the SQLite migration system
# (see migrations.py v5). The old _CREATE_TABLE_SQL constant has been removed.


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class PluginError(Exception):
    """Base exception for plugin system errors."""


class PluginNotFoundError(PluginError):
    """Raised when a plugin ID cannot be found."""


class PluginValidationError(PluginError):
    """Raised when a plugin manifest fails validation."""


# ---------------------------------------------------------------------------
# PluginManager
# ---------------------------------------------------------------------------

class PluginManager:
    """
    Manages CortexDB plugin lifecycle: registration, enable/disable, and querying.

    Parameters
    ----------
    db_path : str or Path, optional
        Path to the SQLite database file. Defaults to ``data/superadmin.db``.
    """

    def __init__(self, db_path: Optional[str | Path] = None) -> None:
        self._db_path = Path(db_path) if db_path else _DB_PATH
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute("PRAGMA foreign_keys=ON;")
        self._ensure_table()
        logger.info("PluginManager initialised (db=%s)", self._db_path)

    # -- Lifecycle ----------------------------------------------------------

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()
        logger.debug("PluginManager closed")

    def __enter__(self) -> "PluginManager":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    # -- Schema -------------------------------------------------------------

    def _ensure_table(self) -> None:
        # Table 'installed_plugins' is managed by migrations (v5). No-op.
        pass

    # -- Validation ---------------------------------------------------------

    @staticmethod
    def _validate_manifest(manifest: dict[str, Any]) -> None:
        """Raise :class:`PluginValidationError` if the manifest is invalid."""
        missing = _REQUIRED_MANIFEST_KEYS - set(manifest.keys())
        if missing:
            raise PluginValidationError(
                f"Manifest missing required keys: {', '.join(sorted(missing))}"
            )

        plugin_type = manifest.get("type", "")
        if plugin_type not in VALID_PLUGIN_TYPES:
            raise PluginValidationError(
                f"Invalid plugin type '{plugin_type}'. "
                f"Must be one of: {', '.join(sorted(VALID_PLUGIN_TYPES))}"
            )

        plugin_id = manifest["id"]
        if not plugin_id or not isinstance(plugin_id, str):
            raise PluginValidationError("Plugin 'id' must be a non-empty string")

        if not manifest.get("entry_point"):
            raise PluginValidationError("Plugin 'entry_point' must be a non-empty string")

    # -- Registration -------------------------------------------------------

    def register_plugin(self, manifest: dict[str, Any]) -> dict[str, Any]:
        """
        Register a plugin from its manifest dictionary.

        If a plugin with the same ID already exists, it is updated in place
        (version bump / config change).

        Parameters
        ----------
        manifest : dict
            Plugin manifest. Required keys: ``id``, ``name``, ``version``,
            ``type``, ``entry_point``.

        Returns
        -------
        dict
            The persisted plugin record.

        Raises
        ------
        PluginValidationError
            If the manifest is invalid.
        """
        self._validate_manifest(manifest)

        now = datetime.now(timezone.utc).isoformat()
        plugin_id = manifest["id"]
        config_json = json.dumps(manifest.get("config", {}))
        deps_json = json.dumps(manifest.get("dependencies", []))

        existing = self._get_row(plugin_id)

        if existing:
            self._conn.execute(
                """
                UPDATE installed_plugins
                SET name = ?, version = ?, description = ?, author = ?,
                    plugin_type = ?, entry_point = ?, config = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    manifest["name"],
                    manifest["version"],
                    manifest.get("description", ""),
                    manifest.get("author", ""),
                    manifest["type"],
                    manifest["entry_point"],
                    config_json,
                    now,
                    plugin_id,
                ),
            )
            logger.info("Updated plugin %s to v%s", plugin_id, manifest["version"])
        else:
            self._conn.execute(
                """
                INSERT INTO installed_plugins
                    (id, name, version, description, author, plugin_type,
                     entry_point, config, enabled, installed_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
                """,
                (
                    plugin_id,
                    manifest["name"],
                    manifest["version"],
                    manifest.get("description", ""),
                    manifest.get("author", ""),
                    manifest["type"],
                    manifest["entry_point"],
                    config_json,
                    now,
                    now,
                ),
            )
            logger.info("Registered plugin %s v%s", plugin_id, manifest["version"])

        self._conn.commit()
        return self.get_plugin(plugin_id)

    def unregister_plugin(self, plugin_id: str) -> None:
        """
        Remove a plugin entirely.

        Parameters
        ----------
        plugin_id : str
            The plugin identifier.

        Raises
        ------
        PluginNotFoundError
            If the plugin does not exist.
        """
        self._require_exists(plugin_id)
        self._conn.execute("DELETE FROM installed_plugins WHERE id = ?", (plugin_id,))
        self._conn.commit()
        logger.info("Unregistered plugin %s", plugin_id)

    # -- Enable / Disable ---------------------------------------------------

    def enable_plugin(self, plugin_id: str) -> dict[str, Any]:
        """
        Enable a registered plugin.

        Parameters
        ----------
        plugin_id : str

        Returns
        -------
        dict
            Updated plugin record.

        Raises
        ------
        PluginNotFoundError
        """
        self._require_exists(plugin_id)
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            "UPDATE installed_plugins SET enabled = 1, updated_at = ? WHERE id = ?",
            (now, plugin_id),
        )
        self._conn.commit()
        logger.info("Enabled plugin %s", plugin_id)
        return self.get_plugin(plugin_id)

    def disable_plugin(self, plugin_id: str) -> dict[str, Any]:
        """
        Disable a registered plugin.

        Parameters
        ----------
        plugin_id : str

        Returns
        -------
        dict
            Updated plugin record.

        Raises
        ------
        PluginNotFoundError
        """
        self._require_exists(plugin_id)
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            "UPDATE installed_plugins SET enabled = 0, updated_at = ? WHERE id = ?",
            (now, plugin_id),
        )
        self._conn.commit()
        logger.info("Disabled plugin %s", plugin_id)
        return self.get_plugin(plugin_id)

    # -- Queries ------------------------------------------------------------

    def get_plugin(self, plugin_id: str) -> dict[str, Any]:
        """
        Get a single plugin by ID.

        Parameters
        ----------
        plugin_id : str

        Returns
        -------
        dict

        Raises
        ------
        PluginNotFoundError
        """
        row = self._get_row(plugin_id)
        if row is None:
            raise PluginNotFoundError(f"Plugin '{plugin_id}' not found")
        return self._row_to_dict(row)

    def list_plugins(self, enabled_only: bool = False) -> list[dict[str, Any]]:
        """
        List all registered plugins.

        Parameters
        ----------
        enabled_only : bool
            If ``True``, return only enabled plugins.

        Returns
        -------
        list[dict]
        """
        if enabled_only:
            cursor = self._conn.execute(
                "SELECT * FROM installed_plugins WHERE enabled = 1 ORDER BY name"
            )
        else:
            cursor = self._conn.execute(
                "SELECT * FROM installed_plugins ORDER BY name"
            )
        return [self._row_to_dict(row) for row in cursor.fetchall()]

    def get_plugin_stats(self) -> dict[str, Any]:
        """
        Return summary statistics about installed plugins.

        Returns
        -------
        dict
            Keys: ``total``, ``enabled``, ``disabled``, ``by_type``.
        """
        cursor = self._conn.execute(
            """
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN enabled = 1 THEN 1 ELSE 0 END) AS enabled,
                SUM(CASE WHEN enabled = 0 THEN 1 ELSE 0 END) AS disabled
            FROM installed_plugins
            """
        )
        row = cursor.fetchone()
        total = row["total"] or 0
        enabled = row["enabled"] or 0
        disabled = row["disabled"] or 0

        # Breakdown by type
        type_cursor = self._conn.execute(
            """
            SELECT plugin_type, COUNT(*) AS count
            FROM installed_plugins
            GROUP BY plugin_type
            ORDER BY plugin_type
            """
        )
        by_type = {r["plugin_type"]: r["count"] for r in type_cursor.fetchall()}

        return {
            "total": total,
            "enabled": enabled,
            "disabled": disabled,
            "by_type": by_type,
        }

    # -- Internal helpers ---------------------------------------------------

    def _get_row(self, plugin_id: str) -> Optional[sqlite3.Row]:
        cursor = self._conn.execute(
            "SELECT * FROM installed_plugins WHERE id = ?", (plugin_id,)
        )
        return cursor.fetchone()

    def _require_exists(self, plugin_id: str) -> None:
        if self._get_row(plugin_id) is None:
            raise PluginNotFoundError(f"Plugin '{plugin_id}' not found")

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        d = dict(row)
        d["enabled"] = bool(d.get("enabled", 0))
        # Parse JSON fields
        for key in ("config",):
            if key in d and isinstance(d[key], str):
                try:
                    d[key] = json.loads(d[key])
                except (json.JSONDecodeError, TypeError):
                    pass
        return d
