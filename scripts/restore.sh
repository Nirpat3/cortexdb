#!/usr/bin/env bash
# ============================================================
# CortexDB Restore Script
# Restores PostgreSQL (Citus), Redis, SQLite, and Qdrant
# from a backup created by backup.sh
# ============================================================
set -euo pipefail

# ----------------------------------------------------------
# Configuration
# ----------------------------------------------------------
BACKUP_BASE_DIR="${BACKUP_BASE_DIR:-/data/backups}"
RESTORE_LOG="${BACKUP_BASE_DIR}/restore.log"

# PostgreSQL
PG_HOST="${PG_HOST:-relational-core}"
PG_PORT="${PG_PORT:-5432}"
PG_USER="${PG_USER:-cortex}"
PG_PASSWORD="${PG_PASSWORD:-${POSTGRES_PASSWORD:-cortex_secret}}"
PG_DB="${PG_DB:-cortexdb}"

# Redis
REDIS_HOST="${REDIS_HOST:-memory-core}"
REDIS_PORT="${REDIS_PORT:-6379}"
REDIS_PASSWORD="${REDIS_PASSWORD:-cortex_redis_secret}"
STREAM_HOST="${STREAM_HOST:-stream-core}"
STREAM_PORT="${STREAM_PORT:-6380}"
STREAM_PASSWORD="${STREAM_PASSWORD:-cortex_stream_secret}"

# SQLite
SQLITE_DB_PATH="${SQLITE_DB_PATH:-/data/superadmin/cortexdb_admin.db}"

# Qdrant
QDRANT_URL="${QDRANT_URL:-http://vector-core:6333}"

# Docker Compose project (for service stop/start)
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
COMPOSE_PROJECT="${COMPOSE_PROJECT:-cortexdb}"

# ----------------------------------------------------------
# Globals
# ----------------------------------------------------------
BACKUP_DIR=""
DRY_RUN=false
AUTO_YES=false
EXIT_CODE=0
COMPONENTS_REQUESTED=()
DO_FULL=false

# ----------------------------------------------------------
# Logging
# ----------------------------------------------------------
log() {
    local level="$1"; shift
    local msg="[$(date '+%Y-%m-%d %H:%M:%S')] [${level}] $*"
    echo "$msg" | tee -a "$RESTORE_LOG"
}

log_info()  { log "INFO"  "$@"; }
log_warn()  { log "WARN"  "$@"; }
log_error() { log "ERROR" "$@"; }

# ----------------------------------------------------------
# Usage
# ----------------------------------------------------------
usage() {
    cat <<EOF
Usage: $(basename "$0") <BACKUP_DIR> [OPTIONS]

Restore CortexDB databases from a backup directory.

Arguments:
  BACKUP_DIR    Path to the timestamped backup directory (e.g., /data/backups/20260308_020000)

Options:
  --postgres    Restore PostgreSQL only
  --redis       Restore Redis (memory-core + stream-core) only
  --sqlite      Restore SQLite superadmin database only
  --qdrant      Restore Qdrant vector snapshots only
  --dry-run     Show what would be restored without doing it
  --yes         Skip confirmation prompt
  --help        Show this help message

If no component flags are given, all available components are restored.
EOF
    exit 0
}

