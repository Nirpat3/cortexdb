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
    Migration(
        version=5,
        description="Superadmin feature tables — copilot, dashboards, edge, integrations, k8s, marketplace, multi-region, plugins, pipelines, vault, templates, voice, white-label, webhooks, zero-trust",
        up_sql="""
-- copilot.py
CREATE TABLE IF NOT EXISTS copilot_sessions (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL DEFAULT 'superadmin',
    title       TEXT,
    messages    TEXT NOT NULL DEFAULT '[]',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_copilot_sessions_user ON copilot_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_copilot_sessions_updated ON copilot_sessions(updated_at DESC);

CREATE TABLE IF NOT EXISTS copilot_suggestions (
    id              TEXT PRIMARY KEY,
    session_id      TEXT,
    suggestion_type TEXT NOT NULL,
    content         TEXT NOT NULL DEFAULT '{}',
    applied         INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES copilot_sessions(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_copilot_suggestions_session ON copilot_suggestions(session_id);

-- custom_dashboards.py
CREATE TABLE IF NOT EXISTS custom_dashboards (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    layout TEXT NOT NULL DEFAULT '{}',
    widgets TEXT NOT NULL DEFAULT '[]',
    theme TEXT NOT NULL DEFAULT '{}',
    owner TEXT NOT NULL DEFAULT 'system',
    shared_with TEXT NOT NULL DEFAULT '[]',
    is_public INTEGER NOT NULL DEFAULT 0,
    refresh_interval INTEGER NOT NULL DEFAULT 30,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_custom_dashboards_owner ON custom_dashboards(owner);
CREATE INDEX IF NOT EXISTS idx_custom_dashboards_public ON custom_dashboards(is_public);

CREATE TABLE IF NOT EXISTS dashboard_widgets (
    id TEXT PRIMARY KEY,
    dashboard_id TEXT NOT NULL,
    widget_type TEXT NOT NULL,
    title TEXT NOT NULL,
    data_source TEXT NOT NULL DEFAULT '',
    query TEXT NOT NULL DEFAULT '',
    config TEXT NOT NULL DEFAULT '{}',
    position TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    FOREIGN KEY (dashboard_id) REFERENCES custom_dashboards(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_dashboard_widgets_did ON dashboard_widgets(dashboard_id);

-- edge_deployment.py
CREATE TABLE IF NOT EXISTS edge_nodes (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    location TEXT NOT NULL,
    region TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'provisioning',
    config TEXT NOT NULL DEFAULT '{}',
    capabilities TEXT NOT NULL DEFAULT '{}',
    last_heartbeat REAL,
    data_synced_at REAL,
    storage_used_mb REAL NOT NULL DEFAULT 0,
    max_storage_mb REAL NOT NULL DEFAULT 1024,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_edge_nodes_status ON edge_nodes(status);
CREATE INDEX IF NOT EXISTS idx_edge_nodes_region ON edge_nodes(region);

CREATE TABLE IF NOT EXISTS edge_sync_log (
    id TEXT PRIMARY KEY,
    node_id TEXT NOT NULL,
    direction TEXT NOT NULL,
    tables_synced TEXT NOT NULL DEFAULT '[]',
    records_count INTEGER NOT NULL DEFAULT 0,
    duration_ms INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pending',
    error TEXT,
    created_at REAL NOT NULL,
    FOREIGN KEY (node_id) REFERENCES edge_nodes(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_edge_sync_node ON edge_sync_log(node_id);
CREATE INDEX IF NOT EXISTS idx_edge_sync_status ON edge_sync_log(status);

-- discord_integration.py
CREATE TABLE IF NOT EXISTS discord_config (
    id TEXT PRIMARY KEY,
    guild_id TEXT,
    bot_token TEXT,
    webhook_url TEXT,
    channel_mappings TEXT DEFAULT '{}',
    command_prefix TEXT DEFAULT '!cortex',
    enabled INTEGER DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS discord_messages (
    id TEXT PRIMARY KEY,
    direction TEXT NOT NULL CHECK(direction IN ('inbound', 'outbound')),
    channel_id TEXT,
    user_id TEXT,
    agent_id TEXT,
    message TEXT NOT NULL,
    command TEXT,
    status TEXT DEFAULT 'pending',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_discord_messages_direction ON discord_messages(direction);
CREATE INDEX IF NOT EXISTS idx_discord_messages_channel ON discord_messages(channel_id);
CREATE INDEX IF NOT EXISTS idx_discord_messages_agent ON discord_messages(agent_id);

-- graphql_gateway.py
CREATE TABLE IF NOT EXISTS graphql_schemas (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    schema_sdl  TEXT NOT NULL,
    config      TEXT NOT NULL DEFAULT '{}',
    enabled     INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_graphql_schemas_enabled ON graphql_schemas(enabled);

CREATE TABLE IF NOT EXISTS graphql_query_log (
    id              TEXT PRIMARY KEY,
    query           TEXT NOT NULL,
    variables       TEXT NOT NULL DEFAULT '{}',
    response_time_ms REAL NOT NULL DEFAULT 0.0,
    status          TEXT NOT NULL DEFAULT 'success',
    error           TEXT,
    created_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_graphql_query_log_created ON graphql_query_log(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_graphql_query_log_status ON graphql_query_log(status);

-- kubernetes_operator.py
CREATE TABLE IF NOT EXISTS k8s_clusters (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    namespace TEXT NOT NULL DEFAULT 'cortexdb',
    kubeconfig_ref TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    node_count INTEGER NOT NULL DEFAULT 0,
    pod_count INTEGER NOT NULL DEFAULT 0,
    config TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_k8s_clusters_status ON k8s_clusters(status);

CREATE TABLE IF NOT EXISTS k8s_deployments (
    id TEXT PRIMARY KEY,
    cluster_id TEXT NOT NULL,
    name TEXT NOT NULL,
    replicas INTEGER NOT NULL DEFAULT 1,
    image TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    config TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    FOREIGN KEY (cluster_id) REFERENCES k8s_clusters(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_k8s_deploy_cluster ON k8s_deployments(cluster_id);

CREATE TABLE IF NOT EXISTS k8s_operations (
    id TEXT PRIMARY KEY,
    cluster_id TEXT NOT NULL,
    operation_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    details TEXT NOT NULL DEFAULT '{}',
    started_at REAL NOT NULL,
    completed_at REAL,
    FOREIGN KEY (cluster_id) REFERENCES k8s_clusters(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_k8s_ops_cluster ON k8s_operations(cluster_id);
CREATE INDEX IF NOT EXISTS idx_k8s_ops_type ON k8s_operations(operation_type);

-- marketplace.py
CREATE TABLE IF NOT EXISTS marketplace_capabilities (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    category    TEXT NOT NULL DEFAULT 'core',
    icon        TEXT NOT NULL DEFAULT 'box',
    version     TEXT NOT NULL DEFAULT '1.0.0',
    enabled     INTEGER NOT NULL DEFAULT 0,
    config      TEXT NOT NULL DEFAULT '{}',
    dependencies TEXT NOT NULL DEFAULT '[]',
    tier        TEXT NOT NULL DEFAULT 'free',
    installed_at TEXT,
    updated_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_marketplace_category ON marketplace_capabilities(category);
CREATE INDEX IF NOT EXISTS idx_marketplace_enabled ON marketplace_capabilities(enabled);

-- multi_region.py
CREATE TABLE IF NOT EXISTS regions (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    endpoint TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'standby',
    is_primary INTEGER NOT NULL DEFAULT 0,
    latency_ms INTEGER NOT NULL DEFAULT 0,
    config TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_regions_status ON regions(status);
CREATE INDEX IF NOT EXISTS idx_regions_primary ON regions(is_primary);

CREATE TABLE IF NOT EXISTS replication_streams (
    id TEXT PRIMARY KEY,
    source_region TEXT NOT NULL,
    target_region TEXT NOT NULL,
    tables TEXT NOT NULL DEFAULT '["*"]',
    status TEXT NOT NULL DEFAULT 'active',
    lag_ms INTEGER NOT NULL DEFAULT 0,
    last_synced REAL,
    config TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    FOREIGN KEY (source_region) REFERENCES regions(id),
    FOREIGN KEY (target_region) REFERENCES regions(id)
);
CREATE INDEX IF NOT EXISTS idx_repl_source ON replication_streams(source_region);
CREATE INDEX IF NOT EXISTS idx_repl_target ON replication_streams(target_region);

CREATE TABLE IF NOT EXISTS replication_conflicts (
    id TEXT PRIMARY KEY,
    stream_id TEXT NOT NULL,
    table_name TEXT NOT NULL,
    record_id TEXT NOT NULL,
    source_value TEXT NOT NULL DEFAULT '{}',
    target_value TEXT NOT NULL DEFAULT '{}',
    resolution TEXT NOT NULL DEFAULT 'unresolved',
    resolved_at REAL,
    created_at REAL NOT NULL,
    FOREIGN KEY (stream_id) REFERENCES replication_streams(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_conflicts_stream ON replication_conflicts(stream_id);
CREATE INDEX IF NOT EXISTS idx_conflicts_resolution ON replication_conflicts(resolution);

CREATE TABLE IF NOT EXISTS failover_log (
    id TEXT PRIMARY KEY,
    from_region TEXT NOT NULL,
    to_region TEXT NOT NULL,
    reason TEXT,
    status TEXT NOT NULL DEFAULT 'completed',
    duration_ms INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_failover_time ON failover_log(created_at);

-- plugin_system.py
CREATE TABLE IF NOT EXISTS installed_plugins (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    version       TEXT NOT NULL,
    description   TEXT DEFAULT '',
    author        TEXT DEFAULT '',
    plugin_type   TEXT NOT NULL CHECK (plugin_type IN ('engine', 'hook', 'middleware')),
    entry_point   TEXT NOT NULL,
    config        TEXT DEFAULT '{}',
    enabled       INTEGER NOT NULL DEFAULT 0,
    installed_at  TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

-- pipeline_builder.py
CREATE TABLE IF NOT EXISTS data_pipelines (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    stages TEXT NOT NULL DEFAULT '[]',
    schedule TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft', 'active', 'paused', 'error')),
    last_run REAL,
    next_run REAL,
    run_count INTEGER NOT NULL DEFAULT 0,
    avg_duration_ms REAL NOT NULL DEFAULT 0,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_data_pipelines_status ON data_pipelines(status);

CREATE TABLE IF NOT EXISTS pipeline_runs (
    id TEXT PRIMARY KEY,
    pipeline_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'running' CHECK(status IN ('running', 'completed', 'failed', 'cancelled')),
    started_at REAL NOT NULL,
    completed_at REAL,
    duration_ms INTEGER,
    stages_completed INTEGER NOT NULL DEFAULT 0,
    total_stages INTEGER NOT NULL DEFAULT 0,
    error TEXT DEFAULT '',
    output TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY (pipeline_id) REFERENCES data_pipelines(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_pipeline_runs_pid ON pipeline_runs(pipeline_id);
CREATE INDEX IF NOT EXISTS idx_pipeline_runs_status ON pipeline_runs(status);

CREATE TABLE IF NOT EXISTS pipeline_stage_types (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    category TEXT NOT NULL CHECK(category IN ('extract', 'transform', 'load')),
    config_schema TEXT NOT NULL DEFAULT '{}',
    icon TEXT DEFAULT ''
);

-- secrets_vault_v2.py
CREATE TABLE IF NOT EXISTS vault_secrets (
    id TEXT PRIMARY KEY,
    path TEXT NOT NULL UNIQUE,
    value_encrypted TEXT NOT NULL,
    metadata TEXT NOT NULL DEFAULT '{}',
    version INTEGER NOT NULL DEFAULT 1,
    lease_duration INTEGER NOT NULL DEFAULT 0,
    lease_expires REAL,
    rotation_policy TEXT NOT NULL DEFAULT '{}',
    created_by TEXT NOT NULL DEFAULT 'system',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_vault_secrets_path ON vault_secrets(path);

CREATE TABLE IF NOT EXISTS vault_access_log (
    id TEXT PRIMARY KEY,
    path TEXT NOT NULL,
    operation TEXT NOT NULL CHECK(operation IN ('read', 'write', 'delete', 'rotate', 'list')),
    accessor TEXT NOT NULL DEFAULT 'system',
    status TEXT NOT NULL DEFAULT 'success',
    timestamp REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_vault_access_ts ON vault_access_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_vault_access_path ON vault_access_log(path);

CREATE TABLE IF NOT EXISTS vault_rotation_schedule (
    id TEXT PRIMARY KEY,
    secret_path TEXT NOT NULL UNIQUE,
    interval_hours INTEGER NOT NULL,
    last_rotated REAL,
    next_rotation REAL,
    rotation_handler TEXT DEFAULT '',
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_vault_rotation_next ON vault_rotation_schedule(next_rotation);

-- teams_integration.py
CREATE TABLE IF NOT EXISTS teams_config (
    id TEXT PRIMARY KEY,
    tenant_id TEXT,
    webhook_url TEXT NOT NULL,
    bot_token TEXT,
    channel_mappings TEXT DEFAULT '{}',
    enabled INTEGER DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS teams_messages (
    id TEXT PRIMARY KEY,
    direction TEXT NOT NULL CHECK(direction IN ('inbound', 'outbound')),
    channel_id TEXT,
    agent_id TEXT,
    message TEXT NOT NULL,
    message_type TEXT DEFAULT 'text',
    status TEXT DEFAULT 'pending',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_teams_messages_direction ON teams_messages(direction);
CREATE INDEX IF NOT EXISTS idx_teams_messages_agent ON teams_messages(agent_id);
CREATE INDEX IF NOT EXISTS idx_teams_messages_created ON teams_messages(created_at);

-- template_marketplace.py
CREATE TABLE IF NOT EXISTS community_templates (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    description     TEXT NOT NULL DEFAULT '',
    author          TEXT NOT NULL DEFAULT 'Anonymous',
    category        TEXT NOT NULL DEFAULT 'general',
    tags            TEXT NOT NULL DEFAULT '[]',
    template_data   TEXT NOT NULL DEFAULT '{}',
    version         TEXT NOT NULL DEFAULT '1.0.0',
    downloads       INTEGER NOT NULL DEFAULT 0,
    rating          REAL NOT NULL DEFAULT 0.0,
    ratings_count   INTEGER NOT NULL DEFAULT 0,
    featured        INTEGER NOT NULL DEFAULT 0,
    published_at    TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_community_templates_category ON community_templates(category);
CREATE INDEX IF NOT EXISTS idx_community_templates_downloads ON community_templates(downloads DESC);

-- voice_interface.py
CREATE TABLE IF NOT EXISTS voice_sessions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL DEFAULT 'superadmin',
    status TEXT NOT NULL DEFAULT 'active',
    config TEXT DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_voice_sessions_user ON voice_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_voice_sessions_status ON voice_sessions(status);

CREATE TABLE IF NOT EXISTS voice_commands (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    transcript TEXT NOT NULL,
    intent TEXT,
    entities TEXT DEFAULT '{}',
    response TEXT,
    audio_url TEXT,
    confidence REAL DEFAULT 0.0,
    processing_time_ms INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES voice_sessions(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_voice_commands_session ON voice_commands(session_id);
CREATE INDEX IF NOT EXISTS idx_voice_commands_intent ON voice_commands(intent);

-- white_label.py
CREATE TABLE IF NOT EXISTS wl_themes (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    colors TEXT NOT NULL DEFAULT '{}',
    typography TEXT NOT NULL DEFAULT '{}',
    logo_url TEXT,
    favicon_url TEXT,
    is_active INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_wl_themes_active ON wl_themes(is_active);

CREATE TABLE IF NOT EXISTS wl_branding (
    id TEXT PRIMARY KEY,
    company_name TEXT NOT NULL DEFAULT 'CortexDB',
    tagline TEXT,
    support_email TEXT,
    support_url TEXT,
    terms_url TEXT,
    privacy_url TEXT,
    custom_domain TEXT,
    custom_css TEXT,
    email_templates TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

-- zapier_connector.py
CREATE TABLE IF NOT EXISTS webhook_endpoints (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    url TEXT NOT NULL,
    secret TEXT,
    event_types TEXT NOT NULL DEFAULT '[]',
    headers TEXT DEFAULT '{}',
    enabled INTEGER DEFAULT 1,
    retry_count INTEGER DEFAULT 3,
    last_triggered TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_webhook_endpoints_enabled ON webhook_endpoints(enabled);

CREATE TABLE IF NOT EXISTS webhook_deliveries (
    id TEXT PRIMARY KEY,
    endpoint_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK(status IN ('pending', 'delivered', 'failed')),
    response_code INTEGER,
    response_body TEXT,
    attempts INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    FOREIGN KEY (endpoint_id) REFERENCES webhook_endpoints(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_webhook_deliveries_endpoint ON webhook_deliveries(endpoint_id);
CREATE INDEX IF NOT EXISTS idx_webhook_deliveries_status ON webhook_deliveries(status);

-- zero_trust.py
CREATE TABLE IF NOT EXISTS zt_policies (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    policy_type TEXT NOT NULL CHECK(policy_type IN ('allow', 'deny', 'require_auth')),
    source_pattern TEXT NOT NULL DEFAULT '*',
    destination_pattern TEXT NOT NULL DEFAULT '*',
    conditions TEXT NOT NULL DEFAULT '{}',
    priority INTEGER NOT NULL DEFAULT 100,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS zt_certificates (
    id TEXT PRIMARY KEY,
    subject TEXT NOT NULL,
    issuer TEXT NOT NULL DEFAULT 'CortexDB-CA',
    serial TEXT NOT NULL UNIQUE,
    fingerprint TEXT NOT NULL UNIQUE,
    not_before REAL NOT NULL,
    not_after REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active', 'revoked', 'expired')),
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS zt_audit_log (
    id TEXT PRIMARY KEY,
    policy_id TEXT,
    source TEXT NOT NULL,
    destination TEXT NOT NULL,
    action TEXT NOT NULL CHECK(action IN ('allow', 'deny')),
    reason TEXT DEFAULT '',
    timestamp REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_zt_policies_priority ON zt_policies(priority);
CREATE INDEX IF NOT EXISTS idx_zt_policies_enabled ON zt_policies(enabled);
CREATE INDEX IF NOT EXISTS idx_zt_certs_status ON zt_certificates(status);
CREATE INDEX IF NOT EXISTS idx_zt_audit_ts ON zt_audit_log(timestamp);
""",
        down_sql="""
DROP TABLE IF EXISTS zt_audit_log;
DROP TABLE IF EXISTS zt_certificates;
DROP TABLE IF EXISTS zt_policies;
DROP TABLE IF EXISTS webhook_deliveries;
DROP TABLE IF EXISTS webhook_endpoints;
DROP TABLE IF EXISTS wl_branding;
DROP TABLE IF EXISTS wl_themes;
DROP TABLE IF EXISTS voice_commands;
DROP TABLE IF EXISTS voice_sessions;
DROP TABLE IF EXISTS community_templates;
DROP TABLE IF EXISTS teams_messages;
DROP TABLE IF EXISTS teams_config;
DROP TABLE IF EXISTS vault_rotation_schedule;
DROP TABLE IF EXISTS vault_access_log;
DROP TABLE IF EXISTS vault_secrets;
DROP TABLE IF EXISTS pipeline_stage_types;
DROP TABLE IF EXISTS pipeline_runs;
DROP TABLE IF EXISTS data_pipelines;
DROP TABLE IF EXISTS installed_plugins;
DROP TABLE IF EXISTS failover_log;
DROP TABLE IF EXISTS replication_conflicts;
DROP TABLE IF EXISTS replication_streams;
DROP TABLE IF EXISTS regions;
DROP TABLE IF EXISTS marketplace_capabilities;
DROP TABLE IF EXISTS k8s_operations;
DROP TABLE IF EXISTS k8s_deployments;
DROP TABLE IF EXISTS k8s_clusters;
DROP TABLE IF EXISTS graphql_query_log;
DROP TABLE IF EXISTS graphql_schemas;
DROP TABLE IF EXISTS discord_messages;
DROP TABLE IF EXISTS discord_config;
DROP TABLE IF EXISTS edge_sync_log;
DROP TABLE IF EXISTS edge_nodes;
DROP TABLE IF EXISTS dashboard_widgets;
DROP TABLE IF EXISTS custom_dashboards;
DROP TABLE IF EXISTS copilot_suggestions;
DROP TABLE IF EXISTS copilot_sessions;
""",
    ),
    Migration(
        version=6,
        description="Sentinel module tables — campaigns, runs, findings, posture, remediation, knowledge base, threat intel",
        up_sql="""
-- sentinel/planner.py
CREATE TABLE IF NOT EXISTS sentinel_campaigns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'draft'
        CHECK(status IN ('draft', 'planned', 'running', 'completed', 'cancelled', 'failed')),
    target_categories TEXT NOT NULL DEFAULT '[]',
    target_endpoints TEXT NOT NULL DEFAULT '[]',
    schedule TEXT NOT NULL DEFAULT '{}',
    config TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL,
    started_at REAL,
    completed_at REAL,
    created_by TEXT DEFAULT 'system'
);
CREATE INDEX IF NOT EXISTS idx_sentinel_campaigns_status ON sentinel_campaigns(status);
CREATE INDEX IF NOT EXISTS idx_sentinel_campaigns_created ON sentinel_campaigns(created_at);

-- sentinel/executor.py
CREATE TABLE IF NOT EXISTS sentinel_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL UNIQUE,
    campaign_id TEXT,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK(status IN ('pending','running','completed','failed','aborted')),
    phase TEXT DEFAULT NULL,
    total_tests INTEGER NOT NULL DEFAULT 0,
    passed INTEGER NOT NULL DEFAULT 0,
    failed INTEGER NOT NULL DEFAULT 0,
    vulnerabilities_found INTEGER NOT NULL DEFAULT 0,
    started_at REAL,
    completed_at REAL,
    summary TEXT DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_sr_run_id ON sentinel_runs(run_id);
CREATE INDEX IF NOT EXISTS idx_sr_campaign ON sentinel_runs(campaign_id);
CREATE INDEX IF NOT EXISTS idx_sr_status ON sentinel_runs(status);

CREATE TABLE IF NOT EXISTS sentinel_findings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    finding_id TEXT NOT NULL UNIQUE,
    run_id TEXT NOT NULL,
    campaign_id TEXT,
    attack_id TEXT,
    category TEXT,
    severity TEXT DEFAULT 'info'
        CHECK(severity IN ('critical','high','medium','low','info')),
    endpoint TEXT,
    method TEXT DEFAULT 'GET',
    payload TEXT,
    request_headers TEXT DEFAULT '{}',
    response_status INTEGER,
    response_body_snippet TEXT,
    response_time_ms REAL,
    vulnerable INTEGER NOT NULL DEFAULT 0,
    evidence TEXT DEFAULT '{}',
    remediation TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'open'
        CHECK(status IN ('open','confirmed','false_positive','remediated','accepted')),
    found_at REAL NOT NULL,
    remediated_at REAL
);
CREATE INDEX IF NOT EXISTS idx_sf_run_id ON sentinel_findings(run_id);
CREATE INDEX IF NOT EXISTS idx_sf_category ON sentinel_findings(category);
CREATE INDEX IF NOT EXISTS idx_sf_severity ON sentinel_findings(severity);
CREATE INDEX IF NOT EXISTS idx_sf_vulnerable ON sentinel_findings(vulnerable);

-- sentinel/analyzer.py
CREATE TABLE IF NOT EXISTS sentinel_posture (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id TEXT NOT NULL UNIQUE,
    overall_score REAL NOT NULL,
    category_scores TEXT NOT NULL DEFAULT '{}',
    total_tests INTEGER NOT NULL DEFAULT 0,
    total_pass INTEGER NOT NULL DEFAULT 0,
    total_fail INTEGER NOT NULL DEFAULT 0,
    critical_findings INTEGER NOT NULL DEFAULT 0,
    high_findings INTEGER NOT NULL DEFAULT 0,
    medium_findings INTEGER NOT NULL DEFAULT 0,
    low_findings INTEGER NOT NULL DEFAULT 0,
    trend TEXT NOT NULL DEFAULT 'stable',
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sentinel_posture_created ON sentinel_posture(created_at);

CREATE TABLE IF NOT EXISTS sentinel_remediation (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_id TEXT NOT NULL UNIQUE,
    finding_id TEXT DEFAULT '',
    title TEXT NOT NULL,
    description TEXT DEFAULT '',
    priority TEXT NOT NULL DEFAULT 'medium'
        CHECK(priority IN ('critical', 'high', 'medium', 'low')),
    effort_estimate TEXT NOT NULL DEFAULT 'medium'
        CHECK(effort_estimate IN ('low', 'medium', 'high')),
    steps TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'open'
        CHECK(status IN ('open', 'in_progress', 'completed', 'dismissed')),
    assigned_to TEXT DEFAULT '',
    created_at REAL NOT NULL,
    completed_at REAL
);
CREATE INDEX IF NOT EXISTS idx_sentinel_remediation_status ON sentinel_remediation(status);
CREATE INDEX IF NOT EXISTS idx_sentinel_remediation_priority ON sentinel_remediation(priority);

-- sentinel/knowledge_base.py
CREATE TABLE IF NOT EXISTS sentinel_kb (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    attack_id TEXT UNIQUE,
    category TEXT,
    name TEXT,
    description TEXT,
    severity TEXT,
    framework TEXT,
    framework_id TEXT,
    payloads TEXT,
    indicators TEXT,
    remediation TEXT,
    enabled INTEGER DEFAULT 1,
    created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_sentinel_kb_category ON sentinel_kb(category);
CREATE INDEX IF NOT EXISTS idx_sentinel_kb_severity ON sentinel_kb(severity);
CREATE INDEX IF NOT EXISTS idx_sentinel_kb_enabled ON sentinel_kb(enabled);

CREATE TABLE IF NOT EXISTS sentinel_threat_intel (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    intel_id TEXT UNIQUE,
    source TEXT,
    cve_id TEXT,
    title TEXT,
    description TEXT,
    severity TEXT,
    affected_component TEXT,
    applicable INTEGER DEFAULT 0,
    mitigation TEXT,
    created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_sentinel_ti_severity ON sentinel_threat_intel(severity);
CREATE INDEX IF NOT EXISTS idx_sentinel_ti_component ON sentinel_threat_intel(affected_component);
""",
        down_sql="""
DROP TABLE IF EXISTS sentinel_threat_intel;
DROP TABLE IF EXISTS sentinel_kb;
DROP TABLE IF EXISTS sentinel_remediation;
DROP TABLE IF EXISTS sentinel_posture;
DROP TABLE IF EXISTS sentinel_findings;
DROP TABLE IF EXISTS sentinel_runs;
DROP TABLE IF EXISTS sentinel_campaigns;
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
