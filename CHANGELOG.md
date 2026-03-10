# CortexDB Changelog

## [6.1.0] - 2026-03-10

**PhD Expert Panel Evaluation + P0/P1/P2 Enhancements**

Type: Major
Previous: 6.0.0

### Security (P0)
- Fixed RLS: SET LOCAL in transactions prevents cross-tenant data leaks on pooled connections
- Fixed admin auth bypass: deny all requests when CORTEX_ADMIN_TOKEN unset; use hmac.compare_digest
- Replaced file-based immutable engine with PostgreSQL-backed ledger (ACID, crash-safe)
- Tenants loaded from PostgreSQL on startup (write-through cache, survives restart)
- Unified dual embedding codepaths (deleted incompatible hash fallback from vector.py)
- Request coalescing in read cascade prevents cache stampede on concurrent identical queries

### Production Readiness (P1)
- Embedding sync pipeline: PG NOTIFY triggers → batch re-embed → Qdrant upsert (eliminates stale vectors)
- Transactional outbox pattern: PG-backed outbox replaces in-memory DLQ (survives crashes)
- Externalized A2A tasks + agent registry + read-your-writes tracking to Redis/PG (multi-instance safe)
- Adaptive semantic cache: per-collection thresholds, auto-detect query type (SQL/NL/RAG/agent)
- Field encryption (AES-256-GCM) + audit logging wired into actual read/write data paths

### Enterprise Features (P2)
- Agent memory protocol: store/recall/forget/share with Ebbinghaus temporal decay
- Memory types: episodic, semantic, working (Redis-cached)
- 4 new MCP tools: memory.store, memory.recall, memory.forget, memory.share
- GDPR-compliant deletion across all engines (PG + Qdrant + Redis)

### Documentation
- PhD Expert Panel evaluation (distributed systems, AI/ML, security specialists)
- 20-item enhancement roadmap with expert attribution
- Updated all documentation to reflect honest positioning

### New Files
- cortexdb/core/outbox_worker.py, outbox_schema.sql
- cortexdb/core/cache_config.py
- cortexdb/core/embedding_sync.py, embedding_sync_triggers.sql
- cortexdb/core/agent_memory.py, agent_memory_schema.sql
- cortexdb/a2a/a2a_tasks_schema.sql
- docs/PHD-EVALUATION.md

---

## [6.0.0] - 2026-03-08

**Phase 12: Marketplace Ecosystem — 18 New Capabilities, SDKs, Full Platform**

Type: Major
Previous: 5.0.0

### Changes

**Marketplace Core**
- **Marketplace Engine**: Capability toggle system — 33 capabilities across 6 categories (core, sdk, integration, security, analytics, infrastructure) with dependency resolution, tier-based access (free/pro/enterprise), SQLite persistence, auto-migration for new capabilities
- **Marketplace Dashboard**: Full UI with category filters, search, toggle switches, dependency visualization, stats, i18n (all 10 languages)
- **Marketplace API**: 10 endpoints — list, get, enable, disable, configure, search, stats, dependency check, dependents
- **Plugin System**: Custom engine/hook/middleware extension framework — register/unregister/enable/disable via manifest, 7 API endpoints

**SDK Packages (4 languages)**
- **Python SDK** (`sdk/python/`): `cortexdb-client` — CortexDBClient + SuperAdminClient, httpx-based, context manager
- **Node.js SDK** (`sdk/nodejs/`): `@cortexdb/client` — TypeScript, native fetch, zero deps, full type definitions
- **Go SDK** (`sdk/go/`): `cortexdb-client-go` — net/http, functional options, no external deps
- **Rust SDK** (`sdk/rust/`): `cortexdb-client` — reqwest + serde + thiserror, async/await

**AI & Intelligence**
- **AI Copilot**: In-dashboard conversational AI assistant — session management, CortexQL generation, agent explanation, optimization suggestions, 9 API endpoints
- **Agent Template Marketplace**: 12 pre-built community templates (Data Analyst, Customer Support, Security Auditor, Content Writer, DevOps Engineer, Research Assistant, Sales Intelligence, QA Test, Financial Analyst, HR Recruiter, Legal Compliance, Marketing Strategist) — install, rate, publish, 8 API endpoints
- **GraphQL Gateway**: Auto-generated GraphQL schema from CortexDB data model — query execution, schema introspection, query logging, 6 API endpoints
- **Voice Interface**: Natural voice command processing — intent detection, entity extraction, 15 supported command types, session management, 7 API endpoints

**Integrations**
- **Microsoft Teams**: Agent alerts, task approvals, adaptive cards, channel mapping, 5 API endpoints
- **Discord**: Bot integration, slash commands, rich embeds, channel mapping, 5 API endpoints
- **Zapier/n8n Connector**: Webhook endpoints, event-driven triggers, HMAC signature verification, delivery tracking, retry logic, n8n workflow generation, 8 API endpoints

**Security**
- **Zero-Trust Network Policies**: Policy-based access control (allow/deny/require_auth), 6 seeded policies, certificate management, audit logging, request evaluation, 10 API endpoints
- **Integrated Secrets Vault**: Versioned secrets with base64 encoding, lease tracking, rotation scheduling, seal/unseal, access logging, 8 API endpoints

