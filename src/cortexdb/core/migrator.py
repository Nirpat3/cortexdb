"""
CortexDB Auto-Migration System
- Tracks applied migrations in `schema_migrations` table
- Applies pending migrations on server startup
- Never backtracks (forward-only)
- Safe for concurrent startup (advisory lock)
"""

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

# Pattern: NNN_name.sql where NNN is a zero-padded integer
MIGRATION_PATTERN = re.compile(r"^(\d+)_(.+)\.sql$")


class Migrator:
    """Forward-only database migration engine with advisory locking."""

    def __init__(self, pool):
        """
        Args:
            pool: asyncpg connection pool
        """
        self.pool = pool

    async def run(self) -> None:
        """Main entry point — apply all pending migrations."""
        async with self.pool.acquire() as conn:
            # Acquire advisory lock to prevent concurrent migration runs
            logger.info("Acquiring migration advisory lock...")
            await conn.execute(f"SELECT pg_advisory_lock({ADVISORY_LOCK_ID})")
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
                    checksum = self._file_checksum(filepath)

                    if version in applied_versions:
                        # Already applied — check for tampering
                        if applied_versions[version] != checksum:
                            logger.warning(
                                "Migration %03d_%s checksum mismatch! "
                                "Expected %s, got %s. File may have been modified after application.",
                                version, name, applied_versions[version], checksum,
                            )
                        continue

                    # Apply this migration
                    logger.info("Applying migration %03d_%s ...", version, name)
                    sql = filepath.read_text(encoding="utf-8")
                    start = time.monotonic()

                    try:
                        await conn.execute(sql)
                        elapsed = time.monotonic() - start

                        # Record in schema_migrations
                        await conn.execute(
                            "INSERT INTO schema_migrations (version, name, checksum) "
                            "VALUES ($1, $2, $3)",
                            version, name, checksum,
                        )
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

    # ── Internal helpers ───────────────────────────────────

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

    @staticmethod
    def _file_checksum(filepath: Path) -> str:
        """Calculate SHA-256 checksum of a migration file."""
        content = filepath.read_bytes()
        return hashlib.sha256(content).hexdigest()
