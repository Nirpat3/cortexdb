-- Migration 016: Add updated_at column to tenants table for hot-reload delta queries
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();

-- Backfill existing rows
UPDATE tenants SET updated_at = COALESCE(activated_at, created_at) WHERE updated_at IS NULL;

-- Auto-update on row changes
CREATE OR REPLACE FUNCTION update_tenants_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_tenants_updated_at
    BEFORE UPDATE ON tenants
    FOR EACH ROW
    EXECUTE FUNCTION update_tenants_updated_at();

-- Index for delta queries
CREATE INDEX IF NOT EXISTS idx_tenants_updated_at ON tenants (updated_at);
