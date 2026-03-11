-- ============================================================
-- Rollback for 002_sharding.sql
-- Undoes Citus distributed/reference table setup and columnar
-- storage conversion.
-- (c) 2026 Nirlab Inc.
-- ============================================================

-- Revert columnar storage back to heap (row) for query_metrics
DO $$
BEGIN
    PERFORM alter_table_set_access_method('query_metrics', 'heap');
    RAISE NOTICE 'query_metrics reverted to heap (row) storage';
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'Could not revert query_metrics access method — skipping';
END $$;

-- Undistribute A2A tables
SELECT undistribute_table('a2a_tasks', cascade_via_foreign_keys := true);
SELECT undistribute_table('a2a_agent_cards', cascade_via_foreign_keys := true);

-- Undistribute core business tables
SELECT undistribute_table('experience_ledger', cascade_via_foreign_keys := true);
SELECT undistribute_table('tasks', cascade_via_foreign_keys := true);
SELECT undistribute_table('agents', cascade_via_foreign_keys := true);
SELECT undistribute_table('blocks', cascade_via_foreign_keys := true);

-- Undistribute CortexGraph tables
SELECT undistribute_table('customer_merges', cascade_via_foreign_keys := true);
SELECT undistribute_table('customer_profiles', cascade_via_foreign_keys := true);
SELECT undistribute_table('customer_events', cascade_via_foreign_keys := true);
SELECT undistribute_table('customer_identifiers', cascade_via_foreign_keys := true);
SELECT undistribute_table('customers', cascade_via_foreign_keys := true);

-- Undistribute reference tables
SELECT undistribute_table('asa_standards', cascade_via_foreign_keys := true);
SELECT undistribute_table('tenants', cascade_via_foreign_keys := true);

-- Drop Citus extension
DROP EXTENSION IF EXISTS citus CASCADE;
