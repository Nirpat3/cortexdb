# CortexDB™ Support & Troubleshooting Guide

---

## Table of Contents

1. [Getting Help](#1-getting-help)
2. [Frequently Asked Questions](#2-frequently-asked-questions)
3. [Common Issues & Solutions](#3-common-issues--solutions)
4. [Health Diagnostics](#4-health-diagnostics)
5. [Performance Troubleshooting](#5-performance-troubleshooting)
6. [Data Recovery](#6-data-recovery)
7. [Compliance Questions](#7-compliance-questions)
8. [Upgrade Guide](#8-upgrade-guide)
9. [Support Tiers](#9-support-tiers)
10. [Reporting Issues](#10-reporting-issues)

---

## 1. Getting Help

### Resources

| Resource | URL | Best For |
|----------|-----|----------|
| Documentation | `docs/` directory | API reference, architecture |
| Developer Guide | `docs/DEVELOPER-GUIDE.md` | Integration help |
| Docker Guide | `docs/DOCKER-GUIDE.md` | Deployment issues |
| GitHub Issues | github.com/nirlab/cortexdb/issues | Bug reports |
| Email Support | support@nirlab.com | Enterprise customers |

### Quick Diagnostics

Run this first when something seems wrong:

```bash
# 1. Are all containers running?
docker compose ps

# 2. Is the API responding?
curl http://localhost:5400/health/live

# 3. Are all engines connected?
curl http://localhost:5400/health/ready

# 4. Deep health check (shows everything)
curl http://localhost:5400/health/deep | python -m json.tool

# 5. Check container logs for errors
docker compose logs --tail=50 cortex-router
docker compose logs --tail=50 relational-core
```

---

## 2. Frequently Asked Questions

### General

**Q: What databases does CortexDB replace?**
A: PostgreSQL (relational), Redis (cache), Pinecone/Weaviate (vectors), Neo4j (graph), TimescaleDB (time-series), Kafka (streaming), Hyperledger (ledger). All seven consolidated into one system.

**Q: Is CortexDB production-ready?**
A: CortexDB v4.0 is designed for production use with built-in compliance (FedRAMP, HIPAA, PCI-DSS), horizontal sharding, and self-healing. Follow the [Production Deployment](DOCKER-GUIDE.md#6-production-deployment) guide.

**Q: What's the maximum dataset size?**
A: With Citus sharding, CortexDB scales to petabytes. Each worker node handles its shard independently. Add workers to scale linearly.

**Q: Can I use standard SQL?**
A: Yes. CortexQL is a superset of PostgreSQL SQL. All standard queries work. CortexQL adds extensions like `FIND SIMILAR`, `TRAVERSE`, and `SUBSCRIBE`.

**Q: Does it work without Docker?**
A: Yes. Install dependencies from `requirements.txt`, set up PostgreSQL/Redis/Qdrant manually, configure environment variables, and run `uvicorn cortexdb.server:app`.

### Architecture

**Q: How does multi-tenancy work?**
A: Every request includes a tenant API key. CortexDB sets PostgreSQL Row-Level Security context (`SET app.current_tenant`), prefixes Redis keys, isolates Qdrant collections, and uses per-tenant encryption keys. Cross-tenant data access is impossible at the database level.

**Q: What happens if an engine goes down?**
A: CortexDB degrades gracefully. If Redis is down, R1 cache is skipped. If Qdrant is down, R2 semantic cache is skipped. RelationalCore (PostgreSQL) is the primary engine — if it's down, the system returns 503. The Grid repair engine automatically detects and recovers failed components.

**Q: How does the cache work?**
A: 5-tier read cascade:
- R0: Process memory (< 0.1ms, 10K entries)
- R1: Redis (< 1ms)
- R2: Semantic/VectorCore (< 5ms, cosine similarity > 0.95)
- R3: PostgreSQL (< 50ms)
- R4: Cross-engine deep retrieval

Writes automatically invalidate caches. Target: 75-85% cache hit rate.

**Q: What is the Sleep Cycle?**
A: Nightly maintenance that runs 6 tasks: prune expired data, consolidate segments, rebuild indexes, precompute hot queries, decay unused paths, and analyze statistics. Runs at 2 AM by default.

### CortexGraph

**Q: What's the difference between deterministic and probabilistic identity matching?**
A: Deterministic matching is exact: if the email or phone matches, it's the same customer (confidence = 1.0). Probabilistic matching uses VectorCore embeddings to find similar attribute combinations (confidence > 0.92 = auto-merge, 0.85-0.92 = human review needed).

**Q: How does churn prediction work?**
A: CortexDB uses a heuristic model based on RFM (Recency, Frequency, Monetary):
- Recency > 90 days: +40% churn score
- Frequency = 0 in 90 days: +30%
- Monetary < $50 in 90 days: +20%

Production systems can upgrade to XGBoost or neural models.

### Sharding

**Q: What is Citus?**
A: Citus is a PostgreSQL extension that distributes tables across multiple PostgreSQL nodes. The coordinator receives queries and routes them to the correct worker nodes. Results are merged transparently. Your SQL doesn't change.

**Q: Why distribute on tenant_id?**
A: Multi-tenant SaaS pattern. Each tenant's data lives on one worker node, so:
- All tenant queries go to one node (fast)
- JOINs within a tenant stay local (no network hop)
- Tenant isolation is physical (different shards)

**Q: Can I shard on a different column?**
A: Yes. Modify `DISTRIBUTED_TABLES` in `cortexdb/scale/sharding.py`. Common alternatives: `customer_id` (per-customer isolation), `region` (geo-sharding), `created_at` (time-based).

---

## 3. Common Issues & Solutions

### Issue: `Connection refused` on port 5400

**Cause**: CortexDB router hasn't started yet.

**Solution**:
```bash
# Check if container is running
docker compose ps cortex-router

# Check logs
docker compose logs cortex-router

# If "depends_on" is waiting for PostgreSQL:
docker compose logs relational-core

# Restart
docker compose restart cortex-router
```

### Issue: `CortexDB not ready` (503 on /health/ready)

**Cause**: One or more engines failed to connect.

**Solution**:
```bash
# Check which engine is down
curl http://localhost:5400/health/deep | python -m json.tool | grep -A3 '"status"'

# Common: PostgreSQL not ready yet
docker compose logs relational-core | tail -20

# Common: Redis auth failed
docker exec cortex-memory redis-cli -a cortex_redis_secret PING
```

### Issue: `Rate limit exceeded` (429)

**Cause**: Tenant exceeded their plan's rate limit.

**Solution**:
```bash
# Check rate limit headers
curl -v http://localhost:5400/v1/query ...

# Headers show:
# X-RateLimit-Limit: 600
# X-RateLimit-Remaining: 0
# Retry-After: 30

# Upgrade tenant plan or wait
```

### Issue: `BLOCKED_BY_AMYGDALA`

**Cause**: Query triggered SQL injection detection.

**Solution**: Review your query for SQL injection patterns. Common false positives:
- Legitimate use of `1=1` in WHERE clauses → restructure query
- Long queries with many quotes → use parameterized queries
- Queries over 10KB → split into smaller queries

### Issue: Slow queries

**Solution**:
```bash
# 1. Check cache hit rate
curl http://localhost:5400/admin/cache/stats

# 2. Get index recommendations
curl http://localhost:5400/v1/admin/indexes/recommend

# 3. Create recommended indexes
curl -X POST http://localhost:5400/v1/admin/indexes/create

# 4. Check if query is using cache
POST /v1/query {"cortexql": "...", "hint": "cache_first"}
```

### Issue: Disk space full

**Solution**:
```bash
# Check what's using space
docker system df -v

# PostgreSQL table sizes
docker exec cortex-relational psql -U cortex -d cortexdb \
  -c "SELECT relname, pg_size_pretty(pg_total_relation_size(oid)) AS size FROM pg_class WHERE relkind = 'r' ORDER BY pg_total_relation_size(oid) DESC LIMIT 20"

# Trigger Sleep Cycle to prune old data
curl -X POST http://localhost:5400/admin/sleep-cycle/run

# Clean Docker
docker system prune -f
```

### Issue: Citus sharding errors

**Solution**:
```bash
# Check if Citus extension is loaded
docker exec cortex-relational psql -U cortex -d cortexdb \
  -c "SELECT * FROM citus_version()"

# Check distributed tables
docker exec cortex-relational psql -U cortex -d cortexdb \
  -c "SELECT * FROM citus_tables"

# Check worker connectivity
docker exec cortex-relational psql -U cortex -d cortexdb \
  -c "SELECT * FROM citus_get_active_worker_nodes()"
```

---

## 4. Health Diagnostics

### Interpreting /health/deep

```json
{
  "status": "healthy",          // "healthy", "degraded", or "unhealthy"
  "version": "4.0.0",
  "uptime_seconds": 86400,
  "queries_total": 150234,

  "engines": {
    "relational": {"status": "healthy"},   // PostgreSQL
    "memory": {"status": "healthy"},       // Redis cache
    "vector": {"status": "healthy"},       // Qdrant
    "stream": {"status": "healthy"},       // Redis streams
    "temporal": {"status": "healthy"},     // TimescaleDB
    "immutable": {"status": "healthy"},    // Append-only ledger
    "graph": {"status": "healthy"}         // Apache AGE
  },

  "cache": {
    "r0_hit_rate": 45.2,         // Target: > 30%
    "r1_hits": 8234,
    "r0_size": 5432              // R0 entries cached
  },

  "amygdala": {
    "checks_total": 150234,
    "blocks_total": 12           // Threats blocked
  },

  "sharding": {
    "initialized": true,
    "shard_count": 128,
    "workers": 2
  },

  "compliance": {
    "frameworks": 5,
    "total_controls": 39
  }
}
```

### Status Meanings

| Status | Meaning | Action |
|--------|---------|--------|
| `healthy` | All engines connected | None |
| `degraded` | Some engines unavailable | Check failed engine logs |
| `unhealthy` | Critical engine down | Immediate investigation |

---

## 5. Performance Troubleshooting

### Step 1: Identify the Bottleneck

```bash
# Cache hit rate (should be > 60%)
curl http://localhost:5400/admin/cache/stats

# If low: queries not being cached
# Solution: check if queries use parameterized values (helps caching)
```

### Step 2: Check Query Performance

```bash
# AI index recommendations
curl http://localhost:5400/v1/admin/indexes/recommend

# Slow queries from pg_stat_statements
curl http://localhost:5400/v1/admin/indexes/slow-queries
```

### Step 3: Optimize

| Symptom | Solution |
|---------|----------|
| Low cache hit rate | Use `hint: "cache_first"` for read-heavy queries |
| Sequential scans | Create indexes: `POST /v1/admin/indexes/create` |
| High latency on large tables | Enable sharding: `POST /v1/admin/sharding/distribute` |
| Slow vector search | Tune HNSW: `POST /v1/admin/indexes/tune-vector` |
| Response too large | Use pagination: `LIMIT` + cursor-based pagination |

### Step 4: Monitor

```bash
# Prometheus metrics
curl http://localhost:5400/health/metrics

# Grafana dashboards
open http://localhost:3000
```

---

## 6. Data Recovery

### Scenario: Accidental Data Deletion

CortexDB's ImmutableCore prevents ledger deletion. For other tables:

```bash
# PostgreSQL point-in-time recovery (if WAL archiving enabled)
docker exec cortex-relational psql -U cortex -d cortexdb \
  -c "SELECT * FROM pg_stat_archiver"

# Restore from backup
docker exec -i cortex-relational psql -U cortex -d cortexdb < backup.sql
```

### Scenario: Corrupted Ledger

```bash
# Verify chain integrity
curl -X POST http://localhost:5400/admin/ledger/verify

# If chain_intact = false:
# The broken_at field shows which entry was corrupted
# Contact support for chain repair procedure
```

### Scenario: Lost Encryption Keys

If `CORTEX_MASTER_KEY` is lost, encrypted fields cannot be decrypted.

**Prevention**:
- Store master key in a secrets manager (AWS Secrets Manager, Vault)
- Back up key rotation metadata
- Test recovery procedure quarterly

---

## 7. Compliance Questions

**Q: How do I prepare for a SOC 2 audit?**
```bash
# 1. Run compliance audit
curl http://localhost:5400/v1/compliance/audit/soc2

# 2. Generate evidence report
curl http://localhost:5400/v1/compliance/evidence/soc2

# 3. Review gaps and remediate
# 4. Verify encryption key rotation
curl http://localhost:5400/v1/compliance/encryption/stats
```

**Q: How do I prove HIPAA compliance?**
```bash
# 1. Verify PHI encryption is active
curl http://localhost:5400/v1/compliance/encryption/classification/customers

# 2. Check audit trail for PHI access
curl "http://localhost:5400/v1/compliance/audit-log?event_type=PHI_ACCESS"

# 3. Verify ledger integrity
curl -X POST http://localhost:5400/admin/ledger/verify

# 4. Generate evidence report
curl http://localhost:5400/v1/compliance/evidence/hipaa
```

**Q: Is CortexDB PCI compliant?**
```bash
# Run PCI audit
curl http://localhost:5400/v1/compliance/audit/pci_dss

# Key controls verified:
# - PAN encryption (AES-256-GCM)
# - Tamper-evident audit trail
# - SQL injection protection (Amygdala)
# - Key rotation (90-day schedule)
```

---

## 8. Upgrade Guide

### v3.0 → v4.0

**New features**: Citus sharding, compliance framework, AI indexing, field encryption, data rendering.

**Steps**:
```bash
# 1. Backup everything
./backup.sh

# 2. Pull new images
docker compose pull

# 3. Run database migrations (new tables)
docker exec cortex-relational psql -U cortex -d cortexdb \
  -f /docker-entrypoint-initdb.d/01-init.sql

# 4. Initialize new features
curl -X POST http://localhost:5400/v1/admin/sharding/initialize

# 5. Verify
curl http://localhost:5400/health/deep
```

**Breaking changes**: None. v4.0 is backward-compatible with v3.0 APIs.

### General Upgrade Process

1. Always backup before upgrading
2. Read the changelog for breaking changes
3. Test in staging environment first
4. Use rolling restart for zero-downtime upgrades
5. Verify health after upgrade

---

## 9. Support Tiers

| Tier | Response Time | Channels | Price |
|------|--------------|----------|-------|
| **Community** | Best effort | GitHub Issues, Docs | Free |
| **Developer** | 24 hours | Email + GitHub | $99/mo |
| **Business** | 4 hours | Email + Slack + Phone | $499/mo |
| **Enterprise** | 1 hour | Dedicated Slack + Phone + On-call | Custom |

### Enterprise Support Includes

- Dedicated Slack channel with CortexDB engineers
- Monthly architecture review
- Compliance audit assistance
- Custom feature prioritization
- On-call incident response (15-minute SLA)
- Quarterly performance tuning session

---

## 10. Reporting Issues

### Bug Reports

Include the following information:

```markdown
## Environment
- CortexDB Version: 4.0.0
- OS: Ubuntu 22.04 / macOS 14 / Windows 11
- Docker Version: 24.0.7
- RAM: 16 GB
- Deployment: Docker Compose / Kubernetes

## Steps to Reproduce
1. ...
2. ...
3. ...

## Expected Behavior
...

## Actual Behavior
...

## Logs
```bash
docker compose logs cortex-router --tail=100
```

## Health Check Output
```json
curl http://localhost:5400/health/deep
```
```

### Collecting Diagnostics

```bash
# Full diagnostic bundle
echo "=== Docker Compose ===" > diagnostics.txt
docker compose ps >> diagnostics.txt
echo "=== Health ===" >> diagnostics.txt
curl -s http://localhost:5400/health/deep >> diagnostics.txt
echo "=== Logs ===" >> diagnostics.txt
docker compose logs --tail=200 >> diagnostics.txt
echo "=== Disk ===" >> diagnostics.txt
docker system df >> diagnostics.txt
```

---

*CortexDB™ — We're here to help.*
*Copyright (c) 2026 Nirlab Inc.*
