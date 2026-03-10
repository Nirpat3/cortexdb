-- ============================================================================
-- Migration 004: Migration Tracking (Bootstrap)
-- ============================================================================
-- This migration is self-referential: it creates the schema_migrations table
-- that the Migrator uses to track which migrations have been applied.
-- The Migrator also creates this table via CREATE IF NOT EXISTS before scanning,
-- so this file serves as the canonical DDL and ensures the table is recorded
-- as a tracked migration itself.
-- ============================================================================

CREATE TABLE IF NOT EXISTS schema_migrations (
    version     INT PRIMARY KEY,
    name        VARCHAR(255) NOT NULL,
    applied_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    checksum    VARCHAR(64) NOT NULL
);

COMMENT ON TABLE schema_migrations IS
    'Tracks applied database migrations. Managed by cortexdb.core.migrator.Migrator.';
