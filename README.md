<p align="center">
  <img src="https://img.shields.io/badge/version-6.2.0-blue" alt="Version">
  <img src="https://img.shields.io/badge/license-Proprietary-red" alt="License">
  <img src="https://img.shields.io/badge/PostgreSQL-16-336791" alt="PostgreSQL">
  <img src="https://img.shields.io/badge/Python-3.11+-3776AB" alt="Python">
  <img src="https://img.shields.io/badge/TypeScript-5.5+-3178C6" alt="TypeScript">
</p>

# CortexEngine (CortexDB)

### AI Agent Data Infrastructure (Logic Layer over Best-of-Breed Engines)

**Semantic search, cross-engine queries, write fan-out, and agent-to-agent discovery. Sits alongside your database, not instead of it.**

CortexDB is an infrastructure layer for AI-native applications. It adds capabilities that no single database or ORM provides: a 5-tier read cascade with semantic caching, automatic write fan-out across multiple engines, agent-to-agent discovery via MCP/A2A protocols, and a unified query interface across relational, vector, graph, temporal, and streaming data.

CortexDB is built **on top of** best-of-breed engines (PostgreSQL, Redis, vector search, streams, and trace stores) — **not** as a replacement for them. The TypeScript SDK connects directly to your databases for simple queries and routes through the CortexDB service only for operations that require cross-engine intelligence.

## CortexDB as a Logic Layer (Engine Abstraction)

CortexDB is the *orchestration/logic layer*; the underlying engines are swappable. A typical deployment maps capabilities like this:

- **Context / working memory** → **Redis**
- **Stream / event bus** → **Redis Streams** today (Kafka/Redpanda-compatible contract)
- **Vector search** → **Qdrant** today (pgvector supported as an alternative)
- **Config / governance** → **PostgreSQL** (source of truth) + optional Redis cache
- **Traces / observability** → **PostgreSQL/Supabase** today (ClickHouse-compatible contract)

This architecture keeps your application code stable while letting CortexDB upgrade/replace the underlying engines as needs evolve (latency, scale, cost, or operational constraints).

---

## What CortexDB Adds (That Your ORM Can't Do)

| Capability | What it does | Why an ORM can't |
|------------|-------------|------------------|
| **Semantic Cache (R2)** | Finds cached responses to semantically similar queries via vector matching | ORMs only do exact-match caching |
| **Write Fan-Out** | One `write('payment', data)` atomically writes to PG + immutable ledger + event stream + cache | ORMs write to one database |
| **A2A Agent Discovery** | AI agents find each other by capability via semantic search | Not in database scope |
| **MCP Tool Exposure** | AI agents discover and use CortexDB as tools automatically | Not in database scope |
| **Cross-Engine Queries** | "Find payments from customers similar to X" hits vector + relational in one call | ORMs are single-engine |
| **5-Tier Read Cascade** | R0 (process LRU) → R1 (Redis) → R2 (semantic) → R3 (PostgreSQL) → R4 (deep retrieval) | ORMs have no tiered caching |
| **Embedding Sync** | PG NOTIFY triggers batch re-embed → Qdrant upsert; vectors never go stale | ORMs don't manage embeddings |
| **Agent Memory** | store/recall/forget/share with Ebbinghaus temporal decay across episodic, semantic, working memory | Not in database scope |
| **Field Encryption** | AES-256-GCM encryption wired into read/write data paths with audit logging | ORMs don't encrypt at field level |
| **Transactional Outbox** | PG-backed outbox replaces in-memory DLQ; survives crashes and restarts | ORMs have no outbox pattern |

## What CortexDB Does NOT Do

- **Does not replace PostgreSQL** — it uses PostgreSQL as its primary storage engine
- **Does not replace your ORM** — for simple CRUD, the SDK goes direct to PG; use Drizzle/Prisma if you prefer
- **Is not a compliance certification** — it provides compliance control mappings, not audited certifications

---

## Architecture: Hybrid Routing

```
┌──────────────────────────────────────────────────────────┐
│                    Your Application                       │
│                         │                                 │
│                  @cortexdb/sdk                            │
│                    ┌────┴────┐                            │
│              ┌─────┘         └─────┐                      │
│         Direct Access         CortexDB Service            │
│         (zero overhead)       (intelligence layer)        │
│              │                     │                      │
│    ┌─────────┤              ┌──────┴──────┐               │
│    │         │              │             │               │
│  PostgreSQL  Redis     Read Cascade   Write Fan-Out       │
│  (CRUD)    (cache)     (R0→R4)      (multi-engine)       │
│                              │             │               │
│                        ┌─────┴─────┐  ┌───┴────┐         │
│                        │  Qdrant   │  │ Stream │         │
│                        │ (vector)  │  │(events)│         │
│                        └───────────┘  └────────┘         │
└──────────────────────────────────────────────────────────┘
```

