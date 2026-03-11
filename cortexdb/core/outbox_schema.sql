-- Transactional Outbox Pattern for CortexDB Write Fan-Out
-- Replaces in-memory DLQ with crash-safe PG-backed outbox table.

CREATE TABLE IF NOT EXISTS write_outbox (
    id BIGSERIAL PRIMARY KEY,
    data_type TEXT NOT NULL,
    payload JSONB NOT NULL,
    actor TEXT NOT NULL DEFAULT 'system',
    target_engine TEXT NOT NULL,  -- which async engine to write to
    tenant_id TEXT,
    status TEXT NOT NULL DEFAULT 'pending',  -- pending, processing, completed, failed, dead_letter
    retry_count INT NOT NULL DEFAULT 0,
    max_retries INT NOT NULL DEFAULT 3,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed_at TIMESTAMPTZ,
    next_retry_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_outbox_pending ON write_outbox (status, next_retry_at) WHERE status IN ('pending', 'failed');
CREATE INDEX IF NOT EXISTS idx_outbox_cleanup ON write_outbox (status, processed_at) WHERE status = 'completed';
CREATE INDEX IF NOT EXISTS idx_outbox_stuck ON write_outbox (status, created_at) WHERE status = 'processing';
