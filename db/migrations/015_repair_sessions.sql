-- 015: Repair session persistence for grid RepairEngine
-- Tracks 5-level automated repair sessions (DOC-015) across restarts.

CREATE TABLE IF NOT EXISTS repair_sessions (
    session_id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    node_id TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    starting_level INT NOT NULL DEFAULT 1,
    current_level INT NOT NULL DEFAULT 1,
    final_result TEXT,
    attempts JSONB DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_repair_sessions_node_id ON repair_sessions(node_id);
CREATE INDEX IF NOT EXISTS idx_repair_sessions_incomplete ON repair_sessions(node_id) WHERE completed_at IS NULL;
