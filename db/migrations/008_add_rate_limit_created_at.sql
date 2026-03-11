-- Add created_at column to rate_limit_log if it does not already exist
ALTER TABLE rate_limit_log ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW();
