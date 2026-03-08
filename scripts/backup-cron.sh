#!/usr/bin/env bash
# ============================================================
# CortexDB Backup Cron Wrapper
# Runs a full backup and optionally pings a health check URL.
#
# Install as a cron job:
#   0 2 * * * /path/to/scripts/backup-cron.sh >> /var/log/cortexdb-backup-cron.log 2>&1
# ============================================================
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HEALTHCHECK_URL="${HEALTHCHECK_URL:-}"
BACKUP_LOG="${BACKUP_BASE_DIR:-/data/backups}/backup.log"

log_cron() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [CRON] $*"
}

# ----------------------------------------------------------
# Run the full backup
# ----------------------------------------------------------
log_cron "Starting scheduled full backup..."

if "${SCRIPT_DIR}/backup.sh" --full; then
    log_cron "Backup completed successfully."

    # Ping health check endpoint on success
    if [[ -n "$HEALTHCHECK_URL" ]]; then
        if curl -sf -m 10 "$HEALTHCHECK_URL" > /dev/null 2>&1; then
            log_cron "Health check ping sent to ${HEALTHCHECK_URL}"
        else
            log_cron "WARNING: Health check ping failed (${HEALTHCHECK_URL})"
        fi
    fi
else
    EXIT_CODE=$?
    log_cron "ERROR: Backup failed with exit code ${EXIT_CODE}"

    # Log to syslog on failure
    if command -v logger > /dev/null 2>&1; then
        logger -t "cortexdb-backup" -p user.err \
            "CortexDB backup failed with exit code ${EXIT_CODE}. Check ${BACKUP_LOG}"
    fi

    # Ping health check with failure status (append /fail for services like healthchecks.io)
    if [[ -n "$HEALTHCHECK_URL" ]]; then
        curl -sf -m 10 "${HEALTHCHECK_URL}/fail" > /dev/null 2>&1 || true
    fi

    exit $EXIT_CODE
fi
