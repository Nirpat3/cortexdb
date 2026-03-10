#!/usr/bin/env bash
# ============================================================
# CortexDB Backup Script
# Backs up PostgreSQL (Citus), Redis, SQLite, and Qdrant
# ============================================================
set -euo pipefail

# ----------------------------------------------------------
# Configuration (override via environment variables)
# ----------------------------------------------------------
BACKUP_BASE_DIR="${BACKUP_BASE_DIR:-/data/backups}"
BACKUP_RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-30}"
BACKUP_LOG="${BACKUP_BASE_DIR}/backup.log"

# PostgreSQL
PG_HOST="${PG_HOST:-relational-core}"
PG_PORT="${PG_PORT:-5432}"
PG_USER="${PG_USER:-cortex}"
PG_PASSWORD="${PG_PASSWORD:-${POSTGRES_PASSWORD:-cortex_secret}}"
PG_DB="${PG_DB:-cortexdb}"

# Redis — memory-core (cache/sessions)
REDIS_HOST="${REDIS_HOST:-memory-core}"
REDIS_PORT="${REDIS_PORT:-6379}"
REDIS_PASSWORD="${REDIS_PASSWORD:-cortex_redis_secret}"

# Redis — stream-core (event streams)
STREAM_HOST="${STREAM_HOST:-stream-core}"
STREAM_PORT="${STREAM_PORT:-6380}"
STREAM_PASSWORD="${STREAM_PASSWORD:-cortex_stream_secret}"

# SQLite superadmin
SQLITE_DB_PATH="${SQLITE_DB_PATH:-/data/superadmin/cortexdb_admin.db}"

# Qdrant vector DB
QDRANT_URL="${QDRANT_URL:-http://vector-core:6333}"

# ----------------------------------------------------------
# Globals
# ----------------------------------------------------------
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP_DIR="${BACKUP_BASE_DIR}/${TIMESTAMP}"
EXIT_CODE=0
COMPONENTS_REQUESTED=()

# ----------------------------------------------------------
# Logging
# ----------------------------------------------------------
log() {
    local level="$1"; shift
    local msg="[$(date '+%Y-%m-%d %H:%M:%S')] [${level}] $*"
    echo "$msg" | tee -a "$BACKUP_LOG"
}

log_info()  { log "INFO"  "$@"; }
log_warn()  { log "WARN"  "$@"; }
log_error() { log "ERROR" "$@"; }

# ----------------------------------------------------------
# Usage
# ----------------------------------------------------------
usage() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Backup CortexDB databases to a timestamped directory.

Options:
  --full        Back up all databases (default if no flags given)
  --postgres    Back up PostgreSQL (Citus) only
  --redis       Back up Redis (memory-core + stream-core) only
  --sqlite      Back up SQLite superadmin database only
  --qdrant      Back up Qdrant vector snapshots only
  --no-rotate   Skip old backup rotation
  --help        Show this help message

Environment variables:
  BACKUP_BASE_DIR         Base directory for backups (default: /data/backups)
  BACKUP_RETENTION_DAYS   Days to keep old backups (default: 30)
  PG_HOST, PG_PORT, PG_USER, PG_PASSWORD, PG_DB
  REDIS_HOST, REDIS_PORT, REDIS_PASSWORD
  STREAM_HOST, STREAM_PORT, STREAM_PASSWORD
  SQLITE_DB_PATH          Path to superadmin SQLite DB
  QDRANT_URL              Qdrant HTTP API base URL
EOF
    exit 0
}

# ----------------------------------------------------------
# Parse arguments
# ----------------------------------------------------------
DO_ROTATE=true
DO_FULL=false

