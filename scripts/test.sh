#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# CortexDB Unified Test Runner
#
# Usage:
#   ./scripts/test.sh unit          Run unit tests only
#   ./scripts/test.sh integration   Run integration tests
#   ./scripts/test.sh e2e           Run Playwright E2E tests
#   ./scripts/test.sh all           Run everything (unit + integration + e2e)
#   ./scripts/test.sh coverage      Run unit + integration with coverage report
#
# Environment variables:
#   DASHBOARD_URL   Base URL for E2E tests (default: http://localhost:3400)
#   API_BASE        CortexDB API URL for E2E  (default: http://localhost:5400)
# ---------------------------------------------------------------------------

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

PASS=0
FAIL=0
SKIP=0

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

banner() {
  echo ""
  echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
  echo -e "${CYAN}  $1${NC}"
  echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

run_step() {
  local label="$1"
  shift
  echo -e "${YELLOW}▶ ${label}${NC}"
  if "$@"; then
    echo -e "${GREEN}✔ ${label} — PASSED${NC}"
    PASS=$((PASS + 1))
  else
    echo -e "${RED}✘ ${label} — FAILED${NC}"
    FAIL=$((FAIL + 1))
  fi
}

summary() {
  banner "Test Summary"
  echo -e "  ${GREEN}Passed:  ${PASS}${NC}"
  echo -e "  ${RED}Failed:  ${FAIL}${NC}"
  echo -e "  ${YELLOW}Skipped: ${SKIP}${NC}"
  echo ""
  if [ "$FAIL" -gt 0 ]; then
    echo -e "${RED}Some test suites failed.${NC}"
    exit 1
  else
    echo -e "${GREEN}All test suites passed.${NC}"
    exit 0
  fi
}

# ---------------------------------------------------------------------------
# Test commands
# ---------------------------------------------------------------------------

run_unit() {
  banner "Unit Tests"
  run_step "Python unit tests" \
    python -m pytest tests/unit/ -v --tb=short -q
}

run_integration() {
  banner "Integration Tests"
  run_step "API endpoint tests" \
    python -m pytest tests/integration/test_api_endpoints.py -v --tb=short -q
  run_step "SuperAdmin API tests" \
    python -m pytest tests/integration/test_superadmin_api.py -v --tb=short -q
  run_step "Multi-tenant isolation tests" \
    python -m pytest tests/integration/test_multi_tenant.py -v --tb=short -q
  run_step "Rate limiting tests" \
    python -m pytest tests/integration/test_rate_limiting.py -v --tb=short -q
}

run_e2e() {
  banner "E2E Tests (Playwright)"
  cd "$ROOT_DIR/dashboard"

  # Install Playwright browsers if not present
  if ! npx playwright --version >/dev/null 2>&1; then
    echo -e "${YELLOW}Installing Playwright browsers...${NC}"
    npx playwright install --with-deps chromium
  fi

  run_step "Dashboard E2E (Chromium)" \
    npx playwright test --config=e2e/playwright.config.ts --project=chromium
  cd "$ROOT_DIR"
}

run_coverage() {
  banner "Coverage Report"
  run_step "Unit + Integration with coverage" \
    python -m pytest tests/unit/ tests/integration/ \
      --cov=src/cortexdb \
      --cov-report=term-missing \
      --cov-report=html:htmlcov \
      -v --tb=short -q
  echo ""
  echo -e "${CYAN}HTML coverage report: ${ROOT_DIR}/htmlcov/index.html${NC}"
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

MODE="${1:-help}"

case "$MODE" in
  unit)
    run_unit
    summary
    ;;
  integration)
    run_integration
    summary
    ;;
  e2e)
    run_e2e
    summary
    ;;
  all)
    run_unit
    run_integration
    run_e2e
    summary
    ;;
  coverage)
    run_coverage
    summary
    ;;
  *)
    echo "CortexDB Test Runner"
    echo ""
    echo "Usage: $0 <command>"
    echo ""
    echo "Commands:"
    echo "  unit          Run Python unit tests"
    echo "  integration   Run Python integration tests"
    echo "  e2e           Run Playwright E2E tests (dashboard)"
    echo "  all           Run unit + integration + e2e"
    echo "  coverage      Run unit + integration with coverage report"
    exit 0
    ;;
esac
