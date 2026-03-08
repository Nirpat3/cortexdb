# CortexDB Security Hardening Guide

Version: 1.0
Last Updated: 2026-03-08

---

## Table of Contents

1. [Network Security](#network-security)
2. [Authentication Hardening](#authentication-hardening)
3. [Secrets Management](#secrets-management)
4. [Database Security](#database-security)
5. [Container Security](#container-security)
6. [API Security](#api-security)
7. [Compliance Checklist](#compliance-checklist)
8. [Security Audit Schedule](#security-audit-schedule)

---

## Network Security

### Firewall Rules

Only the following ports should be exposed to external networks. All other services must be internal-only.

| Port | Service | Exposure | Notes |
|------|---------|----------|-------|
| 5400 | cortex-router (API) | External (via load balancer) | Primary CortexQL API |
| 3400 | cortex-dashboard | External (via load balancer) | Admin UI |
| 5401 | cortex-router (Health) | Internal only | Health probes |
| 5402 | cortex-router (Admin) | Internal only | Admin operations |
| 5432 | relational-core | Internal only | PostgreSQL |
| 6379 | memory-core | Internal only | Redis cache |
| 6380 | stream-core | Internal only | Redis streams |
| 6333/6334 | vector-core | Internal only | Qdrant |

**Lock down docker-compose.yml for production:**

Change internal-only services to bind only to localhost or remove port mappings entirely:

```yaml
# BEFORE (exposes to all interfaces)
relational-core:
  ports:
    - "5432:5432"

# AFTER (localhost only, for admin access from host)
relational-core:
  ports:
    - "127.0.0.1:5432:5432"

# BEST (no host port exposure at all)
relational-core:
  # ports removed -- only accessible via cortex-net
```

**Host firewall (UFW example):**

```bash
# Allow only API and dashboard from external
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp        # SSH
sudo ufw allow 5400/tcp      # CortexDB API
sudo ufw allow 3400/tcp      # Dashboard
sudo ufw enable

# Verify
sudo ufw status verbose
```

**Host firewall (iptables example):**

```bash
# Drop all incoming by default
iptables -P INPUT DROP
iptables -P FORWARD DROP
iptables -P OUTPUT ACCEPT

# Allow established connections
iptables -A INPUT -m state --state ESTABLISHED,RELATED -j ACCEPT

# Allow loopback
iptables -A INPUT -i lo -j ACCEPT

# Allow SSH
iptables -A INPUT -p tcp --dport 22 -j ACCEPT

# Allow CortexDB API and Dashboard
iptables -A INPUT -p tcp --dport 5400 -j ACCEPT
iptables -A INPUT -p tcp --dport 3400 -j ACCEPT

# Save rules
iptables-save > /etc/iptables/rules.v4
```

### Internal Network Isolation

The Docker network `cortex-net` uses subnet `172.30.0.0/24`. Ensure this does not overlap with your VPN or corporate network.

```bash
# Verify network configuration
docker network inspect cortexdb_cortex-net | jq '.[0].IPAM.Config'

# If subnet conflicts, change it in docker-compose.yml:
# networks:
#   cortex-net:
#     ipam:
#       config:
#         - subnet: 10.99.0.0/24
```

### TLS Termination

Place a reverse proxy (nginx, Caddy, Traefik) in front of CortexDB for TLS:

```nginx
server {
    listen 443 ssl http2;
    server_name cortexdb.example.com;

    ssl_certificate /etc/ssl/certs/cortexdb.crt;
    ssl_certificate_key /etc/ssl/private/cortexdb.key;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers on;
    ssl_session_timeout 1d;
    ssl_session_cache shared:SSL:10m;

    # HSTS
    add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload" always;

    location / {
        proxy_pass http://127.0.0.1:5400;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

---

## Authentication Hardening

### CORTEX_SECRET_KEY Requirements

- Minimum 64 characters
- Generated with a cryptographically secure random generator
- Never committed to version control

```bash
# Generate a secure secret key
openssl rand -hex 64
```

### Token Configuration

```bash
# .env settings
CORTEX_SECRET_KEY=<64+ char random hex>

# Admin token (used for admin API on port 5402)
CORTEX_ADMIN_TOKEN=<separate 64+ char random hex>
```

### Session Hardening

Recommended settings for the application:

| Setting | Value | Rationale |
|---------|-------|-----------|
| JWT expiry | 15 minutes | Short-lived tokens reduce window of compromise |
| Refresh token expiry | 7 days | Allows re-auth without password |
| Idle session timeout | 30 minutes | Auto-logout inactive sessions |
| Max concurrent sessions | 5 per user | Prevents credential sharing |
| Token rotation | On each refresh | Detects token theft |

### Brute Force Protection

The CortexDB rate limiter (via `RateLimitMiddleware`) should be configured to limit authentication attempts:

```bash
# Recommended rate limit settings in .env
CORTEX_RATE_LIMIT_AUTH=5/minute    # 5 login attempts per minute per IP
CORTEX_RATE_LIMIT_API=100/minute   # 100 API calls per minute per tenant
```

### Multi-Factor Authentication (MFA)

For dashboard access, integrate TOTP-based MFA:

1. Require MFA for all admin-level accounts.
2. Store TOTP secrets encrypted in the database.
3. Invalidate sessions when MFA is newly enabled.

---

## Secrets Management

### Environment Variables

Never store secrets in docker-compose.yml or code. Use a `.env` file with restricted permissions:

```bash
# Create .env with restricted permissions
touch .env
chmod 600 .env

# Required secrets
CORTEX_SECRET_KEY=<generated>
CORTEX_ADMIN_TOKEN=<generated>
POSTGRES_PASSWORD=<generated>
REDIS_PASSWORD=<generated>
STREAM_PASSWORD=<generated>
CORTEXDB_MASTER_SECRET=<generated>
ANTHROPIC_API_KEY=<from-provider>
OPENAI_API_KEY=<from-provider>
GRAFANA_PASSWORD=<generated>
```

### .env File Security

```bash
# Verify .env is in .gitignore
grep -q '.env' .gitignore || echo '.env' >> .gitignore

# Verify .env permissions
ls -la .env
# Should show: -rw------- 1 <user> <group>

# Verify .env is not tracked by git
git ls-files --error-unmatch .env 2>/dev/null && echo "WARNING: .env is tracked by git!" || echo "OK: .env is not tracked"
```

### HashiCorp Vault Integration

For production deployments, use Vault to manage secrets:

```bash
# Store secrets in Vault
vault kv put secret/cortexdb \
  CORTEX_SECRET_KEY="$(openssl rand -hex 64)" \
  POSTGRES_PASSWORD="$(openssl rand -hex 32)" \
  REDIS_PASSWORD="$(openssl rand -hex 32)" \
  STREAM_PASSWORD="$(openssl rand -hex 32)"

# Retrieve at runtime (in entrypoint script)
export CORTEX_SECRET_KEY=$(vault kv get -field=CORTEX_SECRET_KEY secret/cortexdb)
export POSTGRES_PASSWORD=$(vault kv get -field=POSTGRES_PASSWORD secret/cortexdb)
```

### Secret Rotation Schedule

| Secret | Rotation Frequency | Procedure |
|--------|-------------------|-----------|
| CORTEX_SECRET_KEY | Quarterly | Invalidates all sessions. Plan for re-auth. |
| POSTGRES_PASSWORD | Quarterly | Update DB, .env, restart all services. |
| REDIS_PASSWORD | Quarterly | Update Redis CONFIG, .env, restart router. |
| CORTEX_ADMIN_TOKEN | Monthly | Update .env, restart router. |
| LLM API keys | Per provider policy | Update .env, restart router. |
| TLS certificates | Before expiry (auto-renew) | Use certbot or ACME. |

---

## Database Security

### PostgreSQL Hardening

**Connection encryption (SSL):**

```bash
# Generate server certificate
openssl req -new -x509 -days 365 -nodes \
  -out /etc/ssl/certs/pg-server.crt \
  -keyout /etc/ssl/private/pg-server.key \
  -subj "/CN=cortex-relational"

# Mount into container and configure
# In docker-compose.yml:
# volumes:
#   - ./certs/pg-server.crt:/var/lib/postgresql/server.crt
#   - ./certs/pg-server.key:/var/lib/postgresql/server.key
```

Add to `postgresql.conf` (via environment or config mount):

```
ssl = on
ssl_cert_file = '/var/lib/postgresql/server.crt'
ssl_key_file = '/var/lib/postgresql/server.key'
ssl_min_protocol_version = 'TLSv1.2'
```

**pg_hba.conf hardening:**

```
# Reject unencrypted connections
hostssl all all 172.30.0.0/24 scram-sha-256
host    all all 0.0.0.0/0    reject
```

**Row-Level Security (RLS):**

CortexDB uses multi-tenancy. Enable RLS on tenant-scoped tables:

```sql
-- Enable RLS on a table
ALTER TABLE cortex_data ENABLE ROW LEVEL SECURITY;

-- Create policy for tenant isolation
CREATE POLICY tenant_isolation ON cortex_data
  USING (tenant_id = current_setting('app.current_tenant')::uuid);

-- Force RLS for all users except superuser
ALTER TABLE cortex_data FORCE ROW LEVEL SECURITY;
```

**Audit logging:**

```sql
-- Enable pgaudit extension
CREATE EXTENSION IF NOT EXISTS pgaudit;

-- Log all DDL and DML
ALTER SYSTEM SET pgaudit.log = 'ddl, write, role';
ALTER SYSTEM SET pgaudit.log_catalog = off;
ALTER SYSTEM SET pgaudit.log_level = 'log';

-- Reload configuration
SELECT pg_reload_conf();
```

**Connection limits per role:**

```sql
-- Limit application connections
ALTER ROLE cortex CONNECTION LIMIT 200;

-- Create a read-only role for reporting
CREATE ROLE cortex_readonly WITH LOGIN PASSWORD '<secure_password>';
GRANT CONNECT ON DATABASE cortexdb TO cortex_readonly;
GRANT USAGE ON SCHEMA public TO cortex_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO cortex_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO cortex_readonly;
```

### Redis Security

```bash
# Verify password is required
docker exec cortex-memory redis-cli ping
# Should fail with NOAUTH

# Disable dangerous commands
docker exec cortex-memory redis-cli -a "${REDIS_PASSWORD}" \
  CONFIG SET rename-command FLUSHALL ""
docker exec cortex-memory redis-cli -a "${REDIS_PASSWORD}" \
  CONFIG SET rename-command DEBUG ""
docker exec cortex-memory redis-cli -a "${REDIS_PASSWORD}" \
  CONFIG SET rename-command CONFIG ""
```

For production, use a custom redis.conf:

```
# redis-hardened.conf
requirepass <password>
rename-command FLUSHALL ""
rename-command FLUSHDB ""
rename-command DEBUG ""
rename-command KEYS "CORTEX_KEYS_INTERNAL"
bind 0.0.0.0
protected-mode yes
```

### Qdrant Security

Qdrant does not have built-in auth by default. Protect it at the network level:

```yaml
# Remove port exposure entirely
vector-core:
  # ports: removed
  # Only accessible via cortex-net
```

If Qdrant API key auth is enabled:

```yaml
vector-core:
  environment:
    - QDRANT__SERVICE__API_KEY=${QDRANT_API_KEY}
```

---

## Container Security

### Image Scanning

Scan images for vulnerabilities before deployment:

```bash
# Scan with Trivy
trivy image cortexdb:latest
trivy image citusdata/citus:12.1
trivy image redis:7-alpine
trivy image qdrant/qdrant:latest

# Fail CI/CD on critical vulnerabilities
trivy image --exit-code 1 --severity CRITICAL cortexdb:latest
```

### Dockerfile Best Practices

```dockerfile
# Use specific version tags, not :latest
FROM python:3.12-slim AS base

# Run as non-root user
RUN groupadd -r cortex && useradd -r -g cortex cortex
USER cortex

# Copy only necessary files
COPY --chown=cortex:cortex requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=cortex:cortex src/ ./src/

# No secrets in the image
# Use runtime environment variables instead
```

### Runtime Protection

```yaml
# docker-compose.yml hardening
cortex-router:
  security_opt:
    - no-new-privileges:true
  read_only: true
  tmpfs:
    - /tmp
  cap_drop:
    - ALL
  cap_add:
    - NET_BIND_SERVICE
```

### Container Resource Limits

Already configured in docker-compose.yml. Verify they are enforced:

```bash
# Check resource limits for all containers
docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}"
```

### Image Provenance

```bash
# Pin images to specific digests in production
# Instead of:
#   image: redis:7-alpine
# Use:
#   image: redis:7-alpine@sha256:<digest>

# Get the digest
docker inspect --format='{{index .RepoDigests 0}}' redis:7-alpine
```

---

## API Security

### Rate Limiting

CortexDB includes `RateLimitMiddleware`. Configure per-tenant limits:

```bash
# Default rate limits (set in .env)
CORTEX_RATE_LIMIT_DEFAULT=100/minute
CORTEX_RATE_LIMIT_BURST=20

# Check current rate limiter status
curl -s http://localhost:5400/v1/admin/rate-limits \
  -H "X-Cortex-Admin-Token: ${CORTEX_ADMIN_TOKEN}" | jq .
```

### Input Validation

CortexQL queries should be validated before execution:

- Maximum query length: 64 KB
- Parameter binding required (no string interpolation)
- Disallow raw SQL passthrough for non-admin tenants

```bash
# Test input validation
curl -X POST http://localhost:5400/v1/query \
  -H "Content-Type: application/json" \
  -d '{"cortexql": "SELECT * FROM users; DROP TABLE users;--", "params": []}'
# Should be rejected by query parser
```

### CORS Configuration

```bash
# Set allowed origins explicitly (never use *)
CORTEX_CORS_ORIGINS=https://dashboard.example.com,https://admin.example.com
```

Verify CORS headers:

```bash
curl -v -X OPTIONS http://localhost:5400/v1/query \
  -H "Origin: https://evil.example.com" \
  -H "Access-Control-Request-Method: POST" 2>&1 | grep -i "access-control"
# Should NOT include the evil origin in allowed origins
```

### Request Size Limits

Configure maximum request body size to prevent abuse:

```bash
# In .env or application config
CORTEX_MAX_REQUEST_SIZE=10mb
```

### API Key Security

For tenant API keys:

- Keys must be at least 32 characters
- Hash keys before storing (bcrypt or SHA-256)
- Support key expiry dates
- Log all key creation/revocation events
- Rate-limit key creation

```bash
# Check tenant API keys
curl -s http://localhost:5400/v1/admin/tenants \
  -H "X-Cortex-Admin-Token: ${CORTEX_ADMIN_TOKEN}" | jq '.[].api_keys | length'
```

### Security Headers

Ensure the reverse proxy adds these headers:

```nginx
add_header X-Content-Type-Options "nosniff" always;
add_header X-Frame-Options "DENY" always;
add_header X-XSS-Protection "0" always;
add_header Referrer-Policy "strict-origin-when-cross-origin" always;
add_header Content-Security-Policy "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'" always;
add_header Permissions-Policy "camera=(), microphone=(), geolocation=()" always;
```

---

## Compliance Checklist

CortexDB includes a built-in `ComplianceFramework` module. Use it alongside these operational controls.

### SOC 2 Type II

| Control | Status | Implementation |
|---------|--------|----------------|
| Access control | [ ] | Role-based access, tenant isolation, admin token separation |
| Encryption in transit | [ ] | TLS 1.2+ on all external endpoints |
| Encryption at rest | [ ] | FieldEncryption module for sensitive columns, disk encryption |
| Audit logging | [ ] | pgaudit, ComplianceAudit service, immutable ledger |
| Change management | [ ] | Git-based deployments, migration versioning |
| Incident response | [ ] | This playbook, post-mortem process |
| Monitoring and alerting | [ ] | Prometheus, Grafana, health checks |
| Backup and recovery | [ ] | Automated backups, tested restore procedures |
| Vendor management | [ ] | LLM provider agreements, data processing addendums |

### HIPAA (if handling PHI)

| Control | Status | Implementation |
|---------|--------|----------------|
| Access controls | [ ] | Per-tenant RLS, MFA for admin access |
| Audit controls | [ ] | pgaudit logs all access to PHI tables |
| Transmission security | [ ] | TLS 1.2+ enforced, no plaintext endpoints |
| Integrity controls | [ ] | Immutable ledger, data checksums |
| PHI encryption | [ ] | FieldEncryption on all PHI columns |
| Business associate agreements | [ ] | BAAs with Anthropic, OpenAI, cloud providers |
| Breach notification | [ ] | Incident response process, 72-hour notification SLA |
| Minimum necessary | [ ] | Tenant isolation, column-level access controls |

### GDPR

| Control | Status | Implementation |
|---------|--------|----------------|
| Data inventory | [ ] | Document all personal data fields and retention periods |
| Consent management | [ ] | Tenant-level consent tracking |
| Right to access | [ ] | Tenant data export API (`/admin/tenants/{id}/export`) |
| Right to erasure | [ ] | Tenant data purge API (`/admin/tenants/{id}/purge`) |
| Data portability | [ ] | JSON export format |
| Data processing agreements | [ ] | DPAs with all sub-processors |
| Privacy impact assessment | [ ] | Document for each new data processing activity |
| Data breach notification | [ ] | 72-hour notification process via incident response |
| Cross-border transfers | [ ] | Standard contractual clauses or adequacy decision |

---

## Security Audit Schedule

### Continuous (Automated)

| Check | Tool | Frequency |
|-------|------|-----------|
| Container image CVE scan | Trivy / Snyk | Every build |
| Dependency vulnerability scan | `pip audit`, `npm audit` | Every build |
| Secret detection in code | gitleaks, trufflehog | Every commit (pre-commit hook) |
| Rate limit monitoring | Prometheus alerts | Real-time |
| Failed auth attempt monitoring | Application logs | Real-time |
| Certificate expiry check | certbot / custom script | Daily |

### Weekly

| Check | Responsibility |
|-------|---------------|
| Review failed authentication logs | Security engineer |
| Review rate limit violation logs | Security engineer |
| Check for new CVEs in dependencies | DevOps engineer |
| Verify backup integrity (test restore) | DevOps engineer |

### Monthly

| Check | Responsibility |
|-------|---------------|
| Rotate CORTEX_ADMIN_TOKEN | Security engineer |
| Review tenant access patterns | Security engineer |
| Review and prune unused API keys | Security engineer |
| Update container base images | DevOps engineer |
| Review firewall rules | Network engineer |
| Run OWASP ZAP scan against API | Security engineer |

### Quarterly

| Check | Responsibility |
|-------|---------------|
| Rotate CORTEX_SECRET_KEY | Security engineer (with planned downtime) |
| Rotate database passwords | DevOps engineer |
| Full penetration test | External security firm or internal red team |
| Review and update security policies | Security lead |
| Compliance audit review | Compliance officer |
| Disaster recovery drill | Engineering team |
| Review pgaudit logs for anomalies | Database administrator |

### Annually

| Check | Responsibility |
|-------|---------------|
| SOC 2 audit (if applicable) | External auditor |
| Full security architecture review | Security architect |
| Incident response tabletop exercise | Engineering + management |
| Update threat model | Security lead |
| Review and renew vendor security agreements | Legal + security |

---

## Appendix: Quick Security Verification Commands

Run these commands to quickly verify security posture:

```bash
# 1. Verify no ports exposed beyond what is needed
docker compose ps --format "table {{.Name}}\t{{.Ports}}"

# 2. Verify containers are not running as root
for c in cortex-router cortex-relational cortex-memory cortex-stream cortex-vector cortex-dashboard; do
  USER=$(docker exec $c whoami 2>/dev/null || echo "N/A")
  echo "$c: running as $USER"
done

# 3. Verify Redis requires authentication
docker exec cortex-memory redis-cli ping 2>&1 | grep -q NOAUTH && echo "Redis auth: ENABLED" || echo "Redis auth: DISABLED (FIX THIS)"

# 4. Verify PostgreSQL SSL
docker exec cortex-relational psql -U cortex -d cortexdb -c "SHOW ssl;" 2>/dev/null

# 5. Check for default passwords in .env
grep -E "(cortex_secret|cortex_redis_secret|cortex_stream_secret)" .env && echo "WARNING: Default passwords detected. Change them." || echo "OK: No default passwords found."

# 6. Verify .env file permissions
PERMS=$(stat -c %a .env 2>/dev/null || stat -f %Lp .env 2>/dev/null)
[ "$PERMS" = "600" ] && echo "OK: .env permissions are 600" || echo "WARNING: .env permissions are $PERMS (should be 600)"

# 7. Check immutable ledger integrity
curl -s -X POST http://localhost:5402/admin/ledger/verify \
  -H "X-Cortex-Admin-Token: ${CORTEX_ADMIN_TOKEN}" | jq '.verified'

# 8. Check compliance framework status
curl -s http://localhost:5400/health/deep | jq '.compliance'
```
