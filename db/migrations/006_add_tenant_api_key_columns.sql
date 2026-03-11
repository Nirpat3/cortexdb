-- Add salted API key hashing columns to tenants
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS api_key_salt VARCHAR(32) DEFAULT '';
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS api_key_prefix VARCHAR(8) DEFAULT '';
CREATE INDEX IF NOT EXISTS idx_tenants_api_key_prefix ON tenants(api_key_prefix);
