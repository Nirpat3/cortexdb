"""
Schema Migration System for CortexDB SuperAdmin.

Manages incremental, versioned schema changes for the SQLite persistence layer.
Each migration has an 'up' SQL script and optional 'down' rollback.
Migrations run in order and are tracked in the schema_version table.
"""

import time
import logging
import sqlite3
from typing import List, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class Migration:
    version: int
    description: str
    up_sql: str
    down_sql: str = ""


# ── Migration Registry ──────────────────────────────────
# Add new migrations at the end. Never modify existing ones.

MIGRATIONS: List[Migration] = [
    Migration(
        version=1,
        description="Initial schema — agents, tasks, instructions, messages, audit, counters, kv, provider_config",
        up_sql="""
CREATE TABLE IF NOT EXISTS agents (
    agent_id TEXT PRIMARY KEY,
    data TEXT NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks (
    task_id TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'pending',
    priority TEXT NOT NULL DEFAULT 'medium',
    assigned_to TEXT,
    data TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_assigned ON tasks(assigned_to);

CREATE TABLE IF NOT EXISTS instructions (
    instruction_id TEXT PRIMARY KEY,
    agent_id TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    data TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_instructions_agent ON instructions(agent_id);

CREATE TABLE IF NOT EXISTS messages (
    message_id TEXT PRIMARY KEY,
    msg_type TEXT NOT NULL,
    from_agent TEXT NOT NULL,
    to_agent TEXT,
    department TEXT,
    status TEXT NOT NULL DEFAULT 'sent',
    data TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_to ON messages(to_agent);
CREATE INDEX IF NOT EXISTS idx_messages_type ON messages(msg_type);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp REAL NOT NULL,
    action TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    actor TEXT NOT NULL DEFAULT 'superadmin',
    details TEXT
);
CREATE INDEX IF NOT EXISTS idx_audit_entity ON audit_log(entity_type);
CREATE INDEX IF NOT EXISTS idx_audit_time ON audit_log(timestamp);

CREATE TABLE IF NOT EXISTS counters (
    name TEXT PRIMARY KEY,
    value INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS provider_config (
    provider TEXT PRIMARY KEY,
    data TEXT NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS kv_store (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at REAL NOT NULL
);
""",
    ),
    Migration(
        version=2,
        description="Add sessions table for persistent superadmin sessions",
        up_sql="""
CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    created_at REAL NOT NULL,
    last_active REAL NOT NULL,
    ip_address TEXT,
    active INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_sessions_active ON sessions(active);
""",
        down_sql="DROP TABLE IF EXISTS sessions;",
    ),
    Migration(
        version=3,
        description="Add execution_log for task executor history",
        up_sql="""
CREATE TABLE IF NOT EXISTS execution_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT,
    status TEXT NOT NULL,
    elapsed_ms REAL,
    tokens_used INTEGER,
    result_preview TEXT,
    executed_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_exec_task ON execution_log(task_id);
CREATE INDEX IF NOT EXISTS idx_exec_agent ON execution_log(agent_id);
CREATE INDEX IF NOT EXISTS idx_exec_time ON execution_log(executed_at);
""",
        down_sql="DROP TABLE IF EXISTS execution_log;",
    ),
    Migration(
        version=4,
        description="Phase 10 — Knowledge Network + Simulation Sandbox tables",
        up_sql="""
CREATE TABLE IF NOT EXISTS knowledge_nodes (
    node_id TEXT PRIMARY KEY,
    node_type TEXT NOT NULL DEFAULT 'insight',
    topic TEXT NOT NULL,
    content TEXT NOT NULL,
    source_agent TEXT,
    department TEXT,
    confidence REAL NOT NULL DEFAULT 0.5,
    metadata TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_kn_topic ON knowledge_nodes(topic);
CREATE INDEX IF NOT EXISTS idx_kn_agent ON knowledge_nodes(source_agent);
CREATE INDEX IF NOT EXISTS idx_kn_dept ON knowledge_nodes(department);
CREATE INDEX IF NOT EXISTS idx_kn_type ON knowledge_nodes(node_type);

CREATE TABLE IF NOT EXISTS knowledge_edges (
    edge_id TEXT PRIMARY KEY,
    from_node TEXT NOT NULL,
    to_node TEXT NOT NULL,
    relation TEXT NOT NULL,
    weight REAL NOT NULL DEFAULT 1.0,
    metadata TEXT,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ke_from ON knowledge_edges(from_node);
CREATE INDEX IF NOT EXISTS idx_ke_to ON knowledge_edges(to_node);
CREATE INDEX IF NOT EXISTS idx_ke_rel ON knowledge_edges(relation);

CREATE TABLE IF NOT EXISTS knowledge_propagations (
    propagation_id TEXT PRIMARY KEY,
    source_agent TEXT NOT NULL,
    target_agent TEXT NOT NULL,
    node_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    relevance_score REAL NOT NULL DEFAULT 0.0,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_kp_target ON knowledge_propagations(target_agent);
CREATE INDEX IF NOT EXISTS idx_kp_status ON knowledge_propagations(status);

CREATE TABLE IF NOT EXISTS context_pools (
    pool_id TEXT PRIMARY KEY,
    department TEXT NOT NULL,
    pool_type TEXT NOT NULL DEFAULT 'general',
    data TEXT NOT NULL DEFAULT '[]',
    contributors TEXT NOT NULL DEFAULT '[]',
    updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cp_dept ON context_pools(department);

CREATE TABLE IF NOT EXISTS simulations (
    sim_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    sim_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'created',
    config TEXT NOT NULL DEFAULT '{}',
    results TEXT NOT NULL DEFAULT '{}',
    created_by TEXT NOT NULL DEFAULT 'superadmin',
    created_at REAL NOT NULL,
    completed_at REAL
);
CREATE INDEX IF NOT EXISTS idx_sim_status ON simulations(status);
CREATE INDEX IF NOT EXISTS idx_sim_type ON simulations(sim_type);

CREATE TABLE IF NOT EXISTS sim_agent_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    sim_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    state_data TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_snap_sim ON sim_agent_snapshots(sim_id);

CREATE TABLE IF NOT EXISTS behavior_test_suites (
    suite_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    test_cases TEXT NOT NULL DEFAULT '[]',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS behavior_test_runs (
    run_id TEXT PRIMARY KEY,
    suite_id TEXT NOT NULL,
    sim_id TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    results TEXT NOT NULL DEFAULT '{}',
    started_at REAL NOT NULL,
    completed_at REAL
);
CREATE INDEX IF NOT EXISTS idx_btr_suite ON behavior_test_runs(suite_id);

CREATE TABLE IF NOT EXISTS ab_experiments (
    experiment_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'created',
    variant_a TEXT NOT NULL DEFAULT '{}',
    variant_b TEXT NOT NULL DEFAULT '{}',
    agent_ids TEXT NOT NULL DEFAULT '[]',
    results TEXT NOT NULL DEFAULT '{}',
    config TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL,
    completed_at REAL
);
CREATE INDEX IF NOT EXISTS idx_ab_status ON ab_experiments(status);

CREATE TABLE IF NOT EXISTS chaos_events (
    event_id TEXT PRIMARY KEY,
    sim_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    target TEXT NOT NULL,
    config TEXT NOT NULL DEFAULT '{}',
    injected_at REAL NOT NULL,
    resolved_at REAL,
    observations TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_chaos_sim ON chaos_events(sim_id);
""",
        down_sql="""
DROP TABLE IF EXISTS chaos_events;
DROP TABLE IF EXISTS ab_experiments;
DROP TABLE IF EXISTS behavior_test_runs;
DROP TABLE IF EXISTS behavior_test_suites;
DROP TABLE IF EXISTS sim_agent_snapshots;
DROP TABLE IF EXISTS simulations;
DROP TABLE IF EXISTS context_pools;
DROP TABLE IF EXISTS knowledge_propagations;
DROP TABLE IF EXISTS knowledge_edges;
DROP TABLE IF EXISTS knowledge_nodes;
""",
    ),
]


