-- ============================================================
-- CortexDB RelationalCore + GraphCore + TemporalCore Init
-- Single PostgreSQL instance powers 3 brain regions
-- (c) 2026 Nirlab Inc.
-- ============================================================

-- Enable extensions
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS btree_gist;

-- ================================================
-- MULTI-TENANCY: Tenant management (DOC-019 Section 6)
-- ================================================

CREATE TABLE IF NOT EXISTS tenants (
    tenant_id VARCHAR(100) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    plan VARCHAR(20) DEFAULT 'free' CHECK (plan IN ('free','growth','enterprise','custom')),
    status VARCHAR(20) DEFAULT 'onboarding' CHECK (status IN ('onboarding','active','suspended','offboarding','purged')),
    api_key_hash VARCHAR(64) UNIQUE,
    config JSONB DEFAULT '{}',
    rate_limits JSONB DEFAULT '{}',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    activated_at TIMESTAMPTZ,
    deactivated_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_tenants_status ON tenants(status);
CREATE INDEX IF NOT EXISTS idx_tenants_api_key ON tenants(api_key_hash);

-- ================================================
-- A2A: Agent-to-Agent Protocol (DOC-017/018 G19)
-- ================================================

CREATE TABLE IF NOT EXISTS a2a_agent_cards (
    agent_id VARCHAR(255) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    skills TEXT[] DEFAULT '{}',
    tools TEXT[] DEFAULT '{}',
    auth_config JSONB DEFAULT '{}',
    endpoint_url VARCHAR(500),
    protocol VARCHAR(20) DEFAULT 'mcp',
    model VARCHAR(100),
    max_concurrent_tasks INTEGER DEFAULT 5,
    tenant_id VARCHAR(100) REFERENCES tenants(tenant_id),
    metadata JSONB DEFAULT '{}',
    registered_at TIMESTAMPTZ DEFAULT NOW(),
    last_heartbeat TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_a2a_tenant ON a2a_agent_cards(tenant_id);
CREATE INDEX IF NOT EXISTS idx_a2a_skills ON a2a_agent_cards USING GIN(skills);

CREATE TABLE IF NOT EXISTS a2a_tasks (
    task_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_agent_id VARCHAR(255) REFERENCES a2a_agent_cards(agent_id),
    target_agent_id VARCHAR(255) REFERENCES a2a_agent_cards(agent_id),
    skill_requested VARCHAR(255),
    input_data JSONB DEFAULT '{}',
    output_data JSONB,
    status VARCHAR(20) DEFAULT 'created' CHECK (status IN ('created','assigned','running','completed','failed','cancelled')),
    priority INTEGER DEFAULT 3,
    tenant_id VARCHAR(100) REFERENCES tenants(tenant_id),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    assigned_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    error TEXT
);

CREATE INDEX IF NOT EXISTS idx_a2a_tasks_status ON a2a_tasks(status);
CREATE INDEX IF NOT EXISTS idx_a2a_tasks_target ON a2a_tasks(target_agent_id);
CREATE INDEX IF NOT EXISTS idx_a2a_tasks_tenant ON a2a_tasks(tenant_id);

-- ================================================
-- RELATIONALCORE: Business data tables
-- Brain Region: Neocortex (long-term structured memory)
-- ================================================

CREATE TABLE IF NOT EXISTS blocks (
    block_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    block_type VARCHAR(20) NOT NULL CHECK (block_type IN ('L0_function','L1_skill','L2_workflow','L3_agent_template','L4_solution')),
    name VARCHAR(255) NOT NULL,
    version VARCHAR(20) NOT NULL DEFAULT '1.0.0',
    description TEXT,
    input_schema JSONB,
    output_schema JSONB,
    config_schema JSONB,
    dependencies UUID[] DEFAULT '{}',
    code_hash VARCHAR(64),
    tags TEXT[] DEFAULT '{}',
    status VARCHAR(20) DEFAULT 'active' CHECK (status IN ('active','deprecated','archived')),
    usage_count BIGINT DEFAULT 0,
    avg_duration_ms DOUBLE PRECISION DEFAULT 0,
    avg_cost DOUBLE PRECISION DEFAULT 0,
    success_rate DOUBLE PRECISION DEFAULT 1.0,
    created_by VARCHAR(100) DEFAULT 'nirlab',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(name, version)
);

CREATE INDEX IF NOT EXISTS idx_blocks_type ON blocks(block_type);
CREATE INDEX IF NOT EXISTS idx_blocks_tags ON blocks USING GIN(tags);
CREATE INDEX IF NOT EXISTS idx_blocks_name_search ON blocks USING GIN(name gin_trgm_ops);

CREATE TABLE IF NOT EXISTS agents (
    agent_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    parent_id UUID REFERENCES agents(agent_id),
    birth_certificate JSONB NOT NULL,
    state VARCHAR(20) DEFAULT 'SPAWNED' CHECK (state IN (
        'SPAWNED','INITIALIZING','RUNNING','WAITING','ESCALATING',
        'EVALUATING','RETRY','COMPLETE','FAILED','RETIRED'
    )),
    model VARCHAR(100),
    grid_address VARCHAR(255),
    health_score DOUBLE PRECISION DEFAULT 100.0,
    tokens_used BIGINT DEFAULT 0,
    cost_total DOUBLE PRECISION DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    retired_at TIMESTAMPTZ,
    score DOUBLE PRECISION
);

CREATE INDEX IF NOT EXISTS idx_agents_state ON agents(state);
CREATE INDEX IF NOT EXISTS idx_agents_parent ON agents(parent_id);
CREATE INDEX IF NOT EXISTS idx_agents_grid ON agents(grid_address);

CREATE TABLE IF NOT EXISTS tasks (
    task_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id UUID REFERENCES agents(agent_id),
    block_id UUID REFERENCES blocks(block_id),
    description TEXT,
    expected_output TEXT,
    status VARCHAR(20) DEFAULT 'queued' CHECK (status IN (
        'queued','assigned','running','waiting','completed','failed','cancelled'
    )),
    plan JSONB,
    input_data JSONB,
    output_data JSONB,
    duration_ms INTEGER,
    tokens_used BIGINT DEFAULT 0,
    cost DOUBLE PRECISION DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_agent ON tasks(agent_id);

CREATE TABLE IF NOT EXISTS experience_ledger (
    experience_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    context_summary TEXT NOT NULL,
    context_hash VARCHAR(64),
    confidence DOUBLE PRECISION,
    action_taken TEXT,
    outcome_score DOUBLE PRECISION,
    lessons_learned TEXT,
    similar_experience_ids UUID[] DEFAULT '{}',
    agent_id UUID,
    task_type VARCHAR(100),
    model_used VARCHAR(100),
    tokens_consumed BIGINT DEFAULT 0,
    duration_ms INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_experience_context ON experience_ledger(context_hash);
CREATE INDEX IF NOT EXISTS idx_experience_task_type ON experience_ledger(task_type);

CREATE TABLE IF NOT EXISTS grid_nodes (
    node_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    grid_address VARCHAR(255) UNIQUE NOT NULL,
    node_type VARCHAR(50) NOT NULL,
    zone VARCHAR(20) NOT NULL,
    state VARCHAR(20) DEFAULT 'HEALTHY' CHECK (state IN (
        'HEALTHY','DEGRADED','DEAD','QUARANTINE','REPAIRING',
        'PROBATION','DRAINING','REMOVED','TOMBSTONED','PURGED'
    )),
    health_score DOUBLE PRECISION DEFAULT 100.0,
    health_classification VARCHAR(20) DEFAULT 'PRISTINE' CHECK (health_classification IN (
        'PRISTINE','STABLE','FLAKY','CHRONIC','TERMINAL'
    )),
    metadata JSONB DEFAULT '{}',
    last_heartbeat_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    removed_at TIMESTAMPTZ,
    tombstone JSONB
);

CREATE INDEX IF NOT EXISTS idx_grid_state ON grid_nodes(state);
CREATE INDEX IF NOT EXISTS idx_grid_type ON grid_nodes(node_type);
CREATE INDEX IF NOT EXISTS idx_grid_zone ON grid_nodes(zone);

CREATE TABLE IF NOT EXISTS grid_links (
    link_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_node_id UUID REFERENCES grid_nodes(node_id),
    target_node_id UUID REFERENCES grid_nodes(node_id),
    protocol VARCHAR(20) DEFAULT 'grpc',
    latency_ms DOUBLE PRECISION DEFAULT 0,
    error_rate DOUBLE PRECISION DEFAULT 0,
    bandwidth_mbps DOUBLE PRECISION DEFAULT 1000,
    weight DOUBLE PRECISION DEFAULT 1.0,
    state VARCHAR(20) DEFAULT 'active',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_links_source ON grid_links(source_node_id);
CREATE INDEX IF NOT EXISTS idx_links_target ON grid_links(target_node_id);

CREATE TABLE IF NOT EXISTS asa_standards (
    standard_id VARCHAR(30) PRIMARY KEY,
    category VARCHAR(50) NOT NULL,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    scope TEXT,
    enforcement VARCHAR(20) DEFAULT 'HARD' CHECK (enforcement IN ('HARD','SOFT','ADVISORY')),
    source_document VARCHAR(50),
    version VARCHAR(20) DEFAULT '1.0.0',
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS query_paths (
    path_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    query_pattern_hash VARCHAR(64) UNIQUE NOT NULL,
    query_pattern TEXT NOT NULL,
    engines_used TEXT[] NOT NULL,
    strength DOUBLE PRECISION DEFAULT 1.0,
    avg_latency_ms DOUBLE PRECISION DEFAULT 0,
    hit_count BIGINT DEFAULT 0,
    last_used_at TIMESTAMPTZ DEFAULT NOW(),
    materialized_view_name VARCHAR(255),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_paths_strength ON query_paths(strength DESC);
CREATE INDEX IF NOT EXISTS idx_paths_pattern ON query_paths(query_pattern_hash);

CREATE TABLE IF NOT EXISTS response_cache_meta (
    cache_key VARCHAR(128) PRIMARY KEY,
    query_hash VARCHAR(64) NOT NULL,
    engines_hit TEXT[] NOT NULL,
    tier_served VARCHAR(5) NOT NULL,
    latency_ms DOUBLE PRECISION,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_accessed_at TIMESTAMPTZ DEFAULT NOW(),
    access_count BIGINT DEFAULT 1,
    ttl_seconds INTEGER DEFAULT 3600
);

-- ================================================
-- TEMPORALCORE: Time-series tables (TimescaleDB)
-- Brain Region: Cerebellum (temporal patterns)
-- ================================================

CREATE TABLE IF NOT EXISTS heartbeats (
    time TIMESTAMPTZ NOT NULL,
    node_id UUID NOT NULL,
    grid_address VARCHAR(255),
    state VARCHAR(20),
    cpu_pct DOUBLE PRECISION,
    memory_pct DOUBLE PRECISION,
    latency_p95_ms DOUBLE PRECISION,
    error_rate DOUBLE PRECISION,
    active_connections INTEGER,
    metadata JSONB DEFAULT '{}'
);

SELECT create_hypertable('heartbeats', 'time', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_heartbeats_node ON heartbeats(node_id, time DESC);

CREATE TABLE IF NOT EXISTS agent_metrics (
    time TIMESTAMPTZ NOT NULL,
    agent_id UUID NOT NULL,
    tokens_used_delta BIGINT DEFAULT 0,
    cost_delta DOUBLE PRECISION DEFAULT 0,
    tasks_completed_delta INTEGER DEFAULT 0,
    avg_score DOUBLE PRECISION,
    cache_hit_rate DOUBLE PRECISION
);

SELECT create_hypertable('agent_metrics', 'time', if_not_exists => TRUE);

CREATE TABLE IF NOT EXISTS query_metrics (
    time TIMESTAMPTZ NOT NULL,
    query_hash VARCHAR(64),
    tier_served VARCHAR(5),
    latency_ms DOUBLE PRECISION,
    engines_hit TEXT[],
    cache_hit BOOLEAN DEFAULT FALSE,
    tokens_used BIGINT DEFAULT 0,
    cost DOUBLE PRECISION DEFAULT 0
);

SELECT create_hypertable('query_metrics', 'time', if_not_exists => TRUE);

CREATE MATERIALIZED VIEW IF NOT EXISTS heartbeats_hourly
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 hour', time) AS bucket,
    node_id,
    AVG(cpu_pct) AS avg_cpu,
    AVG(memory_pct) AS avg_memory,
    AVG(latency_p95_ms) AS avg_latency,
    MAX(error_rate) AS max_error_rate,
    COUNT(*) AS heartbeat_count
FROM heartbeats
GROUP BY bucket, node_id
WITH NO DATA;

-- ================================================
-- IMMUTABLECORE: Append-only audit trail
-- Brain Region: Declarative Memory
-- ================================================

CREATE TABLE IF NOT EXISTS immutable_ledger (
    sequence_id BIGSERIAL PRIMARY KEY,
    entry_id UUID DEFAULT gen_random_uuid() UNIQUE,
    entry_type VARCHAR(50) NOT NULL,
    payload JSONB NOT NULL,
    actor VARCHAR(255),
    related_id UUID,
    prev_hash VARCHAR(64),
    entry_hash VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE OR REPLACE FUNCTION prevent_ledger_modification()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'ImmutableCore: ledger entries cannot be modified or deleted.';
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS immutable_ledger_no_update ON immutable_ledger;
CREATE TRIGGER immutable_ledger_no_update
    BEFORE UPDATE OR DELETE ON immutable_ledger
    FOR EACH ROW EXECUTE FUNCTION prevent_ledger_modification();

CREATE INDEX IF NOT EXISTS idx_ledger_type ON immutable_ledger(entry_type);
CREATE INDEX IF NOT EXISTS idx_ledger_related ON immutable_ledger(related_id);
CREATE INDEX IF NOT EXISTS idx_ledger_time ON immutable_ledger(created_at);

-- ================================================
-- SEED DATA: ASA Standards (21 total)
-- ================================================

INSERT INTO asa_standards (standard_id, category, title, description, enforcement, source_document) VALUES
('NIRLAB-STD-001', 'Block Architecture', 'Universal Block Interface', 'All blocks must have: block_id, version, input_schema, output_schema, dependencies, config_schema', 'HARD', 'DOC-013'),
('NIRLAB-STD-002', 'Communication', 'Approved Protocols', 'gRPC (internal), HTTP/2 (API), WebSocket (real-time), Redis Streams (events)', 'HARD', 'DOC-014'),
('NIRLAB-STD-003', 'Data Format', 'Payload Standards', 'JSON (REST), ISO 8601 (dates), ISO 4217 (currency)', 'HARD', 'DOC-010'),
('NIRLAB-SEC-001', 'Security', 'Birth Certificate Enforcement', 'Every agent must have valid Birth Certificate. Tools subset of parent.', 'HARD', 'DOC-003'),
('NIRLAB-SEC-002', 'Security', 'Secret Management', 'No plaintext secrets in env/config/code. Use Vault or encrypted config.', 'HARD', 'DOC-006'),
('NIRLAB-STD-004', 'Naming', 'Resource Naming', 'Services: kebab-case. Agents: PascalCase. Tables: snake_case.', 'SOFT', 'DOC-015'),
('NIRLAB-STD-005', 'API', 'API Versioning', 'All APIs versioned /v1/. Breaking changes = new major version.', 'HARD', 'DOC-015'),
('NIRLAB-STD-006', 'Grid', 'Packet Envelope', 'All grid packets: packet_id, source, destination, priority, ttl', 'HARD', 'DOC-015'),
('NIRLAB-STD-007', 'Error Handling', 'RFC 7807 Errors', 'All errors: {type, title, status, detail, instance}', 'SOFT', 'DOC-015'),
('NIRLAB-STD-008', 'Logging', 'Structured Logging', 'All logs: {timestamp, level, service, trace_id, message, context}', 'SOFT', 'DOC-015'),
('NIRLAB-STD-009', 'Performance', 'Service SLAs', 'Liveness < 3s. API p95 < 500ms. Error rate < 2%.', 'HARD', 'DOC-014'),
('NIRLAB-GRID-001', 'Grid', 'Minimum Redundancy', 'Every node type >= 2 instances (except PRIME). Removal blocked if violation.', 'HARD', 'DOC-015'),
('NIRLAB-GRID-002', 'Grid', 'Dead Node Timeout', 'Nodes dead within 3x heartbeat interval. Strictly enforced.', 'HARD', 'DOC-015'),
('NIRLAB-GRID-003', 'Grid', 'Repair Escalation', 'Max 10 min automated repair window before human escalation.', 'HARD', 'DOC-015'),
('NIRLAB-GRID-004', 'Grid', 'Tombstone Retention', '90 days hot + 7 years cold. Grid address locked 24hr after removal.', 'HARD', 'DOC-015'),
('NIRLAB-GRID-005', 'Grid', 'Health Score Transparency', 'CHRONIC/TERMINAL nodes generate investigation tickets within 24hr.', 'HARD', 'DOC-015')
ON CONFLICT (standard_id) DO NOTHING;

-- ================================================
-- FUNCTIONS: CortexDB utility functions
-- ================================================

CREATE OR REPLACE FUNCTION compute_ledger_hash(
    p_entry_type VARCHAR,
    p_payload JSONB,
    p_prev_hash VARCHAR
) RETURNS VARCHAR AS $$
BEGIN
    RETURN encode(
        digest(
            COALESCE(p_prev_hash, 'GENESIS') || '|' || p_entry_type || '|' || p_payload::TEXT || '|' || NOW()::TEXT,
            'sha256'
        ),
        'hex'
    );
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION append_to_ledger(
    p_entry_type VARCHAR,
    p_payload JSONB,
    p_actor VARCHAR DEFAULT 'system',
    p_related_id UUID DEFAULT NULL
) RETURNS UUID AS $$
DECLARE
    v_prev_hash VARCHAR;
    v_entry_hash VARCHAR;
    v_entry_id UUID;
BEGIN
    SELECT entry_hash INTO v_prev_hash FROM immutable_ledger ORDER BY sequence_id DESC LIMIT 1;
    v_entry_hash := compute_ledger_hash(p_entry_type, p_payload, v_prev_hash);
    v_entry_id := gen_random_uuid();
    INSERT INTO immutable_ledger (entry_id, entry_type, payload, actor, related_id, prev_hash, entry_hash)
    VALUES (v_entry_id, p_entry_type, p_payload, p_actor, p_related_id, v_prev_hash, v_entry_hash);
    RETURN v_entry_id;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION verify_ledger_integrity()
RETURNS TABLE(is_valid BOOLEAN, broken_at BIGINT, total_entries BIGINT) AS $$
DECLARE
    r RECORD;
    expected_hash VARCHAR;
    prev_hash VARCHAR;
    entry_count BIGINT := 0;
BEGIN
    FOR r IN SELECT * FROM immutable_ledger ORDER BY sequence_id ASC LOOP
        entry_count := entry_count + 1;
        expected_hash := compute_ledger_hash(r.entry_type, r.payload, prev_hash);
        IF r.entry_hash != expected_hash THEN
            RETURN QUERY SELECT FALSE, r.sequence_id, entry_count;
            RETURN;
        END IF;
        prev_hash := r.entry_hash;
    END LOOP;
    RETURN QUERY SELECT TRUE, 0::BIGINT, entry_count;
END;
$$ LANGUAGE plpgsql;

-- Genesis entry
DO $$ BEGIN
IF NOT EXISTS (SELECT 1 FROM immutable_ledger WHERE entry_type = 'SYSTEM_GENESIS') THEN
    PERFORM append_to_ledger(
        'SYSTEM_GENESIS',
        ('{"message": "CortexDB initialized", "version": "2.0.0", "timestamp": "' || NOW()::TEXT || '"}')::JSONB,
        'cortexdb_init'
    );
END IF;
END $$;

-- ================================================
-- MULTI-TENANCY: Add tenant_id + Row-Level Security (DOC-019 Section 6.1)
-- ================================================

-- Add tenant_id to all business tables
ALTER TABLE blocks ADD COLUMN IF NOT EXISTS tenant_id VARCHAR(100) REFERENCES tenants(tenant_id);
ALTER TABLE agents ADD COLUMN IF NOT EXISTS tenant_id VARCHAR(100) REFERENCES tenants(tenant_id);
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS tenant_id VARCHAR(100) REFERENCES tenants(tenant_id);
ALTER TABLE experience_ledger ADD COLUMN IF NOT EXISTS tenant_id VARCHAR(100) REFERENCES tenants(tenant_id);

CREATE INDEX IF NOT EXISTS idx_blocks_tenant ON blocks(tenant_id);
CREATE INDEX IF NOT EXISTS idx_agents_tenant ON agents(tenant_id);
CREATE INDEX IF NOT EXISTS idx_tasks_tenant ON tasks(tenant_id);
CREATE INDEX IF NOT EXISTS idx_experience_tenant ON experience_ledger(tenant_id);

-- Enable Row-Level Security
ALTER TABLE blocks ENABLE ROW LEVEL SECURITY;
ALTER TABLE agents ENABLE ROW LEVEL SECURITY;
ALTER TABLE tasks ENABLE ROW LEVEL SECURITY;
ALTER TABLE experience_ledger ENABLE ROW LEVEL SECURITY;

-- RLS Policies: filter by current_setting('app.current_tenant')
-- Bypass for superuser (cortex role)
DO $$ BEGIN
IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'blocks_tenant_isolation') THEN
    CREATE POLICY blocks_tenant_isolation ON blocks
        USING (tenant_id IS NULL OR tenant_id = current_setting('app.current_tenant', true));
END IF;
END $$;

DO $$ BEGIN
IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'agents_tenant_isolation') THEN
    CREATE POLICY agents_tenant_isolation ON agents
        USING (tenant_id IS NULL OR tenant_id = current_setting('app.current_tenant', true));
END IF;
END $$;

DO $$ BEGIN
IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'tasks_tenant_isolation') THEN
    CREATE POLICY tasks_tenant_isolation ON tasks
        USING (tenant_id IS NULL OR tenant_id = current_setting('app.current_tenant', true));
END IF;
END $$;

DO $$ BEGIN
IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'experience_tenant_isolation') THEN
    CREATE POLICY experience_tenant_isolation ON experience_ledger
        USING (tenant_id IS NULL OR tenant_id = current_setting('app.current_tenant', true));
END IF;
END $$;

-- Rate limiting tracking table
CREATE TABLE IF NOT EXISTS rate_limit_log (
    id BIGSERIAL PRIMARY KEY,
    tenant_id VARCHAR(100),
    tier VARCHAR(20),
    endpoint VARCHAR(255),
    count INTEGER DEFAULT 1,
    window_start TIMESTAMPTZ DEFAULT NOW(),
    exceeded BOOLEAN DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_rate_limit_tenant ON rate_limit_log(tenant_id, window_start);

-- ================================================
-- SEED: Additional ASA Standards for multi-tenancy
-- ================================================

INSERT INTO asa_standards (standard_id, category, title, description, enforcement, source_document) VALUES
('NIRLAB-SEC-003', 'Security', 'Tenant Data Isolation', 'RLS enabled on all tenant tables. Cross-tenant access blocked at DB level.', 'HARD', 'DOC-019'),
('NIRLAB-SEC-004', 'Security', 'API Key Hashing', 'API keys stored as SHA-256 hash. Plaintext never persisted.', 'HARD', 'DOC-019'),
('NIRLAB-SEC-005', 'Security', 'Rate Limiting', 'All tiers enforced: global, per-customer, per-agent, per-endpoint.', 'HARD', 'DOC-019'),
('NIRLAB-STD-010', 'Observability', 'Distributed Tracing', 'All requests carry trace_id. Spans for each engine hop.', 'SOFT', 'DOC-019'),
('NIRLAB-STD-011', 'Observability', 'Prometheus Metrics', 'All services expose /health/metrics in Prometheus format.', 'SOFT', 'DOC-019')
ON CONFLICT (standard_id) DO NOTHING;

-- ================================================
-- CORTEXGRAPH: Customer Intelligence (DOC-020)
-- Layer 1: Identity Resolution
-- Layer 2: Event Database
-- Layer 3: Relationship Graph
-- Layer 4: Behavioral Profile
-- ================================================

-- Customers master table (identity resolution target)
CREATE TABLE IF NOT EXISTS customers (
    customer_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    canonical_name VARCHAR(255),
    canonical_email VARCHAR(255),
    canonical_phone VARCHAR(50),
    status VARCHAR(20) DEFAULT 'active' CHECK (status IN ('active','merged','suspended','deleted')),
    merge_count INTEGER DEFAULT 0,
    confidence_score DOUBLE PRECISION DEFAULT 1.0,
    first_seen_at TIMESTAMPTZ DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ DEFAULT NOW(),
    tenant_id VARCHAR(100) REFERENCES tenants(tenant_id),
    metadata JSONB DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_customers_email ON customers(canonical_email);
CREATE INDEX IF NOT EXISTS idx_customers_phone ON customers(canonical_phone);
CREATE INDEX IF NOT EXISTS idx_customers_tenant ON customers(tenant_id);
CREATE INDEX IF NOT EXISTS idx_customers_status ON customers(status);

-- Customer identifiers (multi-identifier resolution)
CREATE TABLE IF NOT EXISTS customer_identifiers (
    identifier_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id UUID NOT NULL REFERENCES customers(customer_id) ON DELETE CASCADE,
    identifier_type VARCHAR(30) NOT NULL CHECK (identifier_type IN (
        'email','phone','device_id','loyalty_id','cookie','ip',
        'social_handle','pos_customer_id','payment_token'
    )),
    identifier_value VARCHAR(500) NOT NULL,
    source VARCHAR(100) DEFAULT 'api',
    confidence DOUBLE PRECISION DEFAULT 1.0,
    first_seen_at TIMESTAMPTZ DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ DEFAULT NOW(),
    tenant_id VARCHAR(100) REFERENCES tenants(tenant_id),
    UNIQUE(identifier_type, identifier_value, tenant_id)
);

CREATE INDEX IF NOT EXISTS idx_ci_customer ON customer_identifiers(customer_id);
CREATE INDEX IF NOT EXISTS idx_ci_lookup ON customer_identifiers(identifier_type, identifier_value);
CREATE INDEX IF NOT EXISTS idx_ci_tenant ON customer_identifiers(tenant_id);

-- Customer events (TimescaleDB hypertable)
CREATE TABLE IF NOT EXISTS customer_events (
    time TIMESTAMPTZ NOT NULL,
    event_id UUID DEFAULT gen_random_uuid(),
    customer_id UUID NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    properties JSONB DEFAULT '{}',
    source VARCHAR(100) DEFAULT 'api',
    session_id VARCHAR(255),
    channel VARCHAR(50),
    tenant_id VARCHAR(100),
    amount DOUBLE PRECISION
);

SELECT create_hypertable('customer_events', 'time', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_ce_customer ON customer_events(customer_id, time DESC);
CREATE INDEX IF NOT EXISTS idx_ce_type ON customer_events(event_type, time DESC);
CREATE INDEX IF NOT EXISTS idx_ce_tenant ON customer_events(tenant_id, time DESC);
CREATE INDEX IF NOT EXISTS idx_ce_session ON customer_events(session_id);

-- Customer merge history (audit trail in ImmutableCore)
CREATE TABLE IF NOT EXISTS customer_merges (
    merge_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    canonical_id UUID NOT NULL REFERENCES customers(customer_id),
    merged_id UUID NOT NULL REFERENCES customers(customer_id),
    reason VARCHAR(50) DEFAULT 'manual',
    identifiers_moved INTEGER DEFAULT 0,
    merged_at TIMESTAMPTZ DEFAULT NOW(),
    merged_by VARCHAR(100) DEFAULT 'system',
    tenant_id VARCHAR(100) REFERENCES tenants(tenant_id)
);

CREATE INDEX IF NOT EXISTS idx_merges_canonical ON customer_merges(canonical_id);
CREATE INDEX IF NOT EXISTS idx_merges_merged ON customer_merges(merged_id);

-- Customer profiles (materialized from events)
CREATE TABLE IF NOT EXISTS customer_profiles (
    customer_id UUID PRIMARY KEY REFERENCES customers(customer_id),
    recency_days DOUBLE PRECISION DEFAULT 0,
    frequency_90d INTEGER DEFAULT 0,
    monetary_90d DOUBLE PRECISION DEFAULT 0,
    avg_basket DOUBLE PRECISION DEFAULT 0,
    churn_probability DOUBLE PRECISION DEFAULT 0,
    health_score DOUBLE PRECISION DEFAULT 100.0,
    rfm_segment VARCHAR(30) DEFAULT 'New',
    segments TEXT[] DEFAULT '{}',
    ltv DOUBLE PRECISION DEFAULT 0,
    preferred_categories TEXT[] DEFAULT '{}',
    preferred_channel VARCHAR(50),
    next_purchase_predicted_days INTEGER,
    tenant_id VARCHAR(100) REFERENCES tenants(tenant_id),
    computed_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_cp_segment ON customer_profiles(rfm_segment);
CREATE INDEX IF NOT EXISTS idx_cp_churn ON customer_profiles(churn_probability DESC);
CREATE INDEX IF NOT EXISTS idx_cp_health ON customer_profiles(health_score);
CREATE INDEX IF NOT EXISTS idx_cp_tenant ON customer_profiles(tenant_id);

-- Continuous aggregate for event counts per customer
CREATE MATERIALIZED VIEW IF NOT EXISTS customer_event_counts_daily
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 day', time) AS bucket,
    customer_id,
    event_type,
    COUNT(*) AS event_count,
    COALESCE(SUM(amount), 0) AS total_amount,
    tenant_id
FROM customer_events
GROUP BY bucket, customer_id, event_type, tenant_id
WITH NO DATA;

-- RLS on CortexGraph tables
ALTER TABLE customers ENABLE ROW LEVEL SECURITY;
ALTER TABLE customer_identifiers ENABLE ROW LEVEL SECURITY;
ALTER TABLE customer_profiles ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'customers_tenant_isolation') THEN
    CREATE POLICY customers_tenant_isolation ON customers
        USING (tenant_id IS NULL OR tenant_id = current_setting('app.current_tenant', true));
END IF;
END $$;

DO $$ BEGIN
IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'ci_tenant_isolation') THEN
    CREATE POLICY ci_tenant_isolation ON customer_identifiers
        USING (tenant_id IS NULL OR tenant_id = current_setting('app.current_tenant', true));
END IF;
END $$;

DO $$ BEGIN
IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'cp_tenant_isolation') THEN
    CREATE POLICY cp_tenant_isolation ON customer_profiles
        USING (tenant_id IS NULL OR tenant_id = current_setting('app.current_tenant', true));
END IF;
END $$;

-- GraphCore: Apache AGE graph for relationship traversal (DOC-020 Section 3.3)
-- Requires AGE extension; gracefully skip if not available
DO $$
BEGIN
    CREATE EXTENSION IF NOT EXISTS age;
    LOAD 'age';
    SET search_path = ag_catalog, "$user", public;

    -- Create customer graph
    PERFORM create_graph('customer_graph');

    RAISE NOTICE 'Apache AGE graph "customer_graph" created successfully';
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'Apache AGE not available - using SQL fallback for graph queries';
END $$;

-- ================================================
-- SEED: CortexGraph ASA Standards
-- ================================================

INSERT INTO asa_standards (standard_id, category, title, description, enforcement, source_document) VALUES
('NIRLAB-CG-001', 'CortexGraph', 'Identity Resolution', 'Deterministic match on exact identifiers. Probabilistic match requires cosine > 0.92.', 'HARD', 'DOC-020'),
('NIRLAB-CG-002', 'CortexGraph', 'Customer Merge Audit', 'All customer merges must be logged to ImmutableCore with reason and identifier count.', 'HARD', 'DOC-020'),
('NIRLAB-CG-003', 'CortexGraph', 'Event Auto-Edge', 'Purchase, visit, and campaign events auto-create graph edges.', 'SOFT', 'DOC-020'),
('NIRLAB-CG-004', 'CortexGraph', 'Profile Freshness', 'Customer profiles recomputed nightly via Sleep Cycle. Max staleness 24hr.', 'SOFT', 'DOC-020')
ON CONFLICT (standard_id) DO NOTHING;

DO $$
BEGIN
    RAISE NOTICE '================================================';
    RAISE NOTICE 'CortexDB v3.0 + CortexGraph Schema Initialized';
    RAISE NOTICE 'Tables: tenants, a2a_agent_cards, a2a_tasks';
    RAISE NOTICE 'Tables: blocks, agents, tasks, experience_ledger, grid_nodes, grid_links';
    RAISE NOTICE 'Tables: asa_standards, query_paths, response_cache_meta, rate_limit_log';
    RAISE NOTICE 'CortexGraph: customers, customer_identifiers, customer_events';
    RAISE NOTICE 'CortexGraph: customer_merges, customer_profiles';
    RAISE NOTICE 'TimeSeries: heartbeats, agent_metrics, query_metrics, customer_events';
    RAISE NOTICE 'ImmutableLedger: append-only with SHA-256 hash chain';
    RAISE NOTICE 'RLS: enabled on blocks, agents, tasks, experience_ledger, customers, customer_identifiers, customer_profiles';
    RAISE NOTICE 'ASA Standards: 25 standards seeded (21 + 4 CortexGraph)';
    RAISE NOTICE 'Multi-Tenancy: ACTIVE | A2A: ACTIVE | CortexGraph: ACTIVE';
    RAISE NOTICE '================================================';
END $$;
