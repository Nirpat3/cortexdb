-- Rollback: drop runtime_runs table
DROP POLICY IF EXISTS runtime_runs_tenant_isolation ON runtime_runs;
DROP TABLE IF EXISTS runtime_runs;
