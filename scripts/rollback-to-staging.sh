#!/usr/bin/env bash
# ============================================================
# CortexDB — Rollback from Production to Staging
# (c) 2026 Nirlab Inc. All Rights Reserved.
# ============================================================
#
# Emergency rollback script. Stops the production stack and
# restarts the staging environment.
#
# Usage:
#   ./scripts/rollback-to-staging.sh
#
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
LOG_DIR="$PROJECT_DIR/logs"
LOG_FILE="$LOG_DIR/promotions.log"
TIMESTAMP="$(date '+%Y-%m-%d %H:%M:%S')"

log() {
  echo "[$(date '+%H:%M:%S')] $*"
}

log_file() {
  mkdir -p "$LOG_DIR"
  echo "[$TIMESTAMP] $*" >> "$LOG_FILE"
}

cd "$PROJECT_DIR"

log "============================================"
log "  CortexDB — Rollback to Staging"
log "============================================"
log ""

# --- Determine env files ---
PROD_ENV_FILE=".env"
if [ -f ".env.prod" ]; then
  PROD_ENV_FILE=".env.prod"
fi

STAGING_ENV_FILE=".env.staging"
if [ ! -f "$STAGING_ENV_FILE" ]; then
  log "WARNING: .env.staging not found. Falling back to .env"
  STAGING_ENV_FILE=".env"
fi

# --- Step 1: Stop production ---
log "Stopping production stack..."
docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file "$PROD_ENV_FILE" down \
  || log "  WARNING: Production stop returned non-zero (may not have been running)."
log "  Production stopped."
log ""

# --- Step 2: Start staging ---
log "Starting staging stack..."
docker compose -f docker-compose.yml -f docker-compose.staging.yml --env-file "$STAGING_ENV_FILE" up -d \
  || { log "FAILED: Could not start staging stack."; log_file "ROLLBACK FAILED"; exit 1; }
log "  Staging containers started."
log ""

# --- Step 3: Wait for health ---
log "Waiting for core services (timeout: 90s)..."
HEALTH_START=$(date +%s)
HEALTH_TIMEOUT=90

wait_for_health() {
  local service="$1"
  local max_wait="$2"

  while true; do
    local elapsed=$(( $(date +%s) - HEALTH_START ))
    if [ $elapsed -ge "$max_wait" ]; then
      return 1
    fi
    local status
    status=$(docker inspect --format='{{.State.Health.Status}}' "$service" 2>/dev/null || echo "missing")
    if [ "$status" = "healthy" ]; then
      return 0
    fi
    sleep 2
  done
}

for svc in cortex-router cortex-relational cortex-memory; do
  log "  Waiting for $svc..."
  if wait_for_health "$svc" "$HEALTH_TIMEOUT"; then
    log "    $svc: healthy"
  else
    log "    $svc: NOT healthy (may need manual intervention)"
  fi
done

log ""

# --- Status ---
log "============================================"
log "  ROLLBACK COMPLETE"
log "============================================"
log ""
log "  Staging is now running."
log "  API:       http://localhost:5400"
log "  Dashboard: http://localhost:3400"
log "  Grafana:   http://localhost:3001"
log "  Postgres:  localhost:5432 (for debugging)"
log ""
log "  To check service status:"
log "    docker compose -f docker-compose.yml -f docker-compose.staging.yml ps"
log ""

log_file "ROLLBACK COMPLETE — production -> staging"
