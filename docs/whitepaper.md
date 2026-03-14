# CortexEngine (CortexDB)™ Technical White Paper

**Version 6.2.0 — March 2026**
**Nirlab Inc.**

---

## Abstract

CortexDB (CortexEngine) is an AI Agent Data Infrastructure **logic layer** that coordinates best-of-breed engines (relational, cache, vector, stream, and trace stores) through a unified API. It provides capabilities no single database or ORM offers: semantic caching (finding cached responses to semantically similar queries), automatic write fan-out with a transactional outbox pattern, embedding sync (automatic vector freshness), agent-to-agent discovery, agent memory with temporal decay, and MCP tool exposure for AI agents.

CortexDB sits **alongside** your existing databases — not as a replacement. The TypeScript SDK routes simple CRUD directly to PostgreSQL/Redis (zero overhead) and only sends cross-engine operations through the CortexDB service when the operation truly requires it (fan-out writes, semantic cache, cross-engine joins, agent discovery, memory protocols).

### Engine Abstraction (Recommended Mapping)

In a typical deployment, CortexDB maps high-level capabilities to engines like:
- **Context / working memory** → Redis
- **Stream / event bus** → Redis Streams (Kafka/Redpanda-compatible contract)
- **Vector search** → Qdrant (pgvector supported as an alternative)
- **Config / governance** → PostgreSQL (source of truth) + optional Redis cache
- **Traces / observability** → PostgreSQL/Supabase today (ClickHouse-compatible contract)

This keeps application code stable while allowing the underlying engines to evolve based on latency, scale, cost, or operational constraints.

Version 6.1.0 incorporates findings from a PhD expert panel evaluation (distributed systems, AI/ML, and security specialists) with all P0 security fixes, P1 production readiness enhancements, and the agent memory protocol implemented.

---

## 1. The Problem

### 1.1 AI Agents Need Multi-Modal Data Access

AI agents (LangGraph, CrewAI, OpenAI Agents, Claude) need to simultaneously query structured data (SQL), semantic data (vectors), relationship data (graphs), and event streams — often in a single reasoning step. Today, developers wire up 3-5 separate clients, manage connection pools for each, and handle cross-system consistency manually. The typical stack includes:

| Need | Typical Solution | Annual Cost |
|------|-----------------|-------------|
| Transactions | PostgreSQL / MySQL | $5K-50K |
| Caching | Redis / Memcached | $3K-30K |
| AI Search | Pinecone / Weaviate | $10K-100K |
| Relationships | Neo4j / Neptune | $15K-80K |
| Time-Series | TimescaleDB / InfluxDB | $5K-40K |
| Event Streaming | Kafka / Pulsar | $10K-60K |
| Audit Trail | Custom / Hyperledger | $10K-50K |
| **Total** | **7 systems** | **$58K-410K** |

Each system requires separate:
- Connection management and pooling
- Schema design and migrations
- Backup and disaster recovery
- Monitoring and alerting
- Security configuration
- Team expertise

### 1.2 The Consistency Problem

With data spread across 7 systems, maintaining consistency is the top engineering challenge:
- A customer record exists in PostgreSQL, cached in Redis, embedded in Pinecone, connected in Neo4j
- Updating the customer requires coordinating writes across 4 systems
- Failure in any one system creates data drift
- Eventually-consistent patterns add cognitive load and bug surface area

### 1.3 The AI Agent Problem

AI agents (Claude, GPT, LangGraph) need unified access to all data types. An agent reasoning about a customer needs:
- Relational data (orders, account info)
- Cached session state
- Semantic similarity (find similar customers)
- Graph relationships (who referred whom)
- Event history (last 90 days of activity)
- Audit trail (compliance evidence)

With 7 databases, the agent needs 7 different connection libraries, query languages, and data models. CortexDB provides one MCP tool interface.

---

## 2. Architecture

### 2.1 Brain-Mapped Design

CortexDB maps 10 brain regions to database components:

| Brain Region | CortexDB Component | Function |
|-------------|-------------------|----------|
| Thalamus | Router | Query routing to appropriate engine |
| Amygdala | Security Engine | Real-time threat detection (< 1ms) |
| Prefrontal Cortex | Query Optimizer | CortexQL parsing, plan optimization |
| Neocortex | RelationalCore | Long-term structured storage (PostgreSQL) |
| Hippocampus | VectorCore | Pattern completion, semantic search (Qdrant) |
| Working Memory | MemoryCore | Fast access cache (Redis) |
| Cerebellum | TemporalCore | Time-series patterns (TimescaleDB) |
| Thalamic Relay | StreamCore | Event streaming (Redis Streams) |
| Association Cortex | GraphCore | Relationship mapping (Apache AGE) |
| Declarative Memory | ImmutableCore | Permanent records, audit trail |