# ----------------------------------------------------------
# Parse arguments
# ----------------------------------------------------------
parse_args() {
    if [[ $# -eq 0 ]]; then
        log_error "No backup directory specified"
        usage
    fi

    # First positional argument is the backup directory
    BACKUP_DIR="$1"
    shift

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --postgres)  COMPONENTS_REQUESTED+=("postgres") ;;
            --redis)     COMPONENTS_REQUESTED+=("redis") ;;
            --sqlite)    COMPONENTS_REQUESTED+=("sqlite") ;;
            --qdrant)    COMPONENTS_REQUESTED+=("qdrant") ;;
            --dry-run)   DRY_RUN=true ;;
            --yes)       AUTO_YES=true ;;
            --help)      usage ;;
            *)           log_error "Unknown option: $1"; usage ;;
        esac
        shift
    done

    if [[ ${#COMPONENTS_REQUESTED[@]} -eq 0 ]]; then
        DO_FULL=true
    fi
}

should_restore() {
    local component="$1"
    if [[ "$DO_FULL" == "true" ]]; then
        return 0
    fi
    for c in "${COMPONENTS_REQUESTED[@]}"; do
        if [[ "$c" == "$component" ]]; then
            return 0
        fi
    done
    return 1
}

# ----------------------------------------------------------
# Validation
# ----------------------------------------------------------
validate_backup() {
    log_info "Validating backup directory: ${BACKUP_DIR}"

    if [[ ! -d "$BACKUP_DIR" ]]; then
        log_error "Backup directory does not exist: ${BACKUP_DIR}"
        exit 1
    fi

    if [[ ! -f "${BACKUP_DIR}/manifest.json" ]]; then
        log_warn "No manifest.json found — backup may be incomplete"
    else
        log_info "Manifest found. Contents:"
        cat "${BACKUP_DIR}/manifest.json" | tee -a "$RESTORE_LOG"
        echo ""
    fi

    local available=()

    if [[ -f "${BACKUP_DIR}/postgres/cortexdb.dump" ]]; then
        local pg_size
        pg_size=$(du -sh "${BACKUP_DIR}/postgres/cortexdb.dump" | cut -f1)
        log_info "  [OK] PostgreSQL dump found (${pg_size})"
        available+=("postgres")

        # Validate dump file integrity
        if pg_restore --list "${BACKUP_DIR}/postgres/cortexdb.dump" > /dev/null 2>&1; then
            log_info "  [OK] PostgreSQL dump integrity verified"
        else
            log_warn "  [!!] PostgreSQL dump may be corrupted — pg_restore --list failed"
        fi
    else
        log_info "  [--] PostgreSQL dump not present"
    fi

    for rdb_name in memory-core stream-core; do
        if [[ -f "${BACKUP_DIR}/redis/${rdb_name}.rdb" ]]; then
            local rdb_size
            rdb_size=$(du -sh "${BACKUP_DIR}/redis/${rdb_name}.rdb" | cut -f1)
            log_info "  [OK] Redis ${rdb_name} RDB found (${rdb_size})"
            available+=("redis")
        else
            log_info "  [--] Redis ${rdb_name} RDB not present"
        fi
    done

    if [[ -f "${BACKUP_DIR}/sqlite/cortexdb_admin.db" ]]; then
        local sq_size
        sq_size=$(du -sh "${BACKUP_DIR}/sqlite/cortexdb_admin.db" | cut -f1)
        log_info "  [OK] SQLite backup found (${sq_size})"
        available+=("sqlite")

        # Validate SQLite integrity
        if sqlite3 "${BACKUP_DIR}/sqlite/cortexdb_admin.db" "PRAGMA integrity_check;" 2>/dev/null | grep -q "ok"; then
            log_info "  [OK] SQLite integrity check passed"
        else
            log_warn "  [!!] SQLite integrity check failed"
        fi
    else
        log_info "  [--] SQLite backup not present"
    fi

    if [[ -d "${BACKUP_DIR}/qdrant" ]] && ls "${BACKUP_DIR}/qdrant/"* > /dev/null 2>&1; then
        local snap_count
        snap_count=$(ls -1 "${BACKUP_DIR}/qdrant/" | wc -l)
        log_info "  [OK] Qdrant snapshots found (${snap_count} file(s))"
        available+=("qdrant")
    else
        log_info "  [--] Qdrant snapshots not present"
    fi

    if [[ ${#available[@]} -eq 0 ]]; then
        log_error "No restorable components found in backup directory"
        exit 1
    fi
}

# ----------------------------------------------------------
# Confirmation
# ----------------------------------------------------------
confirm_restore() {
    if [[ "$AUTO_YES" == "true" ]]; then
        return 0
    fi

    echo ""
    echo "WARNING: Restoring will OVERWRITE current data."
    echo "Backup source: ${BACKUP_DIR}"
    echo ""
    echo "Components to restore:"
    should_restore postgres && [[ -f "${BACKUP_DIR}/postgres/cortexdb.dump" ]] && echo "  - PostgreSQL (cortexdb)"
    should_restore redis && echo "  - Redis (memory-core, stream-core)"
    should_restore sqlite && [[ -f "${BACKUP_DIR}/sqlite/cortexdb_admin.db" ]] && echo "  - SQLite (superadmin)"
    should_restore qdrant && [[ -d "${BACKUP_DIR}/qdrant" ]] && echo "  - Qdrant (vector collections)"
    echo ""
    read -rp "Proceed with restore? [y/N]: " answer
    case "$answer" in
        [yY][eE][sS]|[yY]) return 0 ;;
        *) log_info "Restore cancelled by user."; exit 0 ;;
    esac
}

# ----------------------------------------------------------
# Service management
# ----------------------------------------------------------
stop_service() {
    local service="$1"
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY RUN] Would stop service: ${service}"
        return 0
    fi
    log_info "Stopping service: ${service}"
    docker compose -f "$COMPOSE_FILE" -p "$COMPOSE_PROJECT" stop "$service" 2>>"$RESTORE_LOG" || {
        log_warn "Could not stop ${service} via docker compose — it may not be running"
    }
}

start_service() {
    local service="$1"
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY RUN] Would start service: ${service}"
        return 0
    fi
    log_info "Starting service: ${service}"
    docker compose -f "$COMPOSE_FILE" -p "$COMPOSE_PROJECT" start "$service" 2>>"$RESTORE_LOG" || {
        log_warn "Could not start ${service} via docker compose"
    }
}

# ----------------------------------------------------------
# Restore functions
# ----------------------------------------------------------
restore_postgres() {
    local dump_file="${BACKUP_DIR}/postgres/cortexdb.dump"
    if [[ ! -f "$dump_file" ]]; then
        log_warn "PostgreSQL dump not found — skipping"
        return
    fi

    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY RUN] Would restore PostgreSQL from: ${dump_file}"
        pg_restore --list "$dump_file" 2>/dev/null | head -20 | tee -a "$RESTORE_LOG"
        log_info "[DRY RUN] (showing first 20 entries of dump TOC)"
        return
    fi

    log_info "Restoring PostgreSQL..."
    export PGPASSWORD="$PG_PASSWORD"

    # Drop and recreate the database
    log_info "Dropping existing database..."
    psql -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" -d postgres \
        -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='${PG_DB}' AND pid <> pg_backend_pid();" \
        2>>"$RESTORE_LOG" || true
    psql -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" -d postgres \
        -c "DROP DATABASE IF EXISTS ${PG_DB};" 2>>"$RESTORE_LOG" || true
    psql -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" -d postgres \
        -c "CREATE DATABASE ${PG_DB} OWNER ${PG_USER};" 2>>"$RESTORE_LOG"

    # Restore roles if available
    if [[ -f "${BACKUP_DIR}/postgres/roles.sql" ]]; then
        log_info "Restoring roles..."
        psql -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" -d postgres \
            -f "${BACKUP_DIR}/postgres/roles.sql" 2>>"$RESTORE_LOG" || true
    fi

    # Restore from custom-format dump
    log_info "Restoring database from dump..."
    if pg_restore \
        -h "$PG_HOST" \
        -p "$PG_PORT" \
        -U "$PG_USER" \
        -d "$PG_DB" \
        --no-owner \
        --no-acl \
        --clean \
        --if-exists \
        "$dump_file" 2>>"$RESTORE_LOG"; then
        log_info "PostgreSQL restore complete."
    else
        # pg_restore returns non-zero for warnings too, check if it's serious
        log_warn "pg_restore exited with warnings — review restore.log for details"
    fi

    # Re-enable Citus extension if needed
    psql -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" -d "$PG_DB" \
        -c "CREATE EXTENSION IF NOT EXISTS citus;" 2>>"$RESTORE_LOG" || true

    unset PGPASSWORD
}

