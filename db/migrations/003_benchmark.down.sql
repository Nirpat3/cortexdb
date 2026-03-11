-- ============================================================
-- Rollback for 003_benchmark.sql
-- Drops benchmark scratch tables and their indexes.
-- ============================================================

DROP TABLE IF EXISTS benchmark_audit CASCADE;
DROP TABLE IF EXISTS benchmark_ledger CASCADE;
DROP TABLE IF EXISTS benchmark_scratch CASCADE;
