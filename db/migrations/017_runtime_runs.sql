-- Runtime Runs table for CortexEngine Runtime layer
-- Stores workflow / runtime run state with tenant isolation.

CREATE TABLE IF NOT EXISTS runtime_runs (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    merchant_id TEXT,
    workflow_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',   -- pending, running, completed, failed, cancelled
    spec JSONB NOT NULL DEFAULT '{}'::jsonb,  -- full run specification (input, tags, idempotency_key)
    output JSONB,
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Tenant isolation index (every query filters by tenant_id)
CREATE INDEX IF NOT EXISTS idx_runtime_runs_tenant ON runtime_runs (tenant_id, status);
CREATE INDEX IF NOT EXISTS idx_runtime_runs_type ON runtime_runs (tenant_id, workflow_type);
CREATE INDEX IF NOT EXISTS idx_runtime_runs_created ON runtime_runs (created_at DESC);

-- Enable RLS for tenant isolation (matches existing pattern)
ALTER TABLE runtime_runs ENABLE ROW LEVEL SECURITY;

CREATE POLICY runtime_runs_tenant_isolation ON runtime_runs
    USING (tenant_id = current_setting('app.current_tenant', TRUE));
