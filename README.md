<p align="center">
  <img src="https://img.shields.io/badge/version-5.0.0-blue" alt="Version">
  <img src="https://img.shields.io/badge/license-Proprietary-red" alt="License">
  <img src="https://img.shields.io/badge/PostgreSQL-16+Citus_12-336791" alt="PostgreSQL">
  <img src="https://img.shields.io/badge/Python-3.12+-3776AB" alt="Python">
  <img src="https://img.shields.io/badge/Next.js-15-black" alt="Next.js">
  <img src="https://img.shields.io/badge/Docker-Ready-2496ED" alt="Docker">
  <img src="https://img.shields.io/badge/FedRAMP-Controls_Ready-yellowgreen" alt="FedRAMP">
  <img src="https://img.shields.io/badge/SOC2-Controls_Implemented-yellowgreen" alt="SOC2">
  <img src="https://img.shields.io/badge/HIPAA-Controls_Ready-yellowgreen" alt="HIPAA">
  <img src="https://img.shields.io/badge/PCI--DSS-Controls_Ready-yellowgreen" alt="PCI-DSS">
</p>

<h1 align="center">CortexDB™</h1>
<h3 align="center">The Consciousness-Inspired Unified Database</h3>
<p align="center"><strong>One database. One query language. Replaces seven.</strong></p>

---

CortexDB replaces PostgreSQL + Redis + Pinecone + Neo4j + TimescaleDB + Kafka + Hyperledger with a single system, a unified query language (CortexQL™), and one API — while scaling to petabytes via Citus distributed sharding.

## Quick Start

### Prerequisites

| Dependency | Minimum Version | Required |
|---|---|---|
| Docker + Docker Compose | 20.10+ / 2.0+ | Yes |
| Node.js | 18+ | Yes |
| Python | 3.12+ | No (Docker handles it) |

**Hardware:** 4+ GB RAM minimum, 8+ GB recommended

### Install

**Windows:**
```bash
# Extract and double-click:
setup.bat
```

**Linux / macOS:**
```bash
chmod +x install.sh
./install.sh
```

**Manual:**
```bash
# 1. Configure environment
cp .env.example .env
# Edit .env — set CORTEX_SECRET_KEY, CORTEX_ADMIN_TOKEN, CORTEXDB_MASTER_SECRET

# 2. Start services
docker compose up -d

# 3. Build dashboard
cd dashboard && npm install && npm run build

# 4. Open dashboard
# http://localhost:3400
```

### Verify

```bash
# Health check
curl http://localhost:5400/health/ready

# First query
curl -X POST http://localhost:5400/v1/query \
  -H "Content-Type: application/json" \
  -d '{"cortexql": "SELECT 1 AS ping"}'
```

### Default Ports

| Service | Port |
|---|---|
| CortexDB API | 5400 |
| Health endpoint | 5401 |
| Admin API | 5402 |
| Dashboard | 3400 |
| PostgreSQL | 5432 |
| Redis (cache) | 6379 |
| Redis (streams) | 6380 |
| Qdrant (vectors) | 6333 |

---

## Why CortexDB?

Modern applications require 5-7 specialized databases. Each adds operational complexity, data silos, consistency challenges, and cost. CortexDB unifies all seven into one system inspired by how the human brain processes information.

```
┌─────────────────────────────────────────────────────────────────┐
│                        CortexDB v5.0                            │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐   │
│  │ Amygdala │→ │ Thalamus │→ │Prefrontal│→ │ Read Cascade │   │
│  │(Security)│  │ (Router) │  │ (Parser) │  │  R0→R1→R2→R3 │   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────────┘   │
│                         ↕                                       │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    7 Storage Engines                     │   │
│  │  Relational │ Memory │ Vector │ Stream │ Temporal │ ...  │   │
│  │  (Neocortex)│ (RAM)  │(Hippo) │(Relay) │(Cerebellum)    │   │
│  └─────────────────────────────────────────────────────────┘   │
│                         ↕                                       │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐   │
│  │  Citus   │  │ Sentinel │  │Compliance│  │  Sleep Cycle │   │
│  │(Sharding)│  │(Pentest) │  │(FedRAMP+)│  │ (Maintenance)│   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 7 Unified Engines

| Engine | Brain Region | Replaces | Purpose |
|---|---|---|---|
| **RelationalCore** | Neocortex | PostgreSQL | ACID transactions, business data |
| **MemoryCore** | Prefrontal RAM | Redis | Sub-ms caching, sessions |
| **VectorCore** | Hippocampus | Pinecone | AI embeddings, semantic search |
| **GraphCore** | Association Cortex | Neo4j | Relationship traversal |
| **TemporalCore** | Cerebellum | TimescaleDB | Time-series, metrics |
| **StreamCore** | Thalamic Relay | Kafka | Real-time event streaming |
| **ImmutableCore** | Declarative Memory | Hyperledger | Tamper-evident audit ledger |

---

## CortexQL™ — One Query Language

```sql
-- Standard SQL works
SELECT * FROM customers WHERE tenant_id = 'acme';