restore_redis_instance() {
    local name="$1"
    local host="$2"
    local port="$3"
    local password="$4"
    local rdb_file="${BACKUP_DIR}/redis/${name}.rdb"

    if [[ ! -f "$rdb_file" ]]; then
        log_warn "Redis ${name} RDB not found — skipping"
        return
    fi

    if [[ "$DRY_RUN" == "true" ]]; then
        local rdb_size
        rdb_size=$(du -sh "$rdb_file" | cut -f1)
        log_info "[DRY RUN] Would restore Redis ${name} from: ${rdb_file} (${rdb_size})"
        return
    fi

    log_info "Restoring Redis ${name}..."

    # Determine the Docker container for this Redis instance
    local container
    case "$name" in
        memory-core) container="cortex-memory" ;;
        stream-core) container="cortex-stream" ;;
        *)           container="" ;;
    esac

    if [[ -n "$container" ]]; then
        # Stop Redis, copy RDB, restart
        log_info "Stopping ${container} for RDB restore..."
        docker stop "$container" 2>>"$RESTORE_LOG" || true

        # Copy RDB into the volume
        docker cp "$rdb_file" "${container}:/data/dump.rdb" 2>>"$RESTORE_LOG" || {
            # Container is stopped, try volume mount
            log_warn "Container stopped, attempting direct volume copy..."
            # Use a temp container to copy into the volume
            local volume_name
            case "$name" in
                memory-core) volume_name="cortex-redis-data" ;;
                stream-core) volume_name="cortex-stream-data" ;;
            esac
            docker run --rm -v "${volume_name}:/data" -v "$(dirname "$rdb_file"):/backup" \
                alpine cp "/backup/$(basename "$rdb_file")" /data/dump.rdb 2>>"$RESTORE_LOG"
        }

        docker start "$container" 2>>"$RESTORE_LOG" || true
        log_info "Redis ${name} restore complete — container restarted."
    else
        log_warn "Unknown Redis instance ${name} — manual restore required"
        EXIT_CODE=1
    fi
}

