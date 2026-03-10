#!/usr/bin/env bash
# ============================================================
# CortexDB - Secrets Rotation Script
# Rotates all secrets atomically and restarts affected services.
# (c) 2026 Nirlab Inc. All Rights Reserved.
# ============================================================
#
# Usage:
#   ./scripts/secrets-rotate.sh                  # Rotate all secrets
#   ./scripts/secrets-rotate.sh --dry-run        # Preview changes only
#   ./scripts/secrets-rotate.sh --key-only       # Rotate CORTEX_SECRET_KEY only
#   ./scripts/secrets-rotate.sh --db-only        # Rotate database passwords only
#
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="$PROJECT_DIR/.env"
ENV_BACKUP="$PROJECT_DIR/.env.previous"
LOG_FILE="$PROJECT_DIR/logs/secrets-rotation.log"

DRY_RUN=false
ROTATE_KEYS=true
ROTATE_DB=true
ROTATE_ADMIN=true

# Colors
if [ -t 1 ]; then
    RED='\033[0;31m'
    GREEN='\033[0;32m'
    YELLOW='\033[1;33m'
    NC='\033[0m'
else
    RED='' GREEN='' YELLOW='' NC=''
fi

log_info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }

log_event() {
    local msg="$1"
    mkdir -p "$(dirname "$LOG_FILE")"
    echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] $msg" >> "$LOG_FILE"
}

usage() {
    cat <<'USAGE'
CortexDB Secrets Rotation

Usage:
  secrets-rotate.sh [OPTIONS]

Options:
  --dry-run       Preview changes without applying them
  --key-only      Rotate only CORTEX_SECRET_KEY and CORTEX_ADMIN_TOKEN
  --db-only       Rotate only database passwords (PostgreSQL, Redis)
  -h, --help      Show this help message

Rotated secrets:
  - CORTEX_SECRET_KEY      (64-char hex)
  - CORTEX_ADMIN_TOKEN     (48-char hex)
  - CORTEXDB_MASTER_SECRET (64-char hex)
  - POSTGRES_PASSWORD      (32-char alphanumeric)
  - REDIS_PASSWORD         (32-char alphanumeric)
  - STREAM_PASSWORD        (32-char alphanumeric)
  - GRAFANA_PASSWORD       (24-char alphanumeric)
USAGE
    exit 0
}

# -----------------------------------------------------------
# Parse arguments
# -----------------------------------------------------------
while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run)   DRY_RUN=true; shift ;;
        --key-only)  ROTATE_DB=false; shift ;;
        --db-only)   ROTATE_KEYS=false; ROTATE_ADMIN=false; shift ;;
        -h|--help)   usage ;;
        *)           log_error "Unknown option: $1"; usage ;;
    esac
done

# -----------------------------------------------------------
# Prerequisite checks
# -----------------------------------------------------------
if [[ ! -f "$ENV_FILE" ]]; then
    log_error ".env file not found at $ENV_FILE"
    log_error "Create one from .env.example first."
    exit 1
fi

if ! command -v openssl &>/dev/null; then
    log_error "openssl is required but not found."
    exit 1
fi

# -----------------------------------------------------------
# Secret generation helpers
# -----------------------------------------------------------
generate_hex() {
    local length="${1:-64}"
    openssl rand -hex "$((length / 2))"
}

generate_alnum() {
    local length="${1:-32}"
    openssl rand -base64 "$((length * 2))" | tr -dc 'a-zA-Z0-9' | head -c "$length"
}

# -----------------------------------------------------------
# Update a single key in a file
# Returns 0 if the key existed and was updated, 1 if appended
# -----------------------------------------------------------
update_env_var() {
    local file="$1"
    local key="$2"
    local value="$3"

    if grep -q "^${key}=" "$file" 2>/dev/null; then
        # Use a temp file for atomic replacement (portable across sed versions)
        local tmpfile
        tmpfile=$(mktemp)
        while IFS= read -r line; do
            if [[ "$line" == "${key}="* ]]; then
                echo "${key}=${value}"
            else
                echo "$line"
            fi
        done < "$file" > "$tmpfile"
        mv "$tmpfile" "$file"
        return 0
    else
        echo "${key}=${value}" >> "$file"
        return 1
    fi
}

