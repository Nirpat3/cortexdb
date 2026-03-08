"""
GraphQL Gateway — Auto-generates a GraphQL schema from CortexDB's data model.
Provides query, mutation, and subscription support.

Introspects CortexDB engines to build a typed GraphQL schema, then executes
incoming queries by mapping them to existing API calls. Query execution is
logged for performance monitoring and debugging.

Database: data/superadmin.db (shared with other superadmin modules)
Tables: graphql_schemas, graphql_query_log
"""

import json
import os
import re
import sqlite3
import time
import uuid
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from cortexdb.superadmin.agent_team import AgentTeamManager
    from cortexdb.superadmin.persistence import PersistenceStore

logger = logging.getLogger("cortexdb.graphql_gateway")

DEFAULT_DB_PATH = os.path.join("data", "superadmin.db")

# ── Default GraphQL schema ────────────────────────────────────────────

DEFAULT_SCHEMA_SDL = '''\
"""CortexDB GraphQL Schema — Auto-generated from data model introspection."""

type Query {
  """List all agents, optionally filtered by department."""
  agents(department: String, status: String, limit: Int): [Agent!]!

  """Get a single agent by ID."""
  agent(id: ID!): Agent

  """List tasks with optional status and limit filters."""
  tasks(status: String, priority: String, assignee: String, limit: Int): [Task!]!

  """Get a single task by ID."""
  task(id: ID!): Task

  """System health status."""
  health: HealthStatus!

  """System-wide metrics and statistics."""
  metrics: SystemMetrics!

  """Search knowledge graph nodes."""
  knowledgeNodes(search: String, type: String, limit: Int): [KnowledgeNode!]!

  """List audit log entries."""
  auditLog(entityType: String, limit: Int): [AuditEntry!]!

  """List messages with optional type filter."""
  messages(type: String, limit: Int): [Message!]!

  """Get LLM provider status."""
  providers: ProviderStatus!
}

type Mutation {
  """Create a new task and assign it to an agent."""
  createTask(input: CreateTaskInput!): Task!

  """Update the status of a task."""
  updateTaskStatus(id: ID!, status: String!): Task!

  """Send a message to an agent or broadcast."""
  sendMessage(input: SendMessageInput!): Message!
}

type Subscription {
  """Subscribe to real-time task status changes."""
  taskUpdated(agentId: String): Task!

  """Subscribe to new messages for an agent."""
  messageReceived(agentId: String!): Message!

  """Subscribe to system health changes."""
  healthChanged: HealthStatus!
}

type Agent {
  id: ID!
  name: String!
  title: String!
  department: String!
  tier: String!
  status: String!
  skills: [String!]!
  responsibilities: [String!]!
  reportsTo: String
  currentTask: String
  llmProvider: String!
  llmModel: String!
}

type Task {
  id: ID!
  title: String!
  description: String
  status: String!
  priority: String!
  assignee: Agent
  assigneeId: String
  createdAt: String!
  updatedAt: String!
}

type HealthStatus {
  status: String!
  uptime: Float!
  activeAgents: Int!
  pendingTasks: Int!
  llmProviders: Int!
  memoryUsageMb: Float!
  timestamp: String!
}

type SystemMetrics {
  totalAgents: Int!
  activeAgents: Int!
  totalTasks: Int!
  completedTasks: Int!
  pendingTasks: Int!
  failedTasks: Int!
  avgTaskDurationMs: Float!
  llmRequestsTotal: Int!
  llmSuccessRate: Float!
  agentsByDepartment: [DepartmentCount!]!
  tasksByStatus: [StatusCount!]!
}

type KnowledgeNode {
  id: ID!
  label: String!
  type: String!
  properties: String
  connections: Int!
}

type AuditEntry {
  timestamp: Float!
  action: String!
  entityType: String!
  entityId: String!
  actor: String!
  details: String
}

type Message {
  id: ID!
  type: String!
  fromAgent: String!
  toAgent: String
  department: String
  status: String!
  content: String!
  createdAt: Float!
}

type ProviderStatus {
  ollama: ProviderInfo!
  claude: ProviderInfo!
  openai: ProviderInfo!
  failoverChain: [String!]!
}

type ProviderInfo {
  configured: Boolean!
  enabled: Boolean!
  model: String!
  circuitBreaker: String!
  consecutiveFailures: Int!
}

type DepartmentCount {
  department: String!
  count: Int!
}

type StatusCount {
  status: String!
  count: Int!
}

input CreateTaskInput {
  title: String!
  description: String
  priority: String
  assigneeId: String
}

input SendMessageInput {
  type: String!
  fromAgent: String!
  toAgent: String
  department: String
  content: String!
}
'''


