# CortexDB™ Use Cases

**How industries use one database to replace seven.**

---

## Table of Contents

1. [Retail & E-Commerce](#1-retail--e-commerce)
2. [Healthcare & Life Sciences](#2-healthcare--life-sciences)
3. [Financial Services & Banking](#3-financial-services--banking)
4. [SaaS & Multi-Tenant Platforms](#4-saas--multi-tenant-platforms)
5. [AI Agent Platforms](#5-ai-agent-platforms)
6. [Government & Public Sector](#6-government--public-sector)
7. [Telecommunications](#7-telecommunications)
8. [Gaming & Entertainment](#8-gaming--entertainment)
9. [Logistics & Supply Chain](#9-logistics--supply-chain)
10. [IoT & Industrial](#10-iot--industrial)

---

## 1. Retail & E-Commerce

### The Challenge
A mid-size retailer with 2M customers runs PostgreSQL for orders, Redis for sessions, Elasticsearch for product search, a separate recommendation engine, and Segment for customer analytics. Five teams manage five systems. Customer data is fragmented.

### CortexDB Solution

**Single customer view in one call:**
```bash
GET /v1/cortexgraph/customer/CUST-12345/360
```
```json
{
  "customer_id": "CUST-12345",
  "layers": {
    "identity": {
      "name": "Sarah Chen",
      "email": "sarah@example.com",
      "identifiers": 4,
      "merge_count": 1
    },
    "events": {
      "recent_30d": [
        {"event_type": "purchase_completed", "amount": 89.99},
        {"event_type": "store_visited", "store_id": "NYC-001"}
      ],
      "counts_90d": {"purchase_completed": 8, "page_view": 142}
    },
    "relationships": {
      "purchased": ["SKU-A1", "SKU-B2", "SKU-C3"],
      "visited": ["NYC-001", "LA-002"]
    },
    "profile": {
      "rfm_segment": "VIP",
      "health_score": 92.4,
      "churn_probability": 0.05,
      "monetary_90d": 1245.00
    }
  }
}
```

**Real-time product recommendations:**
```bash
POST /v1/cortexgraph/recommend/CUST-12345
```
Returns products bought by similar customers but not by this customer (collaborative filtering via graph traversal).

**Churn prevention dashboard:**
```bash
GET /v1/cortexgraph/churn-risk?threshold=0.6
```
Returns all customers with churn probability > 60%, sorted by revenue impact.

**Campaign attribution:**
```bash
GET /v1/cortexgraph/attribution/CAMP-SUMMER-2026
```
```json
{
  "campaign_id": "CAMP-SUMMER-2026",
  "customers_targeted": 15000,
  "customers_purchased": 2340,
  "conversion_rate": 15.6,
  "revenue": 234567.89
}
```

### Engines Used
| Feature | Engine | Previously |
|---------|--------|-----------|
| Orders & inventory | RelationalCore | PostgreSQL |
| Session cache | MemoryCore | Redis |
| Product search | VectorCore | Elasticsearch |
| Customer graph | GraphCore | Custom code |
| Purchase events | TemporalCore + StreamCore | Segment + TimescaleDB |
| PCI audit trail | ImmutableCore | Custom ledger |

### ROI
- **Infrastructure**: 7 systems → 1 ($180K/yr savings)
- **Engineering**: 3 fewer DBAs, 2 fewer integration engineers
- **Customer insight**: Real-time 360° view (was 24hr batch delay)
- **Churn reduction**: 12% improvement (early detection + action)

---

## 2. Healthcare & Life Sciences

### The Challenge
A health system with 500K patients needs HIPAA-compliant storage across EHR data, patient identity matching, lab result time-series, care team relationship mapping, and tamper-evident audit trails. Six vendors, six BAAs, six security reviews.

### CortexDB Solution

**Patient identity resolution across systems:**
```bash
POST /v1/cortexgraph/identify
{
  "identifiers": {
    "email": "john.doe@email.com",
    "phone": "+1-555-0123",
    "medical_record_number": "MRN-456789"
  },
  "attributes": {"name": "John Doe", "dob": "1985-03-15"}
}
```
Deterministic match on MRN/email/phone. Probabilistic match via VectorCore for fuzzy cases (cosine > 0.92). HIPAA audit logged automatically.

**PHI field encryption:**
All patient data encrypted at field level with AES-256-GCM:
```python
# Automatic encryption on write
encrypted_payload = field_encryption.encrypt_payload(
    {"canonical_name": "John Doe", "canonical_email": "john@example.com"},
    table="customers",
    tenant_id="hospital-network-1"
)
# canonical_name → {"_encrypted": true, "ciphertext": "...", "key_id": "tenant-hospital-1"}
```

**Lab result time-series:**
```bash
POST /v1/query
{"cortexql": "SELECT time_bucket('1 day', time) AS day, AVG(value) FROM lab_results WHERE patient_id = 'P-12345' AND test_type = 'A1C' AND time > NOW() - INTERVAL '1 year' GROUP BY day ORDER BY day"}
```

**Care team relationship graph:**
```bash
# Which doctors treated this patient? Which patients share the same specialist?
TRAVERSE Patient->TREATED_BY->Doctor->TREATED_BY<-Patient DEPTH 2
```

**HIPAA compliance audit:**
```bash
GET /v1/compliance/audit/hipaa
```
```json
{
  "framework": "hipaa",
  "score": 95.0,
  "total": 8,
  "compliant": 7,
  "partial": 1,
  "gaps": [{"control": "164.312(a)(2)(iv)", "title": "Encryption", "status": "partial"}]
}
```

### Compliance Controls Active
- PHI encryption at rest (AES-256-GCM per-tenant keys)
- Access audit trail (every PHI access logged to ImmutableCore)
- Minimum necessary (column projection, RLS policies)
- Integrity controls (append-only ledger, hash chain)
- Transmission security (TLS 1.3)
- 6-year retention policy enforced

---

## 3. Financial Services & Banking

### The Challenge
A fintech processes 50K transactions/day, requires PCI DSS compliance for card data, SOX audit trails, real-time fraud detection, and customer risk scoring. Currently using PostgreSQL, Redis, Kafka, and a homegrown ledger.

### CortexDB Solution

**Transaction processing with immutable audit:**
```bash
POST /v1/write
{
  "data_type": "payment",
  "payload": {
    "customer_id": "C-789",
    "amount": 1499.99,
    "currency": "USD",
    "payment_token": "tok_visa_4242"
  },
  "actor": "payment-service"
}
```
Sync write to RelationalCore + ImmutableCore (ACID). Async fan-out to TemporalCore (time-series) + StreamCore (real-time alerts) + MemoryCore (balance cache).

**PCI-DSS card data protection:**
- PAN fields encrypted with AES-256-GCM
- Payment tokens stored (never raw card numbers)
- ImmutableCore audit trail satisfies PCI Requirement 10
- Amygdala blocks SQL injection attempts

**Real-time fraud detection:**
```bash
# Stream consumer for real-time transaction analysis
SUBSCRIBE TO events:purchase_completed

# Anomaly detection query
POST /v1/query
{"cortexql": "SELECT customer_id, COUNT(*) as txn_count, SUM(amount) as total FROM customer_events WHERE event_type = 'purchase_completed' AND time > NOW() - INTERVAL '1 hour' GROUP BY customer_id HAVING COUNT(*) > 10 OR SUM(amount) > 5000"}
```

**Customer risk scoring:**
```bash
GET /v1/cortexgraph/customer/C-789/profile
# Returns: health_score, churn_probability, rfm_segment, monetary_90d
```

**Ledger integrity verification:**
```bash
POST /admin/ledger/verify
# {"chain_intact": true, "entries": 1284567}
```

### PCI Controls Active
- PCI-3.4: PAN rendered unreadable (field encryption + tokenization)
- PCI-3.5: Key management with 90-day rotation
- PCI-6.4: Amygdala SQL injection protection
- PCI-10.1: Complete audit trail in ImmutableCore
- PCI-10.5: Tamper-evident hash chain

---

## 4. SaaS & Multi-Tenant Platforms

### The Challenge
A B2B SaaS platform with 500 tenants needs complete data isolation, per-tenant rate limiting, plan-based feature gating, tenant data export (GDPR), and cost tracking per tenant.

### CortexDB Solution

**Tenant onboarding (one API call):**
```bash
POST /v1/admin/tenants
{
  "tenant_id": "acme-corp",
  "name": "Acme Corporation",
  "plan": "enterprise",
  "config": {"custom_domain": "data.acme.com"}
}
```
Creates tenant record, generates API key, provisions RLS policies, creates per-tenant encryption key.

**Complete data isolation:**
```
API Key → TenantMiddleware → SET app.current_tenant = 'acme-corp'
    │
    ├── PostgreSQL RLS: WHERE tenant_id = current_setting('app.current_tenant')
    ├── Redis keys: tenant:acme-corp:cache:*
    ├── Qdrant: collection tenant_acme-corp_vectors
    ├── Encryption: DEK tenant-acme-corp
    └── Streams: tenant:acme-corp:events:*
```

**Per-tenant resource monitoring:**
```bash
GET /v1/admin/tenants/acme-corp
```
```json
{
  "tenant_id": "acme-corp",
  "plan": "enterprise",
  "status": "active",
  "rate_limits": {
    "queries_per_minute": 6000,
    "writes_per_minute": 3000,
    "max_agents": 500
  }
}
```

**GDPR data export:**
```bash
POST /v1/admin/tenants/acme-corp/export
# Returns all tenant data in portable format
```

**GDPR data deletion (right to erasure):**
```bash
POST /v1/admin/tenants/acme-corp/purge
# Cryptographic erasure: delete DEK = all encrypted data unrecoverable
```

**Premium tenant isolation (dedicated shard):**
```bash
POST /v1/admin/sharding/isolate-tenant/acme-corp
# Moves acme-corp to dedicated Citus worker for guaranteed performance
```

---

## 5. AI Agent Platforms

### The Challenge
An AI agent orchestration platform (like MeninBlack) runs 38 AI agents that need to share state, discover each other's capabilities, track tasks, and access customer data — all through a unified interface.

### CortexDB Solution

**Agent registration via A2A protocol:**
```bash
POST /v1/a2a/register
{
  "agent_id": "T1-OPS-POS-001",
  "name": "POS Operations Agent",
  "skills": ["transaction_processing", "receipt_generation", "inventory_check"],
  "tools": ["cortexdb.query", "cortexdb.write", "cortexgraph.customer_360"],
  "protocol": "mcp",
  "model": "claude-sonnet-4-6"
}
```

**Skill-based agent discovery:**
```bash
GET /v1/a2a/discover?skill=customer_analytics
# Returns agents with matching skills, sorted by relevance
```

**Agent-to-Agent task delegation:**
```bash
POST /v1/a2a/task
{
  "source_agent_id": "PRIME",
  "target_agent_id": "T1-OPS-POS-001",
  "skill": "transaction_processing",
  "input_data": {"customer_id": "C-123", "items": [...]}
}
```

**MCP tool access for Claude/GPT agents:**
```bash
POST /v1/mcp/call
{
  "tool": "cortexgraph.customer_360",
  "input": {"customer_id": "C-123"}
}
# Agent gets complete customer intelligence in one tool call
```

**Agent performance tracking:**
```bash
POST /v1/query
{"cortexql": "SELECT agent_id, AVG(score) as avg_score, SUM(tokens_used) as total_tokens, COUNT(*) as tasks_completed FROM tasks WHERE completed_at > NOW() - INTERVAL '7 days' GROUP BY agent_id ORDER BY avg_score DESC"}
```

---

## 6. Government & Public Sector

### The Challenge
A federal agency needs FedRAMP Moderate authorization for a citizen services platform. Must meet NIST 800-53 controls, store audit trails for 3+ years, and support multi-agency data sharing with strict access controls.

### CortexDB Solution

**FedRAMP compliance audit:**
```bash
GET /v1/compliance/audit/fedramp
```
```json
{
  "framework": "fedramp",
  "score": 90.0,
  "total": 10,
  "compliant": 9,
  "controls": [
    {"id": "AC-2", "title": "Account Management", "status": "compliant"},
    {"id": "AC-3", "title": "Access Enforcement", "status": "compliant"},
    {"id": "AU-2", "title": "Audit Events", "status": "compliant"},
    {"id": "AU-9", "title": "Audit Protection", "status": "compliant"},
    {"id": "SC-28", "title": "Data at Rest Protection", "status": "compliant"}
  ]
}
```

**NIST 800-53 control mapping:**

| Control | Requirement | CortexDB Implementation |
|---------|------------|------------------------|
| AC-2 | Account Management | Tenant lifecycle: onboard/activate/suspend/purge |
| AC-3 | Access Enforcement | PostgreSQL RLS + Amygdala + Rate limiting |
| AU-2 | Auditable Events | ImmutableCore captures all writes |
| AU-9 | Audit Protection | Append-only ledger with UPDATE/DELETE triggers |
| IA-2 | Authentication | API key + SHA-256 hashing |
| SC-8 | Transmission Security | TLS 1.3 on all endpoints |
| SC-28 | Data at Rest | AES-256-GCM field encryption |
| SI-4 | System Monitoring | Amygdala + Prometheus + OpenTelemetry |

**Evidence generation for auditors:**
```bash
GET /v1/compliance/evidence/fedramp
# Returns 90-day audit evidence report with event counts, severity breakdown, sample events
```

**Multi-agency data sharing:**
Each agency is a tenant with isolated data. Cross-agency sharing via explicit API calls with audit trail.

---

## 7. Telecommunications

### The Challenge
A telco with 10M subscribers needs real-time CDR (Call Detail Records) analysis, subscriber profile management, network event streaming, churn prediction, and campaign effectiveness measurement.

### CortexDB Solution

**High-throughput event ingestion (CDRs):**
```bash
POST /v1/cortexgraph/track/batch
{
  "events": [
    {"customer_id": "SUB-001", "event_type": "call_completed", "properties": {"duration_sec": 342, "type": "international"}},
    {"customer_id": "SUB-001", "event_type": "data_usage", "properties": {"mb": 1240}},
    {"customer_id": "SUB-002", "event_type": "sms_sent", "properties": {"count": 5}}
  ]
}
```
100K+ events/second via StreamCore → TemporalCore pipeline.

**Subscriber churn prediction:**
```bash
GET /v1/cortexgraph/churn-risk?threshold=0.5&limit=1000
```
Identifies at-risk subscribers based on usage decline, support ticket frequency, and contract expiry.

**Network event time-series:**
```sql
SELECT time_bucket('5 minutes', time) AS bucket,
       AVG(latency_ms) AS avg_latency,
       MAX(error_rate) AS max_errors
FROM network_events
WHERE region = 'us-east'
AND time > NOW() - INTERVAL '24 hours'
GROUP BY bucket
ORDER BY bucket
```

**Campaign effectiveness:**
```bash
GET /v1/cortexgraph/attribution/CAMP-5G-UPGRADE
# Shows: 50K targeted → 8.2K converted → $410K incremental revenue
```

---

## 8. Gaming & Entertainment

### The Challenge
A multiplayer game with 5M players needs real-time leaderboards, player relationship graphs (friends, guilds, rivalries), in-game event streaming, player behavior analytics, and anti-cheat audit trails.

### CortexDB Solution

**Real-time leaderboard (MemoryCore):**
```bash
# Redis sorted set via MemoryCore
POST /v1/write
{"data_type": "heartbeat", "payload": {"player_id": "P-001", "score": 15420, "rank_update": true}}

# Query top 100
POST /v1/query
{"cortexql": "SELECT player_id, score FROM leaderboard ORDER BY score DESC LIMIT 100", "hint": "cache_first"}
```

**Player social graph:**
```bash
# Find friends-of-friends for matchmaking
TRAVERSE Player->FRIENDS_WITH->Player->FRIENDS_WITH->Player DEPTH 2
```

**In-game event streaming:**
```bash
# Real-time achievement tracking
POST /v1/cortexgraph/track
{"customer_id": "P-001", "event_type": "achievement_unlocked", "properties": {"achievement": "dragon_slayer", "level": 45}}
```

**Anti-cheat audit trail:**
Every game action logged to ImmutableCore. Hash chain prevents retroactive score manipulation.

---

## 9. Logistics & Supply Chain

### The Challenge
A logistics company tracks 100K shipments daily across 500 warehouses, 2000 trucks, and 50K delivery routes. Needs real-time tracking, route optimization data, supplier relationships, and regulatory compliance.

### CortexDB Solution

**Shipment tracking time-series:**
```bash
POST /v1/cortexgraph/track
{
  "customer_id": "SHIP-78901",
  "event_type": "location_update",
  "properties": {"lat": 40.7128, "lng": -74.0060, "speed_mph": 55, "eta_hours": 2.3}
}
```

**Supplier relationship graph:**
```sql
-- Which suppliers serve which warehouses? Find alternatives.
TRAVERSE Warehouse->SUPPLIED_BY->Vendor->SUPPLIES->Product DEPTH 2
```

**Route performance analytics:**
```sql
SELECT route_id,
       AVG(delivery_time_hours) AS avg_time,
       COUNT(*) AS deliveries,
       SUM(CASE WHEN on_time THEN 1 ELSE 0 END)::FLOAT / COUNT(*) AS on_time_rate
FROM delivery_events
WHERE time > NOW() - INTERVAL '30 days'
GROUP BY route_id
ORDER BY on_time_rate ASC
LIMIT 20
```

**Regulatory audit (food safety, hazmat):**
Complete chain of custody in ImmutableCore. Every handoff, temperature reading, and inspection logged with tamper-evident hash chain.

---

## 10. IoT & Industrial

### The Challenge
A manufacturing plant with 10K sensors generating 1M data points/minute needs real-time anomaly detection, predictive maintenance, equipment relationship mapping, and compliance reporting.

### CortexDB Solution

**High-frequency sensor ingestion (TemporalCore):**
```bash
POST /v1/write
{
  "data_type": "heartbeat",
  "payload": {
    "sensor_id": "TEMP-A1-003",
    "temperature_c": 78.4,
    "pressure_psi": 142.1,
    "vibration_hz": 3.2
  }
}
```
TimescaleDB hypertable with BRIN indexes = 100x smaller indexes than btree for time-series.

**Anomaly detection via time-series analysis:**
```sql
SELECT sensor_id, time,
       temperature_c,
       AVG(temperature_c) OVER (PARTITION BY sensor_id ORDER BY time ROWS BETWEEN 60 PRECEDING AND CURRENT ROW) AS moving_avg
FROM sensor_readings
WHERE time > NOW() - INTERVAL '1 hour'
AND ABS(temperature_c - moving_avg) > 3 * STDDEV(temperature_c) OVER (PARTITION BY sensor_id)
```

**Equipment relationship graph:**
```
Machine-A ──CONNECTED_TO──> Controller-1
Machine-A ──POWERED_BY───> Generator-3
Machine-A ──MAINTAINED_BY─> Tech-Sarah
Controller-1 ──FEEDS_INTO──> Assembly-Line-2
```

**Predictive maintenance with vector similarity:**
```bash
# Find equipment with similar degradation patterns
POST /v1/query
{"cortexql": "FIND SIMILAR TO 'vibration increase temperature drift' IN equipment_embeddings LIMIT 5"}
```
VectorCore finds equipment that exhibited similar sensor patterns before failure.

---

## Cross-Cutting Capabilities

### Every Use Case Gets These for Free

| Capability | Benefit |
|-----------|---------|
| **5-tier read cache** | 82% cache hit rate, sub-ms reads |
| **Multi-tenant isolation** | RLS + encryption + key prefix |
| **Rate limiting** | Plan-based, per-tenant, per-endpoint |
| **Amygdala security** | SQL injection blocked in < 1ms |
| **Immutable audit trail** | SHA-256 hash chain, 7-year retention |
| **Distributed tracing** | OpenTelemetry end-to-end |
| **Self-healing** | Grid repair, resurrection, Sleep Cycle |
| **AI agent integration** | 13 MCP tools, A2A protocol |
| **Horizontal scaling** | Citus sharding, add workers live |
| **Compliance** | FedRAMP + SOC2 + HIPAA + PCI auto-verified |

---

*CortexDB™ — One database to replace them all.*
*Copyright (c) 2026 Nirlab Inc.*
