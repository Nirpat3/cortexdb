---
title: CortexDB Platform Architecture Summary
version: 4.1.0
date: 2026-03-07
author: SuperAdmin / Claude Opus 4.6
status: ACTIVE
previous_version: 4.0.0
---

# CortexDB Platform Architecture Summary

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

### Grid Coroner — Every dead node gets an automated post-mortem stored in Experience Ledger
### Resurrection Protocol — Risk-assessed re-integration of dead nodes
### GGC — 4 continuous cleanup tasks (zombies, orphans, stale routes, compaction)
### Health Scoring — Weighted score determines traffic allocation (TERMINAL = 0% traffic)
### Circuit Breakers — Per-dependency (PostgreSQL, Redis, Claude API, OpenAI, etc.)

## 4. Self-Enhancement

### Synaptic Plasticity — Frequently-used query paths get strengthened (like neural pathways)
### Sleep Cycle (2 AM) — 6-phase nightly maintenance: Prune, Consolidate, Rebuild, Pre-compute, Decay, Analyze
### AI Index Manager — Auto-detects slow queries, creates optimal indexes, garbage-collects unused
### AI Forecasting Agent — Usage trends, anomaly detection, cost forecasting, breach prediction

## 5. Agent System (27 Unified Agents)

### Monitoring Agents (AGT-*) — 7 agents
- System metrics, DB monitoring, service monitoring, security, error tracking, notifications, forecasting

### Development Team (CDB-*) — 20 agents across 6 departments
- EXEC (1): Atlas (Chief Product Officer)
- ENG (6): Forge, Blueprint, Kernel, Pixel, Schema, Bridge
- QA (5): Guardian, Prober, Pathfinder, Benchmark, Sentinel
- OPS (4): Conductor, Launcher, Watchdog, Terraform
- SEC (3): Aegis, Inspector, Vault
- DOC (4): Scribe, Swagger, Guide, Cartographer

### Task Execution Engine — Background worker (3 concurrent) routes tasks to agent's LLM
### Agent Communication Bus — Direct, delegation, escalation, broadcast messaging
### LLM Router — Ollama (local), Claude API, OpenAI API with per-agent configuration
### Persistence — JSON file-backed storage with auto-save (30s)

## 6. Security & Compliance

- Amygdala: <1ms SQL injection / blocked operation detection on every query
- ASA: 21 architecture standards (HARD/SOFT/ADVISORY enforcement)
- Field Encryption: AES-256-GCM with key versioning and 90-day rotation
- Compliance: SOC2, HIPAA (PHI tracking), PCI-DSS (cardholder data), FedRAMP
- Multi-tenant: RLS isolation, tenant-scoped caching, plan-based gating
- SuperAdmin: SHA-256 passphrase, 48-byte session tokens, IP lockout

## 7. Protocols

- MCP: CortexDB as a tool for AI agents (8 MCP tools)
- A2A: Agent-to-agent task lifecycle (Created->Assigned->Running->Completed)
- Heartbeat: /health/live, /health/ready, /health/deep, /health/metrics
- Prometheus: Counters, gauges, histograms at /health/metrics

## 8. Infrastructure

- Docker Compose: 11 services (router, relational, 2 Citus workers, 2 Redis, Qdrant, OTEL, Prometheus, Loki, Grafana)
- Dashboard: Next.js 15 + React 19 + Tailwind v4 (38 pages)
- API: FastAPI on port 5400 (95+ endpoints)

## 9. Gap Analysis (as of v4.1)

### MISSING: Versioning
- No automatic version bumping on releases
- No data schema migration tracking system
- No changelog generation
- No modification versioning (no audit trail on data changes beyond ImmutableCore)
- Static `__version__ = "4.0.0"` hardcoded in 4 files

### MISSING: CI/CD
- No `.github/workflows/` directory
- No automated test pipeline
- No build/deploy automation
- No pre-commit hooks
- Dockerfile and docker-compose exist but no orchestration

### MISSING: Proper Data Storage for SuperAdmin
- Agent data: JSON files (should be SQLite/PostgreSQL)
- Tasks: JSON files (no indexing, no concurrent write safety)
- Instructions: JSON files (no search, no pagination efficiency)
- Sessions: In-memory only (lost on restart)
- Encryption keys: In-memory only (lost on restart)
- LLM provider config: In-memory only

### PARTIAL: Memory/Storage
- 7-engine architecture is well-designed but not used by SuperAdmin
- No connection between superadmin persistence and the database engines
- No proper ORM or migration system

## 10. File Inventory

### Backend (82 Python files)
- `core/`: database.py, parser.py, bridge.py, cache_invalidation.py, embedding.py, sleep_cycle.py, precompute.py
- `engines/`: relational.py, memory.py, vector.py, temporal.py, stream.py, immutable.py, graph.py
- `grid/`: state_machine.py, repair_engine.py, garbage_collector.py, health_score.py, coroner.py, resurrection.py
- `heartbeat/`: protocol.py, health_checks.py, circuit_breaker.py
- `superadmin/`: auth.py, agent_team.py, ollama_client.py, llm_router.py, persistence.py, task_executor.py, agent_bus.py
- `agents/`: registry.py, system_metrics.py, db_monitor.py, service_monitor.py, security_agent.py, error_tracker.py, notification_agent.py
- `compliance/`: framework.py, encryption.py, audit.py
- `scale/`: sharding.py, replication.py, ai_index.py, rendering.py
- `a2a/`: registry.py, protocol.py
- `mcp/`: server.py
- `cortexgraph/`: identity.py, events.py, relationships.py, profiles.py, insights.py
- `observability/`: metrics.py, tracing.py
- `tenant/`: manager.py, isolation.py, middleware.py
- `budget/`: tracker.py, forecaster.py
- `rate_limit/`: limiter.py, middleware.py
- `asa/`: standards.py
- `benchmark/`: runner.py, stress.py, scenarios.py

### Dashboard (38 pages)
- Main: overview, monitoring, hardware, db-monitor, services, security, errors, notifications, agents
- Database: engines, query, cortexgraph, compliance, grid, heartbeat, scale, benchmark
- Infrastructure: mcp, tenants, budgeting, settings, install, support, api-docs
- SuperAdmin: dashboard, org-chart, agents, tasks, instructions, bus, executor, audit, registry, llm