**Simple queries go direct** — no Python service in the path:
```
SELECT * FROM users WHERE id = $1    →  SDK → PostgreSQL (1 hop)
```

**Cross-engine queries route through the service** — because they need it:
```
FIND SIMILAR TO 'billing issues'     →  SDK → CortexDB → Qdrant + PG (justified)
write('payment', data)               →  SDK → CortexDB → PG + Ledger + Stream (justified)
```

---

## Quick Start

### With TypeScript SDK (Recommended)

```bash
npm install @cortexdb/sdk
```

```typescript
import { CortexClient } from '@cortexdb/sdk';

const cx = new CortexClient({
  postgres: { connectionString: process.env.DATABASE_URL },
  redis: { url: process.env.REDIS_URL },
  cortexUrl: 'http://localhost:5400',
});

// Simple CRUD — goes direct to PostgreSQL (no Python hop)
const users = await cx.sql('SELECT * FROM users WHERE tenant_id = $1', ['acme']);

// Semantic search — routes through CortexDB service
const similar = await cx.search('enterprise billing complaints', {
  collection: 'support_tickets',
  limit: 10,
});

// Write fan-out — one call writes to PG + cache + event stream
await cx.write('payment', {
  amount: 99.99,
  currency: 'USD',
  customer_id: 'cust-001',
});

// Agent discovery
const analysts = await cx.agents.discover('data-analysis');

// Direct cache (no Python hop)
await cx.cacheSet('session:abc', { user: 'alice' }, 3600);
const session = await cx.cacheGet('session:abc');
```

### With REST API

```bash
docker compose up -d

# Health check
curl http://localhost:5400/health/ready

# Query
curl -X POST http://localhost:5400/v1/query \
  -H "Content-Type: application/json" \
  -d '{"cortexql": "SELECT * FROM blocks LIMIT 5"}'

# Write with fan-out
curl -X POST http://localhost:5400/v1/write \
  -H "Content-Type: application/json" \
  -d '{"data_type": "block", "payload": {"name": "my-block"}, "actor": "dev"}'
```

---

## Engines

CortexDB coordinates 7 storage engines. Each engine is a thin client to an existing database — not a reimplementation:

| Engine | Backed By | Purpose |
|--------|-----------|---------|
| **RelationalCore** | PostgreSQL + Citus | ACID transactions, business data, sharding |
| **MemoryCore** | Redis | Sub-ms caching, sessions |
| **VectorCore** | Qdrant | AI embeddings, semantic search |
| **GraphCore** | PostgreSQL (recursive CTEs) | Relationship traversal |
| **TemporalCore** | TimescaleDB | Time-series, metrics |
| **StreamCore** | Redis Streams | Real-time event streaming |
| **ImmutableCore** | PostgreSQL (append-only) | Tamper-evident audit ledger |

---

## 5-Tier Read Cascade

Every read query flows through up to 5 tiers. Upper tiers are checked first; results are promoted upward on cache miss:

| Tier | Backend | Latency | Description |
|------|---------|---------|-------------|
| R0 | Process LRU (in-memory) | < 0.1ms | Hot data, per-process |
| R1 | Redis | < 1ms | Shared cache across processes |
| R2 | Qdrant (semantic) | < 5ms | Finds cached responses to *similar* (not identical) queries |
| R3 | PostgreSQL | < 50ms | Persistent storage |
| R4 | Cross-engine | varies | Deep retrieval across multiple engines |

Target: 75-85% cache hit rate at R0+R1.

---

## Write Fan-Out

One `write()` call automatically fans out to multiple engines based on data type:

| Data Type | Sync (ACID) | Async (best-effort, 3x retry) |
|-----------|-------------|-------------------------------|
| `payment` | Relational + Immutable | Temporal + Stream + Memory |
| `agent` | Relational | Memory + Stream |
| `block` | Relational | Vector + Memory |
| `audit` | Immutable | Relational |

Failed async writes are captured by a **transactional outbox** (PostgreSQL-backed) that survives crashes and restarts. An outbox worker retries delivery with exponential backoff, replacing the previous in-memory DLQ. Backpressure applies at 1000 pending tasks.

---

## AI Agent Integration

### MCP Server
CortexDB exposes itself as MCP tools that AI agents (Claude, GPT, LangGraph) can discover and use:

- `cortexdb.query` — Execute CortexQL
- `cortexdb.write` — Write with fan-out
- `cortexdb.blocks.list` — Browse the block registry
- `cortexdb.agents.list` — List registered agents
- `cortexdb.a2a.discover` — Find agents by capability
- `cortexdb.cache.stats` — Cache performance metrics
- `memory.store` — Store agent memory (episodic, semantic, or working)
- `memory.recall` — Recall memories with Ebbinghaus temporal decay
- `memory.forget` — GDPR-compliant deletion across all engines
- `memory.share` — Share memories between agents

