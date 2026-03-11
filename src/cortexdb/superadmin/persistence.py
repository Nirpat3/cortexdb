"""
Persistence Layer — SQLite-backed storage for superadmin data.
Survives server restarts. Stores agents, tasks, instructions, sessions,
audit log, counters, messages, and provider config.

Database: ./data/superadmin/cortexdb_admin.db
Provides concurrent-safe writes, indexed queries, and ACID guarantees.
"""

import os
import json
import time
import sqlite3
import logging
import asyncio
from typing import Dict, List, Optional, Any
from pathlib import Path

logger = logging.getLogger(__name__)

DATA_DIR = Path(os.environ.get("CORTEXDB_DATA_DIR", "./data/superadmin"))
DB_NAME = "cortexdb_admin.db"

SCHEMA_VERSION = 1
# NOTE: Schema is managed by the SQLite migration system in migrations.py.
# The old SCHEMA_SQL constant was removed — it was dead code superseded by
# MigrationRunner which is invoked in _init_schema() below.


class PersistenceStore:
    """SQLite-backed persistence for superadmin state."""

    def __init__(self, data_dir: Path = DATA_DIR):
        self._dir = data_dir
        self._dir.mkdir(parents=True, exist_ok=True)
        self._db_path = self._dir / DB_NAME
        self._conn: Optional[sqlite3.Connection] = None
        self._lock = asyncio.Lock()
        self._running = False
        self._auto_save_interval = 30

    def _connect(self):
        if self._conn is None:
            self._conn = sqlite3.connect(
                str(self._db_path),
                check_same_thread=False,
                timeout=10,
            )
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._conn.row_factory = sqlite3.Row
            self._init_schema()
        return self._conn

    def _init_schema(self):
        conn = self._conn
        # Use migration system for schema management
        from cortexdb.superadmin.migrations import MigrationRunner
        runner = MigrationRunner(conn)
        applied = runner.migrate()
        current = runner.get_current_version()
        if applied > 0:
            logger.info("Applied %d migration(s), now at schema v%d", applied, current)
        logger.info("SQLite persistence initialized at %s (schema v%d)", self._db_path, current)

    @property
    def conn(self) -> sqlite3.Connection:
        return self._connect()

    # ── Agent CRUD ──

    def save_agent(self, agent_id: str, data: dict):
        self.conn.execute(
            "INSERT OR REPLACE INTO agents (agent_id, data, updated_at) VALUES (?, ?, ?)",
            (agent_id, json.dumps(data, default=str), time.time()),
        )
        self.conn.commit()

    def save_agents_bulk(self, agents: Dict[str, dict]):
        with self.conn:
            for aid, data in agents.items():
                self.conn.execute(
                    "INSERT OR REPLACE INTO agents (agent_id, data, updated_at) VALUES (?, ?, ?)",
                    (aid, json.dumps(data, default=str), time.time()),
                )

    def load_agents(self) -> Dict[str, dict]:
        rows = self.conn.execute("SELECT agent_id, data FROM agents").fetchall()
        return {row["agent_id"]: json.loads(row["data"]) for row in rows}

    # ── Task CRUD ──

    def save_task(self, task_id: str, data: dict):
        self.conn.execute(
            "INSERT OR REPLACE INTO tasks (task_id, status, priority, assigned_to, data, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (task_id, data.get("status", "pending"), data.get("priority", "medium"),
             data.get("assigned_to"), json.dumps(data, default=str),
             data.get("created_at", time.time()), time.time()),
        )
        self.conn.commit()

    def load_tasks(self) -> Dict[str, dict]:
        rows = self.conn.execute("SELECT task_id, data FROM tasks ORDER BY created_at DESC").fetchall()
        return {row["task_id"]: json.loads(row["data"]) for row in rows}

    def load_tasks_by_status(self, status: str) -> List[dict]:
        rows = self.conn.execute(
            "SELECT data FROM tasks WHERE status = ? ORDER BY created_at DESC", (status,)
        ).fetchall()
        return [json.loads(row["data"]) for row in rows]

    # ── Instruction CRUD ──

    def save_instruction(self, instruction_id: str, data: dict):
        self.conn.execute(
            "INSERT OR REPLACE INTO instructions (instruction_id, agent_id, status, data, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (instruction_id, data.get("agent_id"), data.get("status", "pending"),
             json.dumps(data, default=str), data.get("created_at", time.time())),
        )
        self.conn.commit()

    def load_instructions(self, agent_id: str = None, limit: int = 50) -> List[dict]:
        if agent_id:
            rows = self.conn.execute(
                "SELECT data FROM instructions WHERE agent_id = ? ORDER BY created_at DESC LIMIT ?",
                (agent_id, limit),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT data FROM instructions ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [json.loads(row["data"]) for row in rows]

    # ── Message CRUD ──

    def save_message(self, message_id: str, data: dict):
        self.conn.execute(
            "INSERT OR REPLACE INTO messages (message_id, msg_type, from_agent, to_agent, department, status, data, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (message_id, data.get("msg_type", "direct"), data.get("from_agent", ""),
             data.get("to_agent"), data.get("department"), data.get("status", "sent"),
             json.dumps(data, default=str), data.get("created_at", time.time())),
        )
        self.conn.commit()

    def load_messages(self, msg_type: str = None, limit: int = 100) -> List[dict]:
        if msg_type:
            rows = self.conn.execute(
                "SELECT data FROM messages WHERE msg_type = ? ORDER BY created_at DESC LIMIT ?",
                (msg_type, limit),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT data FROM messages ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [json.loads(row["data"]) for row in rows]

    def load_inbox(self, agent_id: str, unread_only: bool = False, limit: int = 50) -> List[dict]:
        sql = "SELECT data FROM messages WHERE (to_agent = ? OR (to_agent IS NULL AND msg_type = 'broadcast'))"
        params: list = [agent_id]
        if unread_only:
            sql += " AND status = 'sent'"
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        rows = self.conn.execute(sql, params).fetchall()
        return [json.loads(row["data"]) for row in rows]

    def update_message_status(self, message_id: str, status: str):
        self.conn.execute(
            "UPDATE messages SET status = ? WHERE message_id = ?", (status, message_id)
        )
        self.conn.commit()

    # ── Audit Log ──

    def audit(self, action: str, entity_type: str, entity_id: str,
              details: Dict = None, actor: str = "superadmin"):
        self.conn.execute(
            "INSERT INTO audit_log (timestamp, action, entity_type, entity_id, actor, details) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (time.time(), action, entity_type, entity_id, actor,
             json.dumps(details or {}, default=str)),
        )
        self.conn.commit()

    def get_audit_log(self, entity_type: str = None, limit: int = 100) -> List[dict]:
        if entity_type:
            rows = self.conn.execute(
                "SELECT timestamp, action, entity_type, entity_id, actor, details "
                "FROM audit_log WHERE entity_type = ? ORDER BY timestamp DESC LIMIT ?",
                (entity_type, limit),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT timestamp, action, entity_type, entity_id, actor, details "
                "FROM audit_log ORDER BY timestamp DESC LIMIT ?", (limit,),
            ).fetchall()
        return [
            {"timestamp": r["timestamp"], "action": r["action"],
             "entity_type": r["entity_type"], "entity_id": r["entity_id"],
             "actor": r["actor"], "details": json.loads(r["details"] or "{}")}
            for r in rows
        ]

    # ── Counters ──

    def get_counter(self, name: str) -> int:
        row = self.conn.execute(
            "SELECT value FROM counters WHERE name = ?", (name,)
        ).fetchone()
        return row["value"] if row else 0

    def increment_counter(self, name: str) -> int:
        self.conn.execute(
            "INSERT INTO counters (name, value) VALUES (?, 1) "
            "ON CONFLICT(name) DO UPDATE SET value = value + 1",
            (name,),
        )
        self.conn.commit()
        return self.get_counter(name)

    # ── KV Store (for provider config, misc) ──

    def kv_set(self, key: str, value: Any):
        self.conn.execute(
            "INSERT OR REPLACE INTO kv_store (key, value, updated_at) VALUES (?, ?, ?)",
            (key, json.dumps(value, default=str), time.time()),
        )
        self.conn.commit()

    def kv_get(self, key: str, default: Any = None) -> Any:
        row = self.conn.execute(
            "SELECT value FROM kv_store WHERE key = ?", (key,)
        ).fetchone()
        if row:
            return json.loads(row["value"])
        return default

    # ── Backward-compatible interface ──

    def load(self, collection: str) -> Any:
        """Backward-compatible load for agent_team.py and agent_bus.py."""
        if collection == "agents":
            return self.load_agents()
        elif collection == "tasks":
            return self.load_tasks()
        elif collection == "instructions":
            return self.load_instructions(limit=9999)
        elif collection == "messages":
            return {m.get("message_id", ""): m for m in self.load_messages(limit=9999)}
        elif collection == "counters":
            rows = self.conn.execute("SELECT name, value FROM counters").fetchall()
            return {r["name"]: r["value"] for r in rows}
        elif collection == "audit_log":
            return self.get_audit_log(limit=5000)
        else:
            return self.kv_get(collection, {})

    def save(self, collection: str, data: Any = None):
        """Backward-compatible save for agent_team.py and agent_bus.py."""
        if data is None:
            return
        if collection == "agents" and isinstance(data, dict):
            self.save_agents_bulk(data)
        elif collection == "tasks" and isinstance(data, dict):
            with self.conn:
                for tid, tdata in data.items():
                    self.save_task(tid, tdata)
        elif collection == "instructions" and isinstance(data, list):
            with self.conn:
                for idata in data:
                    iid = idata.get("instruction_id", "")
                    if iid:
                        self.save_instruction(iid, idata)
        elif collection == "messages" and isinstance(data, dict):
            with self.conn:
                for mid, mdata in data.items():
                    self.save_message(mid, mdata)
        else:
            self.kv_set(collection, data)

    def mark_dirty(self, collection: str):
        """No-op for SQLite — writes are immediate."""
        pass

    def flush_all(self):
        """No-op for SQLite — writes are immediate."""
        pass

    # ── Lifecycle ──

    async def start_auto_save(self):
        """Periodic WAL checkpoint for SQLite."""
        self._running = True
        while self._running:
            await asyncio.sleep(self._auto_save_interval)
            try:
                self.conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
            except Exception:
                pass

    def stop(self):
        self._running = False
        if self._conn:
            try:
                self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                self._conn.close()
            except Exception:
                pass
            self._conn = None
        logger.info("SQLite persistence closed")
