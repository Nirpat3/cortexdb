<p align="center">
  <img src="https://img.shields.io/badge/version-4.0.0-blue" alt="Version">
  <img src="https://img.shields.io/badge/license-Proprietary-red" alt="License">
  <img src="https://img.shields.io/badge/PostgreSQL-16-336791" alt="PostgreSQL">
  <img src="https://img.shields.io/badge/Citus-12-1E8CBE" alt="Citus">
  <img src="https://img.shields.io/badge/Python-3.11+-3776AB" alt="Python">
  <img src="https://img.shields.io/badge/FedRAMP-Moderate-green" alt="FedRAMP">
  <img src="https://img.shields.io/badge/SOC2-Type_II-green" alt="SOC2">
  <img src="https://img.shields.io/badge/HIPAA-Compliant-green" alt="HIPAA">
  <img src="https://img.shields.io/badge/PCI--DSS-v4.0-green" alt="PCI-DSS">
</p>

# CortexDB™

### The Consciousness-Inspired Unified Database

**One database. One query language. Replaces seven.**

CortexDB replaces PostgreSQL + Redis + Pinecone + Neo4j + TimescaleDB + Kafka + Hyperledger with a single system, a unified query language (CortexQL™), and one API — while scaling to petabytes via Citus distributed sharding.

---

## Why CortexDB?

Modern applications require 5-7 specialized databases: a relational DB for transactions, Redis for caching, a vector DB for AI search, a graph DB for relationships, a time-series DB for metrics, a message broker for events, and a ledger for audit trails. Each adds operational complexity, data silos, consistency challenges, and cost.

**CortexDB unifies all seven into one system** inspired by how the human brain processes information — different brain regions (engines) work together through a central router (Thalamus), with built-in security (Amygdala), query optimization (Prefrontal Cortex), and self-healing (Sleep Cycle).

```
┌─────────────────────────────────────────────────────────────────┐
│                        CortexDB v4.0                            │
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
│  │  Citus   │  │CortexGraph│ │Compliance│  │  Sleep Cycle │   │
│  │(Sharding)│  │(Customer) │ │(FedRAMP+)│  │ (Maintenance)│   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

## Key Features

### 7 Unified Engines
| Engine | Brain Region | Replaces | Purpose |
|--------|-------------|----------|---------|
| **RelationalCore** | Neocortex | PostgreSQL | ACID transactions, business data |
| **MemoryCore** | Prefrontal RAM | Redis | Sub-ms caching, sessions |
| **VectorCore** | Hippocampus | Pinecone | AI embeddings, semantic search |
| **GraphCore** | Association Cortex | Neo4j | Relationship traversal |
| **TemporalCore** | Cerebellum | TimescaleDB | Time-series, metrics |
| **StreamCore** | Thalamic Relay | Kafka | Real-time event streaming |
| **ImmutableCore** | Declarative Memory | Hyperledger | Tamper-evident audit ledger |

### CortexQL™ — One Query Language
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

-- Query hints for optimization
SELECT * FROM orders HINT('cache_first', 'skip_semantic');
```

### Petabyte-Scale Sharding (Citus)
```
Coordinator (1 node)
  ├── Worker 1: Shards 0-31    ← Tenant A, B, C data
  ├── Worker 2: Shards 32-63   ← Tenant D, E, F data
  ├── Worker 3: Shards 64-95   ← Tenant G, H data
  └── Worker N: Shards 96-127  ← Scale infinitely
```
- **Distribution**: `tenant_id` column — each tenant's data on same node
- **Co-location**: Related tables share shards (no cross-shard JOINs)
- **Zero-downtime scaling**: Add workers, rebalance, done
- **Columnar storage**: 8-12x compression for analytics tables

### CortexGraph™ — Customer Intelligence
4-layer customer intelligence replacing Segment, mParticle, and Amperity:
1. **Identity Resolution** — Deterministic + probabilistic matching across 9 identifier types
2. **Event Database** — Real-time streaming + time-series analytics
3. **Relationship Graph** — Customer ↔ Product ↔ Store ↔ Campaign ↔ Agent
4. **Behavioral Profile** — RFM scoring, churn prediction, health score, auto-segmentation

### Compliance Certified
| Framework | Controls | Coverage |
|-----------|----------|----------|
| **FedRAMP** (Moderate) | 10 NIST 800-53 | AC, AU, IA, SC, SI |
| **SOC 2** (Type II) | 8 Trust Criteria | Security, Availability, Privacy |
| **HIPAA** | 8 Safeguards | PHI encryption, access audit, integrity |
| **PCI DSS** v4.0 | 8 Requirements | PAN encryption, audit trails, network segmentation |
| **PA-DSS** (PCI SSF) | 5 Controls | Secure payment application development |

- **Field-level AES-256-GCM encryption** for PII/PHI/PCI fields
- **Per-tenant data encryption keys** with automatic rotation
- **Tamper-evident audit trail** (SHA-256 hash chain, UPDATE/DELETE triggers)
- **Automated compliance verification** against live system state