### A2A Protocol
Agent-to-agent task coordination:
- Agents register capability cards (skills, tools, endpoints)
- Other agents discover by semantic skill search
- Task lifecycle: Created → Assigned → Running → Completed/Failed
- Tasks flow through StreamCore for real-time coordination

---

## Multi-Tenancy

- PostgreSQL Row-Level Security (RLS) per tenant with **SET LOCAL** in transactions (prevents cross-tenant data leaks on pooled connections)
- Per-engine isolation: key prefix (Redis), collection (Qdrant), stream key (Redis Streams)
- API key → tenant resolution in middleware
- Rate limiting per tenant, agent, and endpoint
- **Field-level encryption** (AES-256-GCM) for sensitive tenant data with audit logging
- Tenant configuration loaded from PostgreSQL on startup (write-through cache, survives restarts)

---

## Compliance Controls (Pre-Audit)

CortexDB maps to compliance frameworks but has **not been audited**. These are implementation controls, not certifications.

**Field encryption** (AES-256-GCM) is wired into the actual read/write data paths, providing encryption-at-rest for sensitive fields with full audit logging.

| Framework | Controls Mapped | Status |
|-----------|----------------|--------|
| FedRAMP (Moderate) | 10 NIST 800-53 controls | Mapped, not audited |
| SOC 2 (Type II) | 8 Trust Service Criteria | Mapped, not audited |
| HIPAA | 8 Technical Safeguards | Mapped, not audited |
| PCI DSS v4.0 | 8 Requirements | Mapped, not audited |

---

## Security

CortexDB v6.1.0 addresses critical security fixes identified by the PhD Expert Panel:

- **RLS hardening**: All transactions use `SET LOCAL` to set the tenant context, preventing cross-tenant data leaks on pooled connections
- **Admin auth bypass fix**: Requests are denied when `CORTEX_ADMIN_TOKEN` is unset; token comparison uses `hmac.compare_digest` to prevent timing attacks
- **Unified embedding codepath**: Eliminated a duplicate embedding path in vector.py that used incompatible hashing; all embeddings now flow through a single `EmbeddingPipeline`
- **PostgreSQL-backed immutable ledger**: Replaced the file-based append-only engine with a PostgreSQL-backed ledger (ACID, crash-safe)
- **Request coalescing**: Concurrent identical queries in the read cascade are coalesced into a single backend request, preventing cache stampede

---

## Project Structure

```
cortexdb/
├── sdk/                       # TypeScript SDK (recommended client)
│   ├── src/
│   │   ├── client.ts          # Smart query router
│   │   ├── direct/            # Direct PG/Redis clients (no Python hop)
│   │   └── cortex/            # CortexDB service client (cross-engine only)
│   └── package.json
├── cortexdb/                  # Python service (intelligence sidecar)
│   ├── core/
│   │   ├── database.py        # Read cascade, write fan-out, plasticity
│   │   ├── bridge.py          # Cross-engine query merging
│   │   ├── embedding.py       # ML embedding pipeline
│   │   ├── embedding_sync.py  # PG NOTIFY → batch re-embed → Qdrant upsert
│   │   ├── agent_memory.py    # Agent memory protocol (Ebbinghaus decay)
│   │   ├── outbox_worker.py   # Transactional outbox (PG-backed)
│   │   ├── cache_config.py    # Adaptive per-collection cache thresholds
│   │   └── parser.py          # CortexQL parser
│   ├── engines/               # 7 storage engine clients
│   ├── mcp/                   # MCP server for AI agents
│   ├── a2a/                   # Agent-to-agent protocol
│   └── server.py              # FastAPI service
├── dashboard/                 # Next.js admin dashboard
├── db/migrations/             # PostgreSQL schema migrations
├── docker-compose.yml         # Full stack
└── docs/
```

---

## Documentation

| Document | Description |
|----------|-------------|
| [White Paper](docs/whitepaper.md) | Technical architecture deep-dive |
| [Developer Guide](docs/DEVELOPER-GUIDE.md) | API reference and integration guide |
| [Docker Guide](docs/docker-guide.md) | Deployment and operations |
| [PhD Evaluation](docs/PHD-EVALUATION.md) | Expert panel evaluation and enhancement roadmap |
| [Contributing](CONTRIBUTING.md) | Development setup and guidelines |

---

## License

Copyright (c) 2026 Nirlab Inc. All rights reserved.

---

<p align="center">
  <strong>Built by <a href="https://nirlab.com">Nirlab Inc.</a></strong><br>
  <em>AI agent data infrastructure. Built on top of the databases you already trust.</em>
</p>
