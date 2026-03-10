#!/usr/bin/env bash
# ============================================================================
# CortexDB Migration CLI
# ============================================================================
# Run migrations manually (also runs automatically on server startup)
#
# Usage:
#   ./scripts/migrate.sh              # Apply pending migrations
#   ./scripts/migrate.sh --status     # Show migration status
#   ./scripts/migrate.sh --create NAME  # Create new migration file
# ============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
MIGRATIONS_DIR="$PROJECT_ROOT/db/migrations"

# Database connection (override via env vars)
DB_HOST="${CORTEXDB_HOST:-localhost}"
DB_PORT="${CORTEXDB_PORT:-5432}"
DB_NAME="${CORTEXDB_DB:-cortexdb}"
DB_USER="${CORTEXDB_USER:-cortex}"
DB_PASS="${CORTEXDB_PASS:-cortex_secret}"

export PGPASSWORD="$DB_PASS"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

usage() {
    echo "CortexDB Migration Tool"
    echo ""
    echo "Usage:"
    echo "  $0              Apply pending migrations (via server startup)"
    echo "  $0 --status     Show applied and pending migrations"
    echo "  $0 --create NAME  Create a new migration file"
    echo ""
    echo "Environment variables:"
    echo "  CORTEXDB_HOST  (default: localhost)"
    echo "  CORTEXDB_PORT  (default: 5432)"
    echo "  CORTEXDB_DB    (default: cortexdb)"
    echo "  CORTEXDB_USER  (default: cortex)"
    echo "  CORTEXDB_PASS  (default: cortex_secret)"
}

# ── --create: scaffold a new migration file ────────────────
create_migration() {
    local name="$1"
    # Sanitize name: lowercase, replace spaces/special chars with underscores
    name=$(echo "$name" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9]/_/g' | sed 's/__*/_/g' | sed 's/^_//;s/_$//')

    # Find highest existing version number
    local max_version=0
    for f in "$MIGRATIONS_DIR"/*.sql; do
        [ -e "$f" ] || continue
        basename_f=$(basename "$f")
        ver=$(echo "$basename_f" | grep -oP '^\d+' || true)
        if [ -n "$ver" ] && [ "$ver" -gt "$max_version" ]; then
            max_version=$ver
        fi
    done

    local next_version=$((max_version + 1))
    local padded=$(printf "%03d" "$next_version")
    local filename="${padded}_${name}.sql"
    local filepath="$MIGRATIONS_DIR/$filename"

    cat > "$filepath" << SQLEOF
-- ============================================================================
-- Migration ${padded}: ${name}
-- ============================================================================
-- Description: TODO
-- ============================================================================

-- Write your migration SQL here

SQLEOF

    echo -e "${GREEN}Created migration:${NC} $filepath"
}

# ── --status: show migration status ────────────────────────
show_status() {
    echo -e "${CYAN}CortexDB Migration Status${NC}"
    echo "────────────────────────────────────────────────────────"

    # Check if schema_migrations table exists
    local table_exists
    table_exists=$(psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -tAc \
        "SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name='schema_migrations')" 2>/dev/null || echo "false")

    if [ "$table_exists" != "t" ]; then
        echo -e "${YELLOW}Migration system not initialized.${NC}"
        echo "Start the CortexDB server to auto-initialize, or run migrations manually."
        echo ""
        echo "Pending migration files:"
        for f in "$MIGRATIONS_DIR"/*.sql; do
            [ -e "$f" ] || continue
            echo -e "  ${YELLOW}PENDING${NC}  $(basename "$f")"
        done
        return
    fi

    # Fetch applied migrations
    local applied
    applied=$(psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -tA \
        "SELECT version || '|' || name || '|' || applied_at FROM schema_migrations ORDER BY version" 2>/dev/null || true)

    # Build set of applied versions
    declare -A applied_versions
    if [ -n "$applied" ]; then
        while IFS='|' read -r ver name applied_at; do
            applied_versions[$ver]=1
            printf "  ${GREEN}APPLIED${NC}  %03d_%-40s  %s\n" "$ver" "$name" "$applied_at"
        done <<< "$applied"
    fi

    # Show pending files
    for f in "$MIGRATIONS_DIR"/*.sql; do
        [ -e "$f" ] || continue
        basename_f=$(basename "$f")
        ver=$(echo "$basename_f" | grep -oP '^\d+' || true)
        if [ -n "$ver" ] && [ -z "${applied_versions[$ver]:-}" ]; then
            echo -e "  ${YELLOW}PENDING${NC}  $basename_f"
        fi
    done

    echo "────────────────────────────────────────────────────────"
}

# ── Default: apply migrations ──────────────────────────────
apply_migrations() {
    echo -e "${CYAN}CortexDB Migration Runner${NC}"
    echo ""
    echo "Migrations run automatically on server startup."
    echo "To apply migrations now, start the server:"
    echo ""
    echo "  python -m cortexdb.server"
    echo ""
    echo "Or use Python directly:"
    echo ""
    echo "  python -c \""
    echo "    import asyncio, asyncpg"
    echo "    from cortexdb.core.migrator import Migrator"
    echo "    async def run():"
    echo "        pool = await asyncpg.create_pool('postgresql://${DB_USER}:${DB_PASS}@${DB_HOST}:${DB_PORT}/${DB_NAME}')"
    echo "        m = Migrator(pool)"
    echo "        await m.run()"
    echo "        await pool.close()"
    echo "    asyncio.run(run())"
    echo "  \""
}

# ── Main ───────────────────────────────────────────────────
case "${1:-}" in
    --status|-s)
        show_status
        ;;
    --create|-c)
        if [ -z "${2:-}" ]; then
            echo -e "${RED}Error: --create requires a migration name${NC}"
            echo "Usage: $0 --create <name>"
            exit 1
        fi
        create_migration "$2"
        ;;
    --help|-h)
        usage
        ;;
    "")
        apply_migrations
        ;;
    *)
        echo -e "${RED}Unknown option: $1${NC}"
        usage
        exit 1
        ;;
esac