class MigrationRunner:
    """Runs schema migrations against a SQLite connection."""

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def get_current_version(self) -> int:
        """Get the latest applied migration version."""
        try:
            row = self._conn.execute(
                "SELECT MAX(version) as v FROM schema_version"
            ).fetchone()
            return row[0] if row and row[0] else 0
        except sqlite3.OperationalError:
            return 0

    def get_pending(self) -> List[Migration]:
        """List migrations that haven't been applied yet."""
        current = self.get_current_version()
        return [m for m in MIGRATIONS if m.version > current]

    def migrate(self) -> int:
        """Run all pending migrations. Returns count of migrations applied."""
        pending = self.get_pending()
        if not pending:
            logger.info("Schema up to date (v%d)", self.get_current_version())
            return 0

        applied = 0
        for migration in pending:
            logger.info(
                "Applying migration v%d: %s", migration.version, migration.description
            )
            try:
                self._conn.executescript(migration.up_sql)
                self._conn.execute(
                    "INSERT OR REPLACE INTO schema_version (version, applied_at) VALUES (?, ?)",
                    (migration.version, time.time()),
                )
                self._conn.commit()
                applied += 1
                logger.info("Migration v%d applied successfully", migration.version)
            except Exception as e:
                logger.error("Migration v%d FAILED: %s", migration.version, e)
                raise

        logger.info(
            "Migrations complete: %d applied, now at v%d",
            applied, self.get_current_version(),
        )
        return applied

    def rollback(self, target_version: int = 0) -> int:
        """Roll back to a target version. Returns count of migrations rolled back."""
        current = self.get_current_version()
        if current <= target_version:
            return 0

        # Get migrations to roll back in reverse order
        to_rollback = sorted(
            [m for m in MIGRATIONS if target_version < m.version <= current],
            key=lambda m: m.version,
            reverse=True,
        )

        rolled = 0
        for migration in to_rollback:
            if not migration.down_sql:
                logger.warning(
                    "Migration v%d has no rollback SQL — skipping", migration.version
                )
                continue
            logger.info("Rolling back v%d: %s", migration.version, migration.description)
            try:
                self._conn.executescript(migration.down_sql)
                self._conn.execute(
                    "DELETE FROM schema_version WHERE version = ?", (migration.version,)
                )
                self._conn.commit()
                rolled += 1
            except Exception as e:
                logger.error("Rollback v%d FAILED: %s", migration.version, e)
                raise

        return rolled

    def get_history(self) -> List[dict]:
        """Get applied migration history."""
        try:
            rows = self._conn.execute(
                "SELECT version, applied_at FROM schema_version ORDER BY version"
            ).fetchall()
            result = []
            for row in rows:
                ver = row[0]
                mig = next((m for m in MIGRATIONS if m.version == ver), None)
                result.append({
                    "version": ver,
                    "applied_at": row[1],
                    "description": mig.description if mig else "Unknown",
                })
            return result
        except sqlite3.OperationalError:
            return []
