#!/bin/bash
# CortexDB macOS Tuning Script — Optimizes system for database workloads
# Usage: sudo ./scripts/os-tune-macos.sh [--check-only]
set -euo pipefail

CHECK_ONLY="${1:-}"
TOTAL_RAM_MB=$(sysctl -n hw.memsize | awk '{print int($1/1024/1024)}')

echo "=== CortexDB macOS Tuning ==="
echo "Total RAM: ${TOTAL_RAM_MB}MB"
echo ""

# ── 1. File Descriptor Limits ──
echo "--- File Descriptors ---"
CURRENT_SOFT=$(ulimit -n 2>/dev/null || echo "unknown")
CURRENT_HARD=$(ulimit -Hn 2>/dev/null || echo "unknown")
echo "  Current: soft=$CURRENT_SOFT hard=$CURRENT_HARD"
echo "  Target:  soft=65536 hard=65536"

if [ "$CHECK_ONLY" != "--check-only" ]; then
    # Note: LaunchAgent plist already sets SoftResourceLimits.NumberOfFiles=65536
    # This sets the session limit for manual starts
    ulimit -n 65536 2>/dev/null || echo "  ! Cannot set ulimit (run with sudo or set in plist)"
fi

# ── 2. PostgreSQL Tuning Recommendations ──
echo ""
echo "--- PostgreSQL Tuning ---"
# shared_buffers: 25% of RAM (max ~8GB for typical workloads)
SHARED_BUFFERS_MB=$((TOTAL_RAM_MB / 4))
if [ $SHARED_BUFFERS_MB -gt 8192 ]; then SHARED_BUFFERS_MB=8192; fi
# effective_cache_size: 75% of RAM
EFFECTIVE_CACHE_MB=$((TOTAL_RAM_MB * 3 / 4))
# work_mem: RAM / max_connections / 4
WORK_MEM_MB=$((TOTAL_RAM_MB / 100 / 4))
if [ $WORK_MEM_MB -lt 4 ]; then WORK_MEM_MB=4; fi
# maintenance_work_mem: RAM / 16
MAINT_WORK_MB=$((TOTAL_RAM_MB / 16))
if [ $MAINT_WORK_MB -gt 2048 ]; then MAINT_WORK_MB=2048; fi

echo "  shared_buffers = ${SHARED_BUFFERS_MB}MB"
echo "  effective_cache_size = ${EFFECTIVE_CACHE_MB}MB"
echo "  work_mem = ${WORK_MEM_MB}MB"
echo "  maintenance_work_mem = ${MAINT_WORK_MB}MB"
echo "  max_connections = 100"
echo "  wal_buffers = 64MB"
echo "  random_page_cost = 1.1  (SSD)"
echo "  effective_io_concurrency = 200  (SSD)"

PG_CONF_SNIPPET="
# CortexDB tuning (generated for ${TOTAL_RAM_MB}MB RAM)
shared_buffers = ${SHARED_BUFFERS_MB}MB
effective_cache_size = ${EFFECTIVE_CACHE_MB}MB
work_mem = ${WORK_MEM_MB}MB
maintenance_work_mem = ${MAINT_WORK_MB}MB
max_connections = 100
wal_buffers = 64MB
random_page_cost = 1.1
effective_io_concurrency = 200
checkpoint_completion_target = 0.9
max_wal_size = 2GB
min_wal_size = 1GB
"

if [ "$CHECK_ONLY" != "--check-only" ]; then
    PG_TUNE_FILE="$HOME/.shre/pg-tuning.conf"
    mkdir -p "$(dirname "$PG_TUNE_FILE")"
    echo "$PG_CONF_SNIPPET" > "$PG_TUNE_FILE"
    echo "  + Saved to $PG_TUNE_FILE"
    echo "  → Add to postgresql.conf: include = '$PG_TUNE_FILE'"
fi

# ── 3. Redis Tuning ──
echo ""
echo "--- Redis Tuning ---"
REDIS_MAXMEM_MB=$((TOTAL_RAM_MB / 8))
if [ $REDIS_MAXMEM_MB -gt 4096 ]; then REDIS_MAXMEM_MB=4096; fi
echo "  maxmemory = ${REDIS_MAXMEM_MB}mb"
echo "  maxmemory-policy = allkeys-lru"
echo "  tcp-backlog = 511"
echo "  timeout = 300"

if [ "$CHECK_ONLY" != "--check-only" ]; then
    REDIS_TUNE_FILE="$HOME/.shre/redis-tuning.conf"
    cat > "$REDIS_TUNE_FILE" <<REDISEOF
# CortexDB Redis tuning (generated for ${TOTAL_RAM_MB}MB RAM)
maxmemory ${REDIS_MAXMEM_MB}mb
maxmemory-policy allkeys-lru
tcp-backlog 511
timeout 300
hz 10
REDISEOF
    echo "  + Saved to $REDIS_TUNE_FILE"
fi

# ── 4. Validation ──
echo ""
echo "--- Validation ---"

# Check Docker
if command -v docker &>/dev/null; then
    DOCKER_MEM=$(docker info 2>/dev/null | grep "Total Memory" | awk '{print $3, $4}')
    echo "  Docker memory: $DOCKER_MEM"
else
    echo "  ! Docker not found"
fi

# Check open files
echo "  Open files limit: $(ulimit -n)"

# Check TCP settings
echo "  TCP keepalive: $(sysctl -n net.inet.tcp.keepidle 2>/dev/null || echo 'unknown')"

echo ""
echo "=== Done ==="
if [ "$CHECK_ONLY" = "--check-only" ]; then
    echo "Run without --check-only to apply changes"
fi