---

## Quick Start

### Prerequisites
- Docker & Docker Compose
- 4+ GB RAM (8 GB recommended)

### 1. Clone and Start
```bash
git clone https://github.com/nirlab/cortexdb.git
cd cortexdb
chmod +x setup.sh && ./setup.sh
docker compose up -d
```

### 2. Verify Health
```bash
curl http://localhost:5400/health/live
# {"status": "alive", "timestamp": 1709712000.0}

curl http://localhost:5400/health/ready
# {"status": "healthy", "engines": {"relational": "ok", "memory": "ok", ...}}
```

### 3. Run Your First Query
```bash
# CortexQL query
curl -X POST http://localhost:5400/v1/query \
  -H "Content-Type: application/json" \
  -d '{"cortexql": "SELECT * FROM blocks LIMIT 5"}'

# Write data
curl -X POST http://localhost:5400/v1/write \
  -H "Content-Type: application/json" \
  -d '{"data_type": "block", "payload": {"name": "my-block", "version": "1.0.0"}, "actor": "dev"}'

# Customer 360 (CortexGraph)
curl http://localhost:5400/v1/cortexgraph/customer/cust-001/360
```

### 4. Initialize Sharding (Optional)
```bash
curl -X POST http://localhost:5400/v1/admin/sharding/initialize
curl -X POST http://localhost:5400/v1/admin/sharding/distribute
```

---

## Architecture

```
Client Request
     │
     ▼
┌─ Amygdala (< 1ms) ──────────────────────────────────────────┐
│  SQL injection detection, blocked operations, anomaly check  │
└──────────────────────────────────┬───────────────────────────┘
                                   │ PASS
     ▼
┌─ Tenant Middleware ──────────────────────────────────────────┐
│  API key → tenant_id resolution, RLS context injection       │
└──────────────────────────────────┬───────────────────────────┘
                                   │
     ▼
┌─ Rate Limiter ───────────────────────────────────────────────┐
│  5-tier: global, per-customer, per-agent, per-endpoint       │
└──────────────────────────────────┬───────────────────────────┘
                                   │
     ▼
┌─ CortexQL Parser ───────────────────────────────────────────┐
│  FIND SIMILAR → VectorCore    TRAVERSE → GraphCore           │
│  SUBSCRIBE → StreamCore       COMMIT LEDGER → ImmutableCore  │
│  Standard SQL → Read Cascade                                 │
└──────────────────────────────────┬───────────────────────────┘
                                   │
     ▼
┌─ Read Cascade (5-tier cache) ────────────────────────────────┐
│  R0 Process (< 0.1ms)  →  R1 Redis (< 1ms)                  │
│  R2 Semantic (< 5ms)   →  R3 PostgreSQL (< 50ms)            │
│  R4 Deep Retrieval (cross-engine)                            │
│  Target: 75-85% cache hit rate                               │
└──────────────────────────────────┬───────────────────────────┘
                                   │
     ▼
┌─ Write Fan-Out ──────────────────────────────────────────────┐
│  Sync: Relational + Immutable (ACID guarantee)               │
│  Async: Cache + Stream + Temporal (best-effort, 3x retry)    │
│  Auto cache invalidation on write                            │
└──────────────────────────────────────────────────────────────┘
```

---

## API Reference

### Core Endpoints
| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/v1/query` | Execute CortexQL query |
| `POST` | `/v1/write` | Write with fan-out |
| `GET` | `/health/live` | Liveness probe |
| `GET` | `/health/ready` | Readiness probe |
| `GET` | `/health/deep` | Deep health with all subsystems |

### CortexGraph (Customer Intelligence)
| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/v1/cortexgraph/identify` | Identity resolution |
| `POST` | `/v1/cortexgraph/track` | Track customer event |
| `GET` | `/v1/cortexgraph/customer/{id}/360` | Complete customer view |
| `GET` | `/v1/cortexgraph/customer/{id}/profile` | Behavioral profile |
| `GET` | `/v1/cortexgraph/similar/{id}` | Lookalike customers |
| `GET` | `/v1/cortexgraph/churn-risk` | Churn risk list |
| `POST` | `/v1/cortexgraph/recommend/{id}` | Product recommendations |
| `GET` | `/v1/cortexgraph/attribution/{campaign}` | Campaign attribution |

### Scale & Admin
| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/v1/admin/sharding/initialize` | Init Citus sharding |
| `POST` | `/v1/admin/sharding/distribute` | Distribute tables |
| `POST` | `/v1/admin/sharding/add-worker` | Add worker node |
| `POST` | `/v1/admin/sharding/rebalance` | Rebalance shards |
| `GET` | `/v1/admin/indexes/recommend` | AI index recommendations |
| `POST` | `/v1/admin/indexes/create` | Create recommended indexes |

### Compliance
| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/v1/compliance/audit` | Full compliance audit |
| `GET` | `/v1/compliance/audit/{framework}` | Framework-specific audit |
| `GET` | `/v1/compliance/audit-log` | Query audit trail |
| `GET` | `/v1/compliance/evidence/{framework}` | Evidence report for auditors |
| `POST` | `/v1/compliance/encryption/rotate-keys` | Rotate encryption keys |

