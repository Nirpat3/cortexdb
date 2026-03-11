"""
Edge Deployment — Deploy lightweight CortexDB nodes at the edge
for low-latency reads, offline-capable sync, and IoT workloads.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from cortexdb.superadmin.persistence import PersistenceStore

logger = logging.getLogger("cortexdb.edge_deployment")

# Default capabilities for new edge nodes
DEFAULT_CAPABILITIES = {
    "read": True,
    "write": True,
    "query": True,
    "full_text_search": False,
    "vector_search": False,
    "streaming": False,
}

# Heartbeat staleness threshold (seconds)
HEARTBEAT_STALE_THRESHOLD = 120
HEARTBEAT_OFFLINE_THRESHOLD = 300


class EdgeDeploymentManager:
    """Manages lightweight CortexDB edge nodes for low-latency, offline-capable workloads."""

    def __init__(self, persistence_store: "PersistenceStore") -> None:
        self._store = persistence_store
        self._init_db()

    # ── Schema ──────────────────────────────────────────────────────────

    def _init_db(self) -> None:
        # Tables 'edge_nodes' and 'edge_sync_log' are managed by the SQLite
        # migration system (see migrations.py v5).
        logger.info("Edge deployment tables initialized (managed by migrations)")

    # ── Helpers ─────────────────────────────────────────────────────────

    def _row_to_dict(self, row) -> dict:
        """Convert a sqlite3.Row to a plain dict, deserializing JSON fields."""
        if row is None:
            return None
        d = dict(row)
        for key in ("config", "capabilities", "tables_synced"):
            if key in d and isinstance(d[key], str):
                try:
                    d[key] = json.loads(d[key])
                except (json.JSONDecodeError, TypeError):
                    pass
        return d

    def _get_node_row(self, node_id: str) -> Optional[dict]:
        row = self._store.conn.execute(
            "SELECT * FROM edge_nodes WHERE id = ?", (node_id,)
        ).fetchone()
        return self._row_to_dict(row)

    # ── Node CRUD ───────────────────────────────────────────────────────

    def register_node(
        self,
        name: str,
        location: str,
        region: str,
        config: Optional[Dict] = None,
        max_storage_mb: float = 1024,
    ) -> dict:
        """Register a new edge node for deployment."""
        node_id = f"edge-{uuid.uuid4().hex[:12]}"
        now = time.time()
        node_config = config or {}
        capabilities = {**DEFAULT_CAPABILITIES, **(node_config.pop("capabilities", {}))}

        self._store.conn.execute(
            """INSERT INTO edge_nodes
               (id, name, location, region, status, config, capabilities,
                max_storage_mb, created_at, updated_at)
               VALUES (?, ?, ?, ?, 'provisioning', ?, ?, ?, ?, ?)""",
            (
                node_id, name, location, region,
                json.dumps(node_config), json.dumps(capabilities),
                max_storage_mb, now, now,
            ),
        )
        self._store.conn.commit()
        logger.info("Registered edge node %s (%s) in %s", node_id, name, region)

        node = self._get_node_row(node_id)
        self._store.audit("register_edge_node", "edge_node", node_id,
                          {"name": name, "location": location, "region": region})
        return node

    def list_nodes(self, status: Optional[str] = None, region: Optional[str] = None) -> list:
        """List edge nodes with optional status/region filters."""
        sql = "SELECT * FROM edge_nodes WHERE 1=1"
        params: list = []
        if status:
            sql += " AND status = ?"
            params.append(status)
        if region:
            sql += " AND region = ?"
            params.append(region)
        sql += " ORDER BY created_at DESC"
        rows = self._store.conn.execute(sql, params).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def get_node(self, node_id: str) -> dict:
        """Get a single edge node by ID."""
        node = self._get_node_row(node_id)
        if not node:
            raise ValueError(f"Edge node '{node_id}' not found")
        return node

    def update_node(self, node_id: str, updates: Dict[str, Any]) -> dict:
        """Update edge node properties."""
        node = self.get_node(node_id)
        now = time.time()

        allowed = {"name", "location", "region", "status", "config",
                   "capabilities", "max_storage_mb"}
        set_clauses = []
        params = []
        for key, value in updates.items():
            if key not in allowed:
                continue
            if key in ("config", "capabilities"):
                value = json.dumps(value)
            set_clauses.append(f"{key} = ?")
            params.append(value)

        if not set_clauses:
            return node

        set_clauses.append("updated_at = ?")
        params.append(now)
        params.append(node_id)

        self._store.conn.execute(
            f"UPDATE edge_nodes SET {', '.join(set_clauses)} WHERE id = ?", params
        )
        self._store.conn.commit()
        logger.info("Updated edge node %s: %s", node_id, list(updates.keys()))
        return self.get_node(node_id)

    def remove_node(self, node_id: str) -> dict:
        """Remove an edge node and its sync history."""
        node = self.get_node(node_id)
        self._store.conn.execute("DELETE FROM edge_sync_log WHERE node_id = ?", (node_id,))
        self._store.conn.execute("DELETE FROM edge_nodes WHERE id = ?", (node_id,))
        self._store.conn.commit()
        logger.info("Removed edge node %s", node_id)
        self._store.audit("remove_edge_node", "edge_node", node_id, {"name": node["name"]})
        return {"removed": True, "node_id": node_id, "name": node["name"]}

    # ── Heartbeat & Status ──────────────────────────────────────────────

    def heartbeat(self, node_id: str, metrics: Optional[Dict] = None) -> dict:
        """Process a heartbeat from an edge node. Detects stale nodes."""
        node = self.get_node(node_id)
        now = time.time()

        update_fields = {"last_heartbeat": now, "updated_at": now, "status": "online"}
        if metrics:
            if "storage_used_mb" in metrics:
                update_fields["storage_used_mb"] = metrics["storage_used_mb"]

        self._store.conn.execute(
            """UPDATE edge_nodes
               SET last_heartbeat = ?, updated_at = ?, status = ?,
                   storage_used_mb = COALESCE(?, storage_used_mb)
               WHERE id = ?""",
            (now, now, "online", metrics.get("storage_used_mb") if metrics else None, node_id),
        )
        self._store.conn.commit()

        # Detect stale nodes across fleet
        stale_nodes = self._detect_stale_nodes(now)

        return {
            "node_id": node_id,
            "status": "online",
            "heartbeat_at": now,
            "stale_nodes_detected": len(stale_nodes),
        }

    def _detect_stale_nodes(self, now: float) -> List[str]:
        """Detect and mark stale/offline nodes based on heartbeat age."""
        stale = []
        rows = self._store.conn.execute(
            "SELECT id, last_heartbeat, status FROM edge_nodes WHERE status IN ('online', 'syncing')"
        ).fetchall()
        for row in rows:
            if row["last_heartbeat"] is None:
                continue
            age = now - row["last_heartbeat"]
            if age > HEARTBEAT_OFFLINE_THRESHOLD:
                self._store.conn.execute(
                    "UPDATE edge_nodes SET status = 'offline', updated_at = ? WHERE id = ?",
                    (now, row["id"]),
                )
                stale.append(row["id"])
                logger.warning("Edge node %s marked offline (no heartbeat for %.0fs)", row["id"], age)
            elif age > HEARTBEAT_STALE_THRESHOLD and row["status"] != "syncing":
                logger.warning("Edge node %s heartbeat stale (%.0fs ago)", row["id"], age)
        if stale:
            self._store.conn.commit()
        return stale

    def get_node_status(self, node_id: str) -> dict:
        """Get detailed status for an edge node including sync lag and storage."""
        node = self.get_node(node_id)
        now = time.time()

        # Calculate sync lag
        sync_lag_seconds = None
        if node["data_synced_at"]:
            sync_lag_seconds = round(now - node["data_synced_at"], 1)

        # Heartbeat freshness
        heartbeat_age = None
        if node["last_heartbeat"]:
            heartbeat_age = round(now - node["last_heartbeat"], 1)

        # Storage utilization
        storage_pct = 0
        if node["max_storage_mb"] > 0:
            storage_pct = round((node["storage_used_mb"] / node["max_storage_mb"]) * 100, 1)

        # Recent sync count
        recent_syncs = self._store.conn.execute(
            "SELECT COUNT(*) as cnt FROM edge_sync_log WHERE node_id = ? AND created_at > ?",
            (node_id, now - 86400),
        ).fetchone()["cnt"]

        return {
            "node_id": node_id,
            "name": node["name"],
            "status": node["status"],
            "region": node["region"],
            "location": node["location"],
            "sync_lag_seconds": sync_lag_seconds,
            "heartbeat_age_seconds": heartbeat_age,
            "connectivity": "healthy" if heartbeat_age and heartbeat_age < HEARTBEAT_STALE_THRESHOLD else "degraded" if heartbeat_age else "unknown",
            "storage_used_mb": node["storage_used_mb"],
            "max_storage_mb": node["max_storage_mb"],
            "storage_utilization_pct": storage_pct,
            "syncs_last_24h": recent_syncs,
        }

    # ── Data Sync ───────────────────────────────────────────────────────

    def sync_data(
        self,
        node_id: str,
        direction: str = "push",
        tables: Optional[List[str]] = None,
    ) -> dict:
        """Trigger a data sync operation to/from an edge node."""
        if direction not in ("push", "pull"):
            raise ValueError("direction must be 'push' or 'pull'")
        node = self.get_node(node_id)
        if node["status"] == "offline":
            raise ValueError(f"Cannot sync to offline node '{node_id}'. Queue writes instead.")

        sync_id = f"sync-{uuid.uuid4().hex[:12]}"
        now = time.time()
        sync_tables = tables or ["*"]

        # Mark node as syncing
        self._store.conn.execute(
            "UPDATE edge_nodes SET status = 'syncing', updated_at = ? WHERE id = ?",
            (now, node_id),
        )

        # Simulate sync duration (in production, this would be async)
        records_count = len(sync_tables) * 150  # estimated
        duration_ms = len(sync_tables) * 45  # estimated

        self._store.conn.execute(
            """INSERT INTO edge_sync_log
               (id, node_id, direction, tables_synced, records_count, duration_ms, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, 'completed', ?)""",
            (sync_id, node_id, direction, json.dumps(sync_tables),
             records_count, duration_ms, now),
        )

        # Update node sync timestamp and status
        self._store.conn.execute(
            "UPDATE edge_nodes SET data_synced_at = ?, status = 'online', updated_at = ? WHERE id = ?",
            (now, now, node_id),
        )
        self._store.conn.commit()
        logger.info("Sync %s completed: %s %s to node %s (%d records, %dms)",
                     sync_id, direction, sync_tables, node_id, records_count, duration_ms)

        return {
            "sync_id": sync_id,
            "node_id": node_id,
            "direction": direction,
            "tables_synced": sync_tables,
            "records_count": records_count,
            "duration_ms": duration_ms,
            "status": "completed",
        }

    def get_sync_log(self, node_id: Optional[str] = None, limit: int = 50) -> list:
        """Retrieve sync log entries, optionally filtered by node."""
        if node_id:
            rows = self._store.conn.execute(
                "SELECT * FROM edge_sync_log WHERE node_id = ? ORDER BY created_at DESC LIMIT ?",
                (node_id, limit),
            ).fetchall()
        else:
            rows = self._store.conn.execute(
                "SELECT * FROM edge_sync_log ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    # ── Sync Policy ─────────────────────────────────────────────────────

    def configure_sync_policy(self, node_id: str, policy: Dict[str, Any]) -> dict:
        """
        Configure what data to sync and how often.

        Policy shape:
            {
                "tables": ["users", "events"],
                "filters": {"events": "created_at > NOW() - INTERVAL '1 day'"},
                "interval_seconds": 300,
                "conflict_resolution": "source_wins"
            }
        """
        node = self.get_node(node_id)
        current_config = node.get("config", {})
        current_config["sync_policy"] = policy
        now = time.time()

        self._store.conn.execute(
            "UPDATE edge_nodes SET config = ?, updated_at = ? WHERE id = ?",
            (json.dumps(current_config), now, node_id),
        )
        self._store.conn.commit()
        logger.info("Updated sync policy for node %s: tables=%s interval=%ss",
                     node_id, policy.get("tables", ["*"]), policy.get("interval_seconds", 300))

        return {
            "node_id": node_id,
            "sync_policy": policy,
            "updated_at": now,
        }

    # ── Offline Queue ───────────────────────────────────────────────────

    def get_offline_queue(self, node_id: str) -> dict:
        """
        Get pending writes queued while the node was offline.
        In production this reads from a write-ahead log; here we return metadata.
        """
        node = self.get_node(node_id)

        # Count failed/pending syncs as proxy for queued writes
        pending = self._store.conn.execute(
            "SELECT COUNT(*) as cnt FROM edge_sync_log WHERE node_id = ? AND status = 'pending'",
            (node_id,),
        ).fetchone()["cnt"]

        failed = self._store.conn.execute(
            "SELECT COUNT(*) as cnt FROM edge_sync_log WHERE node_id = ? AND status = 'failed'",
            (node_id,),
        ).fetchone()["cnt"]

        return {
            "node_id": node_id,
            "node_status": node["status"],
            "pending_syncs": pending,
            "failed_syncs": failed,
            "queue_depth": pending + failed,
            "is_offline": node["status"] == "offline",
            "recommendation": "Trigger sync_data() once node is back online" if node["status"] == "offline" else "Queue is draining normally",
        }

    # ── Disaster Recovery ───────────────────────────────────────────────

    def promote_to_primary(self, node_id: str) -> dict:
        """Promote an edge node to primary role for disaster recovery."""
        node = self.get_node(node_id)
        if node["status"] == "offline":
            raise ValueError(f"Cannot promote offline node '{node_id}' to primary")

        now = time.time()
        current_config = node.get("config", {})
        current_config["role"] = "primary"
        current_config["promoted_at"] = now

        # Demote any existing primary
        self._store.conn.execute(
            """UPDATE edge_nodes SET config = json_set(COALESCE(config, '{}'), '$.role', 'replica'),
                   updated_at = ?
               WHERE id != ? AND json_extract(config, '$.role') = 'primary'""",
            (now, node_id),
        )

        self._store.conn.execute(
            "UPDATE edge_nodes SET config = ?, status = 'online', updated_at = ? WHERE id = ?",
            (json.dumps(current_config), now, node_id),
        )
        self._store.conn.commit()
        logger.info("Promoted edge node %s to primary (disaster recovery)", node_id)
        self._store.audit("promote_edge_primary", "edge_node", node_id,
                          {"name": node["name"], "region": node["region"]})

        return {
            "node_id": node_id,
            "name": node["name"],
            "role": "primary",
            "promoted_at": now,
            "message": f"Node '{node['name']}' is now the primary. All writes will route here.",
        }

    # ── Statistics ──────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        """Get aggregate statistics across all edge nodes."""
        conn = self._store.conn

        total = conn.execute("SELECT COUNT(*) as cnt FROM edge_nodes").fetchone()["cnt"]

        by_status = {}
        rows = conn.execute(
            "SELECT status, COUNT(*) as cnt FROM edge_nodes GROUP BY status"
        ).fetchall()
        for r in rows:
            by_status[r["status"]] = r["cnt"]

        storage = conn.execute(
            "SELECT COALESCE(SUM(storage_used_mb), 0) as used, COALESCE(SUM(max_storage_mb), 0) as max_total FROM edge_nodes"
        ).fetchone()

        sync_ops = conn.execute(
            "SELECT COUNT(*) as cnt FROM edge_sync_log"
        ).fetchone()["cnt"]

        sync_24h = conn.execute(
            "SELECT COUNT(*) as cnt FROM edge_sync_log WHERE created_at > ?",
            (time.time() - 86400,),
        ).fetchone()["cnt"]

        by_region = {}
        rows = conn.execute(
            "SELECT region, COUNT(*) as cnt FROM edge_nodes GROUP BY region"
        ).fetchall()
        for r in rows:
            by_region[r["region"]] = r["cnt"]

        return {
            "total_nodes": total,
            "by_status": by_status,
            "by_region": by_region,
            "total_storage_used_mb": round(storage["used"], 2),
            "total_storage_capacity_mb": round(storage["max_total"], 2),
            "total_sync_operations": sync_ops,
            "sync_operations_24h": sync_24h,
        }
