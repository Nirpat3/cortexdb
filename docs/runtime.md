# CortexEngine Runtime Layer

> **Version:** 1.0.0-alpha  
> **Status:** Stubbed endpoints with real schemas and tenant enforcement  
> **Aligned with:** RapidRMS Complete Technical Design v3

## Overview

The **Runtime** is CortexEngine's unified API layer for orchestrating workflows
and long-running processes across proven infrastructure components. It is NOT a
database kernel — it's the orchestration surface that wires together:

| Namespace | Engine | Purpose |
|-----------|--------|---------|
| `context` | RelationalEngine (PostgreSQL) | Structured data, tenant config |
| `vector` | VectorEngine (Qdrant) | Semantic search, embeddings |
| `events` | StreamEngine (Redis Streams) | Real-time event bus |
| `config` | RelationalEngine | Tenant/merchant configuration |
| `traces` | Observability (OTEL) | Distributed tracing |
| `workflows` | **Runtime** | Workflow lifecycle management |
| `runtime` | **Runtime** | Convenience aliases for workflows |

## Architecture

```
┌─────────────────────────────────────────────┐
│              API Gateway / Auth              │
│         (TenantMiddleware → RLS)             │
├─────────────┬───────────────┬───────────────┤
│ /workflows  │   /runtime    │  /v1/query    │
│   start     │   run         │  (existing)   │
│   signal    │   cancel      │               │
│   {id}      │   {id}        │               │
├─────────────┴───────────────┴───────────────┤
│              RuntimeStore                     │
│   Postgres: runtime_runs table               │
│   + write_outbox (transactional outbox)      │
├──────────────────────────────────────────────┤
│        StreamCore (event emission)            │
│        Redis Streams: cortex:runtime.*       │
└──────────────────────────────────────────────┘
```

## REST Endpoints

### Workflows

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/workflows/start` | Start a new workflow run |
| `POST` | `/workflows/signal` | Send signal to running workflow |
| `GET` | `/workflows/{workflow_id}` | Get workflow status |

### Runtime (convenience aliases)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/runtime/run` | Start a run (alias of workflow start) |
| `GET` | `/runtime/{run_id}` | Get run status |
| `POST` | `/runtime/cancel` | Cancel a running run |

## Request / Response Contracts

### Tenancy Envelope

Every mutating request carries tenant context:

```json
{
  "tenant_id": "t-abc123",          // required, from auth
  "merchant_id": "m-xyz789"         // optional, scopes within tenant
}
```

The middleware-resolved tenant (from `Authorization: Bearer ctx_live_...`) is
cross-checked against the body `tenant_id`. Mismatches return **403**.

### POST /workflows/start

**Request:**
```json
{
  "tenant_id": "t-abc123",
  "merchant_id": "m-xyz789",
  "workflow_type": "order_pipeline",
  "input": { "order_id": 42 },
  "idempotency_key": "ord-42-v1",
  "tags": { "env": "production" }
}
```

**Response (201):**
```json
{
  "workflow_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending",
  "created_at": "2024-01-15T10:30:00Z"
}
```

### POST /workflows/signal

**Request:**
```json
{
  "tenant_id": "t-abc123",
  "workflow_id": "550e8400-...",
  "signal_name": "approve",
  "payload": { "approved_by": "user-123" }
}
```

**Response:**
```json
{
  "workflow_id": "550e8400-...",
  "signal_name": "approve",
  "accepted": true
}
```

### GET /workflows/{workflow_id}

**Response:**
```json
{
  "workflow_id": "550e8400-...",
  "tenant_id": "t-abc123",
  "merchant_id": "m-xyz789",
  "workflow_type": "order_pipeline",
  "status": "running",
  "input": { "order_id": 42 },
  "output": null,
  "error": null,
  "tags": { "env": "production" },
  "created_at": "2024-01-15T10:30:00Z",
  "updated_at": "2024-01-15T10:30:05Z"
}
```

### POST /runtime/cancel

**Request:**
```json
{
  "tenant_id": "t-abc123",
  "run_id": "550e8400-...",
  "reason": "User requested cancellation"
}
```

**Response:**
```json
{
  "run_id": "550e8400-...",
  "status": "cancelled",
  "cancelled": true
}
```

## Engine Mapping

The runtime layer delegates to existing engines:

| Action | Engine | Detail |
|--------|--------|--------|
| Create run | RelationalEngine | INSERT into `runtime_runs` |
| Emit event | StreamEngine | Outbox → `cortex:runtime.run.created` |
| Signal delivery | StreamEngine | Outbox → `cortex:runtime.run.signal` |
| Status query | RelationalEngine | SELECT from `runtime_runs` |
| Cancel | RelationalEngine | UPDATE status + outbox event |

## Storage

### Postgres Table: `runtime_runs`

```sql
CREATE TABLE runtime_runs (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    merchant_id TEXT,
    workflow_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    spec JSONB NOT NULL DEFAULT '{}'::jsonb,
    output JSONB,
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

Row-Level Security enforces tenant isolation:
```sql
CREATE POLICY runtime_runs_tenant_isolation ON runtime_runs
    USING (tenant_id = current_setting('app.current_tenant', TRUE));
```

### Status Lifecycle

```
pending → running → completed
                  → failed
       → cancelled (from pending or running)
```

## TypeScript SDK

```typescript
import { CortexDBClient } from "@cortexdb/client";

const client = new CortexDBClient("http://localhost:5400", { apiKey: "ctx_live_..." });

// Start a workflow
const { workflow_id } = await client.workflowStart({
  tenant_id: "t-abc123",
  workflow_type: "order_pipeline",
  input: { order_id: 42 },
});

// Check status
const status = await client.workflowStatus(workflow_id);

// Send signal
await client.workflowSignal({
  tenant_id: "t-abc123",
  workflow_id,
  signal_name: "approve",
});

// Cancel
await client.runtimeCancel({
  tenant_id: "t-abc123",
  run_id: workflow_id,
  reason: "No longer needed",
});
```

## Module Structure

```
cortexdb/core/runtime/
├── __init__.py      # Public API exports
├── schemas.py       # Pydantic request/response models
├── store.py         # Postgres data access (RuntimeStore)
└── router.py        # FastAPI endpoints + tenant enforcement
```

## Future Work

- [ ] Actual workflow step execution engine (Temporal/custom)
- [ ] Webhook callbacks on status transitions
- [ ] Batch operations (start multiple workflows)
- [ ] Workflow versioning and blue/green deployments
- [ ] Metrics integration (run duration, success rate)
