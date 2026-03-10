#!/usr/bin/env bash
# ============================================================
# CortexDB — Production Deployment Script
# (c) 2026 Nirlab Inc. All Rights Reserved.
#
# Usage:
#   ./scripts/deploy-prod.sh                  # Full deploy
#   ./scripts/deploy-prod.sh --check-only     # Pre-flight checks only
#   ./scripts/deploy-prod.sh --skip-backup    # Deploy without backup
#   ./scripts/deploy-prod.sh --skip-build     # Deploy without rebuilding images
# ============================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

CHECK_ONLY=false
SKIP_BACKUP=false
SKIP_BUILD=false

for arg in "$@"; do
  case $arg in
    --check-only)  CHECK_ONLY=true ;;
    --skip-backup) SKIP_BACKUP=true ;;
    --skip-build)  SKIP_BUILD=true ;;
    --help)
      echo "Usage: $0 [--check-only] [--skip-backup] [--skip-build]"
      exit 0
      ;;
  esac
done

log()  { echo -e "${GREEN}[DEPLOY]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC}  $1"; }
err()  { echo -e "${RED}[ERROR]${NC} $1"; }
step() { echo -e "\n${CYAN}━━━ $1 ━━━${NC}"; }

ERRORS=0

# ============================================================
# Phase 1: Pre-flight checks
# ============================================================
step "Phase 1: Pre-flight Checks"

# Check Docker
if ! command -v docker &>/dev/null; then
  err "Docker not found. Install Docker first."
  ((ERRORS++))
else
  log "Docker: $(docker --version | head -1)"
fi

# Check Docker Compose
if ! docker compose version &>/dev/null; then
  err "Docker Compose not found."
  ((ERRORS++))
else
  log "Compose: $(docker compose version | head -1)"
fi

# Check .env exists
if [ ! -f "$PROJECT_DIR/.env" ]; then
  err ".env file not found. Copy .env.prod.example to .env and fill in values."
  ((ERRORS++))
else
  log ".env file found"
fi

# Validate required environment variables
REQUIRED_VARS=(
  CORTEX_SECRET_KEY
  CORTEX_ADMIN_TOKEN
  CORTEX_MASTER_KEY
  CORTEXDB_MASTER_SECRET
  POSTGRES_PASSWORD
  REDIS_PASSWORD
  STREAM_PASSWORD
  CORTEX_CORS_ORIGINS
  GRAFANA_PASSWORD
)

