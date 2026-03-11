"""
CortexDB Migration CLI

Usage:
    python -m cortexdb.migrate status                  # show applied/pending
    python -m cortexdb.migrate up                      # apply all pending
    python -m cortexdb.migrate up --to 007             # apply up to version 7
    python -m cortexdb.migrate down --to 005           # rollback to version 5
    python -m cortexdb.migrate baseline --version 5    # mark 1-5 as applied without running
    python -m cortexdb.migrate --dry-run up            # show what would be applied
    python -m cortexdb.migrate --dry-run down --to 005 # show what would roll back
    python -m cortexdb.migrate --force up              # continue despite checksum mismatches
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


async def cmd_up(database_url: str, dry_run: bool = False, to_version: int = None,
                 force: bool = False, **_kwargs):
    """Apply pending migrations."""
    pool = await _create_pool(database_url)
    try:
        from cortexdb.core.migrator import Migrator
        migrator = Migrator(pool, force=force)

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
            label = f"up to version {to_version:03d}" if to_version else "all pending"
            print(_color(f"\nApplying {label} migrations...\n", BOLD))
            await migrator.run(up_to_version=to_version)
            print(_color("Done.", GREEN))
    finally:
        await pool.close()


async def cmd_baseline(database_url: str, to_version: int = None, **_kwargs):
    """Mark migrations as applied without executing them."""
    if to_version is None:
        print(_color("Error: --version VERSION is required for baseline.", RED))
        sys.exit(1)

    pool = await _create_pool(database_url)
    try:
        from cortexdb.core.migrator import Migrator
        migrator = Migrator(pool)
        print(_color(f"\nBaselining migrations up to version {to_version:03d}...\n", BOLD))
        await migrator.baseline(to_version)
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
    parser.add_argument(
        "--force",
        action="store_true",
        help="Continue on checksum mismatches instead of failing",
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

    # baseline
    baseline_parser = subparsers.add_parser("baseline", help="Mark migrations as applied without executing")
    baseline_parser.add_argument("--version", type=int, dest="to_version", required=True,
                                 help="Baseline up to this version number")

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
        "baseline": cmd_baseline,
    }

    coro = commands[args.command](
        database_url=args.database_url,
        dry_run=args.dry_run,
        force=args.force,
        to_version=getattr(args, "to_version", None),
    )
    asyncio.run(coro)


if __name__ == "__main__":
    main()