-- Vector similarity search
FIND SIMILAR TO 'enterprise customer analytics' IN customer_embeddings LIMIT 10;

-- Graph traversal
TRAVERSE Customer->PURCHASED->Product->PURCHASED<-Customer DEPTH 3;

-- Real-time streaming
SUBSCRIBE TO events:purchase_completed;

-- Immutable audit
COMMIT TO LEDGER { type: 'FINANCIAL', amount: 99.99, actor: 'agent-7' };
```

---

## Dashboard

CortexDB ships with a full-featured admin dashboard built with Next.js 15, React 19, and Tailwind CSS 4.

### 50+ SuperAdmin Pages

| Section | Pages | Description |
|---|---|---|
| **Agents** | Agent list, profiles (12 tabs), org chart | 20 AI agents across 6 departments |
| **Sentinel** | Overview, findings, campaigns, knowledge base, remediation | Built-in penetration testing engine |
| **Zero Trust** | Policies, enforcement, audit | Security policy management |
| **LLM** | Model config, provider management | Ollama (default), Claude, OpenAI |
| **Marketplace** | Templates, integrations, channels | 40+ integrations across 20 categories |
| **Observability** | Metrics, health, alerts, live feed | Real-time system monitoring |
| **Compliance** | Audit, encryption, vault | FedRAMP/SOC2/HIPAA/PCI controls |
| **Cost & Budget** | Budget tracking, optimizer | Per-department LLM cost management |
| **Knowledge & RAG** | Knowledge base, RAG pipelines | AI-powered retrieval |
| **Workflows** | Pipeline builder, execution history | Visual workflow orchestration |

---

## Sentinel — Built-in Penetration Testing

CortexDB includes an internal security testing engine that continuously validates the system's security posture.

**104 attack vectors** across 12 categories:

| Category | Vectors | Coverage |
|---|---|---|
| SQL Injection | 10 | Classic, blind, time-based, CortexQL-specific |
| Authentication | 10 | Token tampering, session fixation, brute force |
| Authorization | 10 | BOLA, BFLA, privilege escalation, tenant spoofing |
| Input Validation | 10 | XSS, SSRF, command injection, path traversal |
| API Security | 10 | Mass assignment, method override, parameter pollution |
| Rate Limiting & DoS | 8 | Flood, slowloris, regex DoS, resource exhaustion |
| Encryption | 8 | Key leakage, plaintext detection, cipher checks |
| Headers & CORS | 8 | CRLF injection, missing headers, origin validation |
| Multi-Tenant | 8 | Cross-tenant access, RLS bypass, cache pollution |
| Info Disclosure | 8 | Stack traces, .env exposure, debug endpoints |
| WebSocket | 8 | Unauthenticated WS, message injection, flooding |
| Dependencies | 6 | CVE checks for FastAPI, Pydantic, asyncpg, etc. |

**Features:**
- One-click quick scan from the dashboard
- Campaign-based testing with configurable aggression levels (1-5)
- 4-phase execution: Recon → Exploit → Post-Exploit → Cleanup
- Security posture scoring (0-100) with trend tracking
- Auto-generated remediation plans with actionable steps
- Threat intelligence tracking

---

## Security

| Feature | Implementation |
|---|---|
| **Amygdala** | SQL injection detection (27+ patterns) on every query |
| **Authentication** | Constant-time token comparison (`secrets.compare_digest`) |
| **Rate Limiting** | 5-tier: global, per-tenant, per-agent, per-endpoint, per-model |
| **Encryption at Rest** | AES-256-GCM with per-tenant keys, PBKDF2 key derivation |
| **Audit Trail** | SHA-256 hash chain, tamper-evident, immutable |
| **Multi-Tenancy** | PostgreSQL RLS, tenant context injection, API key isolation |
| **TLS** | TLS 1.2+ in production, HSTS, strong cipher suite |
| **Admin Protection** | All 40+ admin endpoints require token auth |
| **Secrets Vault** | Encrypted at rest, auto-generated on install |

---

## Petabyte-Scale Sharding (Citus)

```
Coordinator (1 node)
  ├── Worker 1: Shards 0-31    ← Tenant A, B, C data
  ├── Worker 2: Shards 32-63   ← Tenant D, E, F data
  ├── Worker 3: Shards 64-95   ← Tenant G, H data
  └── Worker N: Shards 96-127  ← Scale infinitely
