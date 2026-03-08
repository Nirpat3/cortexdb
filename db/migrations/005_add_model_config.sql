-- ============================================================================
-- Migration 005: Model Configurations
-- ============================================================================
-- Model configuration defaults for agent LLM assignments.
-- Supports scoped overrides: global -> department -> agent.
-- ============================================================================

CREATE TABLE IF NOT EXISTS model_configurations (
    id                  SERIAL PRIMARY KEY,
    scope               VARCHAR(50) NOT NULL DEFAULT 'global',   -- global, department, agent
    scope_id            VARCHAR(100),                             -- department name or agent_id
    provider            VARCHAR(50) NOT NULL DEFAULT 'ollama',
    model               VARCHAR(100) NOT NULL DEFAULT 'llama3.1:8b',
    fallback_provider   VARCHAR(50),
    fallback_model      VARCHAR(100),
    temperature         FLOAT DEFAULT 0.7,
    max_tokens          INT DEFAULT 4096,
    priority            INT DEFAULT 0,                            -- higher = takes precedence
    enabled             BOOLEAN DEFAULT TRUE,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_model_config_scope ON model_configurations(scope, scope_id);

-- Seed global default
INSERT INTO model_configurations (scope, provider, model, fallback_provider, fallback_model)
VALUES ('global', 'ollama', 'llama3.1:8b', 'claude', 'claude-sonnet-4-20250514')
ON CONFLICT DO NOTHING;
