-- ============================================================
-- CortexDB Citus Sharding Configuration
-- Petabyte-Scale Horizontal Distribution
-- (c) 2026 Nirlab Inc.
-- ============================================================
--
-- WHAT IS CITUS?
--   Citus is a PostgreSQL extension that transforms a single
--   PostgreSQL database into a distributed database cluster.
--   It shards tables across multiple worker nodes while keeping
--   the SQL interface unchanged.
--
-- ARCHITECTURE:
--   Coordinator (1 node)
--     ├── Worker 1: Shards 0-31   (tenant data subset)
--     ├── Worker 2: Shards 32-63  (tenant data subset)
--     ├── Worker 3: Shards 64-95  (tenant data subset)
--     └── Worker 4: Shards 96-127 (tenant data subset)
--
-- DISTRIBUTION STRATEGY:
--   - Distribution column: tenant_id (all multi-tenant tables)
--   - Co-location: Related tables share the same shard
--     (customers + events + profiles on same node = no cross-shard JOINs)
--   - Reference tables: Small lookup tables replicated everywhere
--   - Columnar storage: Analytics tables use columnar access method
--
-- SCALING:
--   - Add workers: SELECT citus_add_node('worker-5', 5432);
--   - Rebalance:   SELECT citus_rebalance_start();
--   - Isolate tenant: Move premium tenant to dedicated shard
-- ============================================================

-- Step 1: Enable Citus extension
CREATE EXTENSION IF NOT EXISTS citus;

-- Step 2: Configure shard settings
-- 128 shards = supports up to 128 worker nodes
-- Replication factor 1 for single-node, increase for HA
SET citus.shard_count = 128;
SET citus.shard_replication_factor = 1;

-- Step 3: Reference tables (replicated to ALL nodes)
-- Small, frequently-joined lookup tables
SELECT create_reference_table('tenants');
SELECT create_reference_table('asa_standards');

-- Step 4: Distribute CortexGraph tables (co-located on tenant_id)
-- All CortexGraph tables share the same shard = JOINs stay local
SELECT create_distributed_table('customers', 'tenant_id');
SELECT create_distributed_table('customer_identifiers', 'tenant_id',
    colocate_with => 'customers');
SELECT create_distributed_table('customer_events', 'tenant_id',
    colocate_with => 'customers');
SELECT create_distributed_table('customer_profiles', 'tenant_id',
    colocate_with => 'customers');
SELECT create_distributed_table('customer_merges', 'tenant_id',
    colocate_with => 'customers');

-- Step 5: Distribute core business tables (co-located on tenant_id)
SELECT create_distributed_table('blocks', 'tenant_id');
SELECT create_distributed_table('agents', 'tenant_id',
    colocate_with => 'blocks');
SELECT create_distributed_table('tasks', 'tenant_id',
    colocate_with => 'blocks');
SELECT create_distributed_table('experience_ledger', 'tenant_id',
    colocate_with => 'blocks');

-- Step 6: Distribute A2A tables
SELECT create_distributed_table('a2a_agent_cards', 'tenant_id');
SELECT create_distributed_table('a2a_tasks', 'tenant_id',
    colocate_with => 'a2a_agent_cards');

-- Step 7: Columnar storage for analytics (high compression, fast scans)
-- Columnar tables: 8-12x compression vs row storage
-- Best for: append-only, analytics queries, time-series aggregation
DO $$
BEGIN
    -- Convert analytics tables to columnar storage if supported
    PERFORM alter_table_set_access_method('query_metrics', 'columnar');
    RAISE NOTICE 'query_metrics converted to columnar storage';
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'Columnar storage not available (requires Citus 11+)';
END $$;

-- Step 8: Verify distribution
DO $$
DECLARE
    dist_count INTEGER;
    ref_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO dist_count
    FROM citus_tables WHERE distribution_column IS NOT NULL;

    SELECT COUNT(*) INTO ref_count
    FROM citus_tables WHERE table_type = 'reference';

    RAISE NOTICE '================================================';
    RAISE NOTICE 'Citus Sharding Configuration Complete';
    RAISE NOTICE 'Distributed tables: %', dist_count;
    RAISE NOTICE 'Reference tables: %', ref_count;
    RAISE NOTICE 'Shard count: 128';
    RAISE NOTICE 'Distribution column: tenant_id';
    RAISE NOTICE 'Co-location groups: cortexgraph, core, a2a';
    RAISE NOTICE '================================================';
END $$;
