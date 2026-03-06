# CortexDB™ Developer Guide

**Everything you need to build with CortexDB.**

---

## Table of Contents

1. [Getting Started](#1-getting-started)
2. [Authentication & Tenancy](#2-authentication--tenancy)
3. [CortexQL Query Language](#3-cortexql-query-language)
4. [Writing Data](#4-writing-data)
5. [CortexGraph Customer Intelligence](#5-cortexgraph-customer-intelligence)
6. [Vector Search & AI](#6-vector-search--ai)
7. [Real-Time Streaming](#7-real-time-streaming)
8. [Immutable Ledger](#8-immutable-ledger)
9. [MCP Integration (AI Agents)](#9-mcp-integration-ai-agents)
10. [Sharding & Scaling](#10-sharding--scaling)
11. [Compliance & Encryption](#11-compliance--encryption)
12. [Monitoring & Observability](#12-monitoring--observability)
13. [SDK Patterns](#13-sdk-patterns)
14. [Error Handling](#14-error-handling)
15. [Performance Tuning](#15-performance-tuning)

---

## 1. Getting Started

### Installation

```bash
# Clone the repository
git clone https://github.com/nirlab/cortexdb.git
cd cortexdb

# Start all services
docker compose up -d

# Verify
curl http://localhost:5400/health/live
```

### Base URL
```
http://localhost:5400    # CortexQL API
```

### First Request

```bash
curl -X POST http://localhost:5400/v1/query \
  -H "Content-Type: application/json" \
  -d '{"cortexql": "SELECT NOW() as server_time"}'
```

Response:
```json
{
  "data": [{"server_time": "2026-03-06T12:00:00Z"}],
  "tier_served": "R3",
  "engines_hit": ["relational_core"],
  "latency_ms": 2.341,
  "cache_hit": false
}
```

### Python Client

```python
import httpx

class CortexClient:
    def __init__(self, base_url="http://localhost:5400", api_key=None):
        self.base_url = base_url
        self.headers = {"Content-Type": "application/json"}
        if api_key:
            self.headers["Authorization"] = f"Bearer {api_key}"

    async def query(self, cortexql, params=None, hint=None):
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{self.base_url}/v1/query",
                json={"cortexql": cortexql, "params": params, "hint": hint},
                headers=self.headers)
            return resp.json()

    async def write(self, data_type, payload, actor="sdk"):
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{self.base_url}/v1/write",
                json={"data_type": data_type, "payload": payload, "actor": actor},
                headers=self.headers)
            return resp.json()

    async def customer_360(self, customer_id):
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.base_url}/v1/cortexgraph/customer/{customer_id}/360",
                headers=self.headers)
            return resp.json()

# Usage
db = CortexClient(api_key="your-api-key")
result = await db.query("SELECT * FROM blocks LIMIT 10")
```

### JavaScript/TypeScript Client

```typescript
class CortexClient {
  constructor(
    private baseUrl = 'http://localhost:5400',
    private apiKey?: string
  ) {}

  private get headers() {
    const h: Record<string, string> = { 'Content-Type': 'application/json' };
    if (this.apiKey) h['Authorization'] = `Bearer ${this.apiKey}`;
    return h;
  }

  async query(cortexql: string, params?: object, hint?: string) {
    const res = await fetch(`${this.baseUrl}/v1/query`, {
      method: 'POST',
      headers: this.headers,
      body: JSON.stringify({ cortexql, params, hint }),
    });
    return res.json();
  }

  async write(dataType: string, payload: object, actor = 'sdk') {
    const res = await fetch(`${this.baseUrl}/v1/write`, {
      method: 'POST',
      headers: this.headers,
      body: JSON.stringify({ data_type: dataType, payload, actor }),
    });
    return res.json();
  }

  async customer360(customerId: string) {
    const res = await fetch(
      `${this.baseUrl}/v1/cortexgraph/customer/${customerId}/360`,
      { headers: this.headers }
    );
    return res.json();
  }
}
```

---

## 2. Authentication & Tenancy

### API Key Authentication

Every request should include an API key:

```bash
curl -H "Authorization: Bearer YOUR_API_KEY" \
     http://localhost:5400/v1/query \
     -d '{"cortexql": "SELECT * FROM blocks"}'
```

### Tenant Onboarding

```bash
# Create a new tenant
POST /v1/admin/tenants
{
  "tenant_id": "acme-corp",
  "name": "Acme Corporation",
  "plan": "growth"
}

# Response includes API key (shown only once)
{
  "tenant_id": "acme-corp",
  "api_key": "ctx_a1b2c3d4e5f6...",
  "status": "onboarding"
}

# Activate the tenant
POST /v1/admin/tenants/acme-corp/activate
```

### Tenant Lifecycle

```
POST /v1/admin/tenants                          # Create
POST /v1/admin/tenants/{id}/activate            # Activate
POST /v1/admin/tenants/{id}/suspend?reason=...  # Suspend
POST /v1/admin/tenants/{id}/export              # Export data (GDPR)
POST /v1/admin/tenants/{id}/purge               # Delete permanently
```

### How Isolation Works

All queries are automatically scoped to the authenticated tenant:
```sql
-- Developer writes:
SELECT * FROM customers WHERE status = 'active'

-- CortexDB executes (with RLS):
SELECT * FROM customers WHERE status = 'active'
  AND tenant_id = 'acme-corp'  -- Injected by RLS policy
```

No cross-tenant data leakage is possible at the database level.

---

## 3. CortexQL Query Language

### Standard SQL

CortexQL is a superset of SQL. All standard queries work:

```sql
-- Select
SELECT * FROM blocks WHERE block_type = 'L1_skill' ORDER BY usage_count DESC LIMIT 10

-- Join
SELECT a.agent_id, t.description, t.status
FROM agents a JOIN tasks t ON a.agent_id = t.agent_id
WHERE a.state = 'RUNNING'

-- Aggregate
SELECT block_type, COUNT(*) as count, AVG(success_rate) as avg_success
FROM blocks GROUP BY block_type

-- Time-series (TimescaleDB)
SELECT time_bucket('1 hour', time) AS hour,
       AVG(cpu_pct) AS avg_cpu
FROM heartbeats
WHERE time > NOW() - INTERVAL '24 hours'
GROUP BY hour ORDER BY hour
```

### CortexQL Extensions

**Vector Similarity Search:**
```sql
FIND SIMILAR TO 'machine learning customer segmentation' IN block_embeddings LIMIT 10
```
Routes to VectorCore (Qdrant). Returns results sorted by cosine similarity.

**Graph Traversal:**
```sql
TRAVERSE Customer->PURCHASED->Product->PURCHASED<-Customer DEPTH 3
```
Routes to GraphCore (Apache AGE). Cypher-style path traversal.

**Real-Time Subscription:**
```sql
SUBSCRIBE TO events:purchase_completed
```
Routes to StreamCore (Redis Streams). Returns streaming connection.

**Immutable Ledger Write:**
```sql
COMMIT TO LEDGER { type: 'AUDIT', action: 'data_export', actor: 'admin' }
```
Routes to ImmutableCore. SHA-256 hash chain, append-only.

### Query Hints

Control query routing and caching behavior:

```bash
POST /v1/query
{
  "cortexql": "SELECT * FROM customers WHERE customer_id = 'C-123'",
  "hint": "cache_first"
}
```

| Hint | Behavior |
|------|----------|
| `cache_first` | Prioritize cache tiers (R0, R1) |
| `skip_semantic` | Skip R2 semantic cache |
| `force_refresh` | Bypass all caches, go to R3 |

### Response Format

Every query returns:
```json
{
  "data": [...],                    // Query results
  "tier_served": "R1",             // Which cache tier served this
  "engines_hit": ["memory_core"],  // Which engines were queried
  "latency_ms": 0.423,            // Total latency
  "cache_hit": true,              // Whether result was cached
  "metadata": {}                   // Additional info
}
```

---

## 4. Writing Data

### Write Fan-Out

Writes are automatically routed to appropriate engines:

```bash
POST /v1/write
{
  "data_type": "payment",
  "payload": {
    "customer_id": "C-123",
    "amount": 99.99,
    "currency": "USD"
  },
  "actor": "payment-service"
}
```

Response:
```json
{
  "status": "success",
  "fan_out": {
    "sync": {
      "relational": {"status": "success"},
      "immutable": {"status": "success"}
    },
    "async": {
      "temporal": {"status": "queued"},
      "stream": {"status": "queued"},
      "memory": {"status": "queued"}
    },
    "latency_ms": 8.234
  }
}
```

### Data Types and Routing

| Data Type | Sync (ACID) | Async (best-effort) |
|-----------|------------|---------------------|
| `payment` | Relational + Immutable | Temporal + Stream + Memory |
| `agent` | Relational | Memory + Stream |
| `task` | Relational | Temporal + Stream |
| `block` | Relational | Vector + Memory |
| `heartbeat` | Temporal | Memory |
| `audit` | Immutable | Relational |
| `experience` | Relational | Vector |

### Cache Invalidation

Writes automatically invalidate relevant caches:
- R0 (process cache): Cleared for affected keys
- R1 (Redis cache): Deleted
- R2 (semantic cache): Invalidated by table/key pattern

No stale reads after writes.

---

## 5. CortexGraph Customer Intelligence

### Identity Resolution

Resolve one or more identifiers to a single customer:

```bash
POST /v1/cortexgraph/identify
{
  "identifiers": {
    "email": "sarah@example.com",
    "phone": "+1-555-0123",
    "loyalty_id": "LOY-456"
  },
  "attributes": {
    "name": "Sarah Chen",
    "city": "New York"
  }
}
```

Response:
```json
{
  "customer_id": "550e8400-...",
  "is_new": false,
  "match_type": "deterministic",
  "confidence": 1.0,
  "matched_on": "email",
  "identifiers_linked": 1
}
```

Match types:
- **deterministic**: Exact match on identifier (confidence = 1.0)
- **probabilistic**: VectorCore cosine similarity > 0.92
- **new**: No match found, new customer created

### Event Tracking

```bash
# Single event
POST /v1/cortexgraph/track
{
  "customer_id": "C-123",
  "event_type": "purchase_completed",
  "properties": {
    "product_id": "SKU-A1",
    "amount": 89.99,
    "channel": "web"
  },
  "source": "checkout-service"
}

# Batch events
POST /v1/cortexgraph/track/batch
{
  "events": [
    {"customer_id": "C-123", "event_type": "page_view", "properties": {"page": "/products"}},
    {"customer_id": "C-124", "event_type": "cart_abandoned", "properties": {"value": 149.99}}
  ]
}
```

Auto-created graph edges:
- `purchase_completed` → Customer-[PURCHASED]->Product
- `store_visited` → Customer-[VISITED]->Store
- `campaign_responded` → Customer-[RESPONDED_TO]->Campaign

### Customer 360

```bash
GET /v1/cortexgraph/customer/C-123/360
```

Returns all 4 layers in one call:
- **Identity**: Name, email, phone, merge count
- **Events**: Last 30 days activity, 90-day event counts
- **Relationships**: Products purchased, stores visited, campaigns
- **Profile**: RFM segment, health score, churn probability

### Behavioral Profile

```bash
GET /v1/cortexgraph/customer/C-123/profile
```
```json
{
  "customer_id": "C-123",
  "profile": {
    "recency_days": 3,
    "frequency_90d": 12,
    "monetary_90d": 845.50,
    "rfm_segment": "Loyal",
    "health_score": 87.3,
    "churn_probability": 0.08,
    "segments": ["Loyal", "High-Value", "Frequent-Buyer"]
  }
}
```

RFM Segments: VIP, Loyal, Regular, Promising, New, At-Risk, Dormant, Churned

### Similar Customers

```bash
GET /v1/cortexgraph/similar/C-123?limit=10
```
Finds customers sharing behavioral segments. Use for lookalike targeting.

### Product Recommendations

```bash
POST /v1/cortexgraph/recommend/C-123?limit=5
```
Collaborative filtering: products bought by similar customers but not by this customer.

### Campaign Attribution

```bash
GET /v1/cortexgraph/attribution/CAMP-SUMMER-2026
```
Traces: Campaign → Targeted Customers → Purchases after targeting.

---

## 6. Vector Search & AI

### Semantic Search

```bash
POST /v1/query
{
  "cortexql": "FIND SIMILAR TO 'customer churn prediction analytics' IN block_embeddings LIMIT 5"
}
```

### Embedding Pipeline

CortexDB uses `all-MiniLM-L6-v2` (384 dimensions) with hash-based fallback:

```python
# Automatic embedding on vector writes
POST /v1/write
{
  "data_type": "block",
  "payload": {
    "name": "churn-predictor",
    "description": "ML model for predicting customer churn probability",
    "tags": ["ml", "churn", "prediction"]
  }
}
# Description automatically embedded and stored in VectorCore
```

### AI Index Tuning

```bash
# Auto-tune HNSW parameters based on dataset size
POST /v1/admin/indexes/tune-vector?collection=customer_embeddings
```
```json
{
  "total_vectors": 1000000,
  "config": {
    "hnsw_m": 32,
    "hnsw_ef_construction": 256,
    "hnsw_ef_search": 128
  },
  "status": "applied"
}
```

---

## 7. Real-Time Streaming

### Event Subscription

```sql
SUBSCRIBE TO events:purchase_completed
```

### Stream Publishing (via Write)

```bash
POST /v1/write
{
  "data_type": "payment",
  "payload": {"customer_id": "C-123", "amount": 99.99}
}
# Automatically published to StreamCore stream: events:payment
```

### Event Counts

```bash
GET /v1/cortexgraph/customer/C-123/events?event_type=purchase_completed&days=30
```

---

## 8. Immutable Ledger

### Write to Ledger

```bash
POST /v1/write
{
  "data_type": "audit",
  "payload": {
    "entry_type": "DATA_EXPORT",
    "customer_id": "C-123",
    "exported_by": "admin@acme.com",
    "fields": ["name", "email", "orders"]
  },
  "actor": "admin"
}
```

### Verify Chain Integrity

```bash
POST /admin/ledger/verify
```
```json
{
  "chain_intact": true,
  "entries": 15234
}
```

### Read Recent Entries

```bash
GET /v1/ledger/recent?limit=10
```

---

## 9. MCP Integration (AI Agents)

### Discover Available Tools

```bash
GET /v1/mcp/tools
```
Returns 13 tool definitions compatible with Claude MCP, LangGraph, OpenAI function calling.

### Call a Tool

```bash
POST /v1/mcp/call
{
  "tool": "cortexgraph.customer_360",
  "input": {"customer_id": "C-123"}
}
```

### Claude MCP Configuration

```json
{
  "mcpServers": {
    "cortexdb": {
      "url": "http://localhost:5400/v1/mcp",
      "tools": "auto-discover"
    }
  }
}
```

### LangGraph Integration

```python
from langchain_core.tools import tool

@tool
async def cortexdb_query(cortexql: str) -> dict:
    """Execute a CortexQL query against CortexDB."""
    async with httpx.AsyncClient() as client:
        resp = await client.post("http://localhost:5400/v1/mcp/call",
            json={"tool": "cortexdb.query", "input": {"cortexql": cortexql}})
        return resp.json()
```

---

## 10. Sharding & Scaling

### Initialize Citus

```bash
# Step 1: Enable extension
POST /v1/admin/sharding/initialize

# Step 2: Distribute tables
POST /v1/admin/sharding/distribute
```

### Add Workers

```bash
POST /v1/admin/sharding/add-worker
{"host": "worker-3.cortexdb.internal", "port": 5432}

# Rebalance shards
POST /v1/admin/sharding/rebalance
```

### Monitor Shard Health

```bash
GET /v1/admin/sharding/stats
```

### Premium Tenant Isolation

```bash
# Move tenant to dedicated shard for guaranteed performance
POST /v1/admin/sharding/isolate-tenant/enterprise-acme
```

---

## 11. Compliance & Encryption

### Run Compliance Audit

```bash
# All frameworks
GET /v1/compliance/audit

# Specific framework
GET /v1/compliance/audit/hipaa
GET /v1/compliance/audit/pci_dss
GET /v1/compliance/audit/fedramp
GET /v1/compliance/audit/soc2
```

### Field Encryption

Sensitive fields are automatically encrypted based on table classification:

```bash
# Check which fields are encrypted for a table
GET /v1/compliance/encryption/classification/customers
```
```json
{
  "canonical_name": "confidential",
  "canonical_email": "confidential",
  "canonical_phone": "confidential",
  "customer_id": "internal"
}
```

### Key Rotation

```bash
# Rotate keys that are due (90-day schedule)
POST /v1/compliance/encryption/rotate-keys
```

### Audit Trail

```bash
# Query audit events
GET /v1/compliance/audit-log?event_type=PHI_ACCESS&limit=50

# Evidence report for auditors
GET /v1/compliance/evidence/hipaa
```

---

## 12. Monitoring & Observability

### Health Endpoints

```bash
GET /health/live          # Liveness (for Kubernetes)
GET /health/ready         # Readiness (engine connectivity)
GET /health/deep          # All subsystems with stats
GET /health/metrics       # Prometheus format
```

### Prometheus Metrics

```bash
curl http://localhost:5400/health/metrics
```
```
# HELP cortexdb_queries_total Total queries processed
# TYPE cortexdb_queries_total counter
cortexdb_queries_total{tier="R0",tenant="acme"} 15234
cortexdb_queries_total{tier="R1",tenant="acme"} 4521
cortexdb_queries_total{tier="R3",tenant="acme"} 892
```

### Grafana Dashboard

Access Grafana at `http://localhost:3000` (default password: `cortex_admin`).

Pre-configured dashboards:
- CortexDB Overview (QPS, cache hit rate, engine health)
- Tenant Analytics (per-tenant usage, rate limits)
- CortexGraph (identity resolutions, events/sec, churn stats)

### OpenTelemetry Tracing

Every request generates a trace with spans for each engine hop:

```
[cortexdb.query] 12.3ms
  ├── [amygdala.assess] 0.05ms
  ├── [parser.parse] 0.02ms
  ├── [read_cascade.r0] 0.01ms (miss)
  ├── [read_cascade.r1] 0.4ms (miss)
  └── [read_cascade.r3] 11.8ms (hit)
```

---

## 13. SDK Patterns

### Connection Pooling

```python
# Reuse a single client instance
client = CortexClient(api_key="...")

# All requests share connection pool
results = await asyncio.gather(
    client.query("SELECT * FROM blocks LIMIT 10"),
    client.query("SELECT * FROM agents LIMIT 10"),
    client.customer_360("C-123"),
)
```

### Batch Operations

```python
# Batch event tracking (much faster than individual calls)
events = [
    {"customer_id": f"C-{i}", "event_type": "page_view", "properties": {"page": "/home"}}
    for i in range(1000)
]
await client.write("batch_events", {"events": events})
```

### Error Retry Pattern

```python
import asyncio

async def query_with_retry(client, cortexql, max_retries=3):
    for attempt in range(max_retries):
        try:
            return await client.query(cortexql)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:  # Rate limited
                retry_after = int(e.response.headers.get("Retry-After", 1))
                await asyncio.sleep(retry_after)
            elif e.response.status_code >= 500:
                await asyncio.sleep(0.1 * (2 ** attempt))
            else:
                raise
    raise Exception("Max retries exceeded")
```

---

## 14. Error Handling

### HTTP Status Codes

| Code | Meaning | Action |
|------|---------|--------|
| 200 | Success | Process response |
| 400 | Bad request (invalid CortexQL, missing params) | Fix request |
| 401 | Unauthorized (invalid API key) | Check API key |
| 403 | Forbidden (tenant suspended) | Contact admin |
| 404 | Resource not found | Check ID |
| 429 | Rate limited | Retry after `Retry-After` header |
| 500 | Internal error | Retry with backoff |
| 503 | Service unavailable (engine down) | Wait for recovery |

### Rate Limit Response

```json
{
  "detail": "Rate limit exceeded"
}
```
Headers:
```
X-RateLimit-Limit: 600
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 1709712060
Retry-After: 30
```

### Amygdala Block Response

```json
{
  "data": {
    "error": "BLOCKED_BY_AMYGDALA",
    "threats": ["SQL_INJECTION: 'OR 1=1'"]
  },
  "tier_served": "R0",
  "engines_hit": ["amygdala"]
}
```

---

## 15. Performance Tuning

### Query Optimization

1. **Use hints**: `"hint": "cache_first"` for read-heavy queries
2. **Limit results**: Always use `LIMIT` for large tables
3. **Use time ranges**: Filter time-series with `WHERE time > NOW() - INTERVAL '...'`
4. **Leverage indexes**: Check `GET /v1/admin/indexes/recommend` for missing indexes

### Cache Strategy

| Scenario | Hint | Effect |
|----------|------|--------|
| Frequently read, rarely changed | `cache_first` | Serve from R0/R1 |
| Real-time data needed | `force_refresh` | Bypass cache |
| Large analytical query | `skip_semantic` | Skip R2 vector search |

### Batch vs. Individual Writes

| Method | Throughput | Use When |
|--------|-----------|----------|
| Individual `/v1/write` | ~500/sec | Real-time, low volume |
| Batch `/v1/cortexgraph/track/batch` | ~10K/sec | Event ingestion |

### Index Recommendations

```bash
# Let AI analyze your queries and recommend indexes
GET /v1/admin/indexes/recommend

# Create recommended indexes (no locks)
POST /v1/admin/indexes/create?concurrently=true
```

---

*CortexDB™ — Built for developers who refuse to manage seven databases.*
*Copyright (c) 2026 Nirlab Inc.*
