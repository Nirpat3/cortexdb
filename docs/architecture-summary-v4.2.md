---
title: CortexDB Platform Architecture Summary — v4.2.0 (Phase 6 Complete)
version: 4.2.0
date: 2026-03-07
author: SuperAdmin / Claude Opus 4.6
status: COMPLETED
previous_version: 4.1.0
phase: 6 Complete — Intelligence Loops & Auto-Learning
---

# CortexDB Platform Architecture Summary — v4.2.0

## 1. What CortexDB Is

CortexDB is a consciousness-inspired unified database — a single platform combining 7 storage engines, AI agent management, self-healing infrastructure, and multi-tenant compliance. Every subsystem is modeled after a neurological structure.

**Replaces:** PostgreSQL + Redis + Pinecone + Neo4j + TimescaleDB + Kafka + Hyperledger
**With:** One system, one query language (CortexQL), one API, one dashboard

## 2. Core Architecture

### Query Flow
```
Request -> Amygdala (<1ms security scan) -> CortexQL Parser -> Thalamus Router
        -> Read Cascade (R0->R1->R2->R3->R4) or Write Fanout
        -> Engine(s) -> Synaptic Plasticity -> Response
```

### 7 Storage Engines
| Engine | Purpose | Tech |
|--------|---------|------|
| RelationalCore | SQL, ACID, joins | Citus/PostgreSQL 16 |
| MemoryCore | Hot data, sessions, cache | Redis 7 |
| VectorCore | Embeddings, similarity search | Qdrant (HNSW/IVF) |
| TemporalCore | Time-series, append-only | PostgreSQL + BRIN |
| StreamCore | Real-time events | Redis Streams |
| ImmutableCore | Append-only ledger, audit | Hash-chained files |
| GraphCore | Relationships, traversals | PostgreSQL + ltree |

### 5-Tier Read Cascade
- R0: Process-local LRU (microseconds)
- R1: Redis / MemoryCore (sub-ms)
- R2: Semantic cache via VectorCore (similarity at 0.95)
- R3: Persistent store (relational)
- R4: Deep retrieval fallback

## 3. Self-Healing

### Grid Repair Engine (5 Levels, 10-minute window)
| Level | Action | Timeout |
|-------|--------|---------|
| L1 | Soft restart (in-container) | 15s |
| L2 | Hard restart (delete pod, recreate) | 60s |
| L3 | Rebuild (fresh image, clear volumes) | 180s |
| L4 | Replace (new node, migrate traffic) | 300s |
| L5 | Decommission (alert human) | immediate |

### Additional Self-Healing
- Grid Coroner: Automated post-mortem on every dead node
- Resurrection Protocol: Risk-assessed re-integration
- GGC: 4 continuous cleanup tasks (zombies, orphans, stale routes, compaction)
- Health Scoring: Weighted score (PRISTINE/STABLE/FLAKY/CHRONIC/TERMINAL)
- Circuit Breakers: Per-dependency (PostgreSQL, Redis, Claude API, OpenAI, etc.)

## 4. Self-Enhancement

- **Synaptic Plasticity**: Frequently-used query paths get strengthened
- **Sleep Cycle (2 AM)**: 6-phase nightly maintenance
- **AI Index Manager**: Auto-detects slow queries, creates optimal indexes
- **AI Forecasting Agent**: Usage trends, anomaly detection, cost forecasting

## 5. Agent System (27 Unified Agents)

### Monitoring Agents (AGT-*) — 7 agents
### Development Team (CDB-*) — 20 agents across 6 departments

### Task Execution Engine
- Background worker with 3 concurrent slots
- Task chaining/pipelines — sequential multi-step execution with context passing
- Task approval workflow — submit -> approve/reject -> execute lifecycle
- Auto-delegation — intelligent agent scoring based on skills, workload, success rate
- **NEW: Learned delegation** — hybrid scoring using quality data from outcome analyzer

### Agent Communication Bus
- 6 message types: direct, delegation, escalation, broadcast, status, result

### LLM Router
- Providers: Ollama (local), Claude API, OpenAI API
- Failover chain — automatic fallback between providers
- Retry logic — 2 retries with exponential backoff
- Circuit breaker — per-provider, opens after 3 failures (60s cooldown)
- SSE streaming — real-time token streaming for all 3 providers
- **NEW: Model tracker integration** — feeds performance data per request

### Agent Memory System
- Short-term memory: sliding window of recent conversation turns (20 max)
- Long-term memory: key facts and learnings (100 max per agent)
- Task history: compressed summaries of completed tasks
- Context window assembly: auto-injected into LLM prompts
- Multi-turn conversations: instruction endpoint uses full conversation history

## 6. Intelligence Loops & Auto-Learning (Phase 6 — NEW)

### Closed-Loop Learning Architecture
```
Task Executed --> Outcome Analyzer grades 1-10 --> Extract learnings + patterns
     |                    |                              |
     |                    v                              v
     |              Agent Memory stores facts    Model Tracker logs grade
     |                    |                              |
     |                    v                              v
     |              Better context next time    Prompt Evolution tracks effectiveness
     |                    |                              |
     v                    v                              v
Adaptive Delegation uses learned scores <--- Sleep Cycle consolidates & evolves
```

### Outcome Analyzer (`outcome_analyzer.py`)
- After every task: LLM grades result 1-10 using structured prompt
- Extracts: grade, quality (poor/fair/good/excellent), learnings, prompt insight, reusable pattern
- Auto-stores learnings in agent long-term memory by category
- Tracks per-agent and per-category quality scores
- Feeds prompt performance data to prompt evolution tracker

