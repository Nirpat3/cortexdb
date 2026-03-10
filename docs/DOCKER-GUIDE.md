# CortexDB™ Docker Deployment Guide

**From single-node development to petabyte-scale production.**

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Quick Start (Development)](#2-quick-start-development)
3. [Container Reference](#3-container-reference)
4. [Configuration](#4-configuration)
5. [Scaling with Citus Workers](#5-scaling-with-citus-workers)
6. [Production Deployment](#6-production-deployment)
7. [Kubernetes Deployment](#7-kubernetes-deployment)
8. [Backup & Recovery](#8-backup--recovery)
9. [Monitoring Stack](#9-monitoring-stack)
10. [Troubleshooting](#10-troubleshooting)

---

## 1. Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                    Docker Compose Stack                   │
│                                                          │
│  ┌──────────────┐     ┌──────────────────────────────┐  │
│  │ cortex-router │────→│ relational-core (Citus 12)   │  │
│  │ (FastAPI)     │     │ + TimescaleDB + Apache AGE   │  │
│  │ Port 5400     │     │ Port 5432                    │  │
│  └──────┬───────┘     └──────────┬───────────────────┘  │
│         │                        │                       │
│         │              ┌─────────┼─────────┐            │
│         │              │         │         │            │
│         │         ┌────▼───┐ ┌───▼────┐    │            │
│         │         │Worker 1│ │Worker 2│    │            │
│         │         │(Citus) │ │(Citus) │    │            │
│         │         └────────┘ └────────┘    │            │
│         │                                   │            │
│  ┌──────▼───────┐  ┌──────────────┐        │            │
│  │ memory-core  │  │ stream-core  │        │            │
│  │ (Redis 7)    │  │ (Redis 7)    │        │            │
│  │ Port 6379    │  │ Port 6380    │        │            │
│  └──────────────┘  └──────────────┘        │            │
│                                             │            │
│  ┌──────────────┐  ┌──────────────────────┐│            │
│  │ vector-core  │  │ Observability Stack  ││            │
│  │ (Qdrant)     │  │ Grafana + Prometheus ││            │
│  │ Port 6333    │  │ Loki + Tempo + OTel  ││            │
│  └──────────────┘  └──────────────────────┘│            │
│                                             │            │
│  ┌──────────────┐                          │            │
│  │  Dashboard   │                          │            │
│  │  Port 3400   │                          │            │
│  └──────────────┘                          │            │
└─────────────────────────────────────────────────────────┘
```

### Containers (12 total)

| Container | Image | Port | Purpose |
|-----------|-------|------|---------|
| cortex-router | Custom (Dockerfile) | 5400 | CortexQL API server |
| relational-core | citusdata/citus:12.1 | 5432 | PostgreSQL + Citus coordinator |
| citus-worker-1 | citusdata/citus:12.1 | — | Shard worker node |
| citus-worker-2 | citusdata/citus:12.1 | — | Shard worker node |
| memory-core | redis:7-alpine | 6379 | Cache + sessions |
| stream-core | redis:7-alpine | 6380 | Event streaming |
| vector-core | qdrant/qdrant:latest | 6333 | Vector search |
| otel-collector | otel/opentelemetry-collector | 4317 | Trace collection |
| prometheus | prom/prometheus | 9090 | Metrics |
| loki | grafana/loki | 3100 | Log aggregation |
| tempo | grafana/tempo | 3200 | Distributed tracing |
| grafana | grafana/grafana | 3000 | Dashboards |

---

## 2. Quick Start (Development)

### Prerequisites

- Docker Engine 24+
- Docker Compose v2.20+
- 4 GB RAM minimum (8 GB recommended)
- 10 GB disk space

### Step 1: Setup Data Directories

```bash
chmod +x setup.sh
./setup.sh
```

Or manually:
```bash
mkdir -p data/{postgresql,redis,stream,vector,immutable,citus-w1,citus-w2}
```

### Step 2: Start Everything

```bash
docker compose up -d
```

### Step 3: Verify

```bash
# Check all containers are running
docker compose ps

# Check API health
curl http://localhost:5400/health/live

# Check engine connectivity
curl http://localhost:5400/health/ready

# Deep health (all subsystems)
curl http://localhost:5400/health/deep | python -m json.tool
```

### Step 4: Initialize Sharding (Optional)

```bash
curl -X POST http://localhost:5400/v1/admin/sharding/initialize
curl -X POST http://localhost:5400/v1/admin/sharding/distribute
```

### Stopping

```bash
docker compose down        # Stop containers (keep data)
docker compose down -v     # Stop and delete all data
```

---

## 3. Container Reference

### cortex-router (CortexDB API)

The main API server. All client requests go here.

```yaml
environment:
  CORTEX_MODE: production
  CORTEX_PORT: 5400
  CORTEX_SECRET_KEY: "your-64-char-secret"      # For API key hashing
  CORTEX_MASTER_KEY: "your-encryption-key"       # For field encryption
  CORTEX_ENABLE_AMYGDALA: true                   # Security engine
  CORTEX_ENABLE_PLASTICITY: true                 # Query path optimization
  CORTEX_ENABLE_SLEEP_CYCLE: true                # Nightly maintenance
  CORTEX_SLEEP_CYCLE_HOUR: 2                     # 2 AM
```

### relational-core (Citus Coordinator)

PostgreSQL 16 with Citus 12, TimescaleDB, and Apache AGE.

```yaml
environment:
  POSTGRES_USER: cortex
  POSTGRES_PASSWORD: cortex_secret               # CHANGE IN PRODUCTION
  POSTGRES_DB: cortexdb
  POSTGRES_SHARED_BUFFERS: 512MB                 # 25% of RAM
  POSTGRES_EFFECTIVE_CACHE_SIZE: 1536MB           # 75% of RAM
  POSTGRES_WORK_MEM: 32MB
  POSTGRES_MAX_CONNECTIONS: 300
  POSTGRES_WAL_LEVEL: logical                    # Required for Citus
```

**Tuning for your hardware:**

| RAM | shared_buffers | effective_cache_size | work_mem | max_connections |
|-----|---------------|---------------------|----------|----------------|
| 4 GB | 1 GB | 3 GB | 16 MB | 200 |
| 16 GB | 4 GB | 12 GB | 64 MB | 300 |
| 64 GB | 16 GB | 48 GB | 128 MB | 500 |
| 256 GB | 64 GB | 192 GB | 256 MB | 1000 |

### memory-core (Redis Cache)

```yaml
command: >
  redis-server
  --maxmemory 512mb                              # Adjust to available RAM
  --maxmemory-policy allkeys-lru                 # Evict least recently used
  --appendonly yes                               # AOF persistence
  --requirepass cortex_redis_secret              # CHANGE IN PRODUCTION
```

### vector-core (Qdrant)

```yaml
environment:
  QDRANT__SERVICE__GRPC_PORT: 6334
  QDRANT__SERVICE__HTTP_PORT: 6333
  # For large datasets:
  # QDRANT__STORAGE__WAL_CAPACITY_MB: 256
  # QDRANT__STORAGE__PERFORMANCE__MAX_SEARCH_THREADS: 4
```

---

## 4. Configuration

### Environment Variables

Create a `.env` file in the project root:

```bash
# Security (CHANGE ALL OF THESE)
CORTEX_SECRET_KEY=generate-64-char-random-string-here-use-openssl-rand-hex-32
CORTEX_MASTER_KEY=another-64-char-random-string-for-field-encryption-keys
POSTGRES_PASSWORD=strong-database-password-here
MEMORY_CORE_PASSWORD=strong-redis-password-here
STREAM_CORE_PASSWORD=strong-stream-password-here

# Data storage location
CORTEX_DATA_PATH=./data

# Performance
POSTGRES_SHARED_BUFFERS=1GB
POSTGRES_EFFECTIVE_CACHE_SIZE=3GB
REDIS_MAXMEMORY=1gb

# Observability
GRAFANA_PASSWORD=strong-grafana-password
```

### Generate Secure Keys

```bash
# Generate 64-character hex keys
openssl rand -hex 32    # For CORTEX_SECRET_KEY
openssl rand -hex 32    # For CORTEX_MASTER_KEY
openssl rand -hex 16    # For POSTGRES_PASSWORD
```

---

## 5. Scaling with Citus Workers

### Adding More Workers

Edit `docker-compose.yml` to add workers:

```yaml
  citus-worker-3:
    <<: *common
    image: citusdata/citus:12.1
    container_name: cortex-citus-worker-3
    environment:
      - POSTGRES_USER=cortex
      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
      - POSTGRES_DB=cortexdb
    volumes:
      - cortex-citus-w3-data:/var/lib/postgresql/data
    depends_on:
      relational-core:
        condition: service_healthy
    networks:
      - cortex-net
```

Then register the worker:

```bash
# Start the new worker
docker compose up -d citus-worker-3

# Register with coordinator
curl -X POST "http://localhost:5400/v1/admin/sharding/add-worker?host=citus-worker-3&port=5432"

# Rebalance shards across all workers
curl -X POST http://localhost:5400/v1/admin/sharding/rebalance
```

### Scaling Strategy

| Stage | Workers | Expected Load | Storage |
|-------|---------|---------------|---------|
| Development | 0 (single-node) | < 100 QPS | < 10 GB |
| Startup | 2 | < 1K QPS | < 100 GB |
| Growth | 4-8 | < 10K QPS | < 1 TB |
| Enterprise | 16-32 | < 100K QPS | < 10 TB |
| Planet-Scale | 64-128 | 1M+ QPS | 100+ TB |

### Removing Workers

```bash
# Drain shards first (moves data to other workers)
curl -X POST "http://localhost:5400/v1/admin/sharding/remove-worker?host=citus-worker-3&port=5432"

# Then stop the container
docker compose stop citus-worker-3
```

---

## 6. Production Deployment

### Security Checklist

- [ ] Change all default passwords in `.env`
- [ ] Generate unique `CORTEX_SECRET_KEY` and `CORTEX_MASTER_KEY`
- [ ] Enable TLS on all services (PostgreSQL `ssl = on`, Redis TLS)
- [ ] Remove port mappings for internal services (keep only 5400)
- [ ] Set `CORTEX_MODE=production`
- [ ] Configure firewall rules
- [ ] Enable PostgreSQL `log_connections` and `log_disconnections`
- [ ] Set Grafana admin password
- [ ] Review and apply rate limits per tenant plan

### Production docker-compose.override.yml

```yaml
version: "3.9"

services:
  cortex-router:
    environment:
      - CORTEX_MODE=production
      - CORTEX_SECRET_KEY=${CORTEX_SECRET_KEY}
      - CORTEX_MASTER_KEY=${CORTEX_MASTER_KEY}
    deploy:
      replicas: 3                    # Multiple API instances
      resources:
        limits:
          cpus: "4.0"
          memory: 4G

  relational-core:
    environment:
      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
      - POSTGRES_SHARED_BUFFERS=4GB
      - POSTGRES_EFFECTIVE_CACHE_SIZE=12GB
    ports: []                        # No external access
    deploy:
      resources:
        limits:
          cpus: "8.0"
          memory: 16G

  memory-core:
    command: >
      redis-server
      --maxmemory 4gb
      --maxmemory-policy allkeys-lru
      --appendonly yes
      --requirepass ${MEMORY_CORE_PASSWORD}
      --tls-port 6379
      --tls-cert-file /certs/redis.crt
      --tls-key-file /certs/redis.key
    ports: []

  vector-core:
    ports: []
    deploy:
      resources:
        limits:
          cpus: "4.0"
          memory: 8G
```

### High Availability

```
                    Load Balancer
                    ┌─────────┐
                    │  Nginx  │
                    │  :443   │
                    └────┬────┘
                ┌────────┼────────┐
                ▼        ▼        ▼
          ┌──────┐  ┌──────┐  ┌──────┐
          │Router│  │Router│  │Router│
          │  #1  │  │  #2  │  │  #3  │
          └──┬───┘  └──┬───┘  └──┬───┘
             └──────────┼──────────┘
                        ▼
              ┌──────────────────┐
              │ Citus Coordinator│
              │   (Primary)      │
              └────────┬─────────┘
         ┌─────────────┼─────────────┐
         ▼             ▼             ▼
    ┌─────────┐  ┌─────────┐  ┌─────────┐
    │Worker 1 │  │Worker 2 │  │Worker 3 │
    └─────────┘  └─────────┘  └─────────┘
```

---

## 7. Kubernetes Deployment

### Helm Chart (Conceptual)

```yaml
# values.yaml
cortexRouter:
  replicas: 3
  resources:
    requests: { cpu: "1", memory: "2Gi" }
    limits: { cpu: "4", memory: "4Gi" }
  env:
    CORTEX_MODE: production
    CORTEX_SECRET_KEY:
      secretKeyRef: cortexdb-secrets/secret-key

relationalCore:
  image: citusdata/citus:12.1
  storage: 100Gi
  storageClass: gp3          # AWS EBS gp3
  resources:
    requests: { cpu: "2", memory: "8Gi" }
    limits: { cpu: "8", memory: "16Gi" }

citusWorkers:
  replicas: 4
  storage: 500Gi
  storageClass: gp3

memoryCore:
  image: redis:7-alpine
  maxMemory: 4gb
  persistence: true

vectorCore:
  image: qdrant/qdrant:latest
  storage: 50Gi
```

### Kubernetes Health Probes

```yaml
livenessProbe:
  httpGet:
    path: /health/live
    port: 5400
  initialDelaySeconds: 10
  periodSeconds: 5

readinessProbe:
  httpGet:
    path: /health/ready
    port: 5400
  initialDelaySeconds: 15
  periodSeconds: 10
```

---

## 8. Backup & Recovery

### PostgreSQL (Citus Coordinator + Workers)

```bash
# Full backup (coordinator)
docker exec cortex-relational pg_dumpall -U cortex > backup_$(date +%Y%m%d).sql

# Continuous archiving (WAL)
# Add to postgresql.conf:
# archive_mode = on
# archive_command = 'cp %p /backups/wal/%f'

# Point-in-time recovery
# pg_restore --target-time="2026-03-06 12:00:00"
```

### Redis (MemoryCore + StreamCore)

```bash
# Trigger RDB snapshot
docker exec cortex-memory redis-cli -a cortex_redis_secret BGSAVE

# Copy backup
docker cp cortex-memory:/data/dump.rdb ./backups/redis_$(date +%Y%m%d).rdb
```

### Qdrant (VectorCore)

```bash
# Snapshot via API
curl -X POST http://localhost:6333/snapshots

# Download snapshot
curl http://localhost:6333/snapshots/{snapshot_name} -o vector_backup.snapshot
```

### Automated Backup Script

```bash
#!/bin/bash
# backup.sh - Run daily via cron
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/backups/${DATE}"
mkdir -p "${BACKUP_DIR}"

# PostgreSQL
docker exec cortex-relational pg_dumpall -U cortex | gzip > "${BACKUP_DIR}/pg_full.sql.gz"

# Redis
docker exec cortex-memory redis-cli -a cortex_redis_secret BGSAVE
sleep 2
docker cp cortex-memory:/data/dump.rdb "${BACKUP_DIR}/redis.rdb"

# Qdrant
curl -s -X POST http://localhost:6333/snapshots > /dev/null

echo "Backup completed: ${BACKUP_DIR}"
```

---

## 9. Monitoring Stack

### Grafana

Access: `http://localhost:3000`
Default credentials: `admin` / `cortex_admin`

### Prometheus

Access: `http://localhost:9090`
Scrapes CortexDB metrics from `/health/metrics` every 15s.

### Key Metrics to Monitor

| Metric | Alert Threshold | Meaning |
|--------|----------------|---------|
| `cortexdb_queries_total` | — | Total query throughput |
| `cortexdb_cache_hit_rate` | < 60% | Cache needs tuning |
| `cortexdb_write_latency_ms` | > 100ms | Write performance degraded |
| `cortexdb_amygdala_blocks` | > 10/min | Possible attack |
| `cortexdb_engine_health` | unhealthy | Engine connectivity issue |

### Setting Up Alerts

```yaml
# alertmanager.yml
route:
  receiver: 'slack'

receivers:
  - name: 'slack'
    slack_configs:
      - channel: '#cortexdb-alerts'
        send_resolved: true

# prometheus alert rules
groups:
  - name: cortexdb
    rules:
      - alert: HighErrorRate
        expr: rate(cortexdb_errors_total[5m]) > 0.05
        for: 5m
        labels:
          severity: critical
```

---

## 10. Troubleshooting

### Container Won't Start

```bash
# Check logs
docker compose logs cortex-router
docker compose logs relational-core

# Common issues:
# 1. Port already in use → stop other services on 5432/6379
# 2. Data directory permissions → chmod -R 777 data/
# 3. Insufficient memory → increase Docker memory limit
```

### Database Connection Failed

```bash
# Test PostgreSQL directly
docker exec cortex-relational psql -U cortex -d cortexdb -c "SELECT 1"

# Test Redis
docker exec cortex-memory redis-cli -a cortex_redis_secret PING

# Test Qdrant
curl http://localhost:6333/healthz
```

### Slow Queries

```bash
# Check AI index recommendations
curl http://localhost:5400/v1/admin/indexes/recommend

# Check cache hit rate
curl http://localhost:5400/admin/cache/stats

# Check if sharding is healthy
curl http://localhost:5400/v1/admin/sharding/stats
```

### Disk Space

```bash
# Check container disk usage
docker system df

# Check PostgreSQL table sizes
docker exec cortex-relational psql -U cortex -d cortexdb \
  -c "SELECT relname, pg_size_pretty(pg_total_relation_size(oid)) FROM pg_class ORDER BY pg_total_relation_size(oid) DESC LIMIT 10"

# Clean up
docker system prune -f
```

### Reset Everything

```bash
# WARNING: This deletes all data
docker compose down -v
rm -rf data/*
./setup.sh
docker compose up -d
```

---

*CortexDB™ — AI Agent Data Infrastructure.*
*Copyright (c) 2026 Nirlab Inc.*
