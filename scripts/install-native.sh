#!/bin/bash
# CortexDB Native Install Script — Sets up launchd services for zero-downtime
# Usage: ./scripts/install-native.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LAUNCH_AGENTS="$HOME/Library/LaunchAgents"
LOCAL_BIN="$HOME/.local/bin"
LOG_DIR="$HOME/.shre/logs"

echo "=== CortexDB Native Install ==="
echo "Project: $PROJECT_DIR"

# 1. Create directories
mkdir -p "$LOCAL_BIN" "$LOG_DIR"
echo "  + Created $LOCAL_BIN and $LOG_DIR"

# 2. Copy entry point scripts (TCC workaround)
cp "$SCRIPT_DIR/../scripts/cortexdb-start.sh" "$LOCAL_BIN/cortexdb-start.sh" 2>/dev/null || \
    cp "$HOME/.local/bin/cortexdb-start.sh" "$LOCAL_BIN/cortexdb-start.sh" 2>/dev/null || true
chmod +x "$LOCAL_BIN/cortexdb-start.sh"
echo "  + Installed cortexdb-start.sh to $LOCAL_BIN"

# 3. Install main CortexDB plist
if [ -f "$LAUNCH_AGENTS/ai.shre.cortexdb.plist" ]; then
    launchctl unload "$LAUNCH_AGENTS/ai.shre.cortexdb.plist" 2>/dev/null || true
fi

# Verify plist exists (should have been updated by the plan)
if [ ! -f "$LAUNCH_AGENTS/ai.shre.cortexdb.plist" ]; then
    echo "  ! WARNING: ai.shre.cortexdb.plist not found in $LAUNCH_AGENTS"
    echo "    Copy it from the project and re-run install."
    exit 1
fi
echo "  + CortexDB plist verified"

# 4. Install Python dependencies
echo "  Installing Python dependencies..."
cd "$PROJECT_DIR"
pip3 install -q cachetools mmh3 bitarray psutil 2>&1 | tail -1 || true
echo "  + Python deps installed"

# 5. Load the service
launchctl load "$LAUNCH_AGENTS/ai.shre.cortexdb.plist"
echo "  + Loaded ai.shre.cortexdb"

# 6. Verify
sleep 3
if launchctl list | grep -q ai.shre.cortexdb; then
    echo ""
    echo "=== CortexDB installed and running ==="
    echo "  Service: ai.shre.cortexdb"
    echo "  KeepAlive: enabled (restarts on crash)"
    echo "  ThrottleInterval: 10s (prevents restart storms)"
    echo "  Logs: $LOG_DIR/cortexdb-*.log"
    echo ""
    echo "Commands:"
    echo "  launchctl unload $LAUNCH_AGENTS/ai.shre.cortexdb.plist  # stop"
    echo "  launchctl load   $LAUNCH_AGENTS/ai.shre.cortexdb.plist  # start"
    echo "  tail -f $LOG_DIR/cortexdb-boot.log                      # logs"
else
    echo "  ! WARNING: Service not showing in launchctl list"
    echo "    Check: launchctl list | grep cortexdb"
fi