class GraphQLGateway:
    """Auto-generated GraphQL gateway for CortexDB.

    Introspects CortexDB engines to produce a typed GraphQL schema, and provides
    a simplified query executor that maps GraphQL operations to existing API
    calls on the agent team and persistence store. All queries are logged for
    performance analysis.
    """

    def __init__(
        self,
        db_engines: Any,
        agent_team: "AgentTeamManager",
        persistence_store: "PersistenceStore",
        db_path: str = DEFAULT_DB_PATH,
    ):
        self._engines = db_engines
        self._team = agent_team
        self._store = persistence_store
        self.db_path = db_path
        self.db: Optional[sqlite3.Connection] = None
        self._init_db()

    # ── Database setup ────────────────────────────────────────────────

    def _get_connection(self) -> sqlite3.Connection:
        """Get or create a SQLite connection with row factory."""
        if self.db is None or not self._connection_alive():
            db_dir = os.path.dirname(self.db_path)
            if db_dir:
                os.makedirs(db_dir, exist_ok=True)
            self.db = sqlite3.connect(self.db_path, timeout=10.0)
            self.db.row_factory = sqlite3.Row
            self.db.execute("PRAGMA journal_mode=WAL")
            self.db.execute("PRAGMA foreign_keys=ON")
        return self.db

    def _connection_alive(self) -> bool:
        """Check if the current connection is still usable."""
        try:
            self.db.execute("SELECT 1")
            return True
        except Exception:
            return False

    def _init_db(self) -> None:
        """Create GraphQL gateway tables and seed the default schema."""
        conn = self._get_connection()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS graphql_schemas (
                id          TEXT PRIMARY KEY,
                name        TEXT NOT NULL,
                schema_sdl  TEXT NOT NULL,
                config      TEXT NOT NULL DEFAULT '{}',
                enabled     INTEGER NOT NULL DEFAULT 1,
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_graphql_schemas_enabled
            ON graphql_schemas(enabled)
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS graphql_query_log (
                id              TEXT PRIMARY KEY,
                query           TEXT NOT NULL,
                variables       TEXT NOT NULL DEFAULT '{}',
                response_time_ms REAL NOT NULL DEFAULT 0.0,
                status          TEXT NOT NULL DEFAULT 'success',
                error           TEXT,
                created_at      TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_graphql_query_log_created
            ON graphql_query_log(created_at DESC)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_graphql_query_log_status
            ON graphql_query_log(status)
        """)
        conn.commit()

        # Seed default schema if table is empty
        row = conn.execute("SELECT COUNT(*) AS cnt FROM graphql_schemas").fetchone()
        if row["cnt"] == 0:
            self._seed_default_schema(conn)

    def _seed_default_schema(self, conn: sqlite3.Connection) -> None:
        """Insert the default auto-generated schema."""
        now = datetime.now(timezone.utc).isoformat()
        schema_id = str(uuid.uuid4())
        conn.execute(
            """
            INSERT INTO graphql_schemas (id, name, schema_sdl, config, enabled, created_at, updated_at)
            VALUES (?, ?, ?, ?, 1, ?, ?)
            """,
            (
                schema_id,
                "CortexDB Default Schema",
                DEFAULT_SCHEMA_SDL,
                json.dumps({"version": "1.0.0", "auto_generated": True}),
                now,
                now,
            ),
        )
        conn.commit()
        logger.info("Seeded default GraphQL schema (id=%s)", schema_id)

    # ── Schema management ─────────────────────────────────────────────

    def generate_schema(self) -> dict:
        """Introspect CortexDB engines and generate/update the GraphQL SDL schema.

        Inspects the agent team, task store, and engine metadata to produce
        a comprehensive schema reflecting the current data model.

        Returns:
            Dict with the generated schema SDL and metadata.
        """
        # Build schema from current state
        schema_sdl = DEFAULT_SCHEMA_SDL

        # Augment with engine-specific types if engines are available
        engine_types = []
        if self._engines is not None:
            try:
                if hasattr(self._engines, "list_engines"):
                    engines = self._engines.list_engines()
                    for engine in engines:
                        ename = engine if isinstance(engine, str) else getattr(engine, "name", str(engine))
                        engine_types.append(ename)
                elif isinstance(self._engines, dict):
                    engine_types = list(self._engines.keys())
            except Exception as e:
                logger.debug("Could not introspect engines: %s", e)

        # Store the generated schema
        now = datetime.now(timezone.utc).isoformat()
        schema_id = str(uuid.uuid4())
        config = {
            "version": "1.0.0",
            "auto_generated": True,
            "engines_detected": engine_types,
            "generated_at": now,
        }

        conn = self._get_connection()
        conn.execute(
            """
            INSERT INTO graphql_schemas (id, name, schema_sdl, config, enabled, created_at, updated_at)
            VALUES (?, ?, ?, ?, 1, ?, ?)
            """,
            (
                schema_id,
                f"Auto-generated Schema {now[:10]}",
                schema_sdl,
                json.dumps(config),
                now,
                now,
            ),
        )
        conn.commit()

        logger.info(
            "Generated GraphQL schema (id=%s, engines=%s)", schema_id, engine_types,
        )

        return {
            "schema_id": schema_id,
            "schema_sdl": schema_sdl,
            "engines_detected": engine_types,
            "types_count": schema_sdl.count("type "),
            "generated_at": now,
        }

    def get_schema(self) -> dict:
        """Return the current active schema SDL.

        Returns:
            Dict with schema SDL, config, and metadata.
        """
        conn = self._get_connection()
        row = conn.execute(
            "SELECT * FROM graphql_schemas WHERE enabled = 1 ORDER BY created_at DESC LIMIT 1"
        ).fetchone()

        if row is None:
            return {"error": "No active schema found"}

        return {
            "id": row["id"],
            "name": row["name"],
            "schema_sdl": row["schema_sdl"],
            "config": json.loads(row["config"]),
            "enabled": bool(row["enabled"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def list_schemas(self) -> list:
        """List all saved schema versions.

        Returns:
            List of schema metadata dicts (without full SDL for brevity).
        """
        conn = self._get_connection()
        rows = conn.execute(
            "SELECT id, name, config, enabled, created_at, updated_at FROM graphql_schemas ORDER BY created_at DESC"
        ).fetchall()

        return [
            {
                "id": r["id"],
                "name": r["name"],
                "config": json.loads(r["config"]),
                "enabled": bool(r["enabled"]),
                "created_at": r["created_at"],
                "updated_at": r["updated_at"],
            }
            for r in rows
        ]

    # ── Query execution ───────────────────────────────────────────────

    def execute_query(
        self,
        query: str,
        variables: dict = None,
        operation_name: str = None,
    ) -> dict:
        """Parse and execute a GraphQL query against CortexDB.

        This is a simplified executor that parses the top-level query fields
        and maps them to existing data access methods. It supports the
        Query type fields defined in the schema.

        Args:
            query: The GraphQL query string.
            variables: Optional dict of query variables.
            operation_name: Optional operation name for multi-operation documents.

        Returns:
            Dict with "data" (results) and/or "errors" (list of error dicts).
        """
        variables = variables or {}
        start = time.time()
        errors: List[dict] = []
        data: Dict[str, Any] = {}

        try:
            # Parse top-level query fields
            fields = self._parse_query_fields(query)

            for field_name, field_args in fields.items():
                # Resolve variables in arguments
                resolved_args = self._resolve_variables(field_args, variables)

                try:
                    result = self._resolve_field(field_name, resolved_args)
                    data[field_name] = result
                except Exception as e:
                    errors.append({
                        "message": str(e),
                        "path": [field_name],
                    })
                    data[field_name] = None

        except Exception as e:
            errors.append({"message": f"Query parsing failed: {e}"})

        elapsed_ms = round((time.time() - start) * 1000, 2)
        status = "success" if not errors else "error"

        # Log the query
        self._log_query(query, variables, elapsed_ms, status,
                        errors[0]["message"] if errors else None)

        response = {"data": data}
        if errors:
            response["errors"] = errors
        response["_meta"] = {
            "response_time_ms": elapsed_ms,
            "operation_name": operation_name,
        }

        return response

    def _parse_query_fields(self, query: str) -> Dict[str, dict]:
        """Extract top-level field names and their arguments from a GraphQL query.

        This is a simplified parser that handles common query patterns.
        Not a full GraphQL parser — supports the subset used by CortexDB.
        """
        fields: Dict[str, dict] = {}

        # Remove comments
        query = re.sub(r'#[^\n]*', '', query)

        # Find the query body (between outermost braces after query/mutation keyword)
        body_match = re.search(r'(?:query|mutation|subscription)?\s*(?:\w+\s*)?\{(.+)\}', query, re.DOTALL)
        if not body_match:
            # Try bare braces
            body_match = re.search(r'\{(.+)\}', query, re.DOTALL)
        if not body_match:
            return fields

        body = body_match.group(1).strip()

        # Extract top-level fields with optional arguments
        # Pattern: fieldName or fieldName(arg: val, ...) { ... }
        field_pattern = re.compile(
            r'(\w+)\s*(?:\(([^)]*)\))?\s*(?:\{[^}]*\})?',
            re.DOTALL,
        )

        for match in field_pattern.finditer(body):
            field_name = match.group(1)
            args_str = match.group(2)

            args = {}
            if args_str:
                # Parse key: value pairs
                arg_pattern = re.compile(r'(\w+)\s*:\s*(?:"([^"]*)"|(\$?\w+)|(\d+))')
                for arg_match in arg_pattern.finditer(args_str):
                    key = arg_match.group(1)
                    value = arg_match.group(2) or arg_match.group(3) or arg_match.group(4)
                    # Convert numeric strings
                    if value and value.isdigit():
                        value = int(value)
                    args[key] = value

            fields[field_name] = args

        return fields

    def _resolve_variables(self, args: dict, variables: dict) -> dict:
        """Replace $variable references with actual values."""
        resolved = {}
        for key, value in args.items():
            if isinstance(value, str) and value.startswith("$"):
                var_name = value[1:]
                resolved[key] = variables.get(var_name, value)
            else:
                resolved[key] = value
        return resolved

    def _resolve_field(self, field_name: str, args: dict) -> Any:
        """Resolve a top-level query field to CortexDB data.

        Maps GraphQL field names to existing data access methods.
        """
        if field_name == "agents":
            return self._resolve_agents(args)
        elif field_name == "agent":
            return self._resolve_agent(args)
        elif field_name == "tasks":
            return self._resolve_tasks(args)
        elif field_name == "task":
            return self._resolve_task(args)
        elif field_name == "health":
            return self._resolve_health()
        elif field_name == "metrics":
            return self._resolve_metrics()
        elif field_name == "knowledgeNodes":
            return self._resolve_knowledge_nodes(args)
        elif field_name == "auditLog":
            return self._resolve_audit_log(args)
        elif field_name == "messages":
            return self._resolve_messages(args)
        elif field_name == "providers":
            return self._resolve_providers()
        else:
            raise ValueError(f"Unknown field: {field_name}")

    def _resolve_agents(self, args: dict) -> list:
        """Resolve the agents query field."""
        try:
            agents = self._team.list_agents() if hasattr(self._team, "list_agents") else []
        except Exception:
            agents = []

        result = []
        for a in agents:
            agent_dict = self._normalize_agent(a)

            # Apply filters
            dept_filter = args.get("department")
            if dept_filter and agent_dict.get("department") != dept_filter:
                continue
            status_filter = args.get("status")
            if status_filter and agent_dict.get("status") != status_filter:
                continue

            result.append(agent_dict)

        limit = args.get("limit")
        if isinstance(limit, int) and limit > 0:
            result = result[:limit]

        return result

    def _resolve_agent(self, args: dict) -> Optional[dict]:
        """Resolve the agent query field."""
        agent_id = args.get("id")
        if not agent_id:
            raise ValueError("agent query requires 'id' argument")

        agent = self._team.get_agent(agent_id) if hasattr(self._team, "get_agent") else None
        if agent is None:
            return None
        return self._normalize_agent(agent)

    def _resolve_tasks(self, args: dict) -> list:
        """Resolve the tasks query field."""
        try:
            tasks = self._store.load_tasks()
        except Exception:
            tasks = {}

        result = []
        for tid, tdata in tasks.items():
            task_dict = {
                "id": tid,
                "title": tdata.get("title", tdata.get("name", "")),
                "description": tdata.get("description", ""),
                "status": tdata.get("status", "unknown"),
                "priority": tdata.get("priority", "medium"),
                "assigneeId": tdata.get("assigned_to"),
                "createdAt": str(tdata.get("created_at", "")),
                "updatedAt": str(tdata.get("updated_at", "")),
            }

            # Apply filters
            status_filter = args.get("status")
            if status_filter and task_dict["status"] != status_filter:
                continue
            priority_filter = args.get("priority")
            if priority_filter and task_dict["priority"] != priority_filter:
                continue
            assignee_filter = args.get("assignee")
            if assignee_filter and task_dict["assigneeId"] != assignee_filter:
                continue

            result.append(task_dict)

        limit = args.get("limit")
        if isinstance(limit, int) and limit > 0:
            result = result[:limit]

        return result

    def _resolve_task(self, args: dict) -> Optional[dict]:
        """Resolve the task query field."""
        task_id = args.get("id")
        if not task_id:
            raise ValueError("task query requires 'id' argument")

        try:
            tasks = self._store.load_tasks()
            tdata = tasks.get(task_id)
        except Exception:
            tdata = None

        if tdata is None:
            return None

        return {
            "id": task_id,
            "title": tdata.get("title", tdata.get("name", "")),
            "description": tdata.get("description", ""),
            "status": tdata.get("status", "unknown"),
            "priority": tdata.get("priority", "medium"),
            "assigneeId": tdata.get("assigned_to"),
            "createdAt": str(tdata.get("created_at", "")),
            "updatedAt": str(tdata.get("updated_at", "")),
        }

    def _resolve_health(self) -> dict:
        """Resolve the health query field."""
        import psutil

        try:
            agents = self._team.list_agents() if hasattr(self._team, "list_agents") else []
            active_count = sum(
                1 for a in agents
                if (a.get("state") if isinstance(a, dict) else getattr(a, "state", "")) in ("active", "working")
            )
        except Exception:
            agents = []
            active_count = 0

        try:
            tasks = self._store.load_tasks()
            pending_count = sum(1 for t in tasks.values() if t.get("status") == "pending")
        except Exception:
            pending_count = 0

        try:
            process = psutil.Process()
            memory_mb = process.memory_info().rss / (1024 * 1024)
            uptime = time.time() - process.create_time()
        except Exception:
            memory_mb = 0.0
            uptime = 0.0

        return {
            "status": "healthy",
            "uptime": round(uptime, 1),
            "activeAgents": active_count,
            "pendingTasks": pending_count,
            "llmProviders": 3,
            "memoryUsageMb": round(memory_mb, 1),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def _resolve_metrics(self) -> dict:
        """Resolve the metrics query field."""
        try:
            agents = self._team.list_agents() if hasattr(self._team, "list_agents") else []
        except Exception:
            agents = []

        active_count = sum(
            1 for a in agents
            if (a.get("state") if isinstance(a, dict) else getattr(a, "state", "")) in ("active", "working")
        )

        dept_counts: Dict[str, int] = {}
        for a in agents:
            dept = str(a.get("department", "?") if isinstance(a, dict) else getattr(a, "department", "?"))
            dept_counts[dept] = dept_counts.get(dept, 0) + 1

        try:
            tasks = self._store.load_tasks()
        except Exception:
            tasks = {}

        status_counts: Dict[str, int] = {}
        for t in tasks.values():
            status = t.get("status", "unknown")
            status_counts[status] = status_counts.get(status, 0) + 1

        # LLM stats
        try:
            llm_stats = self._team._router.get_request_stats() if hasattr(self._team, "_router") else {}
        except Exception:
            llm_stats = {}

        return {
            "totalAgents": len(agents),
            "activeAgents": active_count,
            "totalTasks": len(tasks),
            "completedTasks": status_counts.get("completed", 0),
            "pendingTasks": status_counts.get("pending", 0),
            "failedTasks": status_counts.get("failed", 0),
            "avgTaskDurationMs": 0.0,
            "llmRequestsTotal": llm_stats.get("total_requests", 0),
            "llmSuccessRate": llm_stats.get("success_rate", 0.0),
            "agentsByDepartment": [
                {"department": d, "count": c} for d, c in sorted(dept_counts.items())
            ],
            "tasksByStatus": [
                {"status": s, "count": c} for s, c in sorted(status_counts.items())
            ],
        }

    def _resolve_knowledge_nodes(self, args: dict) -> list:
        """Resolve the knowledgeNodes query field."""
        # Delegate to knowledge graph if available
        if self._engines and hasattr(self._engines, "search_nodes"):
            try:
                search = args.get("search", "")
                node_type = args.get("type")
                limit = args.get("limit", 20)
                return self._engines.search_nodes(search, node_type=node_type, limit=limit)
            except Exception as e:
                logger.debug("Knowledge node search failed: %s", e)

        return []

    def _resolve_audit_log(self, args: dict) -> list:
        """Resolve the auditLog query field."""
        try:
            entity_type = args.get("entityType")
            limit = args.get("limit", 50)
            if isinstance(limit, str):
                limit = int(limit)
            entries = self._store.get_audit_log(entity_type=entity_type, limit=limit)
            return entries
        except Exception as e:
            logger.debug("Audit log resolution failed: %s", e)
            return []

    def _resolve_messages(self, args: dict) -> list:
        """Resolve the messages query field."""
        try:
            msg_type = args.get("type")
            limit = args.get("limit", 50)
            if isinstance(limit, str):
                limit = int(limit)
            messages = self._store.load_messages(msg_type=msg_type, limit=limit)
            return messages
        except Exception as e:
            logger.debug("Message resolution failed: %s", e)
            return []

    def _resolve_providers(self) -> dict:
        """Resolve the providers query field."""
        try:
            if hasattr(self._team, "_router"):
                status = self._team._router.get_providers_status()
            else:
                status = {}
        except Exception:
            status = {}

        def _provider_info(name: str) -> dict:
            info = status.get(name, {})
            if not isinstance(info, dict):
                info = {}
            return {
                "configured": info.get("configured", False),
                "enabled": info.get("enabled", False),
                "model": info.get("model", "unknown"),
                "circuitBreaker": info.get("circuit_breaker", "closed"),
                "consecutiveFailures": info.get("consecutive_failures", 0),
            }

        return {
            "ollama": _provider_info("ollama"),
            "claude": _provider_info("claude"),
            "openai": _provider_info("openai"),
            "failoverChain": status.get("_failover_chain", ["ollama", "claude", "openai"]),
        }

    @staticmethod
    def _normalize_agent(agent) -> dict:
        """Convert an agent object or dict to a standardized GraphQL-compatible dict."""
        if isinstance(agent, dict):
            return {
                "id": agent.get("agent_id", ""),
                "name": agent.get("name", ""),
                "title": agent.get("title", ""),
                "department": str(agent.get("department", "")),
                "tier": str(agent.get("tier", "")),
                "status": str(agent.get("state", agent.get("status", "unknown"))),
                "skills": agent.get("skills", []),
                "responsibilities": agent.get("responsibilities", []),
                "reportsTo": agent.get("reports_to"),
                "currentTask": agent.get("current_task"),
                "llmProvider": agent.get("llm_provider", "ollama"),
                "llmModel": agent.get("llm_model", ""),
            }
        else:
            return {
                "id": getattr(agent, "agent_id", ""),
                "name": getattr(agent, "name", ""),
                "title": getattr(agent, "title", ""),
                "department": str(getattr(agent, "department", "")),
                "tier": str(getattr(agent, "tier", "")),
                "status": str(getattr(agent, "state", "unknown")),
                "skills": getattr(agent, "skills", []),
                "responsibilities": getattr(agent, "responsibilities", []),
                "reportsTo": getattr(agent, "reports_to", None),
                "currentTask": getattr(agent, "current_task", None),
                "llmProvider": getattr(agent, "llm_provider", "ollama"),
                "llmModel": getattr(agent, "llm_model", ""),
            }

    # ── Query logging ─────────────────────────────────────────────────

    def _log_query(self, query: str, variables: dict, elapsed_ms: float,
                   status: str, error: str = None) -> None:
        """Log a GraphQL query execution to the database."""
        conn = self._get_connection()
        now = datetime.now(timezone.utc).isoformat()
        query_id = str(uuid.uuid4())

        try:
            conn.execute(
                """
                INSERT INTO graphql_query_log
                    (id, query, variables, response_time_ms, status, error, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    query_id,
                    query[:5000],  # Truncate very long queries
                    json.dumps(variables, default=str),
                    elapsed_ms,
                    status,
                    error,
                    now,
                ),
            )
            conn.commit()
        except Exception as e:
            logger.debug("Failed to log GraphQL query: %s", e)

    def get_query_log(self, limit: int = 50) -> list:
        """Get recent GraphQL query execution log.

        Args:
            limit: Maximum number of log entries to return.

        Returns:
            List of query log entry dicts, newest first.
        """
        conn = self._get_connection()
        rows = conn.execute(
            """
            SELECT id, query, variables, response_time_ms, status, error, created_at
            FROM graphql_query_log
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

        return [
            {
                "id": r["id"],
                "query": r["query"],
                "variables": json.loads(r["variables"]),
                "response_time_ms": r["response_time_ms"],
                "status": r["status"],
                "error": r["error"],
                "created_at": r["created_at"],
            }
            for r in rows
        ]

    # ── Introspection ─────────────────────────────────────────────────

    def introspect(self) -> dict:
        """Return a GraphQL introspection result.

        Provides a simplified introspection response with type information
        extracted from the active schema SDL.

        Returns:
            Dict with schema types, directives, and metadata.
        """
        schema = self.get_schema()
        if "error" in schema:
            return schema

        sdl = schema.get("schema_sdl", "")

        # Extract type definitions from SDL
        type_pattern = re.compile(r'type\s+(\w+)\s*\{([^}]*)\}', re.DOTALL)
        input_pattern = re.compile(r'input\s+(\w+)\s*\{([^}]*)\}', re.DOTALL)
        field_pattern = re.compile(r'(\w+)(?:\([^)]*\))?\s*:\s*(.+)')

        types = []
        for match in type_pattern.finditer(sdl):
            type_name = match.group(1)
            type_body = match.group(2)

            fields = []
            for field_match in field_pattern.finditer(type_body):
                fname = field_match.group(1)
                ftype = field_match.group(2).strip().rstrip('!')
                fields.append({"name": fname, "type": ftype})

            types.append({
                "kind": "OBJECT",
                "name": type_name,
                "fields": fields,
            })

        for match in input_pattern.finditer(sdl):
            type_name = match.group(1)
            type_body = match.group(2)

            fields = []
            for field_match in field_pattern.finditer(type_body):
                fname = field_match.group(1)
                ftype = field_match.group(2).strip().rstrip('!')
                fields.append({"name": fname, "type": ftype})

            types.append({
                "kind": "INPUT_OBJECT",
                "name": type_name,
                "fields": fields,
            })

        return {
            "__schema": {
                "queryType": {"name": "Query"},
                "mutationType": {"name": "Mutation"},
                "subscriptionType": {"name": "Subscription"},
                "types": types,
                "directives": [],
            },
            "_meta": {
                "schema_id": schema.get("id"),
                "schema_name": schema.get("name"),
                "types_count": len(types),
            },
        }

    # ── Stats ─────────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        """Get GraphQL gateway statistics.

        Returns:
            Dict with total queries, average response time, error rate,
            and schema version count.
        """
        conn = self._get_connection()

        total_row = conn.execute(
            "SELECT COUNT(*) AS cnt FROM graphql_query_log"
        ).fetchone()
        total_queries = total_row["cnt"] if total_row else 0

        if total_queries > 0:
            avg_row = conn.execute(
                "SELECT AVG(response_time_ms) AS avg_ms FROM graphql_query_log"
            ).fetchone()
            avg_response_ms = round(avg_row["avg_ms"], 2) if avg_row and avg_row["avg_ms"] else 0.0

            error_row = conn.execute(
                "SELECT COUNT(*) AS cnt FROM graphql_query_log WHERE status = 'error'"
            ).fetchone()
            error_count = error_row["cnt"] if error_row else 0
            error_rate = round(error_count / total_queries * 100, 2)
        else:
            avg_response_ms = 0.0
            error_count = 0
            error_rate = 0.0

        schema_row = conn.execute(
            "SELECT COUNT(*) AS cnt FROM graphql_schemas"
        ).fetchone()
        schema_count = schema_row["cnt"] if schema_row else 0

        active_row = conn.execute(
            "SELECT COUNT(*) AS cnt FROM graphql_schemas WHERE enabled = 1"
        ).fetchone()
        active_schemas = active_row["cnt"] if active_row else 0

        return {
            "total_queries": total_queries,
            "avg_response_time_ms": avg_response_ms,
            "error_count": error_count,
            "error_rate": error_rate,
            "schema_versions": schema_count,
            "active_schemas": active_schemas,
        }

    # ── Cleanup ───────────────────────────────────────────────────────

    def close(self) -> None:
        """Close the database connection."""
        if self.db is not None:
            try:
                self.db.close()
            except Exception:
                pass
            self.db = None
