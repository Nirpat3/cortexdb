# Ops Learning Loop v1

> Self-tuning intelligence layer for CortexDB operational parameters.

## Overview

The Ops Learning Loop is a closed-loop system that observes CortexDB runtime behaviour
(latency, error rates, cache hit ratios, queue depth), proposes configuration patches,
validates them against safe ranges, and can automatically roll back to a last-known-good
snapshot when anomalies are detected.

```
 ┌──────────┐   signals   ┌────────────┐  propose   ┌──────────────┐
 │  Emitters├────────────►│ Meta-Agent  ├───────────►│ Config Store │
 │ (metrics,│             │ (scheduled) │            │ (Redis Hash +│
 │  traces) │             └──────┬──────┘            │  PG snapshot)│
 └──────────┘                    │ validate           └──────┬───────┘
                                 ▼                           │
                          ┌──────────────┐   revert     ┌────▼───┐
                          │  Safe Ranges │◄─────────────│ Healer │
                          └──────────────┘              └────────┘
```

## Components

### 1. Signals (`cortexdb/core/ops_learning/signals.py`)

Thin wrapper around `StreamEngine` (Redis Streams) for emitting operational signals.

**Signal types:**
| Signal | Payload | Source |
|--------|---------|--------|
| `ops.latency` | `{p50, p95, p99, endpoint}` | Request middleware |
| `ops.error_rate` | `{rate, window_sec, category}` | Error handler |
| `ops.cache_hit` | `{tier, ratio, window_sec}` | Cache layer |
| `ops.queue_depth` | `{queue, depth, max}` | Task executor |
| `ops.config_change` | `{key, old, new, actor}` | Config store |

All signals land on the Redis Stream `cortex:ops_signals`.

### 2. Config Store (`cortexdb/core/ops_learning/config_store.py`)

Live configuration backed by **Redis Hash** (`system:config`) for fast reads,
with point-in-time snapshots persisted to **PostgreSQL** (`config_snapshots` table).

**Capabilities:**
- `get(key)` / `set(key, value)` — read/write individual keys.
- `snapshot()` — freeze current config to Postgres with a monotonic version.
- `rollback(version)` — restore a previous snapshot to Redis.
- Every `set()` emits an `ops.config_change` signal.

**Safe ranges:** Each config key may declare a `(min, max)` numeric bound or an
enum of allowed values.  `set()` rejects values outside the declared range.

### 3. Meta-Agent (`cortexdb/core/ops_learning/meta_agent.py`)

A scheduled job (cron / `asyncio` loop — *not* Temporal in v1) that:

1. Reads recent signals from `cortex:ops_signals`.
2. Aggregates metrics (windowed averages).
3. Proposes a config patch (dictionary of key→new_value).
4. Validates every proposed value against safe ranges.
5. Applies the patch via Config Store (which auto-snapshots before patching).
6. Logs the decision to the immutable audit chain (if available).

In v1 the proposal logic is a simple rule table (if p95 > X → adjust Y).
Future versions may plug in ML models.

### 4. Healer (`cortexdb/core/ops_learning/healer.py`)

Rule-based anomaly detector that can **revert to the last known good** config
when things go wrong.

**Detectors (v1 stubs):**
| Detector | Trigger | Action |
|----------|---------|--------|
| `LatencySpike` | p99 > 2× baseline for 3 consecutive windows | Rollback config |
| `ErrorFlood` | error_rate > threshold for sustained period | Rollback config |
| `CacheCollapse` | cache hit ratio drops below floor | Rollback cache-related keys |

The Healer maintains a pointer to the "last known good" snapshot version and
always rolls back to that rather than blindly reverting one step.

## Database Migration

A new table is required in PostgreSQL:

```sql
CREATE TABLE IF NOT EXISTS config_snapshots (
    id          BIGSERIAL PRIMARY KEY,
    version     INTEGER NOT NULL UNIQUE,
    config_data JSONB   NOT NULL,
    created_by  TEXT    NOT NULL DEFAULT 'system',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    note        TEXT
);
CREATE INDEX idx_config_snapshots_version ON config_snapshots (version DESC);
```

The migration is applied lazily on first `ConfigStore.connect()` call (safe for
existing deployments).

## MCP Tools / REST Endpoints

| Tool / Endpoint | Method | Description |
|----------------|--------|-------------|
| `ops.get_config` / `GET /ops/config/{key}` | read | Get a config value |
| `ops.set_config` / `PUT /ops/config/{key}` | write | Set a config value (validates safe range) |
| `ops.config_snapshot` / `POST /ops/config/snapshot` | write | Take a named snapshot |
| `ops.emit_signal` / `POST /ops/signals` | write | Emit an operational signal |

## Configuration Defaults

All keys ship with conservative defaults.  The Meta-Agent **never** proposes a
value outside the declared safe range — the worst case is a sub-optimal but
*safe* configuration.

```python
DEFAULT_CONFIG = {
    "cache.ttl_seconds":       {"value": 300,   "min": 60,   "max": 3600},
    "cache.semantic_threshold": {"value": 0.82,  "min": 0.5,  "max": 0.99},
    "query.timeout_ms":        {"value": 5000,  "min": 500,  "max": 30000},
    "query.max_concurrent":    {"value": 50,    "min": 5,    "max": 500},
    "stream.batch_size":       {"value": 100,   "min": 10,   "max": 1000},
}
```

## Safety Guarantees

1. **No silent drift** — every config change emits a signal and is snapshotted.
2. **Bounded exploration** — safe ranges are hard limits, not suggestions.
3. **Instant rollback** — Healer can revert in a single Redis HSET + signal.
4. **Audit trail** — all patches logged with before/after and actor.
5. **Opt-in** — the Meta-Agent loop is disabled by default (`OPS_LEARNING_ENABLED=false`).