### 2.2 Query Flow

Every query passes through the same pipeline:

```
1. AMYGDALA (< 1ms)
   ├── SQL injection detection (pattern matching)
   ├── Blocked operation check
   ├── Anomaly detection (excessive quotes, oversized queries)
   └── VERDICT: ALLOW or BLOCK

2. TENANT MIDDLEWARE
   ├── API key extraction from Authorization header
   ├── Tenant resolution via TenantManager
   ├── RLS context injection (SET app.current_tenant)
   └── Rate limit check (5-tier sliding window)

3. CORTEXQL PARSER
   ├── Pattern recognition (FIND SIMILAR, TRAVERSE, SUBSCRIBE, COMMIT)
   ├── Engine routing decision
   ├── Query hint extraction (cache_first, skip_semantic)
   └── Parameterized query preparation

4. READ CASCADE (5 tiers, adaptive thresholds)
   ├── R0: Process-local cache (< 0.1ms, 10K entries)
   ├── R1: Redis/MemoryCore (< 1ms)
   ├── R2: Semantic cache via VectorCore (< 5ms, adaptive cosine threshold)
   │   ├── SQL queries: skip R2 (exact-match only, semantic cache not useful)
   │   ├── Natural language queries: cosine > 0.87
   │   └── RAG / retrieval queries: cosine > 0.85
   ├── R3: Persistent store via RelationalCore (< 50ms)
   └── R4: Deep retrieval (cross-engine merge)

5. WRITE FAN-OUT (Transactional Outbox)
   ├── Sync engines: ACID guarantee (Relational + Immutable)
   ├── Async engines: PG-backed transactional outbox (crash-safe)
   │   └── Replaces in-memory DLQ — survives restarts, no lost writes
   ├── Request coalescing: concurrent identical writes collapsed (prevents cache stampede)
   └── Cache invalidation: R0 + R1 + R2 cleared on write

6. SYNAPTIC PLASTICITY
   ├── Path strengthening: frequently used query paths get faster
   ├── Decay: unused paths weaken over time
   └── Pre-computation: hot paths materialized as views
```

### 2.3 Write Fan-Out Routes

| Data Type | Sync Engines | Async Engines |
|-----------|-------------|---------------|
| payment | Relational + Immutable | Temporal + Stream + Memory |
| agent | Relational | Memory + Stream |
| task | Relational | Temporal + Stream |
| block | Relational | Vector + Memory |
| heartbeat | Temporal | Memory |
| audit | Immutable | Relational |
| experience | Relational | Vector |

---

## 3. Petabyte-Scale Sharding

### 3.1 Why Citus?

Citus is the only PostgreSQL extension that provides transparent distributed query execution. Unlike sharding middleware (Vitess, ProxySQL), Citus:
- Lives **inside PostgreSQL** as an extension
- Supports **all SQL** including JOINs, CTEs, window functions
- Provides **co-location** so related tables share the same shard
- Enables **columnar storage** for 8-12x analytics compression
- Scales to **petabytes** across hundreds of worker nodes

### 3.2 Distribution Strategy

```
Distribution Column: tenant_id
  ├── Hash-based sharding (even distribution)
  ├── 128 shards (supports up to 128 workers)
  └── 3 co-location groups

Co-location Group "cortexgraph":
  customers ←→ customer_identifiers ←→ customer_events ←→ customer_profiles
  (All on same shard = JOINs never cross the network)

Co-location Group "core":
  blocks ←→ agents ←→ tasks ←→ experience_ledger

Co-location Group "a2a":
  a2a_agent_cards ←→ a2a_tasks

Reference Tables (replicated to ALL nodes):
  tenants, asa_standards
```

### 3.3 Scaling Operations

```bash
# Add a new worker (zero downtime)
POST /v1/admin/sharding/add-worker {"host": "worker-3", "port": 5432}

# Rebalance shards across workers
POST /v1/admin/sharding/rebalance

# Isolate premium tenant onto dedicated shard
POST /v1/admin/sharding/isolate-tenant/enterprise-acme

# Convert analytics table to columnar (8-12x compression)
POST /v1/admin/sharding/columnar/query_metrics
```

### 3.4 Performance at Scale

