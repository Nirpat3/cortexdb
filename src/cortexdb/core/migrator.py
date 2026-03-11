"""
CortexDB Auto-Migration System
- Tracks applied migrations in `schema_migrations` table
- Applies pending migrations on server startup
- Supports rollback via companion .down.sql files
- Safe for concurrent startup (advisory lock)
"""

import asyncio
import hashlib
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("cortexdb.migrator")

# Resolve migrations directory relative to project root
_PROJECT_ROOT = Path(__file__).resolve().parents[3]  # src/cortexdb/core -> project root
MIGRATIONS_DIR = _PROJECT_ROOT / "db" / "migrations"

# Advisory lock ID — arbitrary but fixed for all CortexDB instances
ADVISORY_LOCK_ID = 42

# Timeout (seconds) for acquiring the advisory lock before giving up
LOCK_TIMEOUT = 30

# Marker comment that disables transaction wrapping for a migration file
# (e.g. migrations containing CREATE INDEX CONCURRENTLY)
NO_TRANSACTION_MARKER = "-- no-transaction"

# Pattern: NNN_name.sql where NNN is a zero-padded integer
MIGRATION_PATTERN = re.compile(r"^(\d+)_(.+)\.sql$")

# Pattern: NNN_name.down.sql — companion rollback file
ROLLBACK_PATTERN = re.compile(r"^(\d+)_(.+)\.down\.sql$")


