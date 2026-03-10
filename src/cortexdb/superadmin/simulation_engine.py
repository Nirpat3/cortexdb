"""Simulation sandbox engine for isolated agent testing."""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from cortexdb.agent_team_manager import AgentTeamManager
    from cortexdb.llm_router import LLMRouter
    from cortexdb.memory import AgentMemory
    from cortexdb.persistence_store import PersistenceStore

logger = logging.getLogger(__name__)


class SimulationEngine:
    """Forks agent state into an isolated sandbox for safe experimentation."""

    VALID_TYPES = ("behavior_test", "ab_test", "chaos", "freeform")

    def __init__(
        self,
        team: "AgentTeamManager",
        persistence: "PersistenceStore",
        llm_router: "LLMRouter",
        memory: "AgentMemory",
    ) -> None:
        self._team = team
        self._persistence = persistence
        self._router = llm_router
        self._memory = memory
        self._ensure_tables()

    def _ensure_tables(self) -> None:
        c = self._persistence.conn.cursor()
        c.execute(
            """CREATE TABLE IF NOT EXISTS simulations (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, sim_type TEXT NOT NULL,
                status TEXT DEFAULT 'created', config TEXT DEFAULT '{}',
                results TEXT DEFAULT '[]', created_at TEXT DEFAULT (datetime('now')),
                completed_at TEXT)"""
        )
        c.execute(
            """CREATE TABLE IF NOT EXISTS sim_agent_snapshots (
                id TEXT PRIMARY KEY, sim_id TEXT NOT NULL, agent_id TEXT NOT NULL,
                agent_state TEXT NOT NULL, skill_profile TEXT DEFAULT '{}',
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (sim_id) REFERENCES simulations(id))"""
        )
        self._persistence.conn.commit()

    def _sim_id(self) -> str:
        return f"SIM-{uuid.uuid4().hex[:8]}"

    def _snap_id(self) -> str:
        return f"SNAP-{uuid.uuid4().hex[:8]}"

    # ------------------------------------------------------------------
    def create_simulation(
        self,
        name: str,
        sim_type: str,
        config: Optional[Dict[str, Any]] = None,
        agent_ids: Optional[List[str]] = None,
    ) -> dict:
        if sim_type not in self.VALID_TYPES:
            raise ValueError(f"sim_type must be one of {self.VALID_TYPES}")
        sid = self._sim_id()
        c = self._persistence.conn.cursor()
        c.execute(
            "INSERT INTO simulations (id, name, sim_type, config) VALUES (?,?,?,?)",
            (sid, name, sim_type, json.dumps(config or {})),
        )
        snapshots: list[dict] = []
        for aid in agent_ids or []:
            agent_data = self._team.get_agent(aid)
            if not agent_data:
                logger.warning("Agent %s not found, skipping snapshot", aid)
                continue
            skill = self._persistence.conn.execute(
                "SELECT value FROM kv_store WHERE key=?", (f"skill_profile:{aid}",)
            ).fetchone()
            snap = {
                "id": self._snap_id(), "sim_id": sid, "agent_id": aid,
                "agent_state": json.dumps(agent_data),
                "skill_profile": skill[0] if skill else "{}",
            }
            c.execute(
                "INSERT INTO sim_agent_snapshots (id,sim_id,agent_id,agent_state,skill_profile) VALUES (?,?,?,?,?)",
                (snap["id"], sid, aid, snap["agent_state"], snap["skill_profile"]),
            )
            snapshots.append(snap)
        self._persistence.conn.commit()
        logger.info("Created simulation %s (%s) with %d snapshots", sid, sim_type, len(snapshots))
        return {"id": sid, "name": name, "sim_type": sim_type, "status": "created",
                "config": config or {}, "snapshots": snapshots}

    async def run_task_in_sandbox(
        self, sim_id: str, task_prompt: str, agent_id: str, system_prompt: Optional[str] = None,
    ) -> dict:
        snap = self._persistence.conn.execute(
            "SELECT agent_state, skill_profile FROM sim_agent_snapshots WHERE sim_id=? AND agent_id=?",
            (sim_id, agent_id),
        ).fetchone()
        if not snap:
            raise ValueError(f"No snapshot for agent {agent_id} in simulation {sim_id}")
        agent_state = json.loads(snap[0])
        skills = json.loads(snap[1])
        base_prompt = system_prompt or (
            f"You are agent {agent_state.get('name', agent_id)} in a sandbox simulation. "
            f"Skills: {json.dumps(skills)}. Respond to the task below."
        )
        t0 = time.perf_counter()
        try:
            response = await self._router.chat(
                messages=[{"role": "system", "content": base_prompt},
                          {"role": "user", "content": task_prompt}],
                model=agent_state.get("model"),
            )
            success = True
        except Exception as exc:
            logger.error("Sandbox LLM call failed: %s", exc)
            response = str(exc)
            success = False
        elapsed = round((time.perf_counter() - t0) * 1000, 2)
        result_entry = {"agent_id": agent_id, "prompt": task_prompt,
                        "response": response, "success": success, "elapsed_ms": elapsed}
        row = self._persistence.conn.execute(
            "SELECT results FROM simulations WHERE id=?", (sim_id,)
        ).fetchone()
        results = json.loads(row[0]) if row else []
        results.append(result_entry)
        self._persistence.conn.execute(
            "UPDATE simulations SET results=?, status='running' WHERE id=?",
            (json.dumps(results), sim_id),
        )
        self._persistence.conn.commit()
        return {"response": response, "success": success, "elapsed_ms": elapsed}

    def get_simulation(self, sim_id: str) -> Optional[dict]:
        row = self._persistence.conn.execute("SELECT * FROM simulations WHERE id=?", (sim_id,)).fetchone()
        if not row:
            return None
        sim = dict(row)
        sim["config"] = json.loads(sim.get("config", "{}"))
        sim["results"] = json.loads(sim.get("results", "[]"))
        snaps = self._persistence.conn.execute(
            "SELECT * FROM sim_agent_snapshots WHERE sim_id=?", (sim_id,)
        ).fetchall()
        sim["snapshots"] = [dict(s) for s in snaps]
        return sim

    def list_simulations(self, status: Optional[str] = None, sim_type: Optional[str] = None) -> List[dict]:
        q, params = "SELECT id, name, sim_type, status, created_at, completed_at FROM simulations WHERE 1=1", []
        if status:
            q += " AND status=?"; params.append(status)
        if sim_type:
            q += " AND sim_type=?"; params.append(sim_type)
        q += " ORDER BY created_at DESC"
        return [dict(r) for r in self._persistence.conn.execute(q, params).fetchall()]

    def update_simulation(self, sim_id: str, updates: dict) -> dict:
        allowed = {"status", "results", "completed_at"}
        sets, vals = [], []
        for k, v in updates.items():
            if k not in allowed:
                continue
            sets.append(f"{k}=?")
            vals.append(json.dumps(v) if isinstance(v, (dict, list)) else v)
        if not sets:
            raise ValueError("No valid fields to update")
        vals.append(sim_id)
        self._persistence.conn.execute(f"UPDATE simulations SET {','.join(sets)} WHERE id=?", vals)
        self._persistence.conn.commit()
        return self.get_simulation(sim_id)  # type: ignore[return-value]

    def cleanup_simulation(self, sim_id: str) -> dict:
        c = self._persistence.conn.cursor()
        c.execute("DELETE FROM sim_agent_snapshots WHERE sim_id=?", (sim_id,))
        deleted = c.rowcount
        c.execute("UPDATE simulations SET status='archived' WHERE id=?", (sim_id,))
        self._persistence.conn.commit()
        logger.info("Archived simulation %s, removed %d snapshots", sim_id, deleted)
        return {"sim_id": sim_id, "status": "archived", "snapshots_removed": deleted}

    def get_stats(self) -> dict:
        c = self._persistence.conn
        by_status = dict(c.execute(
            "SELECT status, COUNT(*) FROM simulations GROUP BY status"
        ).fetchall())
        by_type = dict(c.execute(
            "SELECT sim_type, COUNT(*) FROM simulations GROUP BY sim_type"
        ).fetchall())
        avg_row = c.execute(
            "SELECT AVG(json_array_length(results)) FROM simulations"
        ).fetchone()
        return {"total": sum(by_status.values()), "by_status": by_status,
                "by_type": by_type, "avg_results_count": round(avg_row[0] or 0, 2)}
