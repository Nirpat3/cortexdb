DROP INDEX IF EXISTS idx_tenants_api_key_prefix;
ALTER TABLE tenants DROP COLUMN IF EXISTS api_key_prefix;
ALTER TABLE tenants DROP COLUMN IF EXISTS api_key_salt;