class Migrator:
    """Database migration engine with advisory locking, rollback, and dry-run support."""

    def __init__(self, pool, auto_migrate: bool = True, force: bool = False):
        """
        Args:
            pool: asyncpg connection pool
            auto_migrate: When False, run() only checks compatibility but does not apply.
            force: When True, checksum mismatches produce warnings instead of errors.
        """
        self.pool = pool
        self.auto_migrate = auto_migrate
        self.force = force

    async def run(self, up_to_version: int = None) -> None:
        """Main entry point — apply pending migrations (or check-only if auto_migrate=False).

        Args:
            up_to_version: When set, only apply migrations up to and including this version.
        """
        if not self.auto_migrate:
            compatible = await self.check_compatibility()
            if not compatible:
                current = await self.get_current_version()
                latest = await self.get_latest_version()
                raise RuntimeError(
                    f"Database is at version {current} but migration files go up to {latest}. "
                    f"Run `python -m cortexdb.migrate up` to apply pending migrations."
                )
            logger.info("auto_migrate=False: database schema is compatible, skipping migration.")
            return

        async with self.pool.acquire() as conn:
            # HIGH-04: Use pg_try_advisory_lock with a timeout loop so we don't hang
            logger.info("Acquiring migration advisory lock...")
            await self._acquire_advisory_lock(conn)
            try:
                await self._ensure_schema_migrations_table(conn)
                applied = await self._get_applied_migrations(conn)
                pending = self._scan_migration_files()

                if not pending:
                    logger.info("No migration files found in %s", MIGRATIONS_DIR)
                    return

                applied_versions = {m["version"]: m["checksum"] for m in applied}
                migrations_run = 0

                for version, name, filepath in pending:
                    if up_to_version is not None and version > up_to_version:
                        break

                    checksum = self._file_checksum(filepath)

                    if version in applied_versions:
                        # Already applied — check for tampering (MEDIUM-02)
                        if applied_versions[version] != checksum:
                            if self.force:
                                logger.warning(
                                    "Migration %03d_%s checksum mismatch! "
                                    "Expected %s, got %s. File may have been modified after application. "
                                    "(--force: continuing anyway)",
                                    version, name, applied_versions[version], checksum,
                                )
                            else:
                                raise RuntimeError(
                                    f"Migration {version:03d}_{name} checksum mismatch! "
                                    f"Expected {applied_versions[version]}, got {checksum}. "
                                    f"File may have been modified after application. "
                                    f"Use --force to override."
                                )
                        continue

                    # Apply this migration
                    logger.info("Applying migration %03d_%s ...", version, name)
                    sql = filepath.read_text(encoding="utf-8")
                    start = time.monotonic()

                    # HIGH-02: DDL like CREATE INDEX CONCURRENTLY cannot run inside a
                    # transaction. Migrations that need this should include the marker
                    # comment "-- no-transaction" at the top of the file.
                    use_transaction = not sql.lstrip().startswith(NO_TRANSACTION_MARKER)

                    try:
                        if use_transaction:
                            async with conn.transaction():
                                await conn.execute(sql)
                                await conn.execute(
                                    "INSERT INTO schema_migrations (version, name, checksum) "
                                    "VALUES ($1, $2, $3)",
                                    version, name, checksum,
                                )
                        else:
                            logger.info(
                                "Migration %03d_%s uses -- no-transaction marker, "
                                "running without transaction wrapper.", version, name,
                            )
                            await conn.execute(sql)
                            await conn.execute(
                                "INSERT INTO schema_migrations (version, name, checksum) "
                                "VALUES ($1, $2, $3)",
                                version, name, checksum,
                            )

                        elapsed = time.monotonic() - start
                        logger.info(
                            "Migration %03d_%s applied successfully (%.2fs)",
                            version, name, elapsed,
                        )
                        migrations_run += 1

                    except Exception as e:
                        elapsed = time.monotonic() - start
                        logger.error(
                            "Migration %03d_%s FAILED after %.2fs: %s",
                            version, name, elapsed, e,
                        )
                        raise

                if migrations_run == 0:
                    logger.info("Database is up to date — no pending migrations.")
                else:
                    logger.info("Applied %d migration(s) successfully.", migrations_run)

            finally:
                await conn.execute(f"SELECT pg_advisory_unlock({ADVISORY_LOCK_ID})")
                logger.info("Released migration advisory lock.")

    async def rollback(self, target_version: int) -> None:
        """Roll back applied migrations down to (but not including) target_version.

        For each applied migration with version > target_version, the companion
        NNN_name.down.sql file is executed and the schema_migrations row is removed.

        Args:
            target_version: The version to roll back to. Migrations with version > target_version
                            will be undone. Use 0 to roll back everything.
        """
        async with self.pool.acquire() as conn:
            logger.info("Acquiring migration advisory lock for rollback...")
            await self._acquire_advisory_lock(conn)
            try:
                await self._ensure_schema_migrations_table(conn)
                applied = await self._get_applied_migrations(conn)
                rollback_files = self._scan_rollback_files()

                # Sort applied descending so we roll back newest first
                to_rollback = sorted(
                    [m for m in applied if m["version"] > target_version],
                    key=lambda m: m["version"],
                    reverse=True,
                )

                if not to_rollback:
                    logger.info("No migrations to roll back (already at or below version %d).", target_version)
                    return

                rollback_map = {v: fp for v, _name, fp in rollback_files}

                for m in to_rollback:
                    version = m["version"]
                    name = m["name"]

                    if version not in rollback_map:
                        raise RuntimeError(
                            f"Cannot roll back migration {version:03d}_{name}: "
                            f"no companion .down.sql file found in {MIGRATIONS_DIR}"
                        )

                    down_path = rollback_map[version]
                    down_sql = down_path.read_text(encoding="utf-8")

                    logger.info("Rolling back migration %03d_%s ...", version, name)
                    start = time.monotonic()

                    try:
                        async with conn.transaction():
                            await conn.execute(down_sql)
                            await conn.execute(
                                "DELETE FROM schema_migrations WHERE version = $1", version
                            )
                        elapsed = time.monotonic() - start
                        logger.info(
                            "Migration %03d_%s rolled back successfully (%.2fs)",
                            version, name, elapsed,
                        )
                    except Exception as e:
                        elapsed = time.monotonic() - start
                        logger.error(
                            "Rollback of %03d_%s FAILED after %.2fs: %s",
                            version, name, elapsed, e,
                        )
                        raise

                logger.info("Rolled back %d migration(s) to version %d.", len(to_rollback), target_version)

            finally:
                await conn.execute(f"SELECT pg_advisory_unlock({ADVISORY_LOCK_ID})")
                logger.info("Released migration advisory lock.")

    async def dry_run(self) -> List[Dict[str, Any]]:
        """Return list of pending migrations that would be applied by run(), without executing them."""
        async with self.pool.acquire() as conn:
            await self._ensure_schema_migrations_table(conn)
            applied = await self._get_applied_migrations(conn)

        applied_versions = {m["version"] for m in applied}
        pending_files = self._scan_migration_files()

        result = []
        for version, name, filepath in pending_files:
            if version not in applied_versions:
                result.append({
                    "version": version,
                    "name": name,
                    "filepath": str(filepath),
                    "action": "apply",
                })
        return result

    async def dry_run_rollback(self, target_version: int) -> List[Dict[str, Any]]:
        """Return list of migrations that would be rolled back, without executing them."""
        async with self.pool.acquire() as conn:
            await self._ensure_schema_migrations_table(conn)
            applied = await self._get_applied_migrations(conn)

        rollback_files = self._scan_rollback_files()
        rollback_map = {v: fp for v, _name, fp in rollback_files}

        to_rollback = sorted(
            [m for m in applied if m["version"] > target_version],
            key=lambda m: m["version"],
            reverse=True,
        )

        result = []
        for m in to_rollback:
            version = m["version"]
            has_down = version in rollback_map
            result.append({
                "version": version,
                "name": m["name"],
                "has_down_file": has_down,
                "down_filepath": str(rollback_map[version]) if has_down else None,
                "action": "rollback",
            })
        return result

    async def get_latest_version(self) -> int:
        """Return the highest version number among migration files on disk."""
        files = self._scan_migration_files()
        if not files:
            return 0
        return max(v for v, _name, _fp in files)

    async def get_current_version(self) -> int:
        """Return the highest applied migration version from the database."""
        async with self.pool.acquire() as conn:
            await self._ensure_schema_migrations_table(conn)
            row = await conn.fetchval(
                "SELECT COALESCE(MAX(version), 0) FROM schema_migrations"
            )
            return row

    async def check_compatibility(self) -> bool:
        """Check if the database is up to date with migration files.

        Returns True if there are no pending migrations, False otherwise.
        """
        current = await self.get_current_version()
        latest = await self.get_latest_version()
        if current < latest:
            logger.warning(
                "Database version %d is behind latest migration file version %d.",
                current, latest,
            )
            return False
        return True

    async def get_status(self) -> List[Dict[str, Any]]:
        """Return list of applied migrations with pending status info."""
        async with self.pool.acquire() as conn:
            await self._ensure_schema_migrations_table(conn)
            applied = await self._get_applied_migrations(conn)

        applied_versions = {m["version"] for m in applied}
        pending_files = self._scan_migration_files()

        # Build combined status list
        result = []
        for m in applied:
            result.append({
                "version": m["version"],
                "name": m["name"],
                "applied_at": str(m["applied_at"]),
                "checksum": m["checksum"],
                "status": "applied",
            })

        for version, name, filepath in pending_files:
            if version not in applied_versions:
                result.append({
                    "version": version,
                    "name": name,
                    "applied_at": None,
                    "checksum": self._file_checksum(filepath),
                    "status": "pending",
                })

        result.sort(key=lambda x: x["version"])
        return result

    async def baseline(self, version: int) -> None:
        """Mark migrations up to `version` as applied without executing them.

        This lets existing databases record that migrations have already been applied
        manually or by other means, so the migrator won't try to re-run them.

        Args:
            version: Mark all migration files with version <= this as applied.
        """
        async with self.pool.acquire() as conn:
            logger.info("Acquiring migration advisory lock for baseline...")
            await self._acquire_advisory_lock(conn)
            try:
                await self._ensure_schema_migrations_table(conn)
                applied = await self._get_applied_migrations(conn)
                applied_versions = {m["version"] for m in applied}
                all_files = self._scan_migration_files()

                count = 0
                for file_version, name, filepath in all_files:
                    if file_version > version:
                        break
                    if file_version in applied_versions:
                        logger.info("Migration %03d_%s already recorded, skipping.", file_version, name)
                        continue

                    checksum = self._file_checksum(filepath)
                    await conn.execute(
                        "INSERT INTO schema_migrations (version, name, checksum) "
                        "VALUES ($1, $2, $3)",
                        file_version, name, checksum,
                    )
                    logger.info("Baselined migration %03d_%s (checksum %s)", file_version, name, checksum)
                    count += 1

                if count == 0:
                    logger.info("No new migrations to baseline (all up to version %d already recorded).", version)
                else:
                    logger.info("Baselined %d migration(s) up to version %d.", count, version)
            finally:
                await conn.execute(f"SELECT pg_advisory_unlock({ADVISORY_LOCK_ID})")
                logger.info("Released migration advisory lock.")

    # ── Internal helpers ───────────────────────────────────

    async def _acquire_advisory_lock(self, conn) -> None:
        """Acquire advisory lock with a timeout loop (HIGH-04).

        Uses pg_try_advisory_lock to avoid hanging indefinitely. Retries for up
        to LOCK_TIMEOUT seconds before raising a RuntimeError.
        """
        deadline = time.monotonic() + LOCK_TIMEOUT
        while True:
            acquired = await conn.fetchval(
                f"SELECT pg_try_advisory_lock({ADVISORY_LOCK_ID})"
            )
            if acquired:
                return
            if time.monotonic() >= deadline:
                raise RuntimeError(
                    f"Could not acquire migration advisory lock within {LOCK_TIMEOUT}s. "
                    f"Another migration may be running."
                )
            await asyncio.sleep(1)

    async def _ensure_schema_migrations_table(self, conn) -> None:
        """Create the schema_migrations table if it doesn't exist."""
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version     INT PRIMARY KEY,
                name        VARCHAR(255) NOT NULL,
                applied_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                checksum    VARCHAR(64) NOT NULL
            )
        """)

    async def _get_applied_migrations(self, conn) -> List[Dict]:
        """Fetch all previously applied migrations ordered by version."""
        rows = await conn.fetch(
            "SELECT version, name, applied_at, checksum "
            "FROM schema_migrations ORDER BY version"
        )
        return [dict(r) for r in rows]

    def _scan_migration_files(self) -> List[tuple]:
        """Scan migrations directory and return sorted list of (version, name, path)."""
        if not MIGRATIONS_DIR.exists():
            logger.warning("Migrations directory not found: %s", MIGRATIONS_DIR)
            return []

        migrations = []
        for f in MIGRATIONS_DIR.iterdir():
            match = MIGRATION_PATTERN.match(f.name)
            if match:
                version = int(match.group(1))
                name = match.group(2)
                migrations.append((version, name, f))

        migrations.sort(key=lambda x: x[0])
        return migrations

    def _scan_rollback_files(self) -> List[tuple]:
        """Scan migrations directory for .down.sql files, return sorted (version, name, path)."""
        if not MIGRATIONS_DIR.exists():
            logger.warning("Migrations directory not found: %s", MIGRATIONS_DIR)
            return []

        rollbacks = []
        for f in MIGRATIONS_DIR.iterdir():
            match = ROLLBACK_PATTERN.match(f.name)
            if match:
                version = int(match.group(1))
                name = match.group(2)
                rollbacks.append((version, name, f))

        rollbacks.sort(key=lambda x: x[0])
        return rollbacks

    @staticmethod
    def _file_checksum(filepath: Path) -> str:
        """Calculate SHA-256 checksum of a migration file."""
        content = filepath.read_bytes()
        return hashlib.sha256(content).hexdigest()
