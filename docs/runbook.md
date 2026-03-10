# CortexDB Production Operations Runbook

Version: 1.0
Last Updated: 2026-03-08

---

## Table of Contents

1. [Service Architecture Overview](#service-architecture-overview)
2. [Service Management](#service-management)
3. [Health Checks](#health-checks)
4. [Common Operations](#common-operations)
5. [Monitoring](#monitoring)
6. [Scaling Guide](#scaling-guide)

---

## Service Architecture Overview

CortexDB consists of the following services:

| Service | Container | Port(s) | Role |
|---------|-----------|---------|------|
| cortex-router | cortex-router | 5400 (API), 5401 (Health), 5402 (Admin) | CortexQL API gateway, query routing |
| relational-core | cortex-relational | 5432 | Citus 12 / PostgreSQL 16 coordinator |
| citus-worker-1 | cortex-citus-worker-1 | - | Citus shard worker |
| citus-worker-2 | cortex-citus-worker-2 | - | Citus shard worker |
| memory-core | cortex-memory | 6379 | Redis 7 (cache, sessions, pub/sub) |
| stream-core | cortex-stream | 6380 | Redis 7 Streams (event streaming) |
| vector-core | cortex-vector | 6333 (HTTP), 6334 (gRPC) | Qdrant vector search |
| cortex-dashboard | cortex-dashboard | 3400 (default) | Admin UI (Next.js) |
| otel-collector | cortex-otel | 4317, 4318 | OpenTelemetry collector (observability profile) |
| prometheus | cortex-prometheus | 9090 | Metrics (observability profile) |
| loki | cortex-loki | 3100 | Log aggregation (observability profile) |
| tempo | cortex-tempo | 3200 | Distributed tracing (observability profile) |
| grafana | cortex-grafana | 3000 | Dashboards (observability profile) |

**Dependency order:** relational-core + memory-core + stream-core --> cortex-router --> cortex-dashboard

---

## Service Management

### Starting the Full Stack

```bash
# Start all core services
docker compose up -d

# Start with observability stack included
docker compose --profile observability up -d

# Start and rebuild images
docker compose up -d --build
```

### Stopping the Full Stack

```bash
# Graceful stop (sends SIGTERM, waits for shutdown)
docker compose down

# Stop and remove volumes (DESTRUCTIVE - deletes all data)
docker compose down -v
```

### Starting/Stopping Individual Services

```bash
# Start only the router and its dependencies
docker compose up -d cortex-router

# Stop a single service without affecting dependents
docker compose stop memory-core

# Restart a single service
docker compose restart cortex-router

# View logs for a service
docker compose logs -f cortex-router --tail 100
```

### Rolling Restarts (Zero-Downtime)

CortexDB does not have built-in blue/green deployment. Use this procedure for minimal downtime:

**Router restart (brief interruption):**

```bash
# 1. Check current health
curl -s http://localhost:5401/health/ready | jq .

# 2. Restart the router (clients will retry on connection reset)
docker compose restart cortex-router

# 3. Wait for health check to pass
until curl -sf http://localhost:5401/health/live > /dev/null 2>&1; do
  sleep 1
  echo "Waiting for router..."
done
echo "Router is live."
```

**Database rolling restart (Citus workers first, then coordinator):**

```bash
# 1. Restart workers one at a time
docker compose restart citus-worker-1
sleep 10
docker compose restart citus-worker-2
sleep 10

# 2. Restart coordinator last
docker compose restart relational-core

# 3. Verify cluster health
docker exec cortex-relational psql -U cortex -d cortexdb -c "SELECT * FROM citus_check_cluster_node_health();"
```

**Redis restart (cache will be cold, AOF replays on start):**

```bash
# 1. Trigger a background save before restart
docker exec cortex-memory redis-cli -a "${REDIS_PASSWORD:-cortex_redis_secret}" BGSAVE

# 2. Wait for save to complete
docker exec cortex-memory redis-cli -a "${REDIS_PASSWORD:-cortex_redis_secret}" LASTSAVE

# 3. Restart
docker compose restart memory-core
```

### Scaling Services (Adding Citus Workers)

**Add a new Citus worker:**

1. Add the worker definition to `docker-compose.yml`:

```yaml
citus-worker-3:
  <<: *common
  image: citusdata/citus:12.1
  container_name: cortex-citus-worker-3
  environment:
    - POSTGRES_USER=cortex
    - POSTGRES_PASSWORD=${POSTGRES_PASSWORD:-cortex_secret}
    - POSTGRES_DB=cortexdb
    - POSTGRES_SHARED_BUFFERS=256MB
    - POSTGRES_EFFECTIVE_CACHE_SIZE=768MB
    - POSTGRES_WORK_MEM=16MB
    - POSTGRES_MAX_CONNECTIONS=200
  volumes:
    - cortex-citus-w3-data:/var/lib/postgresql/data
  healthcheck:
    test: ["CMD-SHELL", "pg_isready -U cortex -d cortexdb"]
    interval: 5s
    timeout: 3s
    retries: 5
  depends_on:
    relational-core:
      condition: service_healthy
  networks:
    - cortex-net
```

2. Add the volume:

```yaml
volumes:
  cortex-citus-w3-data:
```

3. Start and register the worker:

```bash
# Start the new worker
docker compose up -d citus-worker-3

# Register it with the coordinator
docker exec cortex-relational psql -U cortex -d cortexdb -c \
  "SELECT citus_add_node('citus-worker-3', 5432);"

# Rebalance shards across all workers
docker exec cortex-relational psql -U cortex -d cortexdb -c \
  "SELECT citus_rebalance_start();"

# Monitor rebalance progress
docker exec cortex-relational psql -U cortex -d cortexdb -c \
  "SELECT * FROM citus_rebalance_status();"
```

**Add a read replica (for relational-core):**

```yaml
relational-replica:
  <<: *common
  image: citusdata/citus:12.1
  container_name: cortex-relational-replica
  environment:
    - POSTGRES_USER=cortex
    - POSTGRES_PASSWORD=${POSTGRES_PASSWORD:-cortex_secret}
    - PGDATA=/var/lib/postgresql/data
  command: >
    bash -c "
    until pg_basebackup -h relational-core -U cortex -D /var/lib/postgresql/data -Fp -Xs -R; do
      sleep 5
    done
    postgres
    "
  depends_on:
    relational-core:
      condition: service_healthy
  networks:
    - cortex-net
```

---

## Health Checks

### Health Endpoint Reference

| Endpoint | Port | Purpose | Expected Response |
|----------|------|---------|-------------------|
| `GET /health/live` | 5401 | Liveness probe: is the process running? | `200 OK` |
| `GET /health/ready` | 5401 | Readiness probe: can it serve requests? | `200 OK` or `503` |
| `GET /health/deep` | 5401 | Deep health: all subsystems checked | Full JSON status |
| `GET /health/metrics` | 5401 | Prometheus-format metrics | Metrics text |

### Checking Health

```bash
# Quick liveness check
curl -sf http://localhost:5401/health/live && echo "LIVE" || echo "DOWN"

# Readiness (checks all backend connections)
curl -s http://localhost:5401/health/ready | jq .

# Deep health (full subsystem report)
curl -s http://localhost:5401/health/deep | jq .

# Individual backend checks
docker exec cortex-relational pg_isready -U cortex -d cortexdb
docker exec cortex-memory redis-cli -a "${REDIS_PASSWORD:-cortex_redis_secret}" ping
docker exec cortex-stream redis-cli -p 6380 -a "${STREAM_PASSWORD:-cortex_stream_secret}" ping
curl -s http://localhost:6333/healthz
```

### Decision Tree

```
/health/live returns 200?
  NO  --> Container is crashed or hung. Restart: docker compose restart cortex-router
  YES --> /health/ready returns 200?
            NO  --> One or more backends are unreachable.
                    Check /health/deep for details.
                    Check individual backends (see commands above).
                    If a backend is down, restart it.
                    If all backends are up but ready fails, restart the router.
            YES --> /health/deep shows warnings?
                      NO  --> System is fully healthy. No action needed.
                      YES --> Review warnings:
                              - "high_latency": Check DB query load, consider scaling.
                              - "memory_pressure": Check Redis maxmemory, eviction rate.
                              - "disk_usage_high": Run VACUUM or expand storage.
                              - "replication_lag": Check replica status, network.
                              Take action based on specific warning.
```

### Status Definitions

- **healthy**: All subsystems responding within thresholds. No action needed.
- **degraded**: One or more subsystems responding slowly or with warnings. Investigate within 30 minutes.
- **unhealthy**: One or more subsystems unreachable or failing. Immediate action required.

---

## Common Operations

### Adding a New Agent

```bash
# Register via the A2A API
curl -X POST http://localhost:5400/v1/a2a/register \
  -H "Content-Type: application/json" \
  -H "X-Cortex-Admin-Token: ${CORTEX_ADMIN_TOKEN}" \
  -d '{
    "agent_id": "my-agent-001",
    "name": "My Custom Agent",
    "description": "Handles data transformation tasks",
    "capabilities": ["transform", "validate"],
    "endpoint": "http://my-agent:8080"
  }'

# Verify registration
curl -s http://localhost:5400/v1/a2a/agents | jq '.[] | select(.agent_id == "my-agent-001")'
```

### Updating LLM Provider Configuration

LLM provider keys are set via environment variables on the cortex-router:

```bash
# Update .env file
# ANTHROPIC_API_KEY=sk-ant-...
# OPENAI_API_KEY=sk-...
# OLLAMA_BASE_URL=http://host.docker.internal:11434

# Restart router to pick up changes
docker compose restart cortex-router
```

### Rotating API Keys and Secrets

```bash
# 1. Generate new secrets
NEW_SECRET=$(openssl rand -hex 64)
NEW_REDIS_PW=$(openssl rand -hex 32)
NEW_STREAM_PW=$(openssl rand -hex 32)
NEW_PG_PW=$(openssl rand -hex 32)

# 2. Update .env file with new values
# CORTEX_SECRET_KEY=${NEW_SECRET}
# REDIS_PASSWORD=${NEW_REDIS_PW}
# STREAM_PASSWORD=${NEW_STREAM_PW}
# POSTGRES_PASSWORD=${NEW_PG_PW}

# 3. For Redis password rotation (requires updating both Redis and all clients)
docker exec cortex-memory redis-cli -a "${OLD_REDIS_PASSWORD}" \
  CONFIG SET requirepass "${NEW_REDIS_PW}"

# 4. For PostgreSQL password rotation
docker exec cortex-relational psql -U cortex -d cortexdb -c \
  "ALTER USER cortex PASSWORD '${NEW_PG_PW}';"

# 5. Restart all services to pick up new credentials
docker compose down && docker compose up -d
```

### Clearing Caches (Redis Flush)

```bash
# Flush memory-core cache (sessions, query cache)
# WARNING: This invalidates all sessions and cached queries
docker exec cortex-memory redis-cli -a "${REDIS_PASSWORD:-cortex_redis_secret}" FLUSHDB

# Flush only keys matching a pattern (safer)
docker exec cortex-memory redis-cli -a "${REDIS_PASSWORD:-cortex_redis_secret}" \
  --scan --pattern "cache:*" | xargs -I {} \
  docker exec cortex-memory redis-cli -a "${REDIS_PASSWORD:-cortex_redis_secret}" DEL {}

# Check memory usage before/after
docker exec cortex-memory redis-cli -a "${REDIS_PASSWORD:-cortex_redis_secret}" INFO memory | grep used_memory_human
```

### Reindexing Vector Data

```bash
# Check current Qdrant collections
curl -s http://localhost:6333/collections | jq .

# Get collection info
curl -s http://localhost:6333/collections/{collection_name} | jq .

# Trigger reindex via admin API
curl -X POST http://localhost:5402/admin/plasticity/decay \
  -H "X-Cortex-Admin-Token: ${CORTEX_ADMIN_TOKEN}"

# Force AI index rebuild
curl -X POST http://localhost:5400/v1/admin/reindex \
  -H "X-Cortex-Admin-Token: ${CORTEX_ADMIN_TOKEN}"
```

### Database Maintenance

```bash
# VACUUM ANALYZE (reclaim space and update statistics)
docker exec cortex-relational psql -U cortex -d cortexdb -c "VACUUM ANALYZE;"

# VACUUM FULL on a specific table (locks table, use during maintenance window)
docker exec cortex-relational psql -U cortex -d cortexdb -c "VACUUM FULL table_name;"

# REINDEX a specific index
docker exec cortex-relational psql -U cortex -d cortexdb -c "REINDEX INDEX index_name;"

# REINDEX entire database (long operation)
docker exec cortex-relational psql -U cortex -d cortexdb -c "REINDEX DATABASE cortexdb;"

# Check table sizes
docker exec cortex-relational psql -U cortex -d cortexdb -c "
  SELECT schemaname, tablename,
         pg_size_pretty(pg_total_relation_size(schemaname || '.' || tablename)) AS total_size
  FROM pg_tables
  WHERE schemaname = 'public'
  ORDER BY pg_total_relation_size(schemaname || '.' || tablename) DESC
  LIMIT 20;
"

# Check index usage
docker exec cortex-relational psql -U cortex -d cortexdb -c "
  SELECT indexrelname, idx_scan, idx_tup_read, idx_tup_fetch,
         pg_size_pretty(pg_relation_size(indexrelid)) AS index_size
  FROM pg_stat_user_indexes
  ORDER BY idx_scan ASC
  LIMIT 20;
"

# Run on Citus workers too
for w in cortex-citus-worker-1 cortex-citus-worker-2; do
  docker exec $w psql -U cortex -d cortexdb -c "VACUUM ANALYZE;"
done
```

### Log Rotation

Docker json-file logging is already configured in docker-compose.yml with:
- Max size: 10 MB per log file
- Max files: 3

To view and manage logs:

```bash
# View recent logs
docker compose logs --tail 200 cortex-router

# Follow logs in real time
docker compose logs -f cortex-router

# Check log file sizes on disk
du -sh /var/lib/docker/containers/*/

# Force log truncation (if needed)
truncate -s 0 $(docker inspect --format='{{.LogPath}}' cortex-router)
```

### Checking Disk Usage

```bash
# Docker volume usage
docker system df -v

# Per-volume sizes
for vol in cortex-pg-data cortex-redis-data cortex-stream-data cortex-vector-data cortex-immutable cortex-cache; do
  echo "$vol: $(docker run --rm -v ${vol}:/data alpine du -sh /data 2>/dev/null | cut -f1)"
done

# PostgreSQL database size
docker exec cortex-relational psql -U cortex -d cortexdb -c "
  SELECT pg_size_pretty(pg_database_size('cortexdb')) AS database_size;
"

# Redis memory usage
docker exec cortex-memory redis-cli -a "${REDIS_PASSWORD:-cortex_redis_secret}" INFO memory | grep used_memory_human

# Qdrant storage
curl -s http://localhost:6333/collections | jq '[.result.collections[].name] as $names | $names'
```

---

## Monitoring

### Key Metrics to Watch

| Metric | Warning Threshold | Critical Threshold |
|--------|-------------------|-------------------|
| Router CPU | > 70% sustained | > 90% sustained |
| Router memory | > 75% of 2 GB limit | > 90% of 2 GB limit |
| PostgreSQL connections | > 200 of 300 max | > 270 of 300 max |
| PostgreSQL disk usage | > 70% of volume | > 85% of volume |
| Redis memory | > 400 MB of 512 MB | > 480 MB of 512 MB |
| Redis eviction rate | > 100/s | > 1000/s |
| Stream-core memory | > 200 MB of 256 MB | > 240 MB of 256 MB |
| Qdrant memory | > 750 MB of 1 GB | > 900 MB of 1 GB |
| Query latency (p95) | > 200 ms | > 1000 ms |
| Error rate (5xx) | > 1% of requests | > 5% of requests |
| Disk I/O wait | > 20% | > 40% |

### Prometheus Queries for Common Checks

```promql
# Request rate (per second)
rate(cortex_http_requests_total[5m])

# Error rate percentage
100 * rate(cortex_http_requests_total{status=~"5.."}[5m]) / rate(cortex_http_requests_total[5m])

# Query latency p95
histogram_quantile(0.95, rate(cortex_query_duration_seconds_bucket[5m]))

# Query latency p99
histogram_quantile(0.99, rate(cortex_query_duration_seconds_bucket[5m]))

# Active database connections
cortex_db_connections_active

# Redis memory usage
cortex_redis_used_memory_bytes

# Redis eviction rate
rate(cortex_redis_evicted_keys_total[5m])

# Vector search latency
histogram_quantile(0.95, rate(cortex_vector_search_duration_seconds_bucket[5m]))

# Circuit breaker state (0=closed, 1=open, 2=half-open)
cortex_circuit_breaker_state

# Agent execution count
rate(cortex_agent_executions_total[5m])
```

### Grafana Dashboard Recommendations

If using the observability profile, Grafana is available at `http://localhost:3000`.

Recommended dashboards:

1. **CortexDB Overview** - Request rate, error rate, latency percentiles, active connections
2. **PostgreSQL / Citus** - Connection pool, query throughput, replication lag, table sizes, lock waits
3. **Redis** - Memory usage, hit/miss ratio, eviction rate, connected clients, command latency
4. **Qdrant Vector** - Collection sizes, search latency, indexing throughput
5. **Infrastructure** - CPU, memory, disk I/O, network per container

Import community dashboards:
- PostgreSQL: Grafana ID `9628`
- Redis: Grafana ID `11835`
- Docker containers: Grafana ID `893`

---

## Scaling Guide

### When to Scale

| Indicator | Action |
|-----------|--------|
| Query latency p95 > 500 ms consistently | Add Citus workers or optimize queries |
| PostgreSQL connections > 80% of max | Increase max_connections or add PgBouncer |
| Redis eviction rate increasing | Increase maxmemory or add Redis cluster nodes |
| Qdrant search latency > 100 ms at p95 | Add vector-core replicas or reduce collection sizes |
| Router CPU > 80% sustained | Scale router horizontally (load balancer + multiple instances) |
| Disk usage > 70% | Expand volumes or archive old data |

### Horizontal Scaling (More Workers)

**Citus workers (database sharding):**

See [Scaling Services](#scaling-services-adding-citus-workers) above for adding workers.

**Multiple router instances (behind load balancer):**

```yaml
# In docker-compose.override.yml
cortex-router-2:
  <<: *common
  build:
    context: .
    dockerfile: Dockerfile
  container_name: cortex-router-2
  ports:
    - "5410:5400"
    - "5411:5401"
  environment:
    # Same env vars as cortex-router
  depends_on:
    relational-core:
      condition: service_healthy
    memory-core:
      condition: service_healthy
    stream-core:
      condition: service_healthy
  networks:
    - cortex-net
```

Place an nginx or HAProxy in front:

```nginx
upstream cortex_api {
    least_conn;
    server cortex-router:5400;
    server cortex-router-2:5400;
}

server {
    listen 5400;
    location / {
        proxy_pass http://cortex_api;
        proxy_connect_timeout 5s;
        proxy_read_timeout 60s;
    }
}
```

### Vertical Scaling (Resource Limits)

Adjust resource limits in `docker-compose.yml` under `deploy.resources`:

```yaml
# Example: increase relational-core limits
relational-core:
  deploy:
    resources:
      limits:
        cpus: "8.0"    # was 4.0
        memory: 8G      # was 4G
      reservations:
        cpus: "2.0"    # was 1.0
        memory: 2G      # was 1G
```

Update PostgreSQL tuning to match:

```bash
docker exec cortex-relational psql -U cortex -d cortexdb -c "
  ALTER SYSTEM SET shared_buffers = '2GB';
  ALTER SYSTEM SET effective_cache_size = '6GB';
  ALTER SYSTEM SET work_mem = '64MB';
  ALTER SYSTEM SET maintenance_work_mem = '512MB';
"
docker compose restart relational-core
```

### Database Connection Pooling Tuning

For high-connection environments, add PgBouncer:

```yaml
pgbouncer:
  <<: *common
  image: edoburu/pgbouncer:latest
  container_name: cortex-pgbouncer
  ports:
    - "6432:6432"
  environment:
    - DATABASE_URL=postgresql://cortex:${POSTGRES_PASSWORD:-cortex_secret}@relational-core:5432/cortexdb
    - POOL_MODE=transaction
    - MAX_CLIENT_CONN=1000
    - DEFAULT_POOL_SIZE=50
    - MIN_POOL_SIZE=10
    - RESERVE_POOL_SIZE=10
  depends_on:
    relational-core:
      condition: service_healthy
  networks:
    - cortex-net
```

Then update `RELATIONAL_CORE_URL` for cortex-router to point to `pgbouncer:6432` instead of `relational-core:5432`.

Key PgBouncer settings:

| Setting | Recommendation | Notes |
|---------|---------------|-------|
| `POOL_MODE` | `transaction` | Best for most workloads |
| `DEFAULT_POOL_SIZE` | 50-100 | Per-database pool |
| `MAX_CLIENT_CONN` | 1000-5000 | Max frontend connections |
| `RESERVE_POOL_SIZE` | 10 | Emergency overflow |
| `SERVER_IDLE_TIMEOUT` | 600 | Close idle backend connections |