| Scale | Workers | Shards | Throughput | Storage |
|-------|---------|--------|------------|---------|
| Startup | 1 (single node) | 128 | 10K QPS | < 100 GB |
| Growth | 4 | 128 | 40K QPS | < 1 TB |
| Enterprise | 16 | 128 | 150K QPS | < 10 TB |
| Planet-Scale | 128 | 128 | 1M+ QPS | 100+ TB |

---

## 4. AI-Powered Intelligence

### 4.1 AI Index Manager

Traditional databases require manual index creation. CortexDB's AI Index Manager:

1. **Analyzes** `pg_stat_statements` for slow queries
2. **Recommends** optimal index types:
   - BTREE for equality/range queries
   - BRIN for time-series (100x smaller than btree)
   - GIN for JSONB and array queries
   - HNSW/IVF for vector similarity search
3. **Creates** indexes `CONCURRENTLY` (no table locks)
4. **Tunes** vector index parameters based on dataset size
5. **Garbage collects** unused and duplicate indexes

### 4.2 CortexGraph™ Customer Intelligence

Four-layer customer intelligence platform:

```
Layer 1: IDENTITY RESOLUTION
  ├── 9 identifier types (email, phone, device_id, loyalty_id, ...)
  ├── Deterministic: exact match on identifier
  ├── Probabilistic: VectorCore cosine similarity > 0.92
  └── Merge: unify duplicates with ImmutableCore audit

Layer 2: EVENT DATABASE
  ├── Real-time ingestion via StreamCore
  ├── Time-series storage in TemporalCore
  ├── Auto-graph-edge creation (purchase → PURCHASED edge)
  └── Financial events → ImmutableCore audit trail

Layer 3: RELATIONSHIP GRAPH
  ├── 7 node types (Customer, Product, Store, Campaign, Agent, Vendor, Household)
  ├── 14 edge types (PURCHASED, VISITED, REFERRED, TARGETED, ...)
  ├── Collaborative filtering recommendations
  └── Campaign attribution (Campaign → Customer → Purchase)

Layer 4: BEHAVIORAL PROFILE
  ├── RFM scoring (Recency, Frequency, Monetary)
  ├── Churn probability (heuristic, upgradeable to ML)
  ├── Health score (composite 0-100)
  ├── Auto-segmentation (VIP, Loyal, At-Risk, Churned, ...)
  └── Nightly batch recompute via Sleep Cycle
```

### 4.3 MCP Server for AI Agents

CortexDB exposes itself as an MCP (Model Context Protocol) server with 13 tools:

```
cortexdb.query              → Execute CortexQL
cortexdb.write              → Write with fan-out
cortexdb.health             → System health
cortexdb.blocks.list        → Block registry
cortexdb.agents.list        → Agent registry
cortexdb.ledger.verify      → Audit chain integrity
cortexdb.cache.stats        → Cache performance
cortexdb.a2a.discover       → Agent discovery
cortexgraph.customer_360    → Complete customer view
cortexgraph.similar_customers → Lookalike targeting
cortexgraph.churn_risk      → Churn prediction
cortexgraph.recommend_products → Collaborative filtering
cortexgraph.attribution     → Campaign attribution
```

---

## 5. Embedding Sync Pipeline

The number one problem with hybrid relational + vector architectures is **stale embeddings**. When a row changes in PostgreSQL, the corresponding vector in Qdrant silently goes stale. Queries return semantically incorrect results with no error.

CortexDB eliminates this with a fully automated embedding sync pipeline:

```
1. WRITE to RelationalCore (PostgreSQL)
   └── PG trigger fires NOTIFY on cortexdb_embedding_sync channel

2. LISTENER (async, always-on)
   ├── Receives NOTIFY payload: {table, id, operation, tenant_id}
   ├── Fetches updated row from RelationalCore
   └── Routes to embedding pipeline

3. EMBEDDING PIPELINE
   ├── Unified embedding codepath (same model for writes + queries)
   ├── Re-embeds changed fields using configured embedding model
   └── Upserts new vector to Qdrant (VectorCore)

4. RESULT
   └── Vector search always reflects current relational state
```

Key properties:
- **Zero-config**: Any table registered for vector search gets auto-sync
- **Crash-safe**: Uses the transactional outbox — pending syncs survive restarts
- **Consistent codepath**: Write-time and query-time embeddings use the same model, eliminating drift
- **Tenant-aware**: Each tenant's vectors are synced to their isolated Qdrant collection

