-- ============================================================
-- Rollback for 005_add_model_config.sql
-- Drops the model_configurations table.
-- ============================================================

DROP TABLE IF EXISTS model_configurations CASCADE;
