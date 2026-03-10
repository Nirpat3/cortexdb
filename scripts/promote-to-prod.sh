#!/usr/bin/env bash
# ============================================================
# CortexDB — Promote Staging to Production
# (c) 2026 Nirlab Inc. All Rights Reserved.
# ============================================================
#
# This script:
#   1. Validates production .env exists with real secrets
#   2. Checks TLS certificates exist
#   3. Takes a backup of production data
#   4. Builds production images (with prod API URL)
#   5. Stops staging
#   6. Starts production stack
#   7. Runs smoke tests
#   8. Shows rollback instructions if something fails
#
# Usage:
#   ./scripts/promote-to-prod.sh
#   ./scripts/promote-to-prod.sh --skip-backup   # Skip backup step (not recommended)
#   ./scripts/promote-to-prod.sh --dry-run       # Validate only, don't promote
#
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
LOG_DIR="$PROJECT_DIR/logs"
LOG_FILE="$LOG_DIR/promotions.log"
TIMESTAMP="$(date '+%Y-%m-%d %H:%M:%S')"
SKIP_BACKUP=false
DRY_RUN=false

# --- Parse arguments ---
for arg in "$@"; do
  case "$arg" in
    --skip-backup) SKIP_BACKUP=true ;;
    --dry-run)     DRY_RUN=true ;;
    --help|-h)
      echo "Usage: $0 [--skip-backup] [--dry-run] [--help]"
      exit 0
      ;;
    *)
      echo "Unknown argument: $arg"
      exit 1
      ;;
  esac
done

# --- Helper functions ---
log() {
  echo "[$(date '+%H:%M:%S')] $*"
}

log_file() {
  mkdir -p "$LOG_DIR"
  echo "[$TIMESTAMP] $*" >> "$LOG_FILE"
}

fail() {
  log "FAILED: $*"
  log ""
  log "========================================="
  log "  PROMOTION FAILED — ROLLBACK INSTRUCTIONS"
  log "========================================="
  log ""
  log "  To restart staging:"
  log "    cd $PROJECT_DIR"
  log "    docker compose -f docker-compose.yml -f docker-compose.staging.yml --env-file .env.staging up -d"
  log ""
  log "  Or use the rollback script:"
  log "    ./scripts/rollback-to-staging.sh"
  log ""
  log_file "FAILED: $*"
  exit 1
}

# --- Step 0: Pre-flight checks ---
log "============================================"
log "  CortexDB — Promote Staging to Production"
log "============================================"
log ""

cd "$PROJECT_DIR"

# Check production .env exists
if [ ! -f ".env.prod" ] && [ ! -f ".env" ]; then
  fail "No production .env file found. Copy .env.prod.example to .env.prod (or .env) and fill in all values."
fi

# Determine which env file to use for prod
PROD_ENV_FILE=".env"
if [ -f ".env.prod" ]; then
  PROD_ENV_FILE=".env.prod"
fi

log "Using production env file: $PROD_ENV_FILE"

# Validate required production environment variables
REQUIRED_VARS=(
  CORTEX_SECRET_KEY
  CORTEX_ADMIN_TOKEN
  CORTEXDB_MASTER_SECRET
  POSTGRES_PASSWORD
  REDIS_PASSWORD
  STREAM_PASSWORD
  GRAFANA_PASSWORD
)

log "Validating production environment variables..."
# shellcheck disable=SC1090
source "$PROD_ENV_FILE"

# Verify CORTEX_ENV is set to production
if [ "${CORTEX_ENV:-}" != "production" ]; then
  fail "CORTEX_ENV must be 'production' in $PROD_ENV_FILE (found: '${CORTEX_ENV:-unset}')"
fi

for var in "${REQUIRED_VARS[@]}"; do
  if [ -z "${!var:-}" ]; then
    fail "Required variable $var is empty in $PROD_ENV_FILE"
  fi
done
log "  All required variables present."

# Check TLS certificates
log "Checking TLS certificates..."
if [ ! -d "certs" ]; then
  fail "certs/ directory not found. Run: ./scripts/generate-certs.sh --prod"
fi

if [ ! -f "certs/fullchain.pem" ] || [ ! -f "certs/privkey.pem" ]; then
  fail "TLS certificates not found (certs/fullchain.pem, certs/privkey.pem). Run: ./scripts/generate-certs.sh --prod"
fi
log "  TLS certificates found."

# Check Nginx config exists
if [ ! -d "nginx" ]; then
  fail "nginx/ directory not found. Production requires Nginx for TLS termination."
fi

log ""
log "Pre-flight checks PASSED."
log ""

if [ "$DRY_RUN" = true ]; then
  log "DRY RUN — all checks passed. No changes made."
  log_file "DRY RUN — validation passed"
  exit 0
