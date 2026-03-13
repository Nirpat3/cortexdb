DROP TRIGGER IF EXISTS trg_tenants_updated_at ON tenants;
DROP FUNCTION IF EXISTS update_tenants_updated_at();
DROP INDEX IF EXISTS idx_tenants_updated_at;
ALTER TABLE tenants DROP COLUMN IF EXISTS updated_at;
