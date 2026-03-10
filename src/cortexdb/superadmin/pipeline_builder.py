"""
Visual Data Pipeline Builder — Drag-and-drop ETL/ELT pipeline designer
with scheduling, transformations, and cross-engine data flows.

Pipelines are composed of ordered stages (extract, transform, load) that
execute sequentially. Each stage has a type, configuration, and produces
output consumed by subsequent stages.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from cortexdb.superadmin.persistence import PersistenceStore

logger = logging.getLogger("cortexdb.pipeline_builder")

# ── Seed stage types ───────────────────────────────────────────────────────────

_STAGE_TYPES = [
    {
        "id": "extract_sql",
        "name": "SQL Extract",
        "description": "Extract data by running a SQL query against a database engine",
        "category": "extract",
        "config_schema": {
            "type": "object",
            "properties": {
                "engine": {"type": "string", "description": "Database engine identifier"},
                "query": {"type": "string", "description": "SQL query to execute"},
                "params": {"type": "array", "description": "Query parameters"},
            },
            "required": ["engine", "query"],
        },
        "icon": "database",
    },
    {
        "id": "extract_api",
        "name": "API Extract",
        "description": "Fetch data from an HTTP API endpoint",
        "category": "extract",
        "config_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "API endpoint URL"},
                "method": {"type": "string", "enum": ["GET", "POST"], "default": "GET"},
                "headers": {"type": "object", "description": "Request headers"},
                "body": {"type": "object", "description": "Request body (for POST)"},
            },
            "required": ["url"],
        },
        "icon": "globe",
    },
    {
        "id": "extract_file",
        "name": "File Extract",
        "description": "Read data from a file (CSV, JSON, Parquet)",
        "category": "extract",
        "config_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path or URL"},
                "format": {"type": "string", "enum": ["csv", "json", "parquet", "jsonl"]},
                "encoding": {"type": "string", "default": "utf-8"},
            },
            "required": ["path", "format"],
        },
        "icon": "file",
    },
    {
        "id": "transform_map",
        "name": "Map Transform",
        "description": "Apply a mapping function to each record (rename, compute fields)",
        "category": "transform",
        "config_schema": {
            "type": "object",
            "properties": {
                "mappings": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "source": {"type": "string"},
                            "target": {"type": "string"},
                            "expression": {"type": "string"},
                        },
                    },
                    "description": "Field mapping rules",
                },
            },
            "required": ["mappings"],
        },
        "icon": "arrow-right",
    },
    {
        "id": "transform_filter",
        "name": "Filter Transform",
        "description": "Filter records based on conditions",
        "category": "transform",
        "config_schema": {
            "type": "object",
            "properties": {
                "conditions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "field": {"type": "string"},
                            "operator": {"type": "string", "enum": ["eq", "ne", "gt", "lt", "gte", "lte", "in", "contains"]},
                            "value": {},
                        },
                    },
                },
                "logic": {"type": "string", "enum": ["and", "or"], "default": "and"},
            },
            "required": ["conditions"],
        },
        "icon": "filter",
    },
    {
        "id": "transform_aggregate",
        "name": "Aggregate Transform",
        "description": "Group and aggregate records (sum, avg, count, min, max)",
        "category": "transform",
        "config_schema": {
            "type": "object",
            "properties": {
                "group_by": {"type": "array", "items": {"type": "string"}},
                "aggregations": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "field": {"type": "string"},
                            "function": {"type": "string", "enum": ["sum", "avg", "count", "min", "max"]},
                            "alias": {"type": "string"},
                        },
                    },
                },
            },
            "required": ["aggregations"],
        },
        "icon": "layers",
    },
    {
        "id": "load_table",
        "name": "Table Load",
        "description": "Write data to a database table (insert, upsert, or replace)",
        "category": "load",
        "config_schema": {
            "type": "object",
            "properties": {
                "engine": {"type": "string", "description": "Target database engine"},
                "table": {"type": "string", "description": "Target table name"},
                "mode": {"type": "string", "enum": ["insert", "upsert", "replace"], "default": "insert"},
                "conflict_key": {"type": "string", "description": "Column for upsert conflict resolution"},
            },
            "required": ["engine", "table"],
        },
        "icon": "table",
    },
    {
        "id": "load_api",
        "name": "API Load",
        "description": "Push data to an external API endpoint",
        "category": "load",
        "config_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string"},
                "method": {"type": "string", "enum": ["POST", "PUT", "PATCH"], "default": "POST"},
                "headers": {"type": "object"},
                "batch_size": {"type": "integer", "default": 100},
            },
            "required": ["url"],
        },
        "icon": "upload",
    },
]


class PipelineBuilder:
    """ETL/ELT pipeline designer with sequential stage execution."""

    def __init__(self, persistence_store: "PersistenceStore"):
        self._persistence = persistence_store
        self._init_db()

    # ── Schema ──────────────────────────────────────────────────────────────

    def _init_db(self) -> None:
        conn = self._persistence.conn
        conn.executescript("""
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

            CREATE TABLE IF NOT EXISTS pipeline_stage_types (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                category TEXT NOT NULL CHECK(category IN ('extract', 'transform', 'load')),
                config_schema TEXT NOT NULL DEFAULT '{}',
                icon TEXT DEFAULT ''
            );

            CREATE INDEX IF NOT EXISTS idx_pipeline_runs_pid ON pipeline_runs(pipeline_id);
            CREATE INDEX IF NOT EXISTS idx_pipeline_runs_status ON pipeline_runs(status);
            CREATE INDEX IF NOT EXISTS idx_data_pipelines_status ON data_pipelines(status);
        """)
        conn.commit()
        self._seed_stage_types()

    def _seed_stage_types(self) -> None:
        existing = self._persistence.conn.execute(
            "SELECT COUNT(*) FROM pipeline_stage_types"
        ).fetchone()[0]
        if existing > 0:
            return
        for st in _STAGE_TYPES:
            self._persistence.conn.execute(
                "INSERT INTO pipeline_stage_types (id, name, description, category, config_schema, icon) "
                "VALUES (?,?,?,?,?,?)",
                (st["id"], st["name"], st["description"], st["category"],
                 json.dumps(st["config_schema"]), st["icon"]),
            )
        self._persistence.conn.commit()
        logger.info("Seeded %d pipeline stage types", len(_STAGE_TYPES))

    # ── Helpers ─────────────────────────────────────────────────────────────

    def _row_to_pipeline(self, row) -> dict:
        return {
            "id": row[0],
            "name": row[1],
            "description": row[2],
            "stages": json.loads(row[3]) if row[3] else [],
            "schedule": row[4],
            "status": row[5],
            "last_run": row[6],
            "next_run": row[7],
            "run_count": row[8],
            "avg_duration_ms": row[9],
            "created_at": row[10],
            "updated_at": row[11],
        }

    _PIPELINE_COLS = (
        "id, name, description, stages, schedule, status, last_run, next_run, "
        "run_count, avg_duration_ms, created_at, updated_at"
    )

    def _row_to_run(self, row) -> dict:
        return {
            "id": row[0],
            "pipeline_id": row[1],
            "status": row[2],
            "started_at": row[3],
            "completed_at": row[4],
            "duration_ms": row[5],
            "stages_completed": row[6],
            "total_stages": row[7],
            "error": row[8],
            "output": json.loads(row[9]) if row[9] else {},
        }

    _RUN_COLS = (
        "id, pipeline_id, status, started_at, completed_at, duration_ms, "
        "stages_completed, total_stages, error, output"
    )

    # ── Pipeline CRUD ───────────────────────────────────────────────────────

    def create_pipeline(
        self,
        name: str,
        description: Optional[str] = None,
        stages: Optional[List[Dict]] = None,
        schedule: Optional[str] = None,
    ) -> dict:
        pid = f"DPL-{uuid.uuid4().hex[:8]}"
        now = time.time()
        self._persistence.conn.execute(
            f"INSERT INTO data_pipelines ({self._PIPELINE_COLS}) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                pid, name, description or "", json.dumps(stages or []),
                schedule or "", "draft", None, None, 0, 0.0, now, now,
            ),
        )
        self._persistence.conn.commit()
        logger.info("Created pipeline %s: %s", pid, name)
        return self.get_pipeline(pid)

    def list_pipelines(self, status: Optional[str] = None) -> list:
        sql = f"SELECT {self._PIPELINE_COLS} FROM data_pipelines"
        params: list = []
        if status:
            sql += " WHERE status = ?"
            params.append(status)
        sql += " ORDER BY created_at DESC"
        rows = self._persistence.conn.execute(sql, params).fetchall()
        return [self._row_to_pipeline(r) for r in rows]

    def get_pipeline(self, pipeline_id: str) -> dict:
        row = self._persistence.conn.execute(
            f"SELECT {self._PIPELINE_COLS} FROM data_pipelines WHERE id = ?", (pipeline_id,)
        ).fetchone()
        if not row:
            return {"error": "Pipeline not found", "pipeline_id": pipeline_id}
        return self._row_to_pipeline(row)

    def update_pipeline(self, pipeline_id: str, updates: Dict[str, Any]) -> dict:
        existing = self.get_pipeline(pipeline_id)
        if "error" in existing:
            return existing
        allowed = {"name", "description", "stages", "schedule", "status"}
        sets, params = [], []
        for key, val in updates.items():
            if key not in allowed:
                continue
            if key == "stages":
                val = json.dumps(val)
            sets.append(f"{key} = ?")
            params.append(val)
        if not sets:
            return {"error": "No valid fields to update"}
        sets.append("updated_at = ?")
        params.append(time.time())
        params.append(pipeline_id)
        self._persistence.conn.execute(
            f"UPDATE data_pipelines SET {', '.join(sets)} WHERE id = ?", params
        )
        self._persistence.conn.commit()
        logger.info("Updated pipeline %s", pipeline_id)
        return self.get_pipeline(pipeline_id)

    def delete_pipeline(self, pipeline_id: str) -> dict:
        existing = self.get_pipeline(pipeline_id)
        if "error" in existing:
            return existing
        self._persistence.conn.execute("DELETE FROM data_pipelines WHERE id = ?", (pipeline_id,))
        self._persistence.conn.execute(
            "DELETE FROM pipeline_runs WHERE pipeline_id = ?", (pipeline_id,)
        )
        self._persistence.conn.commit()
        logger.info("Deleted pipeline %s", pipeline_id)
        return {"deleted": True, "pipeline_id": pipeline_id}

    # ── Stage Management ────────────────────────────────────────────────────

    def add_stage(
        self,
        pipeline_id: str,
        stage_type: str,
        config: Dict[str, Any],
        position: Optional[int] = None,
    ) -> dict:
        """Add a stage to a pipeline at the given position (or end)."""
        pipeline = self.get_pipeline(pipeline_id)
        if "error" in pipeline:
            return pipeline

        # Validate stage type exists
        type_row = self._persistence.conn.execute(
            "SELECT id, name, category FROM pipeline_stage_types WHERE id = ?", (stage_type,)
        ).fetchone()
        if not type_row:
            return {"error": f"Unknown stage type '{stage_type}'"}

        stage = {
            "id": f"STG-{uuid.uuid4().hex[:8]}",
            "stage_type": stage_type,
            "stage_name": type_row[1],
            "category": type_row[2],
            "config": config,
        }

        stages = pipeline["stages"]
        if position is not None and 0 <= position <= len(stages):
            stages.insert(position, stage)
        else:
            stages.append(stage)

        self._persistence.conn.execute(
            "UPDATE data_pipelines SET stages = ?, updated_at = ? WHERE id = ?",
            (json.dumps(stages), time.time(), pipeline_id),
        )
        self._persistence.conn.commit()
        logger.info("Added stage %s (%s) to pipeline %s", stage["id"], stage_type, pipeline_id)
        return self.get_pipeline(pipeline_id)

    def remove_stage(self, pipeline_id: str, stage_index: int) -> dict:
        """Remove a stage by index."""
        pipeline = self.get_pipeline(pipeline_id)
        if "error" in pipeline:
            return pipeline
        stages = pipeline["stages"]
        if stage_index < 0 or stage_index >= len(stages):
            return {"error": f"Stage index {stage_index} out of range (0-{len(stages) - 1})"}
        removed = stages.pop(stage_index)
        self._persistence.conn.execute(
            "UPDATE data_pipelines SET stages = ?, updated_at = ? WHERE id = ?",
            (json.dumps(stages), time.time(), pipeline_id),
        )
        self._persistence.conn.commit()
        logger.info("Removed stage at index %d from pipeline %s", stage_index, pipeline_id)
        return {**self.get_pipeline(pipeline_id), "removed_stage": removed}

    def reorder_stages(self, pipeline_id: str, new_order: list) -> dict:
        """Reorder stages by providing a list of stage indices in the desired order."""
        pipeline = self.get_pipeline(pipeline_id)
        if "error" in pipeline:
            return pipeline
        stages = pipeline["stages"]
        if sorted(new_order) != list(range(len(stages))):
            return {"error": "new_order must be a permutation of current stage indices"}
        reordered = [stages[i] for i in new_order]
        self._persistence.conn.execute(
            "UPDATE data_pipelines SET stages = ?, updated_at = ? WHERE id = ?",
            (json.dumps(reordered), time.time(), pipeline_id),
        )
        self._persistence.conn.commit()
        logger.info("Reordered stages in pipeline %s", pipeline_id)
        return self.get_pipeline(pipeline_id)

    # ── Validation ──────────────────────────────────────────────────────────

    def validate_pipeline(self, pipeline_id: str) -> dict:
        """Validate a pipeline's stage configuration and ordering."""
        pipeline = self.get_pipeline(pipeline_id)
        if "error" in pipeline:
            return pipeline

        stages = pipeline["stages"]
        errors: List[str] = []
        warnings: List[str] = []

        if not stages:
            errors.append("Pipeline has no stages")
            return {"valid": False, "errors": errors, "warnings": warnings}

        # Check that stage types exist
        valid_types = {r[0] for r in self._persistence.conn.execute(
            "SELECT id FROM pipeline_stage_types"
        ).fetchall()}

        categories_seen = []
        for i, stage in enumerate(stages):
            st = stage.get("stage_type", "")
            if st not in valid_types:
                errors.append(f"Stage {i}: unknown type '{st}'")
            cat = stage.get("category", "")
            categories_seen.append(cat)
            if not stage.get("config"):
                warnings.append(f"Stage {i} ({st}): empty configuration")

        # Check logical ordering: extracts should come before transforms, loads last
        cat_order = {"extract": 0, "transform": 1, "load": 2}
        prev_order = -1
        for i, cat in enumerate(categories_seen):
            order = cat_order.get(cat, 1)
            if order < prev_order:
                warnings.append(
                    f"Stage {i} ({cat}) appears after a later-phase stage — "
                    f"consider reordering for clarity"
                )
            prev_order = order

        # Check that there's at least one extract and one load
        if "extract" not in categories_seen:
            warnings.append("Pipeline has no extract stage — data source may be missing")
        if "load" not in categories_seen:
            warnings.append("Pipeline has no load stage — results may not be persisted")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "stage_count": len(stages),
        }

    # ── Execution ───────────────────────────────────────────────────────────

    def execute_pipeline(self, pipeline_id: str) -> dict:
        """Execute a pipeline: run each stage sequentially and record the run."""
        pipeline = self.get_pipeline(pipeline_id)
        if "error" in pipeline:
            return pipeline

        stages = pipeline["stages"]
        if not stages:
            return {"error": "Pipeline has no stages to execute"}

        run_id = f"DPR-{uuid.uuid4().hex[:8]}"
        now = time.time()
        total = len(stages)

        self._persistence.conn.execute(
            f"INSERT INTO pipeline_runs ({self._RUN_COLS}) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (run_id, pipeline_id, "running", now, None, None, 0, total, "", "{}"),
        )
        self._persistence.conn.commit()

        stage_outputs: List[Dict] = []
        completed = 0
        error_msg = ""

        for i, stage in enumerate(stages):
            stage_start = time.time()
            try:
                # Simulate stage execution
                output = self._execute_stage(stage, stage_outputs)
                stage_outputs.append({
                    "stage_index": i,
                    "stage_type": stage.get("stage_type"),
                    "status": "completed",
                    "duration_ms": int((time.time() - stage_start) * 1000),
                    "output_summary": output,
                })
                completed += 1
                # Update progress
                self._persistence.conn.execute(
                    "UPDATE pipeline_runs SET stages_completed = ? WHERE id = ?",
                    (completed, run_id),
                )
                self._persistence.conn.commit()
            except Exception as exc:
                error_msg = f"Stage {i} ({stage.get('stage_type', '?')}): {exc}"
                stage_outputs.append({
                    "stage_index": i,
                    "stage_type": stage.get("stage_type"),
                    "status": "failed",
                    "error": str(exc),
                })
                logger.error("Pipeline %s run %s failed at stage %d: %s",
                             pipeline_id, run_id, i, exc)
                break

        # Finalize run
        end_time = time.time()
        duration_ms = int((end_time - now) * 1000)
        final_status = "completed" if not error_msg else "failed"

        self._persistence.conn.execute(
            "UPDATE pipeline_runs SET status = ?, completed_at = ?, duration_ms = ?, "
            "stages_completed = ?, error = ?, output = ? WHERE id = ?",
            (final_status, end_time, duration_ms, completed, error_msg,
             json.dumps({"stages": stage_outputs}), run_id),
        )

        # Update pipeline stats
        run_count = pipeline["run_count"] + 1
        prev_avg = pipeline["avg_duration_ms"]
        new_avg = ((prev_avg * (run_count - 1)) + duration_ms) / run_count
        new_status = "active" if final_status == "completed" else "error"

        self._persistence.conn.execute(
            "UPDATE data_pipelines SET last_run = ?, run_count = ?, avg_duration_ms = ?, "
            "status = ?, updated_at = ? WHERE id = ?",
            (end_time, run_count, round(new_avg, 1), new_status, end_time, pipeline_id),
        )
        self._persistence.conn.commit()

        logger.info("Pipeline %s run %s %s in %dms (%d/%d stages)",
                     pipeline_id, run_id, final_status, duration_ms, completed, total)
        return self.get_run(run_id)

    def _execute_stage(self, stage: Dict, previous_outputs: List[Dict]) -> dict:
        """
        Simulate stage execution. In a real implementation this would invoke
        actual database queries, API calls, or transformations.
        """
        stage_type = stage.get("stage_type", "unknown")
        config = stage.get("config", {})
        category = stage.get("category", "")

        # Produce a summary of what this stage would do
        summary: Dict[str, Any] = {
            "stage_type": stage_type,
            "category": category,
            "simulated": True,
        }

        if stage_type == "extract_sql":
            summary["action"] = f"Execute query on engine '{config.get('engine', '?')}'"
            summary["records_extracted"] = 0
        elif stage_type == "extract_api":
            summary["action"] = f"{config.get('method', 'GET')} {config.get('url', '?')}"
            summary["records_extracted"] = 0
        elif stage_type == "extract_file":
            summary["action"] = f"Read {config.get('format', '?')} from '{config.get('path', '?')}'"
            summary["records_extracted"] = 0
        elif stage_type == "transform_map":
            mappings = config.get("mappings", [])
            summary["action"] = f"Map {len(mappings)} field(s)"
            summary["records_transformed"] = 0
        elif stage_type == "transform_filter":
            conditions = config.get("conditions", [])
            summary["action"] = f"Filter with {len(conditions)} condition(s)"
            summary["records_passed"] = 0
        elif stage_type == "transform_aggregate":
            aggs = config.get("aggregations", [])
            summary["action"] = f"Aggregate {len(aggs)} field(s)"
            summary["groups_produced"] = 0
        elif stage_type == "load_table":
            summary["action"] = f"{config.get('mode', 'insert')} into '{config.get('table', '?')}'"
            summary["records_loaded"] = 0
        elif stage_type == "load_api":
            summary["action"] = f"{config.get('method', 'POST')} to '{config.get('url', '?')}'"
            summary["records_sent"] = 0
        else:
            summary["action"] = "Unknown stage type"

        return summary

    # ── Run Management ──────────────────────────────────────────────────────

    def get_run(self, run_id: str) -> dict:
        row = self._persistence.conn.execute(
            f"SELECT {self._RUN_COLS} FROM pipeline_runs WHERE id = ?", (run_id,)
        ).fetchone()
        if not row:
            return {"error": "Run not found", "run_id": run_id}
        return self._row_to_run(row)

    def list_runs(self, pipeline_id: Optional[str] = None, limit: int = 20) -> list:
        if pipeline_id:
            rows = self._persistence.conn.execute(
                f"SELECT {self._RUN_COLS} FROM pipeline_runs "
                "WHERE pipeline_id = ? ORDER BY started_at DESC LIMIT ?",
                (pipeline_id, limit),
            ).fetchall()
        else:
            rows = self._persistence.conn.execute(
                f"SELECT {self._RUN_COLS} FROM pipeline_runs "
                "ORDER BY started_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._row_to_run(r) for r in rows]

    def cancel_run(self, run_id: str) -> dict:
        row = self._persistence.conn.execute(
            f"SELECT {self._RUN_COLS} FROM pipeline_runs WHERE id = ?", (run_id,)
        ).fetchone()
        if not row:
            return {"error": "Run not found", "run_id": run_id}
        if row[2] != "running":
            return {"error": f"Run is not running (status: {row[2]})", "run_id": run_id}
        now = time.time()
        duration_ms = int((now - row[3]) * 1000)
        self._persistence.conn.execute(
            "UPDATE pipeline_runs SET status = 'cancelled', completed_at = ?, duration_ms = ? WHERE id = ?",
            (now, duration_ms, run_id),
        )
        self._persistence.conn.commit()
        logger.info("Cancelled run %s", run_id)
        return self.get_run(run_id)

    # ── Stage Types ─────────────────────────────────────────────────────────

    def get_stage_types(self) -> list:
        rows = self._persistence.conn.execute(
            "SELECT id, name, description, category, config_schema, icon "
            "FROM pipeline_stage_types ORDER BY category, name"
        ).fetchall()
        return [
            {
                "id": r[0], "name": r[1], "description": r[2],
                "category": r[3], "config_schema": json.loads(r[4]) if r[4] else {},
                "icon": r[5],
            }
            for r in rows
        ]

    # ── Stats ───────────────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        conn = self._persistence.conn
        total_pipelines = conn.execute("SELECT COUNT(*) FROM data_pipelines").fetchone()[0]
        by_status = {}
        for row in conn.execute(
            "SELECT status, COUNT(*) FROM data_pipelines GROUP BY status"
        ).fetchall():
            by_status[row[0]] = row[1]

        total_runs = conn.execute("SELECT COUNT(*) FROM pipeline_runs").fetchone()[0]
        completed_runs = conn.execute(
            "SELECT COUNT(*) FROM pipeline_runs WHERE status = 'completed'"
        ).fetchone()[0]
        failed_runs = conn.execute(
            "SELECT COUNT(*) FROM pipeline_runs WHERE status = 'failed'"
        ).fetchone()[0]

        avg_dur = conn.execute(
            "SELECT COALESCE(AVG(duration_ms), 0) FROM pipeline_runs WHERE status = 'completed'"
        ).fetchone()[0]

        return {
            "total_pipelines": total_pipelines,
            "pipelines_by_status": by_status,
            "total_runs": total_runs,
            "completed_runs": completed_runs,
            "failed_runs": failed_runs,
            "success_rate": round(completed_runs / total_runs * 100, 1) if total_runs else 0.0,
            "avg_duration_ms": round(avg_dur, 1),
        }
