# CortexDB Incident Response Playbook

Version: 1.0
Last Updated: 2026-03-08

---

## Table of Contents

1. [Severity Levels](#severity-levels)
2. [Incident Workflow](#incident-workflow)
3. [Incident Playbooks](#incident-playbooks)
4. [Post-Mortem Template](#post-mortem-template)

---

## Severity Levels

| Level | Name | Definition | Response Time | Update Cadence |
|-------|------|-----------|---------------|----------------|
| P1 | Critical | Full outage. All users affected. Data loss risk. | 15 minutes | Every 30 minutes |
| P2 | High | Partial outage. Major feature broken or significant performance degradation. | 30 minutes | Every 1 hour |
| P3 | Medium | Single service down. Workarounds available. Limited user impact. | 2 hours | Every 4 hours |
| P4 | Low | Minor issue. No user-facing impact. Cosmetic or monitoring-only. | Next business day | As resolved |

### Severity Decision Matrix

```
Data loss occurring or imminent?         --> P1
All users unable to query or write?      --> P1
>50% of queries failing?                 --> P1
One backend down, queries degraded?      --> P2
Dashboard unreachable but API works?     --> P2
Single non-critical service down?        --> P3
Performance slightly degraded?           --> P3
Monitoring alert, no user impact?        --> P4
```

---

## Incident Workflow

### Phase 1: Detection

Sources of detection:
- Automated health check failures (Docker healthcheck, Prometheus alerts)
- Grafana alert notifications
- User reports via dashboard or support channels
- Log anomalies (error rate spikes)

### Phase 2: Triage

1. Confirm the issue is real (not a false alarm).
2. Determine severity using the matrix above.
3. Assign an Incident Commander (IC).
4. Open an incident channel (Slack, Teams, or equivalent).

```
Checklist:
[ ] Issue confirmed
[ ] Severity assigned: P__
[ ] Incident Commander: ___
[ ] Communication channel opened
[ ] Stakeholders notified
```

### Phase 3: Mitigate

Goal: Restore service as fast as possible. Root cause comes later.

Common mitigation actions:
- Restart the failing service
- Failover to a replica
- Increase resource limits
- Roll back a recent deployment
- Block malicious traffic

### Phase 4: Resolve

Goal: Fix the root cause so the incident does not recur.

- Identify the root cause
- Apply a permanent fix
- Verify the fix in staging if possible
- Deploy the fix to production
- Confirm all monitoring is green

### Phase 5: Post-Mortem

Conducted within 48 hours of resolution. See [Post-Mortem Template](#post-mortem-template).

### Communication Templates

**Initial notification (internal):**

```
INCIDENT DECLARED - P[SEVERITY]
Title: [Brief description]
Impact: [Who is affected, what is broken]
Status: Investigating
IC: [Name]
Channel: [Link]
Next update: [Time]
```

**Status update:**

```
INCIDENT UPDATE - P[SEVERITY] - [Title]
Status: [Investigating | Mitigating | Monitoring | Resolved]
Current state: [What we know now]
Actions taken: [What we have done]
Next steps: [What we are doing next]
Next update: [Time]
```

**Resolution notification:**

```
INCIDENT RESOLVED - P[SEVERITY] - [Title]
Duration: [Start time] to [End time] ([total duration])
Impact: [Summary of impact]
Root cause: [Brief root cause]
Post-mortem: Scheduled for [Date]
```

### Escalation Paths

| Severity | First Responder | Escalation (30 min) | Escalation (1 hr) |
|----------|----------------|---------------------|-------------------|
| P1 | On-call engineer | Engineering lead | CTO / VP Engineering |
| P2 | On-call engineer | Engineering lead | - |
| P3 | Assigned engineer | On-call engineer | - |
| P4 | Backlog triage | - | - |

---

## Incident Playbooks

### 1. Database Connection Exhaustion

**Symptoms:**
- Queries timing out or returning `too many connections` errors
- `/health/ready` returns 503
- `/health/deep` shows `connections_active` near 300
- Application logs: `FATAL: too many connections for role "cortex"`

**Diagnosis:**

```bash
# Check active connections
docker exec cortex-relational psql -U cortex -d cortexdb -c "
  SELECT count(*) AS total,
         state,
         usename,
         application_name
  FROM pg_stat_activity
  GROUP BY state, usename, application_name
  ORDER BY total DESC;
"

# Check waiting queries
docker exec cortex-relational psql -U cortex -d cortexdb -c "
  SELECT pid, now() - pg_stat_activity.query_start AS duration, query, state, wait_event_type
  FROM pg_stat_activity
  WHERE state != 'idle'
  ORDER BY duration DESC
  LIMIT 20;
"

# Check for locks
docker exec cortex-relational psql -U cortex -d cortexdb -c "
  SELECT blocked_locks.pid AS blocked_pid,
         blocking_locks.pid AS blocking_pid,
         blocked_activity.query AS blocked_query,
         blocking_activity.query AS blocking_query
  FROM pg_catalog.pg_locks blocked_locks
  JOIN pg_catalog.pg_stat_activity blocked_activity ON blocked_activity.pid = blocked_locks.pid
  JOIN pg_catalog.pg_locks blocking_locks ON blocking_locks.locktype = blocked_locks.locktype
    AND blocking_locks.relation = blocked_locks.relation
    AND blocking_locks.pid != blocked_locks.pid
  JOIN pg_catalog.pg_stat_activity blocking_activity ON blocking_activity.pid = blocking_locks.pid
  WHERE NOT blocked_locks.granted;
"
```

**Mitigation:**

```bash
# Kill idle connections older than 5 minutes
docker exec cortex-relational psql -U cortex -d cortexdb -c "
  SELECT pg_terminate_backend(pid)
  FROM pg_stat_activity
  WHERE state = 'idle'
    AND query_start < now() - interval '5 minutes'
    AND usename = 'cortex';
"

# Kill long-running queries (over 60 seconds)
docker exec cortex-relational psql -U cortex -d cortexdb -c "
  SELECT pg_terminate_backend(pid)
  FROM pg_stat_activity
  WHERE state = 'active'
    AND query_start < now() - interval '60 seconds'
    AND usename = 'cortex'
    AND query NOT LIKE 'autovacuum%';
"
```

**Resolution:**
- Add PgBouncer connection pooler (see runbook Scaling Guide)
- Increase `max_connections` if server resources allow
- Fix application connection leak (ensure connections are returned to pool)

**Prevention:**
- Deploy PgBouncer in production
- Set `idle_in_transaction_session_timeout = '30s'` in PostgreSQL
- Add connection pool monitoring to Grafana
- Set `statement_timeout = '30s'` as a safety net

---

### 2. Redis OOM (Out of Memory)

**Symptoms:**
- Redis returns `OOM command not allowed` errors
- memory-core evicting keys rapidly (cache misses spike)
- `/health/deep` shows Redis memory at or near 512 MB limit
- stream-core with `noeviction` policy rejects writes entirely

**Diagnosis:**

```bash
# Check memory-core usage
docker exec cortex-memory redis-cli -a "${REDIS_PASSWORD:-cortex_redis_secret}" INFO memory

# Check eviction stats
docker exec cortex-memory redis-cli -a "${REDIS_PASSWORD:-cortex_redis_secret}" INFO stats | grep evicted_keys

# Find largest keys
docker exec cortex-memory redis-cli -a "${REDIS_PASSWORD:-cortex_redis_secret}" --bigkeys

# Check stream-core usage
docker exec cortex-stream redis-cli -p 6380 -a "${STREAM_PASSWORD:-cortex_stream_secret}" INFO memory

# Check stream lengths
docker exec cortex-stream redis-cli -p 6380 -a "${STREAM_PASSWORD:-cortex_stream_secret}" \
  --scan --pattern "*" | head -20
```

**Mitigation (memory-core):**

```bash
# Flush non-critical cache data
docker exec cortex-memory redis-cli -a "${REDIS_PASSWORD:-cortex_redis_secret}" \
  --scan --pattern "cache:*" | xargs -L 100 \
  docker exec -i cortex-memory redis-cli -a "${REDIS_PASSWORD:-cortex_redis_secret}" DEL

# Increase maxmemory temporarily
docker exec cortex-memory redis-cli -a "${REDIS_PASSWORD:-cortex_redis_secret}" \
  CONFIG SET maxmemory 768mb
```

**Mitigation (stream-core):**

```bash
# Trim streams to last 10000 entries
docker exec cortex-stream redis-cli -p 6380 -a "${STREAM_PASSWORD:-cortex_stream_secret}" \
  --scan --pattern "*" | while read key; do
    docker exec cortex-stream redis-cli -p 6380 -a "${STREAM_PASSWORD:-cortex_stream_secret}" \
      XTRIM "$key" MAXLEN ~ 10000
  done
```

**Resolution:**
- Increase maxmemory in docker-compose.yml and container memory limits
- Review TTLs on cached data (ensure all cache keys have expiry)
- Add stream trimming to a scheduled job

**Prevention:**
- Alert when memory usage exceeds 75% of maxmemory
- Enforce TTL on all cache keys in application code
- Implement automatic stream trimming (MAXLEN on XADD)
- Monitor `evicted_keys` rate in Grafana

---

### 3. Disk Full

**Symptoms:**
- PostgreSQL: `PANIC: could not write to file` or `No space left on device`
- Redis: AOF writes fail, `MISCONF Redis is configured to save RDB snapshots`
- Qdrant: Indexing fails silently
- Docker: containers fail to start

**Diagnosis:**

```bash
# Check host disk usage
df -h

# Check Docker disk usage
docker system df

# Check specific volumes
for vol in cortex-pg-data cortex-redis-data cortex-stream-data cortex-vector-data cortex-immutable; do
  SIZE=$(docker run --rm -v ${vol}:/data alpine du -sh /data 2>/dev/null | cut -f1)
  echo "${vol}: ${SIZE}"
done

# Check PostgreSQL WAL accumulation
docker exec cortex-relational du -sh /var/lib/postgresql/data/pg_wal/

# Check for large tables
docker exec cortex-relational psql -U cortex -d cortexdb -c "
  SELECT tablename, pg_size_pretty(pg_total_relation_size('public.' || tablename)) AS size
  FROM pg_tables WHERE schemaname = 'public'
  ORDER BY pg_total_relation_size('public.' || tablename) DESC LIMIT 10;
"
```

**Mitigation:**

```bash
# Emergency: clean Docker build cache
docker builder prune -f

# Emergency: remove unused images
docker image prune -f

# Emergency: remove stopped containers
docker container prune -f

# Truncate Docker logs
truncate -s 0 $(docker inspect --format='{{.LogPath}}' cortex-router)
truncate -s 0 $(docker inspect --format='{{.LogPath}}' cortex-relational)

# PostgreSQL: force checkpoint and remove old WAL
docker exec cortex-relational psql -U cortex -d cortexdb -c "CHECKPOINT;"

# PostgreSQL: VACUUM to reclaim space
docker exec cortex-relational psql -U cortex -d cortexdb -c "VACUUM FULL;"
```

**Resolution:**
- Expand the disk/volume
- Archive or delete old data
- Set up WAL archiving with retention limits
- Configure log rotation more aggressively

**Prevention:**
- Alert at 70% disk usage
- Automate `VACUUM` on a schedule (e.g., daily cron)
- Set `max_wal_size` appropriately
- Implement data retention policies (DELETE old rows, partition tables)
- Monitor volume growth trends in Grafana

---

### 4. High CPU / Runaway Queries

**Symptoms:**
- Query latency increases dramatically
- CPU usage on relational-core or cortex-router near limits
- `/health/deep` shows high latency warnings
- Slow response from all API endpoints

**Diagnosis:**

```bash
# Check container CPU usage
docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}"

# Find long-running PostgreSQL queries
docker exec cortex-relational psql -U cortex -d cortexdb -c "
  SELECT pid, now() - query_start AS duration, state, query
  FROM pg_stat_activity
  WHERE state = 'active'
  ORDER BY duration DESC
  LIMIT 10;
"

# Check for sequential scans on large tables
docker exec cortex-relational psql -U cortex -d cortexdb -c "
  SELECT relname, seq_scan, seq_tup_read, idx_scan, idx_tup_fetch
  FROM pg_stat_user_tables
  WHERE seq_scan > 0
  ORDER BY seq_tup_read DESC
  LIMIT 10;
"

# Check router process
docker exec cortex-router ps aux | head -20
```

**Mitigation:**

```bash
# Kill the runaway query
docker exec cortex-relational psql -U cortex -d cortexdb -c "
  SELECT pg_terminate_backend(<PID>);
"

# Set a statement timeout to prevent future runaway queries
docker exec cortex-relational psql -U cortex -d cortexdb -c "
  ALTER DATABASE cortexdb SET statement_timeout = '30s';
"

# If router is pegged, restart it
docker compose restart cortex-router
```

**Resolution:**
- Add missing indexes for the expensive queries
- Optimize the query (EXPLAIN ANALYZE)
- Set `statement_timeout` permanently
- Add query plan caching

**Prevention:**
- Enable `pg_stat_statements` extension to track slow queries
- Set default `statement_timeout` of 30 seconds
- Review EXPLAIN plans for new queries before deployment
- Alert on queries running longer than 10 seconds

---

### 5. LLM Provider Outage (Anthropic/OpenAI Down)

**Symptoms:**
- Agent operations that require LLM calls fail
- Logs show connection timeouts or HTTP 5xx from LLM endpoints
- Circuit breaker for LLM provider trips to OPEN state
- `/v1/heartbeat/circuit-breakers` shows open circuits

**Diagnosis:**

```bash
# Check circuit breaker states
curl -s http://localhost:5400/v1/heartbeat/circuit-breakers | jq .

# Check provider status pages externally
# Anthropic: https://status.anthropic.com
# OpenAI: https://status.openai.com

# Check if Ollama local fallback is available
curl -s http://localhost:11434/api/tags | jq .

# Check recent errors in router logs
docker compose logs --tail 500 cortex-router 2>&1 | grep -i "llm\|anthropic\|openai\|provider"
```

**Mitigation:**

```bash
# If Ollama is available, the circuit breaker should route to it automatically.
# Verify Ollama is running and reachable:
curl -s "${OLLAMA_BASE_URL:-http://localhost:11434}/api/tags" | jq .

# If no local fallback, pause agent operations that require LLM:
# (Application-level: disable agent task execution temporarily)

# Manually reset circuit breaker if provider is back
curl -X POST http://localhost:5402/admin/circuit-breaker/reset \
  -H "X-Cortex-Admin-Token: ${CORTEX_ADMIN_TOKEN}" \
  -d '{"provider": "anthropic"}'
```

**Resolution:**
- Wait for provider to recover (monitor their status page)
- Ensure circuit breaker is configured with appropriate thresholds
- Add or configure local Ollama fallback models

**Prevention:**
- Configure multiple LLM providers (Anthropic + OpenAI + Ollama)
- Set up circuit breakers with reasonable thresholds (5 failures, 60s open period)
- Pre-download Ollama models for critical agent tasks
- Cache common LLM responses where appropriate

---

### 6. Dashboard Unreachable

**Symptoms:**
- Cannot access CortexDB admin UI at port 3400
- Browser shows connection refused or timeout
- API endpoints on port 5400 may still work

**Diagnosis:**

```bash
# Check dashboard container status
docker compose ps cortex-dashboard

# Check dashboard logs
docker compose logs --tail 100 cortex-dashboard

# Check if the container is running
docker inspect cortex-dashboard --format='{{.State.Status}}'

# Check if the port is bound
docker port cortex-dashboard

# Test from inside the network
docker exec cortex-dashboard wget -qO- http://localhost:3000/ > /dev/null && echo "OK" || echo "FAIL"

# Check if cortex-router (dependency) is healthy
curl -sf http://localhost:5401/health/live && echo "Router OK" || echo "Router DOWN"
```

**Mitigation:**

```bash
# Restart the dashboard
docker compose restart cortex-dashboard

# If it fails to start, rebuild
docker compose up -d --build cortex-dashboard

# If the router is down (dependency), restart it first
docker compose restart cortex-router
sleep 10
docker compose restart cortex-dashboard
```

**Resolution:**
- Check for build errors in the dashboard Dockerfile
- Verify environment variables (CORTEX_API_URL, CORTEX_ADMIN_URL)
- Check for port conflicts on host port 3400

**Prevention:**
- Add uptime monitoring for the dashboard URL
- Set up a healthcheck alert that fires within 2 minutes of failure

---

### 7. Agent Stuck in Working State

**Symptoms:**
- Agent shows `status: working` for an abnormally long time
- Tasks assigned to the agent are not progressing
- Other agents waiting on results from the stuck agent

**Diagnosis:**

```bash
# List all agents and their statuses
curl -s http://localhost:5400/v1/agents | jq '.[] | select(.status == "working") | {id, name, status, last_heartbeat}'

# Check agent heartbeat history
curl -s http://localhost:5400/v1/heartbeat/status | jq .

# Check for associated tasks
curl -s http://localhost:5400/v1/heartbeat/health-history | jq .

# Check router logs for the agent
docker compose logs --tail 500 cortex-router 2>&1 | grep "<AGENT_ID>"
```

**Mitigation:**

```bash
# Force-reset the agent status via admin API
curl -X POST "http://localhost:5402/admin/agents/<AGENT_ID>/reset" \
  -H "X-Cortex-Admin-Token: ${CORTEX_ADMIN_TOKEN}"

# If using the MeninBlack agent-service, reset via that service:
# curl -X POST "http://localhost:3006/api/v1/agents/<AGENT_ID>/reset"

# Clear any stuck BullMQ jobs (if applicable)
docker exec cortex-memory redis-cli -a "${REDIS_PASSWORD:-cortex_redis_secret}" \
  --scan --pattern "bull:*:stalled" | head -10
```

**Resolution:**
- Identify why the agent stalled (timeout, LLM hang, infinite loop)
- Fix the underlying task or tool that caused the hang
- Implement execution timeouts for agent tasks

**Prevention:**
- Set maximum execution time per agent task (e.g., 5 minutes)
- Implement stale task recovery (detect tasks running > threshold, auto-reset)
- Monitor agent state transitions and alert on agents in `working` state > 10 minutes

---

### 8. Authentication System Failure

**Symptoms:**
- All API requests return 401 Unauthorized
- Dashboard login fails
- Admin endpoints reject valid tokens
- Logs show JWT verification errors

**Diagnosis:**

```bash
# Check if CORTEX_SECRET_KEY is set
docker exec cortex-router env | grep CORTEX_SECRET_KEY | head -c 20
# (Should show first 20 chars -- enough to confirm it is set)

# Check if CORTEX_ADMIN_TOKEN is set
docker exec cortex-router env | grep CORTEX_ADMIN_TOKEN | head -c 20

# Test with admin token directly
curl -v http://localhost:5400/v1/agents \
  -H "X-Cortex-Admin-Token: ${CORTEX_ADMIN_TOKEN}"

# Check router startup logs for auth-related errors
docker compose logs cortex-router 2>&1 | grep -i "auth\|token\|secret\|jwt" | tail -20

# Check if Redis (session store) is accessible
docker exec cortex-memory redis-cli -a "${REDIS_PASSWORD:-cortex_redis_secret}" ping
```

**Mitigation:**

```bash
# If secret key was rotated accidentally, restore the old key in .env and restart
docker compose restart cortex-router

# If Redis sessions were lost, users must re-authenticate
# (No action needed on backend, sessions regenerate on login)

# Bypass auth for emergency admin access (temporary, remove after)
# Set CORTEX_ADMIN_TOKEN to a known value in .env, restart
```

**Resolution:**
- Ensure CORTEX_SECRET_KEY has not changed since tokens were issued
- If it must change, all active sessions will be invalidated (expected)
- Verify the .env file has not been corrupted

**Prevention:**
- Store CORTEX_SECRET_KEY in a secrets manager (Vault, AWS Secrets Manager)
- Never rotate CORTEX_SECRET_KEY without planning for session invalidation
- Implement token refresh flow so short-lived tokens reduce blast radius

---

### 9. Data Corruption Detected

**Symptoms:**
- PostgreSQL reports checksum verification failures
- Queries return unexpected/inconsistent results
- Immutable ledger verification fails
- Application errors referencing missing or malformed rows

**Diagnosis:**

```bash
# Verify immutable ledger integrity
curl -X POST http://localhost:5402/admin/ledger/verify \
  -H "X-Cortex-Admin-Token: ${CORTEX_ADMIN_TOKEN}" | jq .

# Check PostgreSQL for corruption
docker exec cortex-relational psql -U cortex -d cortexdb -c "
  SELECT datname, checksum_failures, checksum_last_failure
  FROM pg_stat_database
  WHERE datname = 'cortexdb';
"

# Run amcheck on indexes (requires amcheck extension)
docker exec cortex-relational psql -U cortex -d cortexdb -c "
  CREATE EXTENSION IF NOT EXISTS amcheck;
  SELECT bt_index_check(c.oid)
  FROM pg_index i
  JOIN pg_class c ON c.oid = i.indexrelid
  WHERE indisvalid
  LIMIT 50;
"

# Check Qdrant collection integrity
curl -s http://localhost:6333/collections | jq '.result.collections[] | {name, status}'
```

**Mitigation:**

```bash
# CRITICAL: Stop writes immediately to prevent further corruption
# (Application-level: set read-only mode or stop the router)

# Back up current state before any repair
docker exec cortex-relational pg_dump -U cortex cortexdb > /tmp/cortexdb_emergency_$(date +%Y%m%d_%H%M%S).sql

# If indexes are corrupt, reindex
docker exec cortex-relational psql -U cortex -d cortexdb -c "REINDEX DATABASE cortexdb;"

# If table data is corrupt, restore from backup
# (See your backup/restore procedures)
```

**Resolution:**
- Identify the source of corruption (hardware failure, bug, storage issue)
- Restore from the most recent known-good backup
- Replay any WAL logs to recover data since the backup
- If hardware-related, replace the failing disk

**Prevention:**
- Enable PostgreSQL data checksums (`initdb --data-checksums`)
- Run periodic integrity checks (amcheck, ledger verify)
- Implement point-in-time recovery (PITR) with continuous WAL archiving
- Use ECC RAM on database servers
- Test backup restoration regularly (at least monthly)

---

### 10. Network Partition Between Services

**Symptoms:**
- Some services report healthy, others report unhealthy
- Intermittent timeouts between specific service pairs
- Router can reach Redis but not PostgreSQL (or vice versa)
- Docker network errors in logs

**Diagnosis:**

```bash
# Check all container network connectivity
docker exec cortex-router ping -c 3 relational-core
docker exec cortex-router ping -c 3 memory-core
docker exec cortex-router ping -c 3 stream-core
docker exec cortex-router ping -c 3 vector-core

# Check Docker network
docker network inspect cortexdb_cortex-net

# Check DNS resolution inside containers
docker exec cortex-router nslookup relational-core
docker exec cortex-router nslookup memory-core

# Check for container restarts (crash loop)
docker compose ps --format "table {{.Name}}\t{{.Status}}"

# Check Docker daemon logs
journalctl -u docker --since "1 hour ago" --no-pager | tail -50
```

**Mitigation:**

```bash
# Restart the Docker network
docker compose down
docker network rm cortexdb_cortex-net 2>/dev/null
docker compose up -d

# If a specific container is isolated, restart it
docker compose restart <service_name>

# Force recreate all containers (preserves volumes)
docker compose up -d --force-recreate
```

**Resolution:**
- Check for Docker daemon issues (`dockerd` logs)
- Check host network (firewall rules, iptables)
- Verify the subnet 172.30.0.0/24 does not conflict with host networking
- Check for IP address exhaustion in the Docker network

**Prevention:**
- Monitor inter-service latency
- Set up health checks that test connectivity to all dependencies
- Avoid overlapping Docker network subnets with host/VPN networks
- Keep Docker engine updated

---

## Post-Mortem Template

Use this template within 48 hours of any P1 or P2 incident. P3 incidents should have a lightweight version.

```markdown
# Post-Mortem: [Incident Title]

**Date:** [YYYY-MM-DD]
**Severity:** P[1-4]
**Duration:** [Start time] to [End time] ([total duration])
**Incident Commander:** [Name]
**Author:** [Name]

## Summary

[2-3 sentence summary of what happened and the impact.]

## Timeline (all times in UTC)

| Time | Event |
|------|-------|
| HH:MM | [First alert or detection] |
| HH:MM | [Incident declared] |
| HH:MM | [Key diagnosis step] |
| HH:MM | [Mitigation applied] |
| HH:MM | [Service restored] |
| HH:MM | [Incident closed] |

## Impact

- **Users affected:** [Number or percentage]
- **Queries failed:** [Count or estimate]
- **Data loss:** [Yes/No, details]
- **Duration of impact:** [Time]
- **Revenue impact:** [If applicable]

## Root Cause

[Detailed technical explanation of why the incident happened. Include the
chain of events that led to the failure.]

## What Went Well

- [Things that worked during the response]
- [Monitoring that caught the issue early]
- [Runbook steps that helped]

## What Went Poorly

- [Gaps in monitoring or alerting]
- [Missing runbook steps]
- [Communication issues]
- [Slow diagnosis]

## Action Items

| Action | Owner | Priority | Due Date | Status |
|--------|-------|----------|----------|--------|
| [Specific action] | [Name] | P[1-4] | [Date] | Open |
| [Specific action] | [Name] | P[1-4] | [Date] | Open |
| [Specific action] | [Name] | P[1-4] | [Date] | Open |

## Lessons Learned

[Key takeaways that should inform future design, process, or tooling decisions.]
```

### Post-Mortem Ground Rules

1. Post-mortems are blameless. Focus on systems, not individuals.
2. The goal is to prevent recurrence, not assign fault.
3. All action items must have an owner and a due date.
4. Post-mortems are shared openly within the engineering team.
5. Action items are tracked to completion.
