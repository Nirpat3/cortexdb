-- Agent Memory Protocol schema
-- Persistent, shared, access-controlled memory layer for AI agents.

CREATE TABLE IF NOT EXISTS agent_memories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id TEXT NOT NULL,
    tenant_id TEXT,
    memory_type TEXT NOT NULL DEFAULT 'episodic',
    content TEXT NOT NULL,
    metadata JSONB DEFAULT '{}',
    shared_with TEXT[] DEFAULT '{}',
    importance FLOAT DEFAULT 0.5,
    access_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_accessed_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ,
    CONSTRAINT valid_memory_type CHECK (memory_type IN ('episodic', 'semantic', 'working'))
);

CREATE INDEX IF NOT EXISTS idx_agent_memories_agent ON agent_memories(agent_id);
CREATE INDEX IF NOT EXISTS idx_agent_memories_tenant ON agent_memories(tenant_id);
CREATE INDEX IF NOT EXISTS idx_agent_memories_type ON agent_memories(memory_type);
CREATE INDEX IF NOT EXISTS idx_agent_memories_shared ON agent_memories USING GIN(shared_with);
CREATE INDEX IF NOT EXISTS idx_agent_memories_created ON agent_memories(created_at DESC);

-- Row-level security for tenant isolation
ALTER TABLE agent_memories ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'agent_memories' AND policyname = 'agent_memories_tenant_policy'
    ) THEN
        CREATE POLICY agent_memories_tenant_policy ON agent_memories
            USING (tenant_id = current_setting('app.current_tenant', true));
    END IF;
END
$$;