**Analytics**
- **Visual Data Pipeline Builder**: ETL/ELT pipeline designer with 8 stage types (extract_sql, extract_api, extract_file, transform_map, transform_filter, transform_aggregate, load_table, load_api), sequential execution, run tracking, 9 API endpoints
- **Real-Time Custom Dashboards**: Dashboard builder with 10 widget types (counter, line_chart, bar_chart, pie_chart, gauge, table, list, heatmap, text, status_grid), 3 default dashboards, sharing, duplication, 11 API endpoints

**Infrastructure**
- **Edge Deployment**: Edge node registration, heartbeat monitoring, bidirectional data sync, sync policy config, offline queue, primary promotion, 7 API endpoints
- **Kubernetes Operator**: Cluster management, scaling, rolling upgrades, backup CRDs, K8s manifest generation (Deployment, Service, PVC, CRD, RBAC, HPA), 8 API endpoints
- **White-Label & Theming**: 4 built-in themes (Default Dark, Light Mode, Midnight Blue, Forest), color customization, branding (company, logo, domain, CSS), email templates, 9 API endpoints
- **Multi-Region Replication**: 3 default regions (US East, EU West, Asia Pacific), replication streams, conflict resolution (source_wins/target_wins/manual), automatic failover, geo-routing, 12 API endpoints

**Dashboard**
- 14 new superadmin pages: Copilot, Template Market, GraphQL, Integrations, Voice, Vault, Zero-Trust, Data Pipelines, Custom Dashboards, Edge, Kubernetes, Theming, Multi-Region, SDKs
- 15 new sidebar navigation items (46 total nav items)
- i18n: All 10 languages updated with new nav keys
- 50 total superadmin page routes

**API Summary**
- ~140 new API endpoints added in this release
- Total superadmin API surface: ~500+ endpoints

### New Files
- `src/cortexdb/superadmin/marketplace.py` — MarketplaceManager with SQLite persistence
- `src/cortexdb/superadmin/plugin_system.py` — PluginManager for custom extensions
- `dashboard/src/app/superadmin/marketplace/page.tsx` — Marketplace UI
- `sdk/python/cortexdb_client/__init__.py` — Python SDK client
- `sdk/python/setup.py` — Python package config
- `sdk/python/README.md` — Python SDK docs
- `sdk/nodejs/src/index.ts` — TypeScript SDK client
- `sdk/nodejs/package.json` — Node.js package config
- `sdk/nodejs/tsconfig.json` — TypeScript config

### Modified Files
- `src/cortexdb/server.py` — Added marketplace + plugin initialization, 17 new API routes
- `dashboard/src/lib/api.ts` — Added 17 new API client methods (marketplace + plugins)
- `dashboard/src/app/superadmin/layout.tsx` — Added Marketplace nav item
- `dashboard/src/lib/i18n/types.ts` — Added marketplace types
- `dashboard/src/lib/i18n/translations/*.ts` — Added marketplace keys to all 10 languages

---

## [5.0.0] - 2026-03-08

**Phase 11: Production Readiness — i18n, Security, Testing, Observability**

Type: Major
Previous: 4.1.0

### Changes
- **i18n**: Full internationalization system with 10 languages (EN, ZH, HI, ES, FR, AR, BN, PT, RU, JA), all 36 superadmin pages decoupled from hardcoded strings, RTL support, lazy-loaded translations, language switcher
- **Error Boundaries**: Root, global, 404, superadmin-scoped error boundaries and loading states
- **Testing**: Integration test suite (65+ tests via pytest), Playwright E2E tests, unified test runner script
- **HTTPS/TLS**: Nginx reverse proxy with TLS 1.2+, security headers, rate limiting, WebSocket support, production docker-compose override
- **Secrets Management**: Automated rotation script for all credentials, .env.previous backups
- **Database Backups**: Automated backup/restore scripts for PostgreSQL, Redis, SQLite, Qdrant with rotation and cron integration
- **Production Runbooks**: Operations runbook, 10 incident response playbooks (P1-P4), security hardening guide
- **Observability**: Structured JSON logging, Grafana dashboards (provisioned), Prometheus alerting rules (15 alerts), connection pooling
- **API Hardening**: Global exception handlers (HTTP, validation, unhandled), standardized error responses, request ID tracking, API version headers, health endpoint auth in production
- **OpenAPI**: Customized API docs with contact/license/terms, disabled in production
- **Platform Integration**: REST API examples in 6 languages, framework guides, mobile integration, migration paths
- **Installation**: One-command install script with prereq checks and auto-configuration
- **Docker**: Multi-stage builds, non-root containers, health checks, production-ready compose with TLS
- **Agent Features**: Native function calling (Claude + OpenAI), autonomy loop, tool rate limiting, input validation, CLI chat client
- **WebSocket**: Real-time event feed with auto-reconnect and polling fallback

---

## [4.1.0] - 2026-03-07

**Phase 5: Production Hardening — Foundation Fixes**

Type: Feature (minor)
Previous: 4.0.0

### Changes
- Replaced JSON file-backed persistence with SQLite (WAL mode, ACID, indexed queries)
- Added self-versioning system with automatic semver bumping and changelog generation
- Single source of truth for version in `__init__.py`, synced to all files
- Version management API endpoints (get, bump, sync, changelog)
- Removed all hardcoded version strings across codebase (5 files updated)

---
