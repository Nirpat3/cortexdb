CREATE TABLE IF NOT EXISTS a2a_tasks (
    task_id TEXT PRIMARY KEY,
    task_type TEXT NOT NULL,
    input_data JSONB,
    output_data JSONB,
    status TEXT NOT NULL DEFAULT 'CREATED',
    requester_agent TEXT NOT NULL,
    assigned_agent TEXT,
    error_message TEXT,
    tenant_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_a2a_tasks_status ON a2a_tasks (status);
CREATE INDEX IF NOT EXISTS idx_a2a_tasks_agent ON a2a_tasks (assigned_agent, status);
CREATE INDEX IF NOT EXISTS idx_a2a_tasks_tenant ON a2a_tasks (tenant_id);