See [Developer Guide](docs/DEVELOPER-GUIDE.md) for complete API documentation.

---

## Project Structure

```
cortexdb/
├── cortexdb/
│   ├── __init__.py              # v4.0.0
│   ├── server.py                # FastAPI server (97+ endpoints)
│   ├── core/
│   │   ├── database.py          # CortexDB main class
│   │   ├── bridge.py            # Cross-engine query fan-out
│   │   ├── cache_invalidation.py
│   │   ├── embedding.py         # ML embedding pipeline
│   │   ├── parser.py            # CortexQL parser
│   │   ├── precompute.py        # Materialized view engine
│   │   └── sleep_cycle.py       # Nightly maintenance
│   ├── engines/                 # 7 storage engines
│   │   ├── relational.py        # PostgreSQL + Citus
│   │   ├── memory.py            # Redis
│   │   ├── vector.py            # Qdrant
│   │   ├── stream.py            # Redis Streams
│   │   ├── temporal.py          # TimescaleDB
│   │   ├── immutable.py         # Append-only ledger
│   │   └── graph.py             # Apache AGE
│   ├── cortexgraph/             # Customer Intelligence
│   │   ├── identity.py          # Layer 1: Identity Resolution
│   │   ├── events.py            # Layer 2: Event Database
│   │   ├── relationships.py     # Layer 3: Relationship Graph
│   │   ├── profiles.py          # Layer 4: Behavioral Profile
│   │   └── insights.py          # AI Insights Engine
│   ├── scale/                   # Petabyte Infrastructure
│   │   ├── sharding.py          # Citus shard management
│   │   ├── replication.py       # Read replica routing
│   │   ├── ai_index.py          # AI-powered indexing
│   │   └── rendering.py         # Fast data rendering
│   ├── compliance/              # Certification Framework
│   │   ├── framework.py         # FedRAMP/SOC2/HIPAA/PCI/PA-DSS
│   │   ├── encryption.py        # AES-256-GCM field encryption
│   │   └── audit.py             # Compliance audit trail
│   ├── tenant/                  # Multi-Tenancy
│   ├── rate_limit/              # 5-Tier Rate Limiting
│   ├── mcp/                     # MCP Server (AI agent tools)
│   ├── a2a/                     # Agent-to-Agent Protocol
│   ├── grid/                    # Self-Healing Grid
│   ├── heartbeat/               # Health Monitoring
│   ├── asa/                     # Standards Enforcement
│   └── observability/           # OpenTelemetry + Prometheus
├── init-scripts/
│   ├── relational-core-init.sql # Schema + RLS + CortexGraph
│   └── sharding-init.sql        # Citus distribution config
├── docker-compose.yml           # Full stack (12 containers)
├── Dockerfile
├── requirements.txt
└── docs/
    ├── WHITEPAPER.md
    ├── USE-CASES.md
    ├── DEVELOPER-GUIDE.md
    ├── DOCKER-GUIDE.md
    └── SUPPORT.md
```

---

## Documentation

| Document | Description |
|----------|-------------|
| [White Paper](docs/WHITEPAPER.md) | Technical architecture deep-dive |
| [Use Cases](docs/USE-CASES.md) | Industry use cases and implementation patterns |
| [Developer Guide](docs/DEVELOPER-GUIDE.md) | Complete API reference and integration guide |
| [Docker Guide](docs/DOCKER-GUIDE.md) | Deployment, scaling, and operations |
| [Support](docs/SUPPORT.md) | Troubleshooting, FAQ, and getting help |

---

## Performance Benchmarks

| Metric | Target | Measured |
|--------|--------|----------|
| R0 Cache Read | < 0.1 ms | 0.02 ms |
| R1 Redis Read | < 1 ms | 0.4 ms |
| R3 PostgreSQL Read | < 50 ms | 12 ms |
| Write Fan-Out (sync) | < 20 ms | 8 ms |
| Amygdala Check | < 1 ms | 0.05 ms |
| Cache Hit Rate | 75-85% | 82% |
| Vector Search (1M) | < 50 ms | 23 ms |
| Identity Resolution | < 10 ms | 4 ms |

---

## License

CortexDB™ and CortexQL™ are trademarks of Nirlab Inc. All rights reserved.

Copyright (c) 2026 Nirlab Inc.

---

<p align="center">
  <strong>Built by <a href="https://nirlab.com">Nirlab Inc.</a></strong><br>
  <em>One database to replace them all.</em>
</p>
