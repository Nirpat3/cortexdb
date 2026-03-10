#!/usr/bin/env bash
# ============================================================
# CortexDB Installer
# One-command setup for CortexDB and the admin dashboard.
#
# Usage:
#   ./install.sh            # Full install (Docker + dashboard build)
#   ./install.sh --dev      # Full install + start dashboard in dev mode
#   ./install.sh --no-docker # Dashboard only (skip Docker services)
#
# Safe to run multiple times (idempotent).
# (c) 2026 Nirlab Inc. All Rights Reserved.
# ============================================================
set -e

# ------------------------------------------------------------------
# Flags
# ------------------------------------------------------------------
DEV_MODE=false
NO_DOCKER=false

for arg in "$@"; do
  case "$arg" in
    --dev)       DEV_MODE=true ;;
    --no-docker) NO_DOCKER=true ;;
    --help|-h)
      echo "Usage: ./install.sh [--dev] [--no-docker]"
      echo ""
      echo "  --dev        Start the dashboard in dev mode after install"
      echo "  --no-docker  Skip Docker services (dashboard only)"
      echo ""
      exit 0
      ;;
    *)
      echo "Unknown flag: $arg (try --help)"
      exit 1
      ;;
  esac
done

# ------------------------------------------------------------------
# Color helpers
# ------------------------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

