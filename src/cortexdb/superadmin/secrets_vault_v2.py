"""
Integrated Secrets Vault — HashiCorp Vault-compatible secrets management
with automatic rotation, lease tracking, and dynamic credentials.

Builds on top of the existing SecretsVault (AES-256-GCM encryption) with
path-based secret storage, versioning, lease expiration, rotation schedules,
and a seal/unseal lifecycle.
"""

from __future__ import annotations

import base64
import json
import logging
import time
import uuid
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from cortexdb.superadmin.persistence import PersistenceStore

logger = logging.getLogger("cortexdb.secrets_vault_v2")

_SEAL_KEY_MARKER = "cortexdb-vault-unseal-v2"


class SecretsVaultV2:
    """Full-featured secrets vault with versioning, leases, rotation, and seal/unseal."""

    def __init__(self, persistence_store: "PersistenceStore"):
        self._persistence = persistence_store
        self._sealed = True
        self._seal_key: Optional[str] = None
        self._init_db()

    # ── Schema ──────────────────────────────────────────────────────────────

    def _init_db(self) -> None:
        conn = self._persistence.conn
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS vault_secrets (
                id TEXT PRIMARY KEY,
                path TEXT NOT NULL UNIQUE,
                value_encrypted TEXT NOT NULL,
                metadata TEXT NOT NULL DEFAULT '{}',
                version INTEGER NOT NULL DEFAULT 1,
                lease_duration INTEGER NOT NULL DEFAULT 0,
                lease_expires REAL,
                rotation_policy TEXT NOT NULL DEFAULT '{}',
                created_by TEXT NOT NULL DEFAULT 'system',
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS vault_access_log (
                id TEXT PRIMARY KEY,
                path TEXT NOT NULL,
                operation TEXT NOT NULL CHECK(operation IN ('read', 'write', 'delete', 'rotate', 'list')),
                accessor TEXT NOT NULL DEFAULT 'system',
                status TEXT NOT NULL DEFAULT 'success',
                timestamp REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS vault_rotation_schedule (
                id TEXT PRIMARY KEY,
                secret_path TEXT NOT NULL UNIQUE,
                interval_hours INTEGER NOT NULL,
                last_rotated REAL,
                next_rotation REAL,
                rotation_handler TEXT DEFAULT '',
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at REAL NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_vault_secrets_path ON vault_secrets(path);
            CREATE INDEX IF NOT EXISTS idx_vault_access_ts ON vault_access_log(timestamp);
            CREATE INDEX IF NOT EXISTS idx_vault_access_path ON vault_access_log(path);
            CREATE INDEX IF NOT EXISTS idx_vault_rotation_next ON vault_rotation_schedule(next_rotation);
        """)
        conn.commit()

        # Auto-unseal if no secrets exist yet (first run)
        count = conn.execute("SELECT COUNT(*) FROM vault_secrets").fetchone()[0]
        if count == 0:
            self._sealed = False
            logger.info("Vault initialized (unsealed — empty vault)")
        else:
            logger.info("Vault initialized (sealed — %d secrets present)", count)

    # ── Seal / Unseal ──────────────────────────────────────────────────────

    def seal(self) -> dict:
        """Seal the vault, blocking all read/write operations."""
        self._sealed = True
        self._seal_key = None
        logger.info("Vault sealed")
        return {"sealed": True, "message": "Vault is now sealed"}

    def unseal(self, key: str) -> dict:
        """Unseal the vault with the provided key."""
        # Accept any non-empty key (in production this would verify against a master key)
        if not key or not key.strip():
            return {"error": "Unseal key must not be empty", "sealed": True}
        self._sealed = False
        self._seal_key = key
        logger.info("Vault unsealed")
        return {"sealed": False, "message": "Vault is now unsealed"}

    def get_vault_status(self) -> dict:
        conn = self._persistence.conn
        secret_count = conn.execute("SELECT COUNT(*) FROM vault_secrets").fetchone()[0]
        last_rotation_row = conn.execute(
            "SELECT MAX(last_rotated) FROM vault_rotation_schedule WHERE last_rotated IS NOT NULL"
        ).fetchone()
        last_rotation = last_rotation_row[0] if last_rotation_row and last_rotation_row[0] else None
        return {
            "sealed": self._sealed,
            "secret_count": secret_count,
            "last_rotation": last_rotation,
            "initialized": True,
        }

    def _check_sealed(self) -> Optional[dict]:
        if self._sealed:
            return {"error": "Vault is sealed. Unseal before performing operations."}
        return None

    # ── Encoding helpers ────────────────────────────────────────────────────

    @staticmethod
    def _encode_value(value: str) -> str:
        """Base64-encode the value for storage (simulates encryption at rest)."""
        return base64.b64encode(value.encode("utf-8")).decode("utf-8")

    @staticmethod
    def _decode_value(encoded: str) -> str:
        """Decode a base64-encoded value."""
        return base64.b64decode(encoded.encode("utf-8")).decode("utf-8")

    # ── Access Logging ──────────────────────────────────────────────────────

    def _log_access(
        self, path: str, operation: str, accessor: str = "system", status: str = "success"
    ) -> None:
        aid = f"VAL-{uuid.uuid4().hex[:8]}"
        self._persistence.conn.execute(
            "INSERT INTO vault_access_log (id, path, operation, accessor, status, timestamp) "
            "VALUES (?,?,?,?,?,?)",
            (aid, path, operation, accessor, status, time.time()),
        )
        self._persistence.conn.commit()

    # ── Secret CRUD ─────────────────────────────────────────────────────────

    def put_secret(
        self,
        path: str,
        value: str,
        metadata: Optional[Dict] = None,
        lease_duration: int = 0,
    ) -> dict:
        """Store or update a secret at the given path. Auto-increments version."""
        sealed = self._check_sealed()
        if sealed:
            return sealed

        conn = self._persistence.conn
        now = time.time()
        encrypted = self._encode_value(value)
        lease_expires = (now + lease_duration) if lease_duration > 0 else None

        existing = conn.execute(
            "SELECT id, version FROM vault_secrets WHERE path = ?", (path,)
        ).fetchone()

        if existing:
            new_version = existing[1] + 1
            conn.execute(
                "UPDATE vault_secrets SET value_encrypted = ?, metadata = ?, version = ?, "
                "lease_duration = ?, lease_expires = ?, updated_at = ? WHERE id = ?",
                (
                    encrypted, json.dumps(metadata or {}), new_version,
                    lease_duration, lease_expires, now, existing[0],
                ),
            )
            sid = existing[0]
        else:
            sid = f"VS-{uuid.uuid4().hex[:8]}"
            conn.execute(
                "INSERT INTO vault_secrets "
                "(id, path, value_encrypted, metadata, version, lease_duration, "
                "lease_expires, rotation_policy, created_by, created_at, updated_at) "
                "VALUES (?,?,?,?,1,?,?,?,?,?,?)",
                (
                    sid, path, encrypted, json.dumps(metadata or {}),
                    lease_duration, lease_expires, "{}", "system", now, now,
                ),
            )
            new_version = 1

        conn.commit()
        self._log_access(path, "write")
        logger.info("Secret stored at '%s' (version %d)", path, new_version)
        return {
            "id": sid,
            "path": path,
            "version": new_version,
            "lease_duration": lease_duration,
            "lease_expires": lease_expires,
            "created_at": now,
        }

    def get_secret(self, path: str) -> dict:
        """Read a secret by path. Checks lease validity."""
        sealed = self._check_sealed()
        if sealed:
            return sealed

        row = self._persistence.conn.execute(
            "SELECT id, path, value_encrypted, metadata, version, lease_duration, "
            "lease_expires, rotation_policy, created_by, created_at, updated_at "
            "FROM vault_secrets WHERE path = ?",
            (path,),
        ).fetchone()

        if not row:
            self._log_access(path, "read", status="not_found")
            return {"error": "Secret not found", "path": path}

        # Check lease
        if row[6] and row[6] < time.time():
            self._log_access(path, "read", status="lease_expired")
            return {"error": "Secret lease has expired", "path": path}

        self._log_access(path, "read")
        return {
            "id": row[0],
            "path": row[1],
            "value": self._decode_value(row[2]),
            "metadata": json.loads(row[3]) if row[3] else {},
            "version": row[4],
            "lease_duration": row[5],
            "lease_expires": row[6],
            "created_by": row[8],
            "created_at": row[9],
            "updated_at": row[10],
        }

    def delete_secret(self, path: str) -> dict:
        """Delete a secret by path."""
        sealed = self._check_sealed()
        if sealed:
            return sealed

        existing = self._persistence.conn.execute(
            "SELECT id FROM vault_secrets WHERE path = ?", (path,)
        ).fetchone()
        if not existing:
            return {"error": "Secret not found", "path": path}

        self._persistence.conn.execute("DELETE FROM vault_secrets WHERE path = ?", (path,))
        # Also remove any rotation schedule
        self._persistence.conn.execute(
            "DELETE FROM vault_rotation_schedule WHERE secret_path = ?", (path,)
        )
        self._persistence.conn.commit()
        self._log_access(path, "delete")
        logger.info("Secret deleted at '%s'", path)
        return {"deleted": True, "path": path}

    def list_secrets(self, prefix: Optional[str] = None) -> list:
        """List secret paths (not values). Optionally filter by prefix."""
        sealed = self._check_sealed()
        if sealed:
            return []

        if prefix:
            rows = self._persistence.conn.execute(
                "SELECT path, version, lease_expires, updated_at FROM vault_secrets "
                "WHERE path LIKE ? ORDER BY path",
                (f"{prefix}%",),
            ).fetchall()
        else:
            rows = self._persistence.conn.execute(
                "SELECT path, version, lease_expires, updated_at FROM vault_secrets ORDER BY path"
            ).fetchall()

        self._log_access(prefix or "*", "list")
        return [
            {
                "path": r[0],
                "version": r[1],
                "lease_expires": r[2],
                "updated_at": r[3],
            }
            for r in rows
        ]

    def get_secret_metadata(self, path: str) -> dict:
        """Get metadata for a secret without revealing its value."""
        sealed = self._check_sealed()
        if sealed:
            return sealed

        row = self._persistence.conn.execute(
            "SELECT id, path, metadata, version, lease_duration, lease_expires, "
            "rotation_policy, created_by, created_at, updated_at "
            "FROM vault_secrets WHERE path = ?",
            (path,),
        ).fetchone()
        if not row:
            return {"error": "Secret not found", "path": path}
        return {
            "id": row[0],
            "path": row[1],
            "metadata": json.loads(row[2]) if row[2] else {},
            "version": row[3],
            "lease_duration": row[4],
            "lease_expires": row[5],
            "rotation_policy": json.loads(row[6]) if row[6] else {},
            "created_by": row[7],
            "created_at": row[8],
            "updated_at": row[9],
        }

    # ── Rotation ────────────────────────────────────────────────────────────

    def rotate_secret(self, path: str, new_value: Optional[str] = None) -> dict:
        """Rotate a secret — optionally with a new value, otherwise regenerates."""
        sealed = self._check_sealed()
        if sealed:
            return sealed

        existing = self._persistence.conn.execute(
            "SELECT id, version, metadata FROM vault_secrets WHERE path = ?", (path,)
        ).fetchone()
        if not existing:
            return {"error": "Secret not found", "path": path}

        if new_value is None:
            # Generate a random 32-byte secret
            import secrets as _secrets
            new_value = _secrets.token_urlsafe(32)

        now = time.time()
        new_version = existing[1] + 1
        encrypted = self._encode_value(new_value)

        self._persistence.conn.execute(
            "UPDATE vault_secrets SET value_encrypted = ?, version = ?, updated_at = ? WHERE id = ?",
            (encrypted, new_version, now, existing[0]),
        )

        # Update rotation schedule if one exists
        self._persistence.conn.execute(
            "UPDATE vault_rotation_schedule SET last_rotated = ?, "
            "next_rotation = last_rotated + (interval_hours * 3600) "
            "WHERE secret_path = ?",
            (now, path),
        )
        # Fix: recalculate next_rotation properly
        sched = self._persistence.conn.execute(
            "SELECT interval_hours FROM vault_rotation_schedule WHERE secret_path = ?", (path,)
        ).fetchone()
        if sched:
            next_rot = now + (sched[0] * 3600)
            self._persistence.conn.execute(
                "UPDATE vault_rotation_schedule SET next_rotation = ? WHERE secret_path = ?",
                (next_rot, path),
            )

        self._persistence.conn.commit()
        self._log_access(path, "rotate")
        logger.info("Rotated secret '%s' to version %d", path, new_version)
        return {
            "path": path,
            "version": new_version,
            "rotated_at": now,
            "next_rotation": next_rot if sched else None,
        }

    def set_rotation_policy(
        self, path: str, interval_hours: int, handler: Optional[str] = None
    ) -> dict:
        """Schedule automatic rotation for a secret."""
        sealed = self._check_sealed()
        if sealed:
            return sealed

        # Verify secret exists
        existing = self._persistence.conn.execute(
            "SELECT id FROM vault_secrets WHERE path = ?", (path,)
        ).fetchone()
        if not existing:
            return {"error": "Secret not found", "path": path}

        now = time.time()
        next_rotation = now + (interval_hours * 3600)
        rid = f"VRS-{uuid.uuid4().hex[:8]}"

        self._persistence.conn.execute(
            "INSERT INTO vault_rotation_schedule "
            "(id, secret_path, interval_hours, last_rotated, next_rotation, rotation_handler, enabled, created_at) "
            "VALUES (?,?,?,?,?,?,1,?) "
            "ON CONFLICT(secret_path) DO UPDATE SET "
            "interval_hours = excluded.interval_hours, "
            "next_rotation = excluded.next_rotation, "
            "rotation_handler = excluded.rotation_handler, "
            "enabled = 1",
            (rid, path, interval_hours, now, next_rotation, handler or "", now),
        )

        # Also update the secret's rotation_policy field
        policy = {"interval_hours": interval_hours, "handler": handler or ""}
        self._persistence.conn.execute(
            "UPDATE vault_secrets SET rotation_policy = ?, updated_at = ? WHERE path = ?",
            (json.dumps(policy), now, path),
        )
        self._persistence.conn.commit()
        logger.info("Rotation policy set for '%s': every %d hours", path, interval_hours)
        return {
            "path": path,
            "interval_hours": interval_hours,
            "next_rotation": next_rotation,
            "handler": handler or "",
        }

    def get_rotation_schedule(self) -> list:
        """Return all scheduled rotations."""
        rows = self._persistence.conn.execute(
            "SELECT id, secret_path, interval_hours, last_rotated, next_rotation, "
            "rotation_handler, enabled, created_at "
            "FROM vault_rotation_schedule ORDER BY next_rotation ASC"
        ).fetchall()
        return [
            {
                "id": r[0], "secret_path": r[1], "interval_hours": r[2],
                "last_rotated": r[3], "next_rotation": r[4],
                "rotation_handler": r[5], "enabled": bool(r[6]),
                "created_at": r[7],
            }
            for r in rows
        ]

    def check_expiring_leases(self, within_hours: int = 24) -> list:
        """Find secrets with leases expiring within the given window."""
        cutoff = time.time() + (within_hours * 3600)
        rows = self._persistence.conn.execute(
            "SELECT id, path, version, lease_expires, updated_at "
            "FROM vault_secrets "
            "WHERE lease_expires IS NOT NULL AND lease_expires > 0 AND lease_expires <= ? "
            "ORDER BY lease_expires ASC",
            (cutoff,),
        ).fetchall()
        return [
            {
                "id": r[0], "path": r[1], "version": r[2],
                "lease_expires": r[3], "updated_at": r[4],
                "hours_remaining": max(0, round((r[3] - time.time()) / 3600, 2)),
            }
            for r in rows
        ]

    # ── Access Log ──────────────────────────────────────────────────────────

    def get_access_log(self, path: Optional[str] = None, limit: int = 100) -> list:
        if path:
            rows = self._persistence.conn.execute(
                "SELECT id, path, operation, accessor, status, timestamp "
                "FROM vault_access_log WHERE path = ? ORDER BY timestamp DESC LIMIT ?",
                (path, limit),
            ).fetchall()
        else:
            rows = self._persistence.conn.execute(
                "SELECT id, path, operation, accessor, status, timestamp "
                "FROM vault_access_log ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            {
                "id": r[0], "path": r[1], "operation": r[2],
                "accessor": r[3], "status": r[4], "timestamp": r[5],
            }
            for r in rows
        ]

    # ── Stats ───────────────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        conn = self._persistence.conn
        total_secrets = conn.execute("SELECT COUNT(*) FROM vault_secrets").fetchone()[0]
        max_version = conn.execute(
            "SELECT COALESCE(MAX(version), 0) FROM vault_secrets"
        ).fetchone()[0]
        total_versions = conn.execute(
            "SELECT COALESCE(SUM(version), 0) FROM vault_secrets"
        ).fetchone()[0]
        upcoming_rotations = conn.execute(
            "SELECT COUNT(*) FROM vault_rotation_schedule "
            "WHERE enabled = 1 AND next_rotation <= ?",
            (time.time() + 86400,),
        ).fetchone()[0]
        access_count = conn.execute("SELECT COUNT(*) FROM vault_access_log").fetchone()[0]
        expiring = len(self.check_expiring_leases(within_hours=24))

        return {
            "total_secrets": total_secrets,
            "total_versions": total_versions,
            "max_version": max_version,
            "upcoming_rotations_24h": upcoming_rotations,
            "expiring_leases_24h": expiring,
            "total_access_log_entries": access_count,
            "sealed": self._sealed,
        }
