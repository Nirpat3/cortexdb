"""CortexDB SuperAdmin — Chaos Injection for simulation resilience testing."""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from cortexdb.llm_router import LLMRouter
    from cortexdb.persistence import PersistenceStore
    from cortexdb.simulation_engine import SimulationEngine
    from cortexdb.team_manager import AgentTeamManager

logger = logging.getLogger(__name__)

CHAOS_TYPES: Dict[str, Dict[str, Any]] = {
    "llm_timeout": {"description": "Simulates LLM not responding", "default_config": {"duration_ms": 5000}},
    "llm_error": {"description": "Simulates LLM returning an error", "default_config": {"error_message": "Service unavailable"}},
    "agent_crash": {"description": "Simulates agent becoming unavailable", "default_config": {"agent_id": ""}},
    "budget_exhaustion": {"description": "Simulates budget hitting zero", "default_config": {"department": ""}},
    "memory_wipe": {"description": "Simulates agent losing memory", "default_config": {"agent_id": ""}},
    "high_latency": {"description": "Simulates slow responses", "default_config": {"latency_ms": 3000}},
}


class ChaosInjector:
    """Injects controlled failures into simulations to test system resilience."""

    def __init__(
        self,
        simulation_engine: "SimulationEngine",
        team: "AgentTeamManager",
        llm_router: "LLMRouter",
        persistence: "PersistenceStore",
    ) -> None:
        self._sim = simulation_engine
        self._team = team
        self._llm = llm_router
        self._persistence = persistence
        self._ensure_table()

    def _ensure_table(self) -> None:
        self._persistence.conn.execute(
            """CREATE TABLE IF NOT EXISTS chaos_events (
                id TEXT PRIMARY KEY,
                sim_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                target TEXT NOT NULL,
                config TEXT NOT NULL DEFAULT '{}',
                status TEXT NOT NULL DEFAULT 'injected',
                injected_at REAL NOT NULL,
                resolved_at REAL
            )"""
        )
        self._persistence.conn.commit()

    def inject_failure(self, sim_id: str, event_type: str, target: str, config: Optional[Dict] = None) -> dict:
        if event_type not in CHAOS_TYPES:
            raise ValueError(f"Unknown chaos type '{event_type}'. Valid: {list(CHAOS_TYPES)}")
        merged = {**CHAOS_TYPES[event_type]["default_config"], **(config or {})}
        event_id = f"CHAOS-{uuid.uuid4().hex[:8]}"
        now = time.time()
        self._persistence.conn.execute(
            "INSERT INTO chaos_events (id, sim_id, event_type, target, config, status, injected_at) VALUES (?,?,?,?,?,?,?)",
            (event_id, sim_id, event_type, target, json.dumps(merged), "injected", now),
        )
        self._persistence.conn.commit()
        event = {"id": event_id, "sim_id": sim_id, "event_type": event_type, "target": target, "config": merged, "status": "injected", "injected_at": now}
        logger.info("Chaos injected: %s type=%s target=%s", event_id, event_type, target)
        return event

    def get_chaos_events(self, sim_id: str) -> List[dict]:
        rows = self._persistence.conn.execute(
            "SELECT id, sim_id, event_type, target, config, status, injected_at, resolved_at FROM chaos_events WHERE sim_id=? ORDER BY injected_at", (sim_id,)
        ).fetchall()
        return [
            {"id": r[0], "sim_id": r[1], "event_type": r[2], "target": r[3], "config": json.loads(r[4]), "status": r[5], "injected_at": r[6], "resolved_at": r[7]}
            for r in rows
        ]

    def evaluate_recovery(self, event_id: str) -> dict:
        row = self._persistence.conn.execute(
            "SELECT id, sim_id, event_type, target, config, status, injected_at, resolved_at FROM chaos_events WHERE id=?", (event_id,)
        ).fetchone()
        if not row:
            raise ValueError(f"Chaos event '{event_id}' not found")
        event_type, target, injected_at, resolved_at = row[2], row[3], row[6], row[7]
        recovery_detected = resolved_at is not None
        ttr = int((resolved_at - injected_at) * 1000) if recovery_detected else None
        tasks = self._persistence.conn.execute(
            "SELECT status FROM simulation_results WHERE sim_id=? AND created_at > ?", (row[1], injected_at)
        ).fetchall()
        completed = sum(1 for t in tasks if t[0] == "completed")
        fallback = completed > 0 and recovery_detected
        return {
            "event_type": event_type, "target": target, "recovery_detected": recovery_detected,
            "time_to_recovery_ms": ttr, "fallback_activated": fallback,
            "observations": f"{completed}/{len(tasks)} tasks completed post-injection",
        }

    async def run_chaos_scenario(self, name: str, agent_ids: List[str], events_sequence: List[dict]) -> dict:
        sim = self._sim.create_simulation(name=f"chaos-{name}", agent_ids=agent_ids)
        sim_id = sim["id"]
        baseline = await self._sim.run_baseline(sim_id)
        for entry in events_sequence:
            if entry.get("delay_ms"):
                await asyncio.sleep(entry["delay_ms"] / 1000)
            self.inject_failure(sim_id, entry["event_type"], entry["target"], entry.get("config"))
        post = await self._sim.run_baseline(sim_id)
        return {
            "scenario": name, "sim_id": sim_id, "events_injected": len(events_sequence),
            "baseline": baseline, "post_chaos": post,
            "degradation": self._compare(baseline, post),
        }

    @staticmethod
    def _compare(before: dict, after: dict) -> dict:
        b_rate = before.get("success_rate", 1.0)
        a_rate = after.get("success_rate", 0.0)
        return {"success_rate_before": b_rate, "success_rate_after": a_rate, "delta": round(a_rate - b_rate, 4)}

    def get_chaos_catalog(self) -> List[dict]:
        return [{"type": k, "description": v["description"], "default_config": v["default_config"]} for k, v in CHAOS_TYPES.items()]

    def get_stats(self) -> dict:
        rows = self._persistence.conn.execute(
            "SELECT event_type, COUNT(*), SUM(CASE WHEN resolved_at IS NOT NULL THEN 1 ELSE 0 END) FROM chaos_events GROUP BY event_type"
        ).fetchall()
        by_type = {r[0]: {"total": r[1], "recovered": r[2]} for r in rows}
        total = sum(v["total"] for v in by_type.values()) or 1
        recovered = sum(v["recovered"] for v in by_type.values())
        return {"total_events": total, "recovery_rate": round(recovered / total, 4), "by_type": by_type}
