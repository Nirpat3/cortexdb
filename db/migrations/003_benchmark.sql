-- CortexDB Benchmark Schema
-- Scratch tables used by performance and stress tests.
-- Safe to drop after testing. Isolated from production data.

-- Benchmark scratch table for insert/select tests
CREATE TABLE IF NOT EXISTS benchmark_scratch (
    id TEXT PRIMARY KEY,
    data JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Benchmark ledger for immutable write tests
CREATE TABLE IF NOT EXISTS benchmark_ledger (
    id BIGSERIAL PRIMARY KEY,
    entry_hash TEXT NOT NULL,
    prev_hash TEXT NOT NULL,
    data TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Benchmark audit log for compliance tests
CREATE TABLE IF NOT EXISTS benchmark_audit (
    id BIGSERIAL PRIMARY KEY,
    event_type TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    details JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Index for time-range queries
CREATE INDEX IF NOT EXISTS idx_bench_scratch_created
    ON benchmark_scratch (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_bench_audit_created
    ON benchmark_audit (created_at DESC);

-- Auto-cleanup: drop rows older than 1 hour (run via Sleep Cycle or cron)
-- DELETE FROM benchmark_scratch WHERE created_at < NOW() - INTERVAL '1 hour';
-- DELETE FROM benchmark_ledger WHERE created_at < NOW() - INTERVAL '1 hour';
-- DELETE FROM benchmark_audit WHERE created_at < NOW() - INTERVAL '1 hour';
