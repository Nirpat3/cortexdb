#!/bin/bash
# ============================================================
# CortexDB Setup Script
# One command to initialize the entire system
# Works on: Synology NAS, AWS EC2, any Linux/Mac with Docker
# (c) 2026 Nirlab Inc.
# ============================================================

set -e

echo "================================================"
echo "  CortexDB v2.0 - Setup"
echo "  Consciousness-Inspired Unified Database"
echo "  (c) 2026 Nirlab Inc."
echo "================================================"
echo ""

DATA_PATH="${CORTEX_DATA_PATH:-./data}"

echo "-> Creating data directories at: $DATA_PATH"
mkdir -p "$DATA_PATH"/{postgresql,redis,stream,vector,immutable}

echo "-> Generating secret key (change in production!)"
if [ -z "$CORTEX_SECRET_KEY" ]; then
    export CORTEX_SECRET_KEY=$(openssl rand -hex 32 2>/dev/null || python3 -c "import secrets; print(secrets.token_hex(32))")
    echo "  Generated CORTEX_SECRET_KEY: ${CORTEX_SECRET_KEY:0:8}..."
fi

echo ""
echo "-> Starting CortexDB engines..."
docker-compose up -d

echo ""
echo "-> Waiting for engines to initialize..."
sleep 10

echo ""
echo "-> Checking health..."
MAX_RETRIES=30
RETRY=0
while [ $RETRY -lt $MAX_RETRIES ]; do
    if curl -sf http://localhost:5400/health/live > /dev/null 2>&1; then
        echo "  CortexDB is alive!"
        break
    fi
    RETRY=$((RETRY + 1))
    echo "  Waiting... ($RETRY/$MAX_RETRIES)"
    sleep 2
done

if [ $RETRY -eq $MAX_RETRIES ]; then
    echo "  CortexDB failed to start. Check: docker-compose logs cortex-router"
    exit 1
fi

echo ""
echo "-> Running deep health check..."
curl -s http://localhost:5401/health/deep | python3 -m json.tool 2>/dev/null || echo "(install python3 for formatted output)"

echo ""
echo "================================================"
echo "  CortexDB is RUNNING!"
echo ""
echo "  API:        http://localhost:5400"
echo "  Health:     http://localhost:5401/health/deep"
echo "  Dashboard:  http://localhost:3400"
echo ""
echo "  Quick test:"
echo "    curl http://localhost:5400/v1/asa/standards"
echo "    curl http://localhost:5400/admin/cache/stats"
echo ""
echo "================================================"