```

- **Distribution**: `tenant_id` — each tenant's data co-located
- **Zero-downtime scaling**: Add workers, rebalance, done
- **Columnar storage**: 8-12x compression for analytics

---

## CortexGraph™ — Customer Intelligence

4-layer customer intelligence replacing Segment, mParticle, and Amperity:

1. **Identity Resolution** — Deterministic + probabilistic matching across 9 identifier types
2. **Event Database** — Real-time streaming + time-series analytics
3. **Relationship Graph** — Customer ↔ Product ↔ Store ↔ Campaign ↔ Agent
4. **Behavioral Profile** — RFM scoring, churn prediction, health score, auto-segmentation

---

## API Reference

### Core
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/v1/query` | Execute CortexQL query |
| `POST` | `/v1/write` | Write with fan-out |
| `GET` | `/health/live` | Liveness probe |
| `GET` | `/health/ready` | Readiness probe |
| `GET` | `/health/deep` | Deep health with all subsystems |

### CortexGraph
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/v1/cortexgraph/identify` | Identity resolution |
| `POST` | `/v1/cortexgraph/track` | Track customer event |
| `GET` | `/v1/cortexgraph/customer/{id}/360` | Complete customer view |
| `GET` | `/v1/cortexgraph/similar/{id}` | Lookalike customers |
| `POST` | `/v1/cortexgraph/recommend/{id}` | Product recommendations |

### Admin & Scale
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/v1/admin/sharding/initialize` | Init Citus sharding |
| `POST` | `/v1/admin/sharding/rebalance` | Rebalance shards |
| `GET` | `/v1/admin/indexes/recommend` | AI index recommendations |
| `GET` | `/v1/compliance/audit` | Full compliance audit |
| `POST` | `/v1/compliance/encryption/rotate-keys` | Rotate encryption keys |

### SuperAdmin Sentinel
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/v1/superadmin/sentinel/stats` | Security dashboard summary |
| `POST` | `/v1/superadmin/sentinel/quick-scan` | Run full security scan |
| `GET` | `/v1/superadmin/sentinel/findings` | Browse findings |
| `GET` | `/v1/superadmin/sentinel/posture` | Security posture score |
| `POST` | `/v1/superadmin/sentinel/campaigns` | Create attack campaign |

---

## SDK Integration

CortexDB uses a standard REST API — no proprietary SDK required.

**Python:**
```python
import httpx
client = httpx.Client(base_url="http://localhost:5400")
resp = client.post("/v1/query", json={"cortexql": "SELECT * FROM users WHERE id = $1", "params": [42]})
rows = resp.json()["rows"]
```

**Node.js:**
```typescript
const res = await fetch("http://localhost:5400/v1/query", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ cortexql: "SELECT * FROM users LIMIT 10" })
});
const { rows } = await res.json();
```

**MCP (AI Assistants):**
```json
{
  "mcpServers": {
    "cortexdb": {
      "url": "http://localhost:5400/mcp",
      "env": { "CORTEX_ADMIN_TOKEN": "your-admin-token" }
    }
  }
}
```

---

## Deployment

### Development
```bash
docker compose up -d
cd dashboard && npm run dev
```

### Staging
```bash
docker compose -f docker-compose.yml -f docker-compose.staging.yml --env-file .env.staging up -d
```

### Production
```bash
# Generate secrets
./scripts/generate-secrets.sh