# -----------------------------------------------------------
# Main rotation logic
# -----------------------------------------------------------
main() {
    log_info "CortexDB Secrets Rotation"
    log_info "========================="

    if $DRY_RUN; then
        log_warn "DRY RUN MODE -- no changes will be applied"
        echo ""
    fi

    # Collect new secrets
    declare -A new_secrets

    if $ROTATE_KEYS; then
        new_secrets[CORTEX_SECRET_KEY]="$(generate_hex 64)"
        new_secrets[CORTEXDB_MASTER_SECRET]="$(generate_hex 64)"
        log_info "Generated new CORTEX_SECRET_KEY (64 hex chars)"
        log_info "Generated new CORTEXDB_MASTER_SECRET (64 hex chars)"
    fi

    if $ROTATE_ADMIN; then
        new_secrets[CORTEX_ADMIN_TOKEN]="$(generate_hex 48)"
        log_info "Generated new CORTEX_ADMIN_TOKEN (48 hex chars)"
    fi

    if $ROTATE_DB; then
        new_secrets[POSTGRES_PASSWORD]="$(generate_alnum 32)"
        new_secrets[REDIS_PASSWORD]="$(generate_alnum 32)"
        new_secrets[STREAM_PASSWORD]="$(generate_alnum 32)"
        new_secrets[GRAFANA_PASSWORD]="$(generate_alnum 24)"
        log_info "Generated new POSTGRES_PASSWORD (32 alnum chars)"
        log_info "Generated new REDIS_PASSWORD (32 alnum chars)"
        log_info "Generated new STREAM_PASSWORD (32 alnum chars)"
        log_info "Generated new GRAFANA_PASSWORD (24 alnum chars)"
    fi

    echo ""

    if $DRY_RUN; then
        log_info "Secrets that would be rotated:"
        for key in "${!new_secrets[@]}"; do
            local preview="${new_secrets[$key]}"
            # Show only first/last 4 chars
            echo "  $key = ${preview:0:4}...${preview: -4}"
        done
        echo ""
        log_info "Dry run complete. No changes were made."
        return 0
    fi

    # Backup current .env
    log_info "Backing up current .env to .env.previous"
    cp "$ENV_FILE" "$ENV_BACKUP"
    chmod 600 "$ENV_BACKUP"
    log_event "Backup created: $ENV_BACKUP"

    # Create a working copy for atomic update
    local tmpenv
    tmpenv=$(mktemp)
    cp "$ENV_FILE" "$tmpenv"

    # Apply all new secrets to the temp file
    for key in "${!new_secrets[@]}"; do
        update_env_var "$tmpenv" "$key" "${new_secrets[$key]}"
        log_event "Rotated: $key"
    done

    # Atomic replacement
    mv "$tmpenv" "$ENV_FILE"
    chmod 600 "$ENV_FILE"

    log_info "All secrets updated in .env"
    log_event "Rotation complete. Secrets rotated: ${!new_secrets[*]}"
    echo ""

    # Determine which services need restart
    local services_to_restart=()

    if $ROTATE_KEYS || $ROTATE_ADMIN; then
        services_to_restart+=(cortex-router)
    fi

    if $ROTATE_DB; then
        services_to_restart+=(
            relational-core
            citus-worker-1
            citus-worker-2
            memory-core
            stream-core
            cortex-router
        )
    fi

    # Deduplicate
    local unique_services
    unique_services=($(printf '%s\n' "${services_to_restart[@]}" | sort -u))

    if [[ ${#unique_services[@]} -gt 0 ]]; then
        log_warn "The following services need to be restarted for new secrets to take effect:"
        for svc in "${unique_services[@]}"; do
            echo "  - $svc"
        done
        echo ""
        read -rp "Restart these services now? [y/N] " confirm
        if [[ "$confirm" =~ ^[Yy]$ ]]; then
            log_info "Restarting services..."
            cd "$PROJECT_DIR"

            for svc in "${unique_services[@]}"; do
                log_info "Restarting $svc..."
                docker compose restart "$svc" 2>/dev/null || \
                    docker-compose restart "$svc" 2>/dev/null || \
                    log_warn "Failed to restart $svc (is Docker running?)"
                log_event "Restarted service: $svc"
            done

            log_info "All services restarted."
            log_event "Service restarts complete"
        else
            log_info "Skipping restart. Remember to restart services manually."
            log_info "Run: docker compose restart ${unique_services[*]}"
        fi
    fi

    echo ""
    log_info "Rotation complete."
    log_info "Previous secrets saved to: $ENV_BACKUP"
    log_info "Rotation log: $LOG_FILE"
    log_warn "To rollback: cp .env.previous .env && docker compose restart"
}

main