This is CortexDB's answer to the consistency problem (Section 1.2): when data changes in one engine, all other engines converge automatically.

---

## 6. Agent Memory Protocol

CortexDB provides a structured memory system for AI agents, exposed as MCP tools. Agents can **store**, **recall**, **forget**, and **share** memories with built-in cognitive decay.

### 6.1 Memory Operations

| Operation | Description | MCP Tool |
|-----------|------------|----------|
| **Store** | Persist a memory with importance score | `cortexdb.memory.store` |
| **Recall** | Retrieve memories by semantic similarity | `cortexdb.memory.recall` |
| **Forget** | Explicitly remove a memory | `cortexdb.memory.forget` |
| **Share** | Make a memory accessible to other agents | `cortexdb.memory.share` |

### 6.2 Ebbinghaus Decay Model

Memories decay over time following an Ebbinghaus-inspired forgetting curve:

```
retention(t) = importance × e^(-λt)

Where:
  importance = initial weight (0.0–1.0), set at store time
  λ = decay constant (configurable per agent/collection)
  t = time elapsed since last access
```

High-importance memories decay slowly; low-importance memories fade. Each recall resets the decay timer (spaced repetition effect). The Sleep Cycle's nightly decay phase garbage-collects memories below the retention threshold.

### 6.3 Multi-Agent Memory Sharing

Agents can share memories via the `share` operation, which copies the memory into a shared collection accessible by target agents. Shared memories carry provenance metadata (source agent, timestamp, original importance) so receiving agents can assess trust.

---

## 7. Security Hardening

Version 4.0 includes critical security fixes identified during expert evaluation:

| Fix | Category | Detail |
|-----|----------|--------|
| RLS context injection | P0 | Changed `SET app.current_tenant` to `SET LOCAL` — scoped to transaction, prevents leakage across pooled connections |
| Admin auth bypass | P0 | Admin endpoints now require authentication; previously accessible without credentials |
| Field encryption in read/write paths | P1 | AES-256-GCM encryption wired directly into RelationalCore read/write — not a bolt-on layer |
| A2A task externalization | P1 | Agent-to-agent tasks persisted to Redis + PostgreSQL with read-your-writes consistency (multi-instance safe) |
| Unified embedding codepath | P1 | Single embedding model for both indexing and querying eliminates vector drift |
| PostgreSQL-backed immutable ledger | P1 | Ledger entries stored in PostgreSQL with append-only triggers, replacing in-memory structure |

---

## 8. Compliance Architecture

### 8.1 Control Coverage

CortexDB maps 39 controls across 5 compliance frameworks to specific implementation features:

| Framework | Controls | Key CortexDB Features |
|-----------|----------|----------------------|
| FedRAMP Moderate | 10 | RLS isolation, Amygdala threat detection, ImmutableCore audit |
| SOC 2 Type II | 8 | Tenant lifecycle, monitoring, change management, privacy |
| HIPAA | 8 | PHI field encryption, access audit, integrity controls |
| PCI DSS v4.0 | 8 | PAN tokenization, key management, secure development |
| PA-DSS | 5 | Application logging, secure auth, testing |

### 8.2 Encryption Architecture

```
Master Key (KEK)
  ├── Stored in environment variable (production: AWS KMS / GCP KMS)
  └── Encrypts all Data Encryption Keys

Data Encryption Keys (DEK) — per tenant
  ├── Generated: secrets.token_bytes(32) → 256 bits
  ├── Algorithm: AES-256-GCM (authenticated encryption)
  ├── Rotation: 90-day schedule, old versions kept for decryption
  └── Envelope encryption: DEK encrypted by KEK

Field Classification:
  PUBLIC       → No encryption (customer_id, block_type)
  INTERNAL     → Organization-internal (preferred_categories)
  CONFIDENTIAL → PII encryption (name, email, phone)
  RESTRICTED   → PHI/PCI encryption (SSN, PAN, diagnoses)
```

### 8.3 Audit Trail

Every compliance-relevant action generates an immutable audit event:

```json
{
  "event_id": "550e8400-e29b-41d4-a716-446655440000",
  "event_type": "PHI_ACCESS",
  "actor": "agent-analytics-001",
  "resource": "patient:P-12345",
  "action": "phi_access",
  "outcome": "success",
  "details": {
    "fields_accessed": ["diagnosis", "medication"],
    "purpose": "treatment_recommendation"
  },
  "timestamp": 1709712000.0
}
```

