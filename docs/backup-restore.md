# CortexDB Backup and Restore Guide

## Overview

CortexDB consists of four data stores that require backup:

| Component | Technology | Container | Data |
|-----------|-----------|-----------|------|
| Relational Core | PostgreSQL 16 (Citus 12) | `cortex-relational` | Tables, indexes, sharded data |
| Memory Core | Redis 7 | `cortex-memory` | Cache, sessions, pub/sub state |
| Stream Core | Redis 7 | `cortex-stream` | Event streams (append-only) |
| Vector Core | Qdrant | `cortex-vector` | Vector embeddings, collections |
| Superadmin | SQLite | Inside `cortex-router` | Agent config, tasks, audit log |

Additionally, two Citus worker nodes (`cortex-citus-worker-1`, `cortex-citus-worker-2`) store sharded PostgreSQL data and are included in the coordinator dump when using `pg_dump` against the coordinator.

---

## Backup Strategy

### What Gets Backed Up

- **PostgreSQL**: Full database dump in custom format (`pg_dump -Fc`) with compression. Includes all tables, indexes, functions, and Citus distribution metadata. A separate roles-only dump is also saved.
- **Redis (memory-core)**: RDB snapshot of the cache and session store.
- **Redis (stream-core)**: RDB snapshot of the event stream store.
- **SQLite**: Binary copy via `sqlite3 .backup` (online, consistent) plus a SQL text dump for portability.
- **Qdrant**: Per-collection snapshots downloaded via the Qdrant REST API.

### What Is NOT Backed Up

- Docker volumes for `cortex-immutable` and `cortex-cache` (ephemeral/rebuildable data).
- Observability data (Prometheus, Loki, Tempo, Grafana) -- these are considered disposable.
- Application code and configuration (managed via version control).

### Recommended Frequency

| Schedule | Type | Retention |
|----------|------|-----------|
| Daily at 02:00 | Full backup (all components) | 30 days |
| Weekly (Sunday 03:00) | Off-site sync to S3/GCS | 90 days |
| Before any migration | Manual full backup | Until migration verified |

---

## Scripts

All scripts are located in the `scripts/` directory.

### backup.sh

Creates a timestamped backup of one or more database components.

```
Usage: backup.sh [OPTIONS]

Options:
  --full        Back up all databases (default if no flags given)
  --postgres    Back up PostgreSQL only
  --redis       Back up Redis (memory-core + stream-core) only
  --sqlite      Back up SQLite superadmin database only
  --qdrant      Back up Qdrant vector snapshots only
  --no-rotate   Skip old backup rotation
  --help        Show help
```

**Environment variables:**

| Variable | Default | Description |
|----------|---------|-------------|
| `BACKUP_BASE_DIR` | `/data/backups` | Root directory for all backups |
| `BACKUP_RETENTION_DAYS` | `30` | Days to keep old backup directories |
| `PG_HOST` | `relational-core` | PostgreSQL hostname |
| `PG_PORT` | `5432` | PostgreSQL port |
| `PG_USER` | `cortex` | PostgreSQL user |
| `PG_PASSWORD` | `cortex_secret` | PostgreSQL password |
| `PG_DB` | `cortexdb` | PostgreSQL database name |
| `REDIS_HOST` | `memory-core` | Redis cache hostname |
| `REDIS_PORT` | `6379` | Redis cache port |
| `REDIS_PASSWORD` | `cortex_redis_secret` | Redis cache password |
| `STREAM_HOST` | `stream-core` | Redis streams hostname |
| `STREAM_PORT` | `6380` | Redis streams port |
| `STREAM_PASSWORD` | `cortex_stream_secret` | Redis streams password |
| `SQLITE_DB_PATH` | `/data/superadmin/cortexdb_admin.db` | Path to SQLite DB |
| `QDRANT_URL` | `http://vector-core:6333` | Qdrant HTTP API URL |

**Output structure:**

```
/data/backups/
  20260308_020000/
    manifest.json
    postgres/
      cortexdb.dump          # pg_dump custom format
      roles.sql              # pg_dumpall --roles-only
    redis/
      memory-core.rdb        # Redis cache snapshot
      stream-core.rdb        # Redis streams snapshot
    sqlite/
      cortexdb_admin.db      # Binary SQLite copy
      cortexdb_admin.sql     # SQL text dump
    qdrant/
      collection1_snapshot   # Per-collection snapshots
      collection2_snapshot
  backup.log                 # Append-only log file
```

### restore.sh

Restores databases from a backup directory.

```
Usage: restore.sh <BACKUP_DIR> [OPTIONS]

Options:
  --postgres    Restore PostgreSQL only
  --redis       Restore Redis only
  --sqlite      Restore SQLite only
  --qdrant      Restore Qdrant only
  --dry-run     Show what would be restored without doing it
  --yes         Skip confirmation prompt
  --help        Show help
```

