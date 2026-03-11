-- Add performance indexes present in relational-core-init.sql but missing from 001_schema.sql

-- a2a_tasks: compound indexes for sorted queries
CREATE INDEX IF NOT EXISTS idx_a2a_tasks_source_created ON a2a_tasks(source_agent_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_a2a_tasks_target_created ON a2a_tasks(target_agent_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_a2a_tasks_tenant_status ON a2a_tasks(tenant_id, status, created_at DESC);

-- experience_ledger: index on agent_id for per-agent lookups
CREATE INDEX IF NOT EXISTS idx_experience_agent ON experience_ledger(agent_id);

-- response_cache_meta: index on query_hash for cache lookups
CREATE INDEX IF NOT EXISTS idx_rcm_query_hash ON response_cache_meta(query_hash);

-- immutable_ledger: index on actor for audit queries
CREATE INDEX IF NOT EXISTS idx_ledger_actor ON immutable_ledger(actor);

-- customer_events: compound index for per-customer event-type queries
CREATE INDEX IF NOT EXISTS idx_ce_customer_type ON customer_events(customer_id, event_type, time DESC);

-- rate_limit_log: index on created_at for cleanup queries
CREATE INDEX IF NOT EXISTS idx_rate_limit_log_created ON rate_limit_log(created_at);
