"""
Multi-Region Replication — Cross-datacenter synchronization
with conflict resolution, geo-routing, and automatic failover.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from cortexdb.superadmin.persistence import PersistenceStore

logger = logging.getLogger("cortexdb.multi_region")

# Default seed regions
DEFAULT_REGIONS = [
    {
        "name": "us-east-1",
        "display_name": "US East (Virginia)",
        "endpoint": "https://us-east-1.cortexdb.io",
        "is_primary": True,
        "status": "active",
        "latency_ms": 0,
        "config": {"availability_zone": "us-east-1a", "provider": "aws"},
    },
    {
        "name": "eu-west-1",
        "display_name": "EU West (Ireland)",
        "endpoint": "https://eu-west-1.cortexdb.io",
        "is_primary": False,
        "status": "standby",
        "latency_ms": 85,
        "config": {"availability_zone": "eu-west-1a", "provider": "aws"},
    },
    {
        "name": "ap-south-1",
        "display_name": "Asia Pacific (Mumbai)",
        "endpoint": "https://ap-south-1.cortexdb.io",
        "is_primary": False,
        "status": "standby",
        "latency_ms": 165,
        "config": {"availability_zone": "ap-south-1a", "provider": "aws"},
    },
]

VALID_REGION_STATUSES = {"active", "standby", "offline", "syncing"}
VALID_STREAM_STATUSES = {"active", "paused", "error"}
VALID_CONFLICT_RESOLUTIONS = {"source_wins", "target_wins", "manual", "unresolved"}


class MultiRegionManager:
    """Manages cross-datacenter replication, conflict resolution, geo-routing, and failover."""

    def __init__(self, persistence_store: "PersistenceStore") -> None:
        self._store = persistence_store
        self._init_db()

    # ── Schema & Seeds ──────────────────────────────────────────────────

    def _init_db(self) -> None:
        """Seed default regions. Tables 'regions', 'replication_streams',
        'replication_conflicts', and 'failover_log' are managed by the SQLite
        migration system (see migrations.py v5)."""
        conn = self._store.conn

        # Seed default regions if empty
        existing = conn.execute("SELECT COUNT(*) as cnt FROM regions").fetchone()["cnt"]
        if existing == 0:
            self._seed_defaults()

        logger.info("Multi-region tables initialized (managed by migrations)")

    def _seed_defaults(self) -> None:
        """Seed the 3 default regions."""
        conn = self._store.conn
        now = time.time()
        for region in DEFAULT_REGIONS:
            region_id = f"region-{uuid.uuid4().hex[:12]}"
            conn.execute(
                """INSERT INTO regions
                   (id, name, display_name, endpoint, status, is_primary, latency_ms, config, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    region_id, region["name"], region["display_name"],
                    region["endpoint"], region["status"],
                    1 if region["is_primary"] else 0,
                    region["latency_ms"], json.dumps(region["config"]),
                    now, now,
                ),
            )
        conn.commit()
        logger.info("Seeded %d default regions", len(DEFAULT_REGIONS))

    # ── Helpers ─────────────────────────────────────────────────────────

    def _row_to_dict(self, row) -> Optional[dict]:
        if row is None:
            return None
        d = dict(row)
        for key in ("config", "tables", "source_value", "target_value"):
            if key in d and isinstance(d[key], str):
                try:
                    d[key] = json.loads(d[key])
                except (json.JSONDecodeError, TypeError):
                    pass
        if "is_primary" in d:
            d["is_primary"] = bool(d["is_primary"])
        return d

    def _get_region_row(self, region_id: str) -> Optional[dict]:
        row = self._store.conn.execute(
            "SELECT * FROM regions WHERE id = ?", (region_id,)
        ).fetchone()
        return self._row_to_dict(row)

    # ── Region CRUD ─────────────────────────────────────────────────────

    def list_regions(self, status: Optional[str] = None) -> list:
        """List all regions with optional status filter."""
        sql = "SELECT * FROM regions WHERE 1=1"
        params: list = []
        if status:
            if status not in VALID_REGION_STATUSES:
                raise ValueError(f"Invalid status '{status}'. Valid: {VALID_REGION_STATUSES}")
            sql += " AND status = ?"
            params.append(status)
        sql += " ORDER BY is_primary DESC, name ASC"
        rows = self._store.conn.execute(sql, params).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def get_region(self, region_id: str) -> dict:
        """Get a single region by ID."""
        region = self._get_region_row(region_id)
        if not region:
            raise ValueError(f"Region '{region_id}' not found")
        return region

    def add_region(
        self,
        name: str,
        display_name: str,
        endpoint: str,
        config: Optional[Dict] = None,
    ) -> dict:
        """Add a new region to the replication topology."""
        # Check uniqueness
        existing = self._store.conn.execute(
            "SELECT id FROM regions WHERE name = ?", (name,)
        ).fetchone()
        if existing:
            raise ValueError(f"Region with name '{name}' already exists")

        region_id = f"region-{uuid.uuid4().hex[:12]}"
        now = time.time()

        self._store.conn.execute(
            """INSERT INTO regions
               (id, name, display_name, endpoint, status, is_primary, latency_ms, config, created_at, updated_at)
               VALUES (?, ?, ?, ?, 'standby', 0, 0, ?, ?, ?)""",
            (region_id, name, display_name, endpoint, json.dumps(config or {}), now, now),
        )
        self._store.conn.commit()
        logger.info("Added region %s (%s) at %s", region_id, name, endpoint)
        self._store.audit("add_region", "region", region_id,
                          {"name": name, "endpoint": endpoint})
        return self.get_region(region_id)

    def update_region(self, region_id: str, updates: Dict[str, Any]) -> dict:
        """Update region properties."""
        self.get_region(region_id)
        now = time.time()

        allowed = {"name", "display_name", "endpoint", "status", "latency_ms", "config"}
        set_clauses = []
        params = []
        for key, value in updates.items():
            if key not in allowed:
                continue
            if key == "config":
                value = json.dumps(value)
            if key == "status" and value not in VALID_REGION_STATUSES:
                raise ValueError(f"Invalid status '{value}'. Valid: {VALID_REGION_STATUSES}")
            set_clauses.append(f"{key} = ?")
            params.append(value)

        if not set_clauses:
            return self.get_region(region_id)

        set_clauses.append("updated_at = ?")
        params.append(now)
        params.append(region_id)

        self._store.conn.execute(
            f"UPDATE regions SET {', '.join(set_clauses)} WHERE id = ?", params
        )
        self._store.conn.commit()
        logger.info("Updated region %s: %s", region_id, list(updates.keys()))
        return self.get_region(region_id)

    def remove_region(self, region_id: str) -> dict:
        """Remove a region. Cannot remove the primary region."""
        region = self.get_region(region_id)
        if region["is_primary"]:
            raise ValueError("Cannot remove the primary region. Promote another region first.")

        # Clean up streams referencing this region
        self._store.conn.execute(
            "DELETE FROM replication_streams WHERE source_region = ? OR target_region = ?",
            (region_id, region_id),
        )
        self._store.conn.execute("DELETE FROM regions WHERE id = ?", (region_id,))
        self._store.conn.commit()
        logger.info("Removed region %s (%s)", region_id, region["name"])
        self._store.audit("remove_region", "region", region_id, {"name": region["name"]})
        return {"removed": True, "region_id": region_id, "name": region["name"]}

    def set_primary(self, region_id: str) -> dict:
        """Promote a region to primary. Demotes the current primary to standby."""
        region = self.get_region(region_id)
        if region["is_primary"]:
            return region  # Already primary

        if region["status"] == "offline":
            raise ValueError(f"Cannot promote offline region '{region['name']}' to primary")

        now = time.time()

        # Demote current primary
        self._store.conn.execute(
            "UPDATE regions SET is_primary = 0, status = 'standby', updated_at = ? WHERE is_primary = 1",
            (now,),
        )

        # Promote new primary
        self._store.conn.execute(
            "UPDATE regions SET is_primary = 1, status = 'active', updated_at = ? WHERE id = ?",
            (now, region_id),
        )
        self._store.conn.commit()
        logger.info("Promoted region %s (%s) to primary", region_id, region["name"])
        self._store.audit("set_primary_region", "region", region_id,
                          {"name": region["name"]})
        return self.get_region(region_id)

    # ── Replication Streams ─────────────────────────────────────────────

    def create_replication_stream(
        self,
        source: str,
        target: str,
        tables: Optional[List[str]] = None,
        config: Optional[Dict] = None,
    ) -> dict:
        """Create a replication stream between two regions."""
        # Validate regions exist
        source_region = self.get_region(source)
        target_region = self.get_region(target)

        if source == target:
            raise ValueError("Source and target regions must be different")

        # Check for duplicate stream
        existing = self._store.conn.execute(
            "SELECT id FROM replication_streams WHERE source_region = ? AND target_region = ?",
            (source, target),
        ).fetchone()
        if existing:
            raise ValueError(f"Replication stream from '{source_region['name']}' to '{target_region['name']}' already exists")

        stream_id = f"stream-{uuid.uuid4().hex[:12]}"
        now = time.time()
        sync_tables = tables or ["*"]

        self._store.conn.execute(
            """INSERT INTO replication_streams
               (id, source_region, target_region, tables, status, lag_ms, config, created_at, updated_at)
               VALUES (?, ?, ?, ?, 'active', 0, ?, ?, ?)""",
            (stream_id, source, target, json.dumps(sync_tables),
             json.dumps(config or {}), now, now),
        )
        self._store.conn.commit()
        logger.info("Created replication stream %s: %s -> %s (tables: %s)",
                     stream_id, source_region["name"], target_region["name"], sync_tables)
        self._store.audit("create_replication_stream", "replication_stream", stream_id,
                          {"source": source_region["name"], "target": target_region["name"]})

        return self._row_to_dict(
            self._store.conn.execute(
                "SELECT * FROM replication_streams WHERE id = ?", (stream_id,)
            ).fetchone()
        )

    def list_streams(self, region_id: Optional[str] = None) -> list:
        """List replication streams, optionally filtered by region (as source or target)."""
        if region_id:
            rows = self._store.conn.execute(
                """SELECT * FROM replication_streams
                   WHERE source_region = ? OR target_region = ?
                   ORDER BY created_at DESC""",
                (region_id, region_id),
            ).fetchall()
        else:
            rows = self._store.conn.execute(
                "SELECT * FROM replication_streams ORDER BY created_at DESC"
            ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def pause_stream(self, stream_id: str) -> dict:
        """Pause a replication stream."""
        row = self._store.conn.execute(
            "SELECT * FROM replication_streams WHERE id = ?", (stream_id,)
        ).fetchone()
        if not row:
            raise ValueError(f"Replication stream '{stream_id}' not found")

        now = time.time()
        self._store.conn.execute(
            "UPDATE replication_streams SET status = 'paused', updated_at = ? WHERE id = ?",
            (now, stream_id),
        )
        self._store.conn.commit()
        logger.info("Paused replication stream %s", stream_id)
        return self._row_to_dict(
            self._store.conn.execute(
                "SELECT * FROM replication_streams WHERE id = ?", (stream_id,)
            ).fetchone()
        )

    def resume_stream(self, stream_id: str) -> dict:
        """Resume a paused replication stream."""
        row = self._store.conn.execute(
            "SELECT * FROM replication_streams WHERE id = ?", (stream_id,)
        ).fetchone()
        if not row:
            raise ValueError(f"Replication stream '{stream_id}' not found")

        now = time.time()
        self._store.conn.execute(
            "UPDATE replication_streams SET status = 'active', updated_at = ? WHERE id = ?",
            (now, stream_id),
        )
        self._store.conn.commit()
        logger.info("Resumed replication stream %s", stream_id)
        return self._row_to_dict(
            self._store.conn.execute(
                "SELECT * FROM replication_streams WHERE id = ?", (stream_id,)
            ).fetchone()
        )

    def get_replication_lag(self, stream_id: Optional[str] = None) -> dict:
        """Get current replication lag across all or a specific stream."""
        if stream_id:
            row = self._store.conn.execute(
                "SELECT * FROM replication_streams WHERE id = ?", (stream_id,)
            ).fetchone()
            if not row:
                raise ValueError(f"Replication stream '{stream_id}' not found")
            stream = self._row_to_dict(row)
            return {
                "stream_id": stream_id,
                "lag_ms": stream["lag_ms"],
                "last_synced": stream["last_synced"],
                "status": stream["status"],
            }

        rows = self._store.conn.execute(
            "SELECT * FROM replication_streams WHERE status = 'active' ORDER BY lag_ms DESC"
        ).fetchall()
        streams = [self._row_to_dict(r) for r in rows]

        max_lag = max((s["lag_ms"] for s in streams), default=0)
        avg_lag = round(sum(s["lag_ms"] for s in streams) / len(streams), 1) if streams else 0

        return {
            "total_active_streams": len(streams),
            "max_lag_ms": max_lag,
            "avg_lag_ms": avg_lag,
            "streams": [
                {
                    "stream_id": s["id"],
                    "source_region": s["source_region"],
                    "target_region": s["target_region"],
                    "lag_ms": s["lag_ms"],
                    "last_synced": s["last_synced"],
                }
                for s in streams
            ],
        }

    # ── Conflict Resolution ─────────────────────────────────────────────

    def list_conflicts(
        self,
        stream_id: Optional[str] = None,
        status: str = "unresolved",
    ) -> list:
        """List replication conflicts, optionally filtered by stream and resolution status."""
        sql = "SELECT * FROM replication_conflicts WHERE 1=1"
        params: list = []

        if stream_id:
            sql += " AND stream_id = ?"
            params.append(stream_id)
        if status:
            sql += " AND resolution = ?"
            params.append(status)

        sql += " ORDER BY created_at DESC"
        rows = self._store.conn.execute(sql, params).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def resolve_conflict(self, conflict_id: str, resolution: str) -> dict:
        """Resolve a replication conflict with the specified strategy."""
        if resolution not in VALID_CONFLICT_RESOLUTIONS:
            raise ValueError(f"Invalid resolution '{resolution}'. Valid: {VALID_CONFLICT_RESOLUTIONS}")

        row = self._store.conn.execute(
            "SELECT * FROM replication_conflicts WHERE id = ?", (conflict_id,)
        ).fetchone()
        if not row:
            raise ValueError(f"Conflict '{conflict_id}' not found")

        now = time.time()
        self._store.conn.execute(
            "UPDATE replication_conflicts SET resolution = ?, resolved_at = ? WHERE id = ?",
            (resolution, now, conflict_id),
        )
        self._store.conn.commit()
        logger.info("Resolved conflict %s with strategy '%s'", conflict_id, resolution)
        self._store.audit("resolve_conflict", "replication_conflict", conflict_id,
                          {"resolution": resolution})

        return self._row_to_dict(
            self._store.conn.execute(
                "SELECT * FROM replication_conflicts WHERE id = ?", (conflict_id,)
            ).fetchone()
        )

    # ── Failover ────────────────────────────────────────────────────────

    def trigger_failover(
        self,
        from_region: str,
        to_region: str,
        reason: Optional[str] = None,
    ) -> dict:
        """Trigger a failover from one region to another with full logging."""
        source = self.get_region(from_region)
        target = self.get_region(to_region)

        if target["status"] == "offline":
            raise ValueError(f"Cannot failover to offline region '{target['name']}'")

        failover_id = f"fo-{uuid.uuid4().hex[:12]}"
        start_time = time.time()

        # Mark source as offline
        self._store.conn.execute(
            "UPDATE regions SET status = 'offline', is_primary = 0, updated_at = ? WHERE id = ?",
            (start_time, from_region),
        )

        # Promote target
        self._store.conn.execute(
            "UPDATE regions SET status = 'active', is_primary = 1, updated_at = ? WHERE id = ?",
            (start_time, to_region),
        )

        # Pause streams from the failed region
        self._store.conn.execute(
            "UPDATE replication_streams SET status = 'paused', updated_at = ? WHERE source_region = ?",
            (start_time, from_region),
        )

        end_time = time.time()
        duration_ms = int((end_time - start_time) * 1000)

        # Log the failover
        self._store.conn.execute(
            """INSERT INTO failover_log
               (id, from_region, to_region, reason, status, duration_ms, created_at)
               VALUES (?, ?, ?, ?, 'completed', ?, ?)""",
            (failover_id, from_region, to_region, reason or "manual failover",
             duration_ms, start_time),
        )
        self._store.conn.commit()

        logger.warning("Failover executed: %s -> %s (reason: %s, duration: %dms)",
                        source["name"], target["name"], reason or "manual", duration_ms)
        self._store.audit("trigger_failover", "region", to_region, {
            "from": source["name"], "to": target["name"],
            "reason": reason, "duration_ms": duration_ms,
        })

        return {
            "failover_id": failover_id,
            "from_region": {"id": from_region, "name": source["name"], "status": "offline"},
            "to_region": {"id": to_region, "name": target["name"], "status": "active", "is_primary": True},
            "reason": reason or "manual failover",
            "duration_ms": duration_ms,
            "status": "completed",
        }

    def get_failover_log(self, limit: int = 20) -> list:
        """Retrieve the failover event log."""
        rows = self._store.conn.execute(
            "SELECT * FROM failover_log ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Health & Routing ────────────────────────────────────────────────

    def get_health(self) -> dict:
        """Get overall health of all regions, streams, lag, and conflicts."""
        regions = self.list_regions()
        streams = self.list_streams()
        lag = self.get_replication_lag()
        unresolved = self._store.conn.execute(
            "SELECT COUNT(*) as cnt FROM replication_conflicts WHERE resolution = 'unresolved'"
        ).fetchone()["cnt"]

        active_regions = [r for r in regions if r["status"] == "active"]
        primary = [r for r in regions if r["is_primary"]]
        error_streams = [s for s in streams if s["status"] == "error"]

        # Overall health determination
        if not primary:
            health = "critical"
            message = "No primary region configured"
        elif error_streams:
            health = "degraded"
            message = f"{len(error_streams)} replication stream(s) in error state"
        elif unresolved > 10:
            health = "warning"
            message = f"{unresolved} unresolved replication conflicts"
        elif lag.get("max_lag_ms", 0) > 5000:
            health = "warning"
            message = f"High replication lag detected ({lag['max_lag_ms']}ms)"
        else:
            health = "healthy"
            message = "All regions and streams operating normally"

        return {
            "health": health,
            "message": message,
            "regions": {
                "total": len(regions),
                "active": len(active_regions),
                "primary": primary[0]["name"] if primary else None,
                "by_status": {},
            },
            "streams": {
                "total": len(streams),
                "active": len([s for s in streams if s["status"] == "active"]),
                "paused": len([s for s in streams if s["status"] == "paused"]),
                "error": len(error_streams),
            },
            "replication_lag": lag,
            "unresolved_conflicts": unresolved,
            "checked_at": time.time(),
        }

    def get_geo_routing_config(self) -> dict:
        """Generate a latency-based geo-routing configuration table."""
        regions = self.list_regions()
        active_regions = [r for r in regions if r["status"] in ("active", "standby")]

        routing_table = []
        for region in active_regions:
            routing_table.append({
                "region_id": region["id"],
                "region_name": region["name"],
                "display_name": region["display_name"],
                "endpoint": region["endpoint"],
                "latency_ms": region["latency_ms"],
                "is_primary": region["is_primary"],
                "status": region["status"],
                "weight": 100 if region["is_primary"] else max(10, 100 - region["latency_ms"]),
            })

        # Sort by latency (lowest first)
        routing_table.sort(key=lambda r: r["latency_ms"])

        primary = next((r for r in regions if r["is_primary"]), None)
        return {
            "strategy": "latency_based",
            "primary_endpoint": primary["endpoint"] if primary else None,
            "fallback_order": [r["region_name"] for r in routing_table],
            "routing_table": routing_table,
            "generated_at": time.time(),
        }

    # ── Statistics ──────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        """Get aggregate multi-region statistics."""
        conn = self._store.conn

        total_regions = conn.execute(
            "SELECT COUNT(*) as cnt FROM regions"
        ).fetchone()["cnt"]

        by_status = {}
        rows = conn.execute(
            "SELECT status, COUNT(*) as cnt FROM regions GROUP BY status"
        ).fetchall()
        for r in rows:
            by_status[r["status"]] = r["cnt"]

        total_streams = conn.execute(
            "SELECT COUNT(*) as cnt FROM replication_streams"
        ).fetchone()["cnt"]

        active_streams = conn.execute(
            "SELECT COUNT(*) as cnt FROM replication_streams WHERE status = 'active'"
        ).fetchone()["cnt"]

        avg_lag = conn.execute(
            "SELECT COALESCE(AVG(lag_ms), 0) as avg_lag FROM replication_streams WHERE status = 'active'"
        ).fetchone()["avg_lag"]

        total_conflicts = conn.execute(
            "SELECT COUNT(*) as cnt FROM replication_conflicts"
        ).fetchone()["cnt"]

        unresolved_conflicts = conn.execute(
            "SELECT COUNT(*) as cnt FROM replication_conflicts WHERE resolution = 'unresolved'"
        ).fetchone()["cnt"]

        total_failovers = conn.execute(
            "SELECT COUNT(*) as cnt FROM failover_log"
        ).fetchone()["cnt"]

        return {
            "total_regions": total_regions,
            "regions_by_status": by_status,
            "total_streams": total_streams,
            "active_streams": active_streams,
            "average_lag_ms": round(avg_lag, 1),
            "total_conflicts": total_conflicts,
            "unresolved_conflicts": unresolved_conflicts,
            "total_failovers": total_failovers,
        }