parse_args() {
    if [[ $# -eq 0 ]]; then
        DO_FULL=true
        return
    fi

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --full)      DO_FULL=true ;;
            --postgres)  COMPONENTS_REQUESTED+=("postgres") ;;
            --redis)     COMPONENTS_REQUESTED+=("redis") ;;
            --sqlite)    COMPONENTS_REQUESTED+=("sqlite") ;;
            --qdrant)    COMPONENTS_REQUESTED+=("qdrant") ;;
            --no-rotate) DO_ROTATE=false ;;
            --help)      usage ;;
            *)           log_error "Unknown option: $1"; usage ;;
        esac
        shift
    done

    if [[ ${#COMPONENTS_REQUESTED[@]} -eq 0 ]]; then
        DO_FULL=true
    fi
}

should_backup() {
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
# Backup functions
# ----------------------------------------------------------
backup_postgres() {
    log_info "Starting PostgreSQL backup..."
    local dump_file="${BACKUP_DIR}/postgres/cortexdb.dump"
    mkdir -p "${BACKUP_DIR}/postgres"

    export PGPASSWORD="$PG_PASSWORD"
    if pg_dump \
        -h "$PG_HOST" \
        -p "$PG_PORT" \
        -U "$PG_USER" \
        -d "$PG_DB" \
        -Fc \
        -Z 6 \
        --no-owner \
        --no-acl \
        -f "$dump_file" 2>>"$BACKUP_LOG"; then
        local size
        size=$(du -sh "$dump_file" | cut -f1)
        log_info "PostgreSQL backup complete: ${dump_file} (${size})"

        # Also dump Citus metadata for disaster recovery
        pg_dumpall \
            -h "$PG_HOST" \
            -p "$PG_PORT" \
            -U "$PG_USER" \
            --roles-only \
            -f "${BACKUP_DIR}/postgres/roles.sql" 2>>"$BACKUP_LOG" || true
        log_info "PostgreSQL roles dump saved."
    else
        log_error "PostgreSQL backup FAILED"
        EXIT_CODE=1
    fi
    unset PGPASSWORD
}

backup_redis_instance() {
    local name="$1"
    local host="$2"
    local port="$3"
    local password="$4"
    local dest_dir="${BACKUP_DIR}/redis"
    mkdir -p "$dest_dir"

    log_info "Starting Redis backup for ${name} (${host}:${port})..."

    # Trigger BGSAVE
    if redis-cli -h "$host" -p "$port" -a "$password" --no-auth-warning BGSAVE 2>>"$BACKUP_LOG"; then
        # Wait for background save to finish (max 60 seconds)
        local waited=0
        while [[ $waited -lt 60 ]]; do
            local status
            status=$(redis-cli -h "$host" -p "$port" -a "$password" --no-auth-warning LASTSAVE 2>/dev/null)
            sleep 2
            local status2
            status2=$(redis-cli -h "$host" -p "$port" -a "$password" --no-auth-warning LASTSAVE 2>/dev/null)
            if [[ "$status" != "$status2" ]] || [[ $waited -ge 4 ]]; then
                break
            fi
            waited=$((waited + 2))
        done

        # Copy RDB file. Redis in Docker typically stores at /data/dump.rdb
        # We use redis-cli --rdb to download the file directly
        if redis-cli -h "$host" -p "$port" -a "$password" --no-auth-warning \
            --rdb "${dest_dir}/${name}.rdb" 2>>"$BACKUP_LOG"; then
            local size
            size=$(du -sh "${dest_dir}/${name}.rdb" | cut -f1)
            log_info "Redis ${name} backup complete: ${dest_dir}/${name}.rdb (${size})"
        else
            log_warn "redis-cli --rdb failed for ${name}, attempting BGSAVE copy fallback"
            # Fallback: try to copy from mounted volume
            if [[ -f "/data/redis-${name}/dump.rdb" ]]; then
                cp "/data/redis-${name}/dump.rdb" "${dest_dir}/${name}.rdb"
                log_info "Redis ${name} backup via file copy complete."
            else
                log_error "Redis ${name} backup FAILED — could not retrieve RDB"
                EXIT_CODE=1
            fi
        fi
    else
        log_error "Redis ${name} BGSAVE command failed"
        EXIT_CODE=1
    fi
}

backup_redis() {
    backup_redis_instance "memory-core" "$REDIS_HOST" "$REDIS_PORT" "$REDIS_PASSWORD"
    backup_redis_instance "stream-core" "$STREAM_HOST" "$STREAM_PORT" "$STREAM_PASSWORD"
}

backup_sqlite() {
    log_info "Starting SQLite backup..."
    local dest_dir="${BACKUP_DIR}/sqlite"
    mkdir -p "$dest_dir"

    if [[ ! -f "$SQLITE_DB_PATH" ]]; then
        log_warn "SQLite database not found at ${SQLITE_DB_PATH} — skipping"
        return
    fi

    # Use SQLite .backup command for a consistent online backup
    if sqlite3 "$SQLITE_DB_PATH" ".backup '${dest_dir}/cortexdb_admin.db'" 2>>"$BACKUP_LOG"; then
        local size
        size=$(du -sh "${dest_dir}/cortexdb_admin.db" | cut -f1)
        log_info "SQLite backup complete: ${dest_dir}/cortexdb_admin.db (${size})"

        # Also dump as SQL for portability
        sqlite3 "$SQLITE_DB_PATH" ".dump" > "${dest_dir}/cortexdb_admin.sql" 2>>"$BACKUP_LOG" || true
        log_info "SQLite SQL dump saved."
    else
        log_error "SQLite backup FAILED"
        EXIT_CODE=1
    fi
}

backup_qdrant() {
    log_info "Starting Qdrant vector backup..."
    local dest_dir="${BACKUP_DIR}/qdrant"
    mkdir -p "$dest_dir"

    # List all collections
    local collections_json
    collections_json=$(curl -sf "${QDRANT_URL}/collections" 2>>"$BACKUP_LOG") || {
        log_error "Qdrant backup FAILED — could not list collections"
        EXIT_CODE=1
        return
    }

    # Parse collection names (requires jq)
    local collections
    collections=$(echo "$collections_json" | jq -r '.result.collections[].name' 2>/dev/null) || {
        log_error "Qdrant backup FAILED — could not parse collections (is jq installed?)"
        EXIT_CODE=1
        return
    }

    if [[ -z "$collections" ]]; then
        log_info "Qdrant has no collections — nothing to back up"
        return
    fi

    for collection in $collections; do
        log_info "Creating snapshot for Qdrant collection: ${collection}"

        # Create snapshot
        local snap_response
        snap_response=$(curl -sf -X POST "${QDRANT_URL}/collections/${collection}/snapshots" 2>>"$BACKUP_LOG") || {
            log_error "Failed to create snapshot for collection: ${collection}"
            EXIT_CODE=1
            continue
        }

        local snap_name
        snap_name=$(echo "$snap_response" | jq -r '.result.name' 2>/dev/null)

        if [[ -z "$snap_name" || "$snap_name" == "null" ]]; then
            log_error "Could not get snapshot name for collection: ${collection}"
            EXIT_CODE=1
            continue
        fi

        # Download snapshot
        if curl -sf -o "${dest_dir}/${collection}_${snap_name}" \
            "${QDRANT_URL}/collections/${collection}/snapshots/${snap_name}" 2>>"$BACKUP_LOG"; then
            local size
            size=$(du -sh "${dest_dir}/${collection}_${snap_name}" | cut -f1)
            log_info "Qdrant snapshot for ${collection}: ${snap_name} (${size})"
        else
            log_error "Failed to download Qdrant snapshot: ${collection}/${snap_name}"
            EXIT_CODE=1
        fi

        # Clean up remote snapshot to save space
        curl -sf -X DELETE "${QDRANT_URL}/collections/${collection}/snapshots/${snap_name}" \
            2>>"$BACKUP_LOG" || true
    done

    log_info "Qdrant backup complete."
}

# ----------------------------------------------------------
# Rotation
# ----------------------------------------------------------
rotate_old_backups() {
    log_info "Rotating backups older than ${BACKUP_RETENTION_DAYS} days..."
    local count=0
    while IFS= read -r -d '' dir; do
        log_info "Removing old backup: ${dir}"
        rm -rf "$dir"
        count=$((count + 1))
    done < <(find "$BACKUP_BASE_DIR" -maxdepth 1 -mindepth 1 -type d \
        -mtime "+${BACKUP_RETENTION_DAYS}" -print0 2>/dev/null)
    log_info "Rotation complete. Removed ${count} old backup(s)."
}

# ----------------------------------------------------------
# Manifest
# ----------------------------------------------------------
write_manifest() {
    local manifest="${BACKUP_DIR}/manifest.json"
    local end_time
    end_time=$(date -u +%Y-%m-%dT%H:%M:%SZ)

    cat > "$manifest" <<MANIFEST
{
  "version": "1.0",
  "timestamp": "${TIMESTAMP}",
  "completed_at": "${end_time}",
  "exit_code": ${EXIT_CODE},
  "components": {
    "postgres": $(should_backup postgres && [[ -f "${BACKUP_DIR}/postgres/cortexdb.dump" ]] && echo true || echo false),
    "redis_memory": $(should_backup redis && [[ -f "${BACKUP_DIR}/redis/memory-core.rdb" ]] && echo true || echo false),
    "redis_stream": $(should_backup redis && [[ -f "${BACKUP_DIR}/redis/stream-core.rdb" ]] && echo true || echo false),
    "sqlite": $(should_backup sqlite && [[ -f "${BACKUP_DIR}/sqlite/cortexdb_admin.db" ]] && echo true || echo false),
    "qdrant": $(should_backup qdrant && [[ -d "${BACKUP_DIR}/qdrant" ]] && echo true || echo false)
  },
  "retention_days": ${BACKUP_RETENTION_DAYS}
}
MANIFEST
    log_info "Manifest written: ${manifest}"
}

# ----------------------------------------------------------
# Main
# ----------------------------------------------------------
main() {
    parse_args "$@"

    # Ensure base directory and log file exist
    mkdir -p "$BACKUP_BASE_DIR"
    touch "$BACKUP_LOG"

    log_info "============================================"
    log_info "CortexDB Backup Starting"
    log_info "Backup directory: ${BACKUP_DIR}"
    log_info "============================================"

    mkdir -p "$BACKUP_DIR"

    if should_backup postgres; then backup_postgres; fi
    if should_backup redis;    then backup_redis;    fi
    if should_backup sqlite;   then backup_sqlite;   fi
    if should_backup qdrant;   then backup_qdrant;   fi

    write_manifest

    if [[ "$DO_ROTATE" == "true" ]]; then
        rotate_old_backups
    fi

    if [[ $EXIT_CODE -eq 0 ]]; then
        log_info "Backup completed successfully: ${BACKUP_DIR}"
    else
        log_error "Backup completed with errors (exit code ${EXIT_CODE})"
    fi

    log_info "============================================"
    exit $EXIT_CODE
}

main "$@"
