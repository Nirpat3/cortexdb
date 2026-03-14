-- Trace tables for CortexEngine observability layer.
-- Stores trace headers and individual steps with tenant isolation.

-- Trace header — one per logical operation / request.
CREATE TABLE IF NOT EXISTS traces (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    merchant_id TEXT,
    task_id TEXT,                              -- optional link to runtime_runs
    request_id TEXT,                           -- correlation with HTTP request
    name TEXT NOT NULL,                        -- human-readable trace name
    status TEXT NOT NULL DEFAULT 'open',       -- open, closed, error
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_traces_tenant ON traces (tenant_id, status);
CREATE INDEX IF NOT EXISTS idx_traces_task ON traces (tenant_id, task_id) WHERE task_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_traces_request ON traces (tenant_id, request_id) WHERE request_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_traces_created ON traces (created_at DESC);

ALTER TABLE traces ENABLE ROW LEVEL SECURITY;

CREATE POLICY traces_tenant_isolation ON traces
    USING (tenant_id = current_setting('app.current_tenant', TRUE));


-- Trace steps — ordered events within a trace.
CREATE TABLE IF NOT EXISTS trace_steps (
    id TEXT PRIMARY KEY,
    trace_id TEXT NOT NULL REFERENCES traces(id) ON DELETE CASCADE,
    tenant_id TEXT NOT NULL,
    step_index INTEGER NOT NULL DEFAULT 0,
    name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'ok',        -- ok, error, warning
    input JSONB,
    output JSONB,
    error TEXT,
    duration_ms DOUBLE PRECISION,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_trace_steps_trace ON trace_steps (trace_id, step_index);
CREATE INDEX IF NOT EXISTS idx_trace_steps_tenant ON trace_steps (tenant_id);

ALTER TABLE trace_steps ENABLE ROW LEVEL SECURITY;

CREATE POLICY trace_steps_tenant_isolation ON trace_steps
    USING (tenant_id = current_setting('app.current_tenant', TRUE));