### backup-cron.sh

Cron wrapper that runs `backup.sh --full`, sends a health check ping on success, and logs to syslog on failure.

Set `HEALTHCHECK_URL` to integrate with monitoring services like healthchecks.io or Uptime Kuma.

---

## Setting Up Automated Backups

### Option 1: Host-level cron

Add to the host machine's crontab (`crontab -e`):

```cron
# CortexDB daily backup at 2:00 AM
0 2 * * * BACKUP_BASE_DIR=/data/backups HEALTHCHECK_URL=https://hc-ping.com/YOUR-UUID /path/to/CortexDB/scripts/backup-cron.sh >> /var/log/cortexdb-backup.log 2>&1
```

This works when scripts run on the same host as Docker and can reach containers via `localhost` or Docker network.

### Option 2: Docker one-off container

Run the backup inside the Docker network so it can reach all services by their container names:

```bash
docker run --rm \
  --network cortexdb_cortex-net \
  -v cortexdb_cortex-backups:/data/backups \
  -v cortexdb_cortex-superadmin:/data/superadmin:ro \
  -v ./scripts:/scripts:ro \
  -e PG_HOST=relational-core \
  -e REDIS_HOST=memory-core \
  -e STREAM_HOST=stream-core \
  -e QDRANT_URL=http://vector-core:6333 \
  -e POSTGRES_PASSWORD=cortex_secret \
  -e REDIS_PASSWORD=cortex_redis_secret \
  -e STREAM_PASSWORD=cortex_stream_secret \
  --entrypoint bash \
  postgres:16-alpine -c "apk add --no-cache redis curl jq sqlite && /scripts/backup.sh --full"
```

Schedule this via cron or systemd timer on the host.

### Option 3: Systemd timer (Linux)

Create `/etc/systemd/system/cortexdb-backup.service`:

```ini
[Unit]
Description=CortexDB Daily Backup

[Service]
Type=oneshot
ExecStart=/path/to/CortexDB/scripts/backup-cron.sh
Environment=BACKUP_BASE_DIR=/data/backups
Environment=BACKUP_RETENTION_DAYS=30
```

Create `/etc/systemd/system/cortexdb-backup.timer`:

```ini
[Unit]
Description=CortexDB backup timer

[Timer]
OnCalendar=*-*-* 02:00:00
Persistent=true

[Install]
WantedBy=timers.target
```

Enable with:

```bash
sudo systemctl enable --now cortexdb-backup.timer
```

---

## Manual Backup Procedure

### Full backup

```bash
./scripts/backup.sh --full
```

### PostgreSQL only

```bash
./scripts/backup.sh --postgres
```

### Before a migration

```bash
# Tag the backup for easy identification
BACKUP_BASE_DIR=/data/backups/pre-migration ./scripts/backup.sh --full
```

---

## Restore Procedures

### Pre-flight: dry run

Always start with a dry run to verify what will be restored:

```bash
./scripts/restore.sh /data/backups/20260308_020000 --dry-run
```

### Full restore

```bash
./scripts/restore.sh /data/backups/20260308_020000 --yes
```

### Restore PostgreSQL only

```bash
./scripts/restore.sh /data/backups/20260308_020000 --postgres --yes
```

### Restore SQLite only (superadmin data)

```bash
./scripts/restore.sh /data/backups/20260308_020000 --sqlite --yes
```

This will stop the `cortex-router` service, replace the SQLite file, and restart it.

### Restore via Docker (when running inside containers)

```bash
docker run --rm -it \
  --network cortexdb_cortex-net \
  -v cortexdb_cortex-backups:/data/backups \
  -v cortexdb_cortex-superadmin:/data/superadmin \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v ./scripts:/scripts:ro \
  -e POSTGRES_PASSWORD=cortex_secret \
  --entrypoint bash \
  postgres:16-alpine -c "apk add --no-cache redis curl jq sqlite docker-cli && /scripts/restore.sh /data/backups/20260308_020000 --yes"
```

---

## Disaster Recovery Scenarios

### Scenario 1: Single service data corruption

Symptoms: One database returns errors or inconsistent data.

Steps:
1. Identify the affected component (PostgreSQL, Redis, SQLite, or Qdrant).
2. Run a dry-run restore for that component only.
3. Stop the affected service if the restore script does not handle it.
4. Restore the single component from the latest good backup.
5. Verify data integrity.
6. Restart any stopped services.

```bash
# Example: PostgreSQL corruption
./scripts/restore.sh /data/backups/20260308_020000 --postgres --yes
```

### Scenario 2: Complete host failure

