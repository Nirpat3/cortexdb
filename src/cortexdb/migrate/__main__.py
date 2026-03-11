"""
CortexDB Migration CLI

Usage:
    python -m cortexdb.migrate status                  # show applied/pending
    python -m cortexdb.migrate up                      # apply all pending
    python -m cortexdb.migrate up --to 007             # apply up to version 7
    python -m cortexdb.migrate down --to 005           # rollback to version 5
    python -m cortexdb.migrate --dry-run up            # show what would be applied
    python -m cortexdb.migrate --dry-run down --to 005 # show what would roll back
"""

import argparse
import asyncio
import os
import sys

# ANSI color codes
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
CYAN = "\033[36m"
BOLD = "\033[1m"
RESET = "\033[0m"


def _color(text: str, color: str) -> str:
    """Wrap text in ANSI color codes. Disable if NO_COLOR is set or not a tty."""
    if os.environ.get("NO_COLOR") or not sys.stdout.isatty():
        return text
    return f"{color}{text}{RESET}"


async def _create_pool(database_url: str):
    import asyncpg
    return await asyncpg.create_pool(database_url, min_size=1, max_size=2)


async def cmd_status(database_url: str, **_kwargs):
    """Show applied and pending migrations."""
    pool = await _create_pool(database_url)
    try:
        from cortexdb.core.migrator import Migrator
        migrator = Migrator(pool)
        status = await migrator.get_status()
        current = await migrator.get_current_version()
        latest = await migrator.get_latest_version()

        print(_color(f"\nCortexDB Migration Status", BOLD))
        print(_color(f"  Current DB version : {current}", CYAN))
        print(_color(f"  Latest file version: {latest}", CYAN))
        print()

        if not status:
            print("  No migrations found.")
            return

        # Header
        print(f"  {'Ver':>5}  {'Name':<40}  {'Status':<10}  {'Applied At'}")
        print(f"  {'─'*5}  {'─'*40}  {'─'*10}  {'─'*24}")

        for m in status:
            ver = f"{m['version']:03d}"
            name = m["name"][:40]
            if m["status"] == "applied":
                status_str = _color("applied", GREEN)
                applied_at = m.get("applied_at", "")
            else:
                status_str = _color("pending", YELLOW)
                applied_at = ""
            print(f"  {ver:>5}  {name:<40}  {status_str:<20}  {applied_at}")

        print()
    finally:
        await pool.close()


async def cmd_up(database_url: str, dry_run: bool = False, to_version: int = None, **_kwargs):
    """Apply pending migrations."""
    pool = await _create_pool(database_url)
    try:
        from cortexdb.core.migrator import Migrator
        migrator = Migrator(pool)

        if dry_run:
            pending = await migrator.dry_run()
            if to_version is not None:
                pending = [m for m in pending if m["version"] <= to_version]

            if not pending:
                print(_color("No pending migrations to apply.", GREEN))
                return

            print(_color("\n[DRY RUN] The following migrations would be applied:\n", YELLOW))
            for m in pending:
                ver = f"{m['version']:03d}"
                print(f"  {_color(ver, CYAN)}  {m['name']}")
            print()
        else:
            if to_version is not None:
                # Apply up to a specific version: run() applies all, so we use
                # a filtered approach by temporarily limiting scan results.
                # For simplicity, apply one-by-one up to target.
                pending = await migrator.dry_run()
                pending = [m for m in pending if m["version"] <= to_version]
                if not pending:
                    print(_color("Database is up to date (no pending migrations up to version %d)." % to_version, GREEN))
                    return
                # Apply by running full migrator — it applies all pending.
                # To limit, we do manual application.
                async with pool.acquire() as conn:
                    await conn.execute("SELECT pg_advisory_lock(42)")
                    try:
                        from cortexdb.core.migrator import MIGRATIONS_DIR, MIGRATION_PATTERN
                        for m in pending:
                            ver = m["version"]
                            name = m["name"]
                            filepath = MIGRATIONS_DIR / m["filepath"].split("/")[-1].split("\\")[-1]
                            # Reconstruct from scan
                            pass

                        # Simpler: just use the migrator internals
                        await migrator._ensure_schema_migrations_table(conn)
                        applied = await migrator._get_applied_migrations(conn)
                        applied_versions = {am["version"] for am in applied}
                        all_files = migrator._scan_migration_files()
                        count = 0
                        for version, name, filepath in all_files:
                            if version in applied_versions:
                                continue
                            if version > to_version:
                                break
                            sql = filepath.read_text(encoding="utf-8")
                            checksum = migrator._file_checksum(filepath)
                            print(f"  Applying {_color(f'{version:03d}', CYAN)}_{name} ... ", end="", flush=True)
                            await conn.execute(sql)
                            await conn.execute(
                                "INSERT INTO schema_migrations (version, name, checksum) VALUES ($1, $2, $3)",
                                version, name, checksum,
                            )
                            print(_color("OK", GREEN))
                            count += 1
                        if count == 0:
                            print(_color("No pending migrations up to version %d." % to_version, GREEN))
                        else:
                            print(_color(f"\nApplied {count} migration(s).", GREEN))
                    finally:
                        await conn.execute("SELECT pg_advisory_unlock(42)")
            else:
                print(_color("\nApplying all pending migrations...\n", BOLD))
                await migrator.run()
                print(_color("Done.", GREEN))
    finally:
        await pool.close()