restore_redis() {
    restore_redis_instance "memory-core" "$REDIS_HOST" "$REDIS_PORT" "$REDIS_PASSWORD"
    restore_redis_instance "stream-core" "$STREAM_HOST" "$STREAM_PORT" "$STREAM_PASSWORD"
}

restore_sqlite() {
    local backup_db="${BACKUP_DIR}/sqlite/cortexdb_admin.db"
    if [[ ! -f "$backup_db" ]]; then
        log_warn "SQLite backup not found — skipping"
        return
    fi

    if [[ "$DRY_RUN" == "true" ]]; then
        local sq_size
        sq_size=$(du -sh "$backup_db" | cut -f1)
        log_info "[DRY RUN] Would restore SQLite from: ${backup_db} (${sq_size})"
        log_info "[DRY RUN] Target: ${SQLITE_DB_PATH}"
        return
    fi

    log_info "Restoring SQLite superadmin database..."

    # Stop cortex-router since it holds the SQLite connection
    stop_service "cortex-router"

    local target_dir
    target_dir=$(dirname "$SQLITE_DB_PATH")
    mkdir -p "$target_dir"

    # Create a backup of the current database before overwriting
    if [[ -f "$SQLITE_DB_PATH" ]]; then
        cp "$SQLITE_DB_PATH" "${SQLITE_DB_PATH}.pre-restore.bak"
        log_info "Current SQLite DB backed up to ${SQLITE_DB_PATH}.pre-restore.bak"
    fi

    cp "$backup_db" "$SQLITE_DB_PATH"
    log_info "SQLite restore complete: ${SQLITE_DB_PATH}"

    start_service "cortex-router"
}

restore_qdrant() {
    local snap_dir="${BACKUP_DIR}/qdrant"
    if [[ ! -d "$snap_dir" ]] || ! ls "${snap_dir}/"* > /dev/null 2>&1; then
        log_warn "Qdrant snapshots not found — skipping"
        return
    fi

    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY RUN] Would restore Qdrant snapshots:"
        ls -lh "${snap_dir}/" | tee -a "$RESTORE_LOG"
        return
    fi

    log_info "Restoring Qdrant vector collections..."

    for snap_file in "${snap_dir}"/*; do
        local filename
        filename=$(basename "$snap_file")

        # Snapshot files are named: {collection}_{snapshot_name}
        # Extract collection name (everything before the last underscore+timestamp pattern)
        local collection
        collection=$(echo "$filename" | sed 's/_[0-9]*-[0-9]*-[0-9]*-[0-9]*-[0-9]*-.*$//')

        if [[ -z "$collection" ]]; then
            log_warn "Could not determine collection name from: ${filename}"
            continue
        fi

        log_info "Restoring Qdrant collection: ${collection} from ${filename}"

        # Upload snapshot to Qdrant
        if curl -sf -X POST "${QDRANT_URL}/collections/${collection}/snapshots/upload" \
            -H "Content-Type: multipart/form-data" \
            -F "snapshot=@${snap_file}" 2>>"$RESTORE_LOG"; then
            log_info "Qdrant collection ${collection} restored."
        else
            log_error "Failed to restore Qdrant collection: ${collection}"
            EXIT_CODE=1
        fi
    done

    log_info "Qdrant restore complete."
}

# ----------------------------------------------------------
# Main
# ----------------------------------------------------------
main() {
    parse_args "$@"

    mkdir -p "$BACKUP_BASE_DIR"
    touch "$RESTORE_LOG"

    log_info "============================================"
    log_info "CortexDB Restore Starting"
    log_info "Source: ${BACKUP_DIR}"
    log_info "Dry run: ${DRY_RUN}"
    log_info "============================================"

    validate_backup
    confirm_restore

    if should_restore postgres; then restore_postgres; fi
    if should_restore redis;    then restore_redis;    fi
    if should_restore sqlite;   then restore_sqlite;   fi
    if should_restore qdrant;   then restore_qdrant;   fi

    if [[ $EXIT_CODE -eq 0 ]]; then
        log_info "Restore completed successfully."
    else
        log_error "Restore completed with errors (exit code ${EXIT_CODE})"
    fi

    log_info "============================================"
    exit $EXIT_CODE
}

main "$@"