info()    { echo -e "${BLUE}[INFO]${NC}  $1"; }
success() { echo -e "${GREEN}[OK]${NC}    $1"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $1"; }
error()   { echo -e "${RED}[ERROR]${NC} $1"; }
step()    { echo -e "\n${CYAN}${BOLD}==>${NC} ${BOLD}$1${NC}"; }

# ------------------------------------------------------------------
# Resolve project root (directory containing this script)
# ------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo ""
echo -e "${BOLD}CortexDB Installer${NC}"
echo "=============================================="
echo ""

# ------------------------------------------------------------------
# 1. Check prerequisites
# ------------------------------------------------------------------
step "Checking prerequisites"

MISSING=0

# Docker (only required when not --no-docker)
if [ "$NO_DOCKER" = false ]; then
  if command -v docker &>/dev/null; then
    DOCKER_VER=$(docker --version | head -1)
    success "Docker: $DOCKER_VER"
  else
    error "Docker is not installed. Install from https://docs.docker.com/get-docker/"
    MISSING=1
  fi

  # Docker Compose (v2 plugin or standalone)
  if docker compose version &>/dev/null 2>&1; then
    COMPOSE_VER=$(docker compose version --short 2>/dev/null || docker compose version)
    success "Docker Compose: $COMPOSE_VER"
  elif command -v docker-compose &>/dev/null; then
    COMPOSE_VER=$(docker-compose --version | head -1)
    success "Docker Compose (standalone): $COMPOSE_VER"
  else
    error "Docker Compose is not installed. Install from https://docs.docker.com/compose/install/"
    MISSING=1
  fi
fi

# Node.js 18+
if command -v node &>/dev/null; then
  NODE_VER=$(node -v | sed 's/v//')
  NODE_MAJOR=$(echo "$NODE_VER" | cut -d. -f1)
  if [ "$NODE_MAJOR" -ge 18 ]; then
    success "Node.js: v$NODE_VER"
  else
    error "Node.js v$NODE_VER found, but v18+ is required."
    MISSING=1
  fi
else
  error "Node.js is not installed. Install v18+ from https://nodejs.org/"
  MISSING=1
fi

# Python 3.12+ (optional but recommended)
if command -v python3 &>/dev/null; then
  PY_VER=$(python3 --version 2>&1 | awk '{print $2}')
  PY_MAJOR=$(echo "$PY_VER" | cut -d. -f1)
  PY_MINOR=$(echo "$PY_VER" | cut -d. -f2)
  if [ "$PY_MAJOR" -ge 3 ] && [ "$PY_MINOR" -ge 12 ]; then
    success "Python: v$PY_VER"
  else
    warn "Python v$PY_VER found, but v3.12+ is recommended for local development."
  fi
elif command -v python &>/dev/null; then
  PY_VER=$(python --version 2>&1 | awk '{print $2}')
  PY_MAJOR=$(echo "$PY_VER" | cut -d. -f1)
  PY_MINOR=$(echo "$PY_VER" | cut -d. -f2)
  if [ "$PY_MAJOR" -ge 3 ] && [ "$PY_MINOR" -ge 12 ]; then
    success "Python: v$PY_VER"
  else
    warn "Python v$PY_VER found, but v3.12+ is recommended for local development."
  fi
else
  warn "Python not found. Optional for local development; Docker handles it otherwise."
fi

if [ "$MISSING" -eq 1 ]; then
  error "Missing required prerequisites. Install them and re-run this script."
  exit 1
fi

# ------------------------------------------------------------------
# 2. Set up .env
# ------------------------------------------------------------------
step "Configuring environment"

if [ ! -f .env ]; then
  if [ -f .env.example ]; then
    cp .env.example .env
    success "Created .env from .env.example"
  else
    error ".env.example not found. Cannot create .env."
    exit 1
  fi
else
  success ".env already exists (keeping existing)"
fi

# Generate CORTEX_SECRET_KEY if it contains a placeholder
generate_secret() {
  # 64-character hex string
  if command -v openssl &>/dev/null; then
    openssl rand -hex 32
  elif command -v python3 &>/dev/null; then
    python3 -c "import secrets; print(secrets.token_hex(32))"
  else
    # Fallback: /dev/urandom
    head -c 32 /dev/urandom | xxd -p | tr -d '\n' | head -c 64
  fi
}

# Replace placeholder secret key
CURRENT_SECRET=$(grep '^CORTEX_SECRET_KEY=' .env | cut -d'=' -f2-)
if echo "$CURRENT_SECRET" | grep -qi 'your-\|change-this\|placeholder\|example\|here'; then
  NEW_SECRET=$(generate_secret)
  sed -i "s|^CORTEX_SECRET_KEY=.*|CORTEX_SECRET_KEY=$NEW_SECRET|" .env
  success "Generated random CORTEX_SECRET_KEY"
fi

# Generate or add CORTEX_ADMIN_TOKEN if missing/placeholder
CURRENT_ADMIN_TOKEN=$(grep '^CORTEX_ADMIN_TOKEN=' .env 2>/dev/null | cut -d'=' -f2- || echo "")
if [ -z "$CURRENT_ADMIN_TOKEN" ] || echo "$CURRENT_ADMIN_TOKEN" | grep -qi 'your-\|change-this\|placeholder\|example\|here'; then
  NEW_TOKEN=$(generate_secret)
  if grep -q '^CORTEX_ADMIN_TOKEN=' .env; then
    sed -i "s|^CORTEX_ADMIN_TOKEN=.*|CORTEX_ADMIN_TOKEN=$NEW_TOKEN|" .env
  else
    echo "CORTEX_ADMIN_TOKEN=$NEW_TOKEN" >> .env
  fi
  success "Generated random CORTEX_ADMIN_TOKEN"
fi

# Replace placeholder master secret
CURRENT_MASTER=$(grep '^CORTEXDB_MASTER_SECRET=' .env | cut -d'=' -f2-)
if echo "$CURRENT_MASTER" | grep -qi 'your-\|change-this\|placeholder\|example\|here\|passphrase'; then
  NEW_MASTER=$(generate_secret)
  sed -i "s|^CORTEXDB_MASTER_SECRET=.*|CORTEXDB_MASTER_SECRET=$NEW_MASTER|" .env
  success "Generated random CORTEXDB_MASTER_SECRET"
fi

# ------------------------------------------------------------------
# 3. Prompt for optional LLM API keys
# ------------------------------------------------------------------
CURRENT_ANTHROPIC=$(grep '^ANTHROPIC_API_KEY=' .env | cut -d'=' -f2-)
CURRENT_OPENAI=$(grep '^OPENAI_API_KEY=' .env | cut -d'=' -f2-)

if [ -z "$CURRENT_ANTHROPIC" ] && [ -z "$CURRENT_OPENAI" ]; then
  echo ""
  info "LLM API keys enable AI-powered features (optional)."
  info "Press Enter to skip any key."
  echo ""

  read -rp "  Anthropic API key (sk-ant-...): " INPUT_ANTHROPIC
  if [ -n "$INPUT_ANTHROPIC" ]; then
    sed -i "s|^ANTHROPIC_API_KEY=.*|ANTHROPIC_API_KEY=$INPUT_ANTHROPIC|" .env
    success "Set ANTHROPIC_API_KEY"
  fi

  read -rp "  OpenAI API key (sk-...): " INPUT_OPENAI
  if [ -n "$INPUT_OPENAI" ]; then
    sed -i "s|^OPENAI_API_KEY=.*|OPENAI_API_KEY=$INPUT_OPENAI|" .env
    success "Set OPENAI_API_KEY"
  fi
else
  success "LLM API keys already configured"
fi

# ------------------------------------------------------------------
# 4. Start Docker services
# ------------------------------------------------------------------
if [ "$NO_DOCKER" = false ]; then
  step "Starting Docker services"

  # Determine compose command
  if docker compose version &>/dev/null 2>&1; then
    COMPOSE="docker compose"
  else
    COMPOSE="docker-compose"
  fi

  $COMPOSE up -d --build
  success "Docker services started"

  # ------------------------------------------------------------------
  # 5. Wait for health checks
  # ------------------------------------------------------------------
  step "Waiting for CortexDB to become healthy"

  HEALTH_URL="http://localhost:5401/health/ready"
  MAX_RETRIES=60
  RETRY_INTERVAL=3
  RETRIES=0

  while [ $RETRIES -lt $MAX_RETRIES ]; do
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$HEALTH_URL" 2>/dev/null || echo "000")
    if [ "$HTTP_CODE" = "200" ]; then
      success "CortexDB is healthy"
      break
    fi

    RETRIES=$((RETRIES + 1))
    if [ $((RETRIES % 10)) -eq 0 ]; then
      info "Still waiting... ($RETRIES/${MAX_RETRIES}) [HTTP $HTTP_CODE]"
    fi
    sleep $RETRY_INTERVAL
  done

  if [ $RETRIES -eq $MAX_RETRIES ]; then
    warn "CortexDB health check did not pass within $((MAX_RETRIES * RETRY_INTERVAL))s."
    warn "Services may still be starting. Check: docker compose logs cortex-router"
  fi
else
  info "Skipping Docker services (--no-docker)"
fi

# ------------------------------------------------------------------
# 6. Build the dashboard
# ------------------------------------------------------------------
step "Setting up the dashboard"

if [ -d dashboard ]; then
  cd dashboard

  # Set up dashboard .env.local if it doesn't exist
  if [ ! -f .env.local ]; then
    cat > .env.local <<'ENVLOCAL'
NEXT_PUBLIC_CORTEX_API_URL=http://localhost:5400
NEXT_PUBLIC_CORTEX_WS_URL=ws://localhost:5400
ENVLOCAL
    success "Created dashboard/.env.local"
  else
    success "dashboard/.env.local already exists"
  fi

  info "Installing dashboard dependencies..."
  npm install --loglevel=warn
  success "Dependencies installed"

  if [ "$DEV_MODE" = true ]; then
    info "Building dashboard for production (one-time)..."
    npm run build
    success "Dashboard built"

    step "Starting dashboard in dev mode"
    info "Dashboard running at http://localhost:3400"
    info "Press Ctrl+C to stop."
    echo ""
    npm run dev
  else
    info "Building dashboard..."
    npm run build
    success "Dashboard built"
  fi

  cd "$SCRIPT_DIR"
else
  warn "dashboard/ directory not found. Skipping dashboard setup."
fi

# ------------------------------------------------------------------
# 7. Print summary
# ------------------------------------------------------------------
echo ""
echo -e "${GREEN}${BOLD}=============================================="
echo " CortexDB is ready!"
echo "==============================================${NC}"
echo ""

if [ "$NO_DOCKER" = false ]; then
  echo -e "  ${BOLD}CortexDB API${NC}       http://localhost:5400"
  echo -e "  ${BOLD}Health endpoint${NC}    http://localhost:5401/health/ready"
  echo -e "  ${BOLD}Admin API${NC}          http://localhost:5402"
  echo -e "  ${BOLD}Dashboard${NC}          http://localhost:3400"
  echo ""
  echo -e "  ${BOLD}PostgreSQL${NC}         localhost:5432  (user: cortex)"
  echo -e "  ${BOLD}Redis (cache)${NC}      localhost:6379"
  echo -e "  ${BOLD}Redis (streams)${NC}    localhost:6380"
  echo -e "  ${BOLD}Qdrant (vectors)${NC}   localhost:6333"
else
  echo -e "  ${BOLD}Dashboard${NC}          http://localhost:3400"
fi

echo ""
echo -e "  ${CYAN}Quick start:${NC}"
echo "    curl http://localhost:5400/v1/query \\"
echo '      -H "Content-Type: application/json" \\'
echo '      -d '"'"'{"cortexql": "SELECT 1 AS ping"}'"'"''
echo ""

if [ "$DEV_MODE" = false ] && [ "$NO_DOCKER" = false ]; then
  echo -e "  ${CYAN}Start the dashboard:${NC}"
  echo "    cd dashboard && npm run start"
  echo ""
  echo -e "  ${CYAN}Start in dev mode:${NC}"
  echo "    cd dashboard && npm run dev"
  echo ""
fi

echo -e "  ${CYAN}View logs:${NC}"
echo "    docker compose logs -f cortex-router"
echo ""
echo -e "  ${CYAN}Stop everything:${NC}"
echo "    docker compose down"
echo ""
echo -e "  ${CYAN}Enable observability (Grafana, Prometheus, Loki):${NC}"
echo "    docker compose --profile observability up -d"
echo ""