fi

# --- Step 1: Backup ---
if [ "$SKIP_BACKUP" = true ]; then
  log "Skipping backup (--skip-backup flag set)."
else
  log "Taking backup before promotion..."
  if [ -x "$SCRIPT_DIR/backup.sh" ]; then
    "$SCRIPT_DIR/backup.sh" --full || fail "Backup failed. Fix the issue or use --skip-backup to proceed without backup."
    log "  Backup completed."
  else
    log "  WARNING: backup.sh not found or not executable. Skipping backup."
  fi
fi

log ""

# --- Step 2: Build production images ---
log "Building production images..."
docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file "$PROD_ENV_FILE" build \
  || fail "Production image build failed."
log "  Build completed."
log ""

# --- Step 3: Stop staging ---
log "Stopping staging stack..."
STAGING_ENV_FILE=".env.staging"
if [ ! -f "$STAGING_ENV_FILE" ]; then
  STAGING_ENV_FILE=".env"
fi

docker compose -f docker-compose.yml -f docker-compose.staging.yml --env-file "$STAGING_ENV_FILE" down \
  || log "  WARNING: Staging stop returned non-zero (may not have been running)."
log "  Staging stopped."
log ""

# --- Step 4: Start production ---
log "Starting production stack..."
docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file "$PROD_ENV_FILE" up -d \
  || fail "Production stack failed to start."
log "  Production containers started."
log ""

# --- Step 5: Wait for health checks ---
log "Waiting for services to become healthy (timeout: 120s)..."
HEALTH_TIMEOUT=120
HEALTH_START=$(date +%s)

wait_for_health() {
  local service="$1"
  local max_wait="$2"
  local elapsed=0

  while [ $elapsed -lt "$max_wait" ]; do
    local status
    status=$(docker inspect --format='{{.State.Health.Status}}' "$service" 2>/dev/null || echo "missing")
    if [ "$status" = "healthy" ]; then
      return 0
    fi
    sleep 2
    elapsed=$(( $(date +%s) - HEALTH_START ))
  done
  return 1
}

# Check critical services
for svc in cortex-router cortex-relational cortex-memory cortex-stream; do
  log "  Waiting for $svc..."
  if ! wait_for_health "$svc" "$HEALTH_TIMEOUT"; then
    fail "Service $svc did not become healthy within ${HEALTH_TIMEOUT}s."
  fi
  log "    $svc: healthy"
done

log ""

# --- Step 6: Smoke tests ---
log "Running smoke tests..."
SMOKE_PASSED=true

# Test 1: Backend health endpoint
log "  [1/3] Backend health check..."
if curl -sf http://localhost:5401/health/live > /dev/null 2>&1; then
  log "    PASS: Backend health endpoint responding"
elif curl -sf https://localhost/api/health/live --insecure > /dev/null 2>&1; then
  log "    PASS: Backend health via Nginx responding"
else
  log "    FAIL: Backend health endpoint not responding"
  SMOKE_PASSED=false
fi

# Test 2: Nginx HTTPS (production entry point)
log "  [2/3] Nginx HTTPS check..."
if curl -sf https://localhost/ --insecure -o /dev/null 2>&1; then
  log "    PASS: Nginx HTTPS responding"
else
  log "    WARN: Nginx HTTPS not responding (may need DNS or cert setup)"
fi

# Test 3: Dashboard (via Nginx in prod)
log "  [3/3] Dashboard check..."
if curl -sf https://localhost/ --insecure -o /dev/null 2>&1; then
  log "    PASS: Dashboard accessible via Nginx"
elif curl -sf http://localhost:3000/ -o /dev/null 2>&1; then
  log "    PASS: Dashboard responding on direct port"
else
  log "    WARN: Dashboard not responding (may still be starting)"
fi

log ""

if [ "$SMOKE_PASSED" = false ]; then
  log "========================================="
  log "  SMOKE TESTS FAILED"
  log "========================================="
  log ""
  log "  Some critical smoke tests failed."
  log "  To rollback to staging:"
  log "    ./scripts/rollback-to-staging.sh"
  log ""
  log_file "PROMOTION COMPLETED WITH FAILURES — smoke tests failed"
  exit 1
fi

# --- Done ---
log "========================================="
log "  PROMOTION SUCCESSFUL"
log "========================================="
log ""
log "  Production stack is running."
log "  Nginx:     https://localhost (port 443)"
log "  Grafana:   https://localhost/grafana/"
log ""
log "  To rollback if issues are found later:"
log "    ./scripts/rollback-to-staging.sh"
log ""

log_file "PROMOTION SUCCESSFUL — staging -> production"