async def cmd_down(database_url: str, dry_run: bool = False, to_version: int = None, **_kwargs):
    """Rollback migrations."""
    if to_version is None:
        print(_color("Error: --to VERSION is required for rollback.", RED))
        sys.exit(1)

    pool = await _create_pool(database_url)
    try:
        from cortexdb.core.migrator import Migrator
        migrator = Migrator(pool)

        if dry_run:
            pending = await migrator.dry_run_rollback(to_version)
            if not pending:
                print(_color("No migrations to roll back.", GREEN))
                return

            print(_color(f"\n[DRY RUN] The following migrations would be rolled back to version {to_version:03d}:\n", YELLOW))
            for m in pending:
                down_status = _color("has .down.sql", GREEN) if m["has_down_file"] else _color("MISSING .down.sql", RED)
                ver = f"{m['version']:03d}"
                print(f"  {_color(ver, CYAN)}  {m['name']}  ({down_status})")

            missing = [m for m in pending if not m["has_down_file"]]
            if missing:
                print(_color(f"\nWarning: {len(missing)} migration(s) are missing .down.sql files!", RED))
            print()
        else:
            print(_color(f"\nRolling back to version {to_version:03d}...\n", BOLD))
            await migrator.rollback(to_version)
            print(_color("Done.", GREEN))
    finally:
        await pool.close()


def main():
    parser = argparse.ArgumentParser(
        prog="python -m cortexdb.migrate",
        description="CortexDB database migration tool",
    )
    parser.add_argument(
        "--database-url",
        default=os.environ.get("DATABASE_URL"),
        help="PostgreSQL connection URL (default: DATABASE_URL env var)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )

    subparsers = parser.add_subparsers(dest="command", help="Migration command")

    # status
    subparsers.add_parser("status", help="Show migration status")

    # up
    up_parser = subparsers.add_parser("up", help="Apply pending migrations")
    up_parser.add_argument("--to", type=int, dest="to_version", help="Apply up to this version number")

    # down
    down_parser = subparsers.add_parser("down", help="Rollback migrations")
    down_parser.add_argument("--to", type=int, dest="to_version", help="Roll back to this version number")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if not args.database_url:
        print(_color("Error: --database-url is required (or set DATABASE_URL env var).", RED))
        sys.exit(1)

    commands = {
        "status": cmd_status,
        "up": cmd_up,
        "down": cmd_down,
    }

    coro = commands[args.command](
        database_url=args.database_url,
        dry_run=args.dry_run,
        to_version=getattr(args, "to_version", None),
    )
    asyncio.run(coro)


if __name__ == "__main__":
    main()