Steps:
1. Provision a new host with Docker installed.
2. Clone the CortexDB repository.
3. Copy backup files from off-site storage to `/data/backups/`.
4. Start infrastructure services (PostgreSQL, Redis, Qdrant) without the application.
5. Run a full restore.
6. Start all services.

```bash
# Step 4: Start data stores only
docker compose up -d relational-core memory-core stream-core vector-core

# Step 5: Wait for health checks, then restore
./scripts/restore.sh /data/backups/20260308_020000 --yes

# Step 6: Start everything
docker compose up -d
```

### Scenario 3: Accidental data deletion

Steps:
1. Immediately stop writes to the affected service if possible.
2. Identify the most recent backup that predates the deletion.
3. For PostgreSQL, consider point-in-time recovery if WAL archiving is enabled. Otherwise, restore from the nearest backup.
4. Restore only the affected component.

### Scenario 4: Corrupted backup

If the latest backup is corrupted:
1. The restore script validates backups before applying them. Check the validation output.
2. Try the previous day's backup.
3. For PostgreSQL, verify with `pg_restore --list <dump_file>`.
4. For SQLite, verify with `sqlite3 <db_file> "PRAGMA integrity_check;"`.

---

## Testing Backup Integrity

Regular testing is critical. Run these checks periodically (weekly recommended).

### Automated validation

```bash
# Validate a backup without restoring it
./scripts/restore.sh /data/backups/20260308_020000 --dry-run
```

The dry run checks:
- Manifest file existence and contents.
- PostgreSQL dump table of contents (`pg_restore --list`).
- SQLite integrity check (`PRAGMA integrity_check`).
- Qdrant snapshot file existence.

### Full restore test

For thorough validation, restore to a separate environment:

```bash
# Start a temporary PostgreSQL instance
docker run -d --name pg-test -e POSTGRES_PASSWORD=test postgres:16
sleep 5

# Restore into it
export PG_HOST=localhost PG_PORT=5433 PG_PASSWORD=test
pg_restore -h localhost -p 5433 -U postgres -d cortexdb_test \
  /data/backups/20260308_020000/postgres/cortexdb.dump

# Run queries to verify data
psql -h localhost -p 5433 -U postgres -d cortexdb_test \
  -c "SELECT count(*) FROM agents;"

# Clean up
docker rm -f pg-test
```

---

## Off-site Backup (S3 Example)

### Prerequisites

Install the AWS CLI (`aws`) and configure credentials.

### Sync to S3

```bash
# After backup completes, sync to S3
BACKUP_DIR="/data/backups/$(ls -1t /data/backups/ | head -1)"
aws s3 sync "$BACKUP_DIR" "s3://your-bucket/cortexdb-backups/$(basename "$BACKUP_DIR")/" \
  --storage-class STANDARD_IA \
  --sse AES256
```

### Automated off-site sync via cron

```cron
# Sync latest backup to S3 at 3:00 AM (after 2 AM backup)
0 3 * * * aws s3 sync /data/backups/ s3://your-bucket/cortexdb-backups/ --storage-class STANDARD_IA --sse AES256 --delete >> /var/log/cortexdb-s3-sync.log 2>&1
```

### S3 lifecycle policy

Configure an S3 lifecycle rule to transition backups:
- Move to Glacier after 30 days.
- Delete from Glacier after 365 days.

### Restore from S3

```bash
# Download a specific backup
aws s3 sync "s3://your-bucket/cortexdb-backups/20260308_020000/" /data/backups/20260308_020000/

# Then restore normally
./scripts/restore.sh /data/backups/20260308_020000 --yes
```

### Alternative: Google Cloud Storage

```bash
# Upload
gsutil -m rsync -r /data/backups/ gs://your-bucket/cortexdb-backups/

# Download
gsutil -m rsync -r gs://your-bucket/cortexdb-backups/20260308_020000/ /data/backups/20260308_020000/
```

---

## Monitoring Backups

### Health check integration

Set `HEALTHCHECK_URL` in the cron wrapper to ping a monitoring service:

- [healthchecks.io](https://healthchecks.io) -- pings on success, alerts on missing ping
- [Uptime Kuma](https://github.com/louislam/uptime-kuma) -- self-hosted alternative
- Any HTTP endpoint that accepts GET requests

### Log monitoring

Backup logs are written to `/data/backups/backup.log` (append-only). Monitor this file for `[ERROR]` entries:

```bash
# Check for recent errors
grep '\[ERROR\]' /data/backups/backup.log | tail -20
```

### Backup size tracking

Monitor backup sizes over time to detect anomalies:

```bash
# List all backups with sizes
du -sh /data/backups/*/
```

A sudden drop in backup size may indicate data loss. A sudden increase may indicate bloat or unexpected data growth.