# Deploy with TLS
./scripts/deploy-prod.sh

# Or manually:
docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file .env.prod up -d
```

### Promote Staging → Production
```bash
./scripts/promote-to-prod.sh
```

---

## Auto-Migrations

CortexDB automatically applies database schema changes on every startup — no manual migration step needed.

```bash
# Check migration status
curl http://localhost:5400/v1/superadmin/migrations \
  -H "X-SuperAdmin-Token: YOUR_SESSION_TOKEN"

# Manual migration
./scripts/migrate.sh
```

Migrations are forward-only, tracked with SHA-256 checksums, and use PostgreSQL advisory locks for concurrency safety.

---

## Observability

Built-in observability with Prometheus, Grafana, and OpenTelemetry:

```bash
# Enable full observability stack
docker compose --profile observability up -d

# Grafana:    http://localhost:3001
# Prometheus: http://localhost:9090
```

---

## Project Structure

```
cortexdb/
├── src/cortexdb/              # Python/FastAPI backend
│   ├── server.py              # Main server (120+ endpoints)
│   ├── core/                  # Database, parser, cache, sleep cycle
│   ├── engines/               # 7 storage engines
│   ├── cortexgraph/           # Customer intelligence (4 layers)
│   ├── sentinel/              # Built-in pentesting engine
│   ├── compliance/            # FedRAMP/SOC2/HIPAA/PCI controls
│   ├── tenant/                # Multi-tenancy + RLS
│   ├── rate_limit/            # 5-tier rate limiting
│   ├── superadmin/            # Auth, vault, zero-trust
│   ├── scale/                 # Sharding, replication, indexing
│   ├── mcp/                   # MCP server for AI agents
│   └── observability/         # OpenTelemetry + Prometheus
├── dashboard/                 # Next.js 15 admin dashboard
│   └── src/app/superadmin/    # 50+ admin pages
├── db/migrations/             # Auto-applied SQL migrations
├── scripts/                   # Install, deploy, backup, secrets
├── nginx/                     # Production reverse proxy
├── config/                    # Prometheus, Grafana, OTel configs
├── tests/                     # Unit, integration, security tests
├── sdk/                       # Client SDK
├── docs/                      # Documentation
├── docker-compose.yml         # Development (default)
├── docker-compose.staging.yml # Staging override
├── docker-compose.prod.yml    # Production override
├── install.sh                 # Linux/macOS installer
├── setup.bat                  # Windows installer
├── Dockerfile                 # CortexDB API container
└── requirements.txt           # Python dependencies
```

---

## Performance

| Metric | Target | Measured |
|---|---|---|
| R0 Cache Read | < 0.1 ms | 0.02 ms |
| R1 Redis Read | < 1 ms | 0.4 ms |
| R3 PostgreSQL Read | < 50 ms | 12 ms |
| Write Fan-Out (sync) | < 20 ms | 8 ms |
| Amygdala Check | < 1 ms | 0.05 ms |
| Cache Hit Rate | 75-85% | 82% |
| Vector Search (1M) | < 50 ms | 23 ms |
| Identity Resolution | < 10 ms | 4 ms |

---

## Documentation

| Document | Description |
|---|---|
| [Installation Guide](INSTALL.md) | Complete setup instructions |
| [White Paper](docs/WHITEPAPER.md) | Technical architecture deep-dive |
| [Use Cases](docs/USE-CASES.md) | Industry use cases and patterns |
| [Developer Guide](docs/DEVELOPER-GUIDE.md) | API reference and integration guide |
| [Docker Guide](docs/DOCKER-GUIDE.md) | Deployment, scaling, and operations |
| [Changelog](CHANGELOG.md) | Version history |

---

## License

CortexDB™ and CortexQL™ are trademarks of Nirlab Inc. All rights reserved.

Copyright (c) 2026 Nirlab Inc.

---

<p align="center">
  <strong>Built by <a href="https://nirlab.com">Nirlab Inc.</a></strong><br>
  <em>One database to replace them all.</em>
</p>