### Model Performance Tracker (`model_tracker.py`)
- Tracks per-(provider, model, category) metrics: success rate, latency, grade
- Composite scoring: quality (50%) + reliability (35%) + speed (15%)
- Auto-generates per-category best model recommendations
- Task executor checks recommendations before each execution (threshold: score > 0.6)

### Prompt Evolution (`prompt_evolution.py`)
- Records prompt hash + grade per (agent, category)
- Identifies weak categories below grade threshold
- LLM-powered prompt generation: analyzes failures and generates improved prompts
- Apply evolution: hot-swap agent system prompts
- Evolution history tracking

### Adaptive Delegation
- Hybrid scoring: static rules (department match, skills, workload) + learned quality (0-30 points)
- Quality data sourced from outcome analyzer's per-agent/per-category scores
- Automatically improves delegation accuracy as more tasks are executed

### Agent Sleep Cycle (`agent_sleep_cycle.py`)
- Runs every 6 hours (background scheduler), manual trigger available
- **Phase 1 — Consolidate**: Extracts durable learnings from short-term conversation memory
- **Phase 2 — Decay**: Removes facts older than 30 days (preserves patterns/consolidated/prompt_insights)
- **Phase 3 — Strengthen**: Reinforces patterns that correlate with high-grade outcomes (avg >= 8)
- **Phase 4 — Precompute**: Refreshes model recommendations
- **Phase 5 — Auto-Evolve**: Rewrites prompts for agents scoring below 5.0
- Stores cycle history (last 50 cycles)

### Intelligence Dashboard (`/superadmin/intelligence`)
- **Overview tab**: KPIs, grade distribution, quality breakdown, category scores, recent analyses
- **Model Performance tab**: Full performance table, learned recommendations per category
- **Prompt Evolution tab**: Per-agent prompt performance with trends, evolution history
- **Sleep Cycle tab**: Status, manual trigger, last result breakdown, cycle history

## 7. Persistence & Security

- SQLite with WAL mode (replaced JSON files)
- Schema migration system — versioned incremental migrations with rollback
- Secrets vault — AES-256-GCM encryption for API keys at rest (PBKDF2, 600K iterations)
- Amygdala: <1ms SQL injection detection
- ASA: 21 architecture standards
- Compliance: SOC2, HIPAA, PCI-DSS, FedRAMP
- Multi-tenant: RLS isolation, tenant-scoped caching
- SuperAdmin: SHA-256 passphrase, 48-byte session tokens, IP lockout

## 8. Self-Versioning & CI/CD

- Single source of truth: `__version__` in `__init__.py`
- Semver bumping (major/minor/patch) via API
- Auto-sync to pyproject.toml, server.py, database.py, service_monitor.py
- CHANGELOG.md auto-generated
- CI: lint, test, build, docker, version check
- Release: tag-triggered, GitHub Release + Docker push

## 9. Real-Time Communication

- WebSocket: `ws://host:5400/ws/events` — task lifecycle events
- SSE Streaming: token-by-token from all LLM providers

## 10. Platform Totals (v4.2.0)

| Metric | Count |
|--------|-------|
| Python modules | ~45 |
| API endpoints | ~130 (115 + 15 new learning endpoints) |
| Dashboard pages | 40 |
| Storage engines | 7 |
| AI agents (CDB team) | 20 |
| Monitoring agents | 7 |
| Departments | 6 |
| Version | 4.2.0 |

## 11. Phase 6 Completion Summary

### Sprint 1: Closed-Loop Learning (4/4 COMPLETED)
| # | Task | Status |
|---|------|--------|
| 1 | Outcome analyzer | COMPLETED |
| 2 | Model performance tracker | COMPLETED |
| 3 | Prompt evolution | COMPLETED |
| 4 | Adaptive delegation | COMPLETED |

### Sprint 2: Deep Integration (2/2 COMPLETED)
| # | Task | Status |
|---|------|--------|
| 5 | Agent sleep cycle | COMPLETED |
| 6 | Intelligence dashboard | COMPLETED |

### New Files (Phase 6)
- `src/cortexdb/superadmin/outcome_analyzer.py` — Core learning feedback loop (284 lines)
- `src/cortexdb/superadmin/model_tracker.py` — Per-model performance tracking (~150 lines)
- `src/cortexdb/superadmin/prompt_evolution.py` — Prompt tracking and auto-evolution (~200 lines)
- `src/cortexdb/superadmin/agent_sleep_cycle.py` — 5-phase nightly maintenance (259 lines)
- `dashboard/src/app/superadmin/intelligence/page.tsx` — Intelligence dashboard (~350 lines)
- `docs/task-list-phase6.md` — Phase 6 task tracking

### Modified Files (Phase 6)
- `src/cortexdb/server.py` — Phase 6 globals, lifespan init, sleep scheduler, 17 new endpoints
- `src/cortexdb/superadmin/task_executor.py` — Memory injection, model recommendations, outcome analysis
- `src/cortexdb/superadmin/llm_router.py` — Model tracker integration
- `dashboard/src/lib/api.ts` — 18 new API methods for learning endpoints
- `dashboard/src/app/superadmin/layout.tsx` — Added Intelligence nav item
- `src/cortexdb/__init__.py` — Version bumped to 4.2.0

### New API Endpoints (Phase 6): 15 total
- Prompt Evolution: 5 endpoints
- Model Tracker: 3 endpoints
- Outcome Analyzer: 5 endpoints
- Sleep Cycle: 2 endpoints

## 12. Remaining Gaps

- SuperAdmin data not yet connected to the 7 core engines (still SQLite-only)
- No proper ORM layer (raw SQL)
- No automated test suite (pytest configured but minimal tests)
- Dashboard WebSocket client not yet implemented (server-side ready)
- LLM cost tracking is estimated, not token-precise
- No A/B testing framework for prompt evolution (applies based on threshold only)
