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

CREATE INDEX idx_blocks_type ON blocks(block_type);
CREATE INDEX idx_blocks_tags ON blocks USING GIN(tags);
CREATE INDEX idx_blocks_name_search ON blocks USING GIN(name gin_trgm_ops);

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

CREATE INDEX idx_agents_state ON agents(state);
CREATE INDEX idx_agents_parent ON agents(parent_id);
CREATE INDEX idx_agents_grid ON agents(grid_address);

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

CREATE INDEX idx_tasks_status ON tasks(status);
CREATE INDEX idx_tasks_agent ON tasks(agent_id);

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

CREATE INDEX idx_experience_context ON experience_ledger(context_hash);
CREATE INDEX idx_experience_task_type ON experience_ledger(task_type);

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

CREATE INDEX idx_grid_state ON grid_nodes(state);
CREATE INDEX idx_grid_type ON grid_nodes(node_type);
CREATE INDEX idx_grid_zone ON grid_nodes(zone);

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

CREATE INDEX idx_links_source ON grid_links(source_node_id);
CREATE INDEX idx_links_target ON grid_links(target_node_id);

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

CREATE INDEX idx_paths_strength ON query_paths(strength DESC);
CREATE INDEX idx_paths_pattern ON query_paths(query_pattern_hash);

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
CREATE INDEX idx_heartbeats_node ON heartbeats(node_id, time DESC);

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

CREATE INDEX idx_ledger_type ON immutable_ledger(entry_type);
CREATE INDEX idx_ledger_related ON immutable_ledger(related_id);
CREATE INDEX idx_ledger_time ON immutable_ledger(created_at);

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
SELECT append_to_ledger(
    'SYSTEM_GENESIS',
    ('{"message": "CortexDB initialized", "version": "2.0.0", "timestamp": "' || NOW()::TEXT || '"}')::JSONB,
    'cortexdb_init'
);

DO $$
BEGIN
    RAISE NOTICE '================================================';
    RAISE NOTICE 'CortexDB RelationalCore + TemporalCore + ImmutableCore initialized';
    RAISE NOTICE 'Tables: blocks, agents, tasks, experience_ledger, grid_nodes, grid_links';
    RAISE NOTICE 'Tables: asa_standards, query_paths, response_cache_meta';
    RAISE NOTICE 'TimeSeries: heartbeats, agent_metrics, query_metrics';
    RAISE NOTICE 'ImmutableLedger: append-only with SHA-256 hash chain';
    RAISE NOTICE 'ASA Standards: 16 standards seeded';
    RAISE NOTICE '================================================';
END $$;
