-- ============================================================
-- Rollback for 001_schema.sql
-- Drops ALL objects created by the up migration in reverse
-- dependency order.
-- (c) 2026 Nirlab Inc.
-- ============================================================

-- ── Drop RLS policies ─────────────────────────────────────
DROP POLICY IF EXISTS cp_tenant_isolation ON customer_profiles;
DROP POLICY IF EXISTS ci_tenant_isolation ON customer_identifiers;
DROP POLICY IF EXISTS customers_tenant_isolation ON customers;
DROP POLICY IF EXISTS experience_tenant_isolation ON experience_ledger;
DROP POLICY IF EXISTS tasks_tenant_isolation ON tasks;
DROP POLICY IF EXISTS agents_tenant_isolation ON agents;
DROP POLICY IF EXISTS blocks_tenant_isolation ON blocks;

-- ── Drop triggers ─────────────────────────────────────────
DROP TRIGGER IF EXISTS immutable_ledger_no_update ON immutable_ledger;

-- ── Drop continuous aggregates / materialized views ───────
DROP MATERIALIZED VIEW IF EXISTS customer_event_counts_daily CASCADE;
DROP MATERIALIZED VIEW IF EXISTS heartbeats_hourly CASCADE;

-- ── Drop tables with foreign key dependencies first ───────
DROP TABLE IF EXISTS customer_merges CASCADE;
DROP TABLE IF EXISTS customer_profiles CASCADE;
DROP TABLE IF EXISTS customer_identifiers CASCADE;
DROP TABLE IF EXISTS customer_events CASCADE;
DROP TABLE IF EXISTS customers CASCADE;

DROP TABLE IF EXISTS rate_limit_log CASCADE;

DROP TABLE IF EXISTS a2a_tasks CASCADE;
DROP TABLE IF EXISTS a2a_agent_cards CASCADE;

DROP TABLE IF EXISTS tasks CASCADE;
DROP TABLE IF EXISTS experience_ledger CASCADE;
DROP TABLE IF EXISTS agents CASCADE;
DROP TABLE IF EXISTS blocks CASCADE;

DROP TABLE IF EXISTS grid_links CASCADE;
DROP TABLE IF EXISTS grid_nodes CASCADE;

DROP TABLE IF EXISTS response_cache_meta CASCADE;
DROP TABLE IF EXISTS query_paths CASCADE;
DROP TABLE IF EXISTS asa_standards CASCADE;

DROP TABLE IF EXISTS immutable_ledger CASCADE;

DROP TABLE IF EXISTS query_metrics CASCADE;
DROP TABLE IF EXISTS agent_metrics CASCADE;
DROP TABLE IF EXISTS heartbeats CASCADE;

DROP TABLE IF EXISTS tenants CASCADE;

-- ── Drop Apache AGE graph (if exists) ─────────────────────
DO $$
BEGIN
    PERFORM drop_graph('customer_graph', true);
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'Apache AGE graph not present or extension not loaded — skipping';
END $$;

-- ── Drop functions ────────────────────────────────────────
DROP FUNCTION IF EXISTS verify_ledger_integrity();
DROP FUNCTION IF EXISTS append_to_ledger(VARCHAR, JSONB, VARCHAR, UUID);
DROP FUNCTION IF EXISTS compute_ledger_hash(VARCHAR, JSONB, VARCHAR);
DROP FUNCTION IF EXISTS prevent_ledger_modification();

-- ── Drop extensions (only if no other objects depend on them) ──
DROP EXTENSION IF EXISTS age CASCADE;
DROP EXTENSION IF EXISTS btree_gist CASCADE;
DROP EXTENSION IF EXISTS pg_trgm CASCADE;
DROP EXTENSION IF EXISTS pgcrypto CASCADE;
DROP EXTENSION IF EXISTS timescaledb CASCADE;