Evidence reports generated per framework with retention policies:
- HIPAA: 6 years
- FedRAMP: 3 years
- PCI-DSS: 1 year online + 1 year archive
- Maximum retention: 7 years

---

## 9. Multi-Tenancy

### 9.1 Isolation Model

CortexDB implements defense-in-depth tenant isolation:

| Layer | Mechanism | Bypass Protection |
|-------|-----------|-------------------|
| API | Bearer token + tenant resolution | Invalid tokens rejected |
| Middleware | ContextVar tenant injection | No cross-request leakage |
| Database | PostgreSQL Row-Level Security | Database-level enforcement |
| Cache | Key prefix `tenant:{id}:` | Namespace isolation |
| Vector | Collection-per-tenant | Physical separation |
| Stream | Channel prefix `tenant:{id}:` | Subscription isolation |
| Encryption | Per-tenant DEK | Cryptographic isolation |

### 9.2 Tenant Lifecycle

```
ONBOARDING → ACTIVE → SUSPENDED → OFFBOARDING → PURGED
     │          │          │           │            │
     │          │          │           │            └── Data deleted
     │          │          │           └── Data export
     │          │          └── Access frozen
     │          └── Full access
     └── Provisioning
```

### 9.3 Plan-Based Rate Limiting

| Plan | Queries/min | Writes/min | Agents | Endpoints/min |
|------|------------|------------|--------|---------------|
| Free | 60 | 30 | 5 | 30 |
| Growth | 600 | 300 | 50 | 300 |
| Enterprise | 6000 | 3000 | 500 | 3000 |
| Custom | Configurable | Configurable | Unlimited | Configurable |

---

## 10. Self-Healing Infrastructure

### 10.1 Grid State Machine

Every node in the CortexDB grid follows a deterministic state machine:

```
SPAWNED → INITIALIZING → RUNNING ←→ WAITING
                                ↕
                          ESCALATING → RETRY
                                ↕
                    EVALUATING → COMPLETE
                                ↕
                              FAILED → RETIRED
```

### 10.2 Health Scoring

Composite health score (0-100) based on:
- Heartbeat recency (25%)
- Error rate (25%)
- Latency percentile (20%)
- Memory utilization (15%)
- CPU utilization (15%)

Classifications: PRISTINE (90+) → STABLE (70-89) → FLAKY (40-69) → CHRONIC (20-39) → TERMINAL (0-19)

### 10.3 Sleep Cycle (Nightly Maintenance)

Six ordered tasks run during off-peak hours:

1. **Prune**: Remove expired cache entries, old metrics
2. **Consolidate**: Merge small segments, compact storage
3. **Rebuild**: Refresh materialized views, rebuild degraded indexes
4. **Precompute**: Materialize hot query paths
5. **Decay**: Weaken unused synaptic paths
6. **Analyze**: Update PostgreSQL statistics, health report

---

## 11. Technology Stack

| Component | Technology | Version |
|-----------|-----------|---------|
| API Framework | FastAPI | 0.115 |
| Primary Database | PostgreSQL + Citus | 16 + 12.1 |
| Time-Series | TimescaleDB | Latest |
| Graph Engine | Apache AGE | Latest |
| Cache | Redis | 7 |
| Vector Search | Qdrant | Latest |
| Event Streaming | Redis Streams | 7 |
| Observability | OpenTelemetry + Prometheus + Grafana | Latest |
| Container | Docker Compose | 3.9 |
| Language | Python | 3.11+ |

---

## 12. Conclusion

CortexDB v4.0 represents a paradigm shift in database architecture. By unifying seven database paradigms into one consciousness-inspired system, it eliminates data silos, reduces operational complexity by 7x, and provides native AI agent integration — all while meeting the strictest compliance requirements (FedRAMP, HIPAA, PCI-DSS) and scaling to petabytes via Citus distributed sharding.

The database is not just a storage layer — it is an intelligent system that optimizes itself (AI indexing, synaptic plasticity), heals itself (grid repair, resurrection protocol), and understands its data (CortexGraph customer intelligence, semantic search, relationship traversal).

Version 4.0's architecture has been validated through a **PhD expert panel evaluation** comprising three specialists in distributed systems, database internals, and AI/ML infrastructure. Their review confirmed the soundness of the embedding sync pipeline, transactional outbox pattern, and agent memory protocol, while driving the P0 security fixes (RLS scoping, admin auth) documented in Section 7.

---

*CortexDB™ and CortexQL™ are trademarks of Nirlab Inc.*
*Copyright (c) 2026 Nirlab Inc. All rights reserved.*