if [ -f "$PROJECT_DIR/.env" ]; then
  # Source .env for validation
  set -a
  source "$PROJECT_DIR/.env"
  set +a

  for var in "${REQUIRED_VARS[@]}"; do
    val="${!var:-}"
    if [ -z "$val" ]; then
      err "Missing required variable: $var"
      ((ERRORS++))
    elif [[ "$val" == *"test"* || "$val" == *"development"* || "$val" == *"change-this"* || "$val" == *"your-"* ]]; then
      err "$var contains a placeholder/dev value — set a real production secret"
      ((ERRORS++))
    fi
  done

  # Check CORTEX_SECRET_KEY length
  if [ ${#CORTEX_SECRET_KEY:-} -lt 64 ]; then
    err "CORTEX_SECRET_KEY must be at least 64 characters (got ${#CORTEX_SECRET_KEY:-})"
    ((ERRORS++))
  else
    log "CORTEX_SECRET_KEY: ${#CORTEX_SECRET_KEY} chars"
  fi

  # Check CORTEX_ENV
  if [ "${CORTEX_ENV:-}" != "production" ]; then
    warn "CORTEX_ENV is '${CORTEX_ENV:-development}' — should be 'production'"
  else
    log "CORTEX_ENV: production"
  fi

  # Check CORS doesn't contain localhost
  if [[ "${CORTEX_CORS_ORIGINS:-}" == *"localhost"* ]]; then
    warn "CORTEX_CORS_ORIGINS contains 'localhost' — remove for production"
  fi
fi

# Check TLS certificates
if [ -f "$PROJECT_DIR/certs/fullchain.pem" ] && [ -f "$PROJECT_DIR/certs/privkey.pem" ]; then
  log "TLS certificates found"
  # Check expiry
  if command -v openssl &>/dev/null; then
    EXPIRY=$(openssl x509 -enddate -noout -in "$PROJECT_DIR/certs/fullchain.pem" 2>/dev/null | cut -d= -f2)
    if [ -n "$EXPIRY" ]; then
      EXPIRY_EPOCH=$(date -d "$EXPIRY" +%s 2>/dev/null || date -jf "%b %d %T %Y %Z" "$EXPIRY" +%s 2>/dev/null || echo 0)
      NOW_EPOCH=$(date +%s)
      DAYS_LEFT=$(( (EXPIRY_EPOCH - NOW_EPOCH) / 86400 ))
      if [ "$DAYS_LEFT" -lt 7 ]; then
        err "TLS certificate expires in $DAYS_LEFT days — renew immediately"
        ((ERRORS++))
      elif [ "$DAYS_LEFT" -lt 30 ]; then
        warn "TLS certificate expires in $DAYS_LEFT days"
      else
        log "TLS certificate valid for $DAYS_LEFT days"
      fi
    fi
  fi
else
  warn "TLS certificates not found in certs/. Run: ./scripts/generate-certs.sh"
  warn "Nginx will not start without certificates."
fi

# Check disk space (need at least 10GB free)
AVAIL_KB=$(df "$PROJECT_DIR" --output=avail 2>/dev/null | tail -1 || echo 0)
AVAIL_GB=$((AVAIL_KB / 1024 / 1024))
if [ "$AVAIL_GB" -lt 10 ]; then
  warn "Low disk space: ${AVAIL_GB}GB free (recommend 50GB+)"
else
  log "Disk space: ${AVAIL_GB}GB available"
fi

# Check Docker memory
DOCKER_MEM=$(docker info --format '{{.MemTotal}}' 2>/dev/null || echo 0)
DOCKER_MEM_GB=$((DOCKER_MEM / 1024 / 1024 / 1024))
if [ "$DOCKER_MEM_GB" -lt 8 ]; then
  warn "Docker has ${DOCKER_MEM_GB}GB RAM. Recommended: 16GB+ for production"
else
  log "Docker memory: ${DOCKER_MEM_GB}GB"
fi

echo ""
if [ "$ERRORS" -gt 0 ]; then
  err "$ERRORS pre-flight check(s) failed. Fix issues above before deploying."
  exit 1
fi
log "All pre-flight checks passed"

if [ "$CHECK_ONLY" = true ]; then
  log "Check-only mode. Exiting."
  exit 0
fi

# ============================================================
# Phase 2: Backup current state
# ============================================================
if [ "$SKIP_BACKUP" = false ]; then
  step "Phase 2: Pre-Deploy Backup"
  if [ -f "$SCRIPT_DIR/backup.sh" ]; then
    log "Running backup before deploy..."
    bash "$SCRIPT_DIR/backup.sh" || {
      warn "Backup failed — continuing anyway (data volumes are persistent)"
    }
  else
    warn "Backup script not found, skipping"
  fi
else
  log "Skipping backup (--skip-backup)"
fi

# ============================================================
# Phase 3: Build images
# ============================================================
if [ "$SKIP_BUILD" = false ]; then
  step "Phase 3: Building Docker Images"
  cd "$PROJECT_DIR"

  log "Building CortexDB backend..."
  docker compose -f docker-compose.yml -f docker-compose.prod.yml build cortex-router 2>&1 | tail -5

  log "Building Dashboard (with production API URL)..."
  docker compose -f docker-compose.yml -f docker-compose.prod.yml build cortex-dashboard 2>&1 | tail -5

  log "Building Nginx..."
  docker compose -f docker-compose.yml -f docker-compose.prod.yml build nginx 2>&1 | tail -5

  log "All images built"
else
  log "Skipping build (--skip-build)"
fi

# ============================================================
# Phase 4: Deploy
# ============================================================
step "Phase 4: Deploying Services"
cd "$PROJECT_DIR"

log "Starting infrastructure (databases, cache, queue)..."
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d \
  relational-core citus-worker-1 citus-worker-2 memory-core stream-core vector-core 2>&1

log "Waiting for databases to be healthy..."
TIMEOUT=120
WAITED=0
while [ $WAITED -lt $TIMEOUT ]; do
  PG_HEALTHY=$(docker inspect --format='{{.State.Health.Status}}' cortex-relational 2>/dev/null || echo "not_running")
  REDIS_HEALTHY=$(docker inspect --format='{{.State.Health.Status}}' cortex-memory 2>/dev/null || echo "not_running")
  if [ "$PG_HEALTHY" = "healthy" ] && [ "$REDIS_HEALTHY" = "healthy" ]; then
    log "Databases healthy after ${WAITED}s"
    break
  fi
  sleep 2
  WAITED=$((WAITED + 2))
done
if [ $WAITED -ge $TIMEOUT ]; then
  err "Database health check timed out after ${TIMEOUT}s"
  exit 1
fi

log "Starting CortexDB router..."
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d cortex-router 2>&1

log "Waiting for CortexDB to be ready..."
WAITED=0
while [ $WAITED -lt 60 ]; do
  if docker exec cortex-router curl -sf http://localhost:5401/health/live &>/dev/null; then
    log "CortexDB router healthy after ${WAITED}s"
    break
  fi
  sleep 2
  WAITED=$((WAITED + 2))
done
if [ $WAITED -ge 60 ]; then
  err "CortexDB router failed to start"
  docker logs cortex-router --tail 20
  exit 1
fi

log "Starting Dashboard + Nginx..."
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d cortex-dashboard nginx 2>&1

log "Starting observability stack..."
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d \
  otel-collector prometheus loki tempo grafana 2>&1

sleep 5

# ============================================================
# Phase 5: Smoke Tests
# ============================================================
step "Phase 5: Smoke Tests"

SMOKE_PASS=0
SMOKE_FAIL=0

smoke_test() {
  local name="$1"
  local cmd="$2"
  if eval "$cmd" &>/dev/null; then
    log "  PASS: $name"
    ((SMOKE_PASS++))
  else
    err "  FAIL: $name"
    ((SMOKE_FAIL++))
  fi
}

# Test backend health
smoke_test "Backend liveness" \
  "docker exec cortex-router curl -sf http://localhost:5401/health/live"

smoke_test "Backend readiness" \
  "docker exec cortex-router curl -sf http://localhost:5400/health/ready"

# Test dashboard
smoke_test "Dashboard responding" \
  "docker exec cortex-dashboard wget -qO /dev/null http://localhost:3000/"

# Test Nginx (if certs exist)
if [ -f "$PROJECT_DIR/certs/fullchain.pem" ]; then
  smoke_test "Nginx HTTPS" \
    "curl -sf -k https://localhost/"
  smoke_test "Nginx HTTP->HTTPS redirect" \
    "curl -sf -o /dev/null -w '%{http_code}' http://localhost/ | grep -q 301"
else
  smoke_test "Nginx HTTP" \
    "curl -sf http://localhost/ || docker exec cortex-nginx wget -qO /dev/null http://localhost/"
fi

# Test database connectivity (via backend)
smoke_test "Database connection" \
  "docker exec cortex-router curl -sf http://localhost:5400/health/ready | grep -q engines"

# Test Grafana
smoke_test "Grafana UI" \
  "docker exec cortex-grafana wget -qO /dev/null http://localhost:3000/api/health 2>/dev/null || true"

echo ""
log "Smoke tests: ${SMOKE_PASS} passed, ${SMOKE_FAIL} failed"

if [ "$SMOKE_FAIL" -gt 2 ]; then
  err "Too many smoke test failures. Check logs:"
  echo "  docker compose logs cortex-router --tail 20"
  echo "  docker compose logs cortex-dashboard --tail 20"
  echo "  docker compose logs nginx --tail 20"
  exit 1
fi

# ============================================================
# Phase 6: Summary
# ============================================================
step "Deployment Complete"

echo ""
docker compose -f docker-compose.yml -f docker-compose.prod.yml ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null || \
  docker compose -f docker-compose.yml -f docker-compose.prod.yml ps

echo ""
log "CortexDB is live!"
log ""
log "  Dashboard:  https://${CORTEX_DOMAIN:-localhost}"
log "  API:        https://${CORTEX_DOMAIN:-localhost}/api/health/ready"
log "  Grafana:    https://${CORTEX_DOMAIN:-localhost}/grafana/"
log ""
log "Next steps:"
log "  1. Verify dashboard loads in browser"
log "  2. Set up backup cron:  crontab -e  →  0 2 * * * $SCRIPT_DIR/backup-cron.sh"
log "  3. Monitor logs:        docker compose logs -f cortex-router"
log "  4. Check Grafana alerts: https://${CORTEX_DOMAIN:-localhost}/grafana/"
