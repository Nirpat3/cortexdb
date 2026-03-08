"""
Prompt A/B Testing — Compare two system prompt variants on identical tasks.

Creates experiments that run the same task prompts against two prompt variants
across specified agents, grades each response via LLM, and determines a winner.
Results stored in the `ab_experiments` SQLite table.
"""

import json
import logging
import time
import uuid
from typing import Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from cortexdb.superadmin.simulation_engine import SimulationEngine
    from cortexdb.superadmin.llm_router import LLMRouter
    from cortexdb.superadmin.persistence import PersistenceStore

logger = logging.getLogger(__name__)

GRADE_PROMPT = "Rate this response quality 1-10. Just respond with the number."


class PromptABTesting:
    """Run controlled A/B experiments on system prompt variants."""

    def __init__(
        self,
        simulation_engine: "SimulationEngine",
        llm_router: "LLMRouter",
        persistence: "PersistenceStore",
    ) -> None:
        self._sim = simulation_engine
        self._router = llm_router
        self._persistence = persistence
        self._ensure_table()

    def _ensure_table(self) -> None:
        self._persistence.conn.execute(
            """CREATE TABLE IF NOT EXISTS ab_experiments (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                variant_a TEXT NOT NULL,
                variant_b TEXT NOT NULL,
                agent_ids TEXT NOT NULL,
                task_prompts TEXT NOT NULL,
                config TEXT DEFAULT '{}',
                results TEXT DEFAULT '{}',
                status TEXT DEFAULT 'created',
                created_at TEXT DEFAULT (datetime('now')),
                completed_at TEXT
            )"""
        )
        self._persistence.conn.commit()

    def _exp_id(self) -> str:
        return f"AB-{uuid.uuid4().hex[:8]}"

    # ── CRUD ──

    def create_experiment(
        self, name: str, variant_a_prompt: str, variant_b_prompt: str,
        agent_ids: List[str], task_prompts: List[str], config: Optional[dict] = None,
    ) -> dict:
        """Create a new A/B experiment."""
        eid = self._exp_id()
        cfg = config or {}
        self._persistence.conn.execute(
            "INSERT INTO ab_experiments (id,name,variant_a,variant_b,agent_ids,task_prompts,config) VALUES (?,?,?,?,?,?,?)",
            (eid, name, variant_a_prompt, variant_b_prompt,
             json.dumps(agent_ids), json.dumps(task_prompts), json.dumps(cfg)),
        )
        self._persistence.conn.commit()
        exp = {"id": eid, "name": name, "variant_a": variant_a_prompt,
               "variant_b": variant_b_prompt, "agent_ids": agent_ids,
               "task_prompts": task_prompts, "config": cfg, "status": "created"}
        logger.info("Created A/B experiment %s: %s", eid, name)
        return exp

    def get_experiment(self, experiment_id: str) -> Optional[dict]:
        """Return full experiment with results."""
        row = self._persistence.conn.execute(
            "SELECT * FROM ab_experiments WHERE id=?", (experiment_id,)
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        for k in ("agent_ids", "task_prompts", "config", "results"):
            d[k] = json.loads(d.get(k, "{}"))
        return d

    def list_experiments(self, status: Optional[str] = None) -> List[dict]:
        """List experiments, optionally filtered by status."""
        q, params = "SELECT * FROM ab_experiments WHERE 1=1", []
        if status:
            q += " AND status=?"; params.append(status)
        q += " ORDER BY created_at DESC"
        rows = self._persistence.conn.execute(q, params).fetchall()
        out = []
        for row in rows:
            d = dict(row)
            for k in ("agent_ids", "task_prompts", "config", "results"):
                d[k] = json.loads(d.get(k, "{}"))
            out.append(d)
        return out

    # ── Execution ──

    async def run_experiment(self, experiment_id: str) -> dict:
        """Run both variants against all tasks/agents and grade results."""
        exp = self.get_experiment(experiment_id)
        if not exp:
            return {"error": "Experiment not found"}

        agent_ids = exp["agent_ids"]
        task_prompts = exp["task_prompts"]
        cfg = exp.get("config", {})
        temperature = cfg.get("temperature", 0.7)

        sim = self._sim.create_simulation(
            name=f"ab-{experiment_id}", sim_type="ab_test", agent_ids=agent_ids,
        )
        sim_id = sim["id"]

        per_task: List[dict] = []
        scores_a, scores_b = [], []

        for task_prompt in task_prompts:
            for agent_id in agent_ids:
                try:
                    res_a = await self._sim.run_task_in_sandbox(
                        sim_id, task_prompt, agent_id, system_prompt=exp["variant_a"])
                    res_b = await self._sim.run_task_in_sandbox(
                        sim_id, task_prompt, agent_id, system_prompt=exp["variant_b"])

                    grade_a = await self._grade_response(res_a.get("response", ""))
                    grade_b = await self._grade_response(res_b.get("response", ""))
                    scores_a.append(grade_a)
                    scores_b.append(grade_b)

                    per_task.append({
                        "agent_id": agent_id, "task_prompt": task_prompt[:120],
                        "a": {"grade": grade_a, "elapsed_ms": res_a.get("elapsed_ms", 0),
                              "length": len(str(res_a.get("response", "")))},
                        "b": {"grade": grade_b, "elapsed_ms": res_b.get("elapsed_ms", 0),
                              "length": len(str(res_b.get("response", "")))},
                        "winner": "a" if grade_a > grade_b else ("b" if grade_b > grade_a else "tie"),
                    })
                except Exception as e:
                    logger.warning("AB task failed (%s / %s): %s", agent_id, task_prompt[:40], e)

        mean_a = round(sum(scores_a) / max(len(scores_a), 1), 2)
        mean_b = round(sum(scores_b) / max(len(scores_b), 1), 2)
        a_wins = sum(1 for t in per_task if t["winner"] == "a")
        b_wins = sum(1 for t in per_task if t["winner"] == "b")

        summary = {"mean_a": mean_a, "mean_b": mean_b, "a_wins": a_wins,
                    "b_wins": b_wins, "ties": len(per_task) - a_wins - b_wins,
                    "overall_winner": "a" if mean_a > mean_b else ("b" if mean_b > mean_a else "tie"),
                    "per_task": per_task}

        self._persistence.conn.execute(
            "UPDATE ab_experiments SET results=?, status='completed', completed_at=datetime('now') WHERE id=?",
            (json.dumps(summary), experiment_id),
        )
        self._persistence.conn.commit()
        logger.info("Experiment %s completed: A=%.1f B=%.1f winner=%s",
                     experiment_id, mean_a, mean_b, summary["overall_winner"])
        return summary

    async def _grade_response(self, response: str) -> int:
        """Ask LLM to grade a response 1-10."""
        try:
            result = await self._router.chat(
                messages=[{"role": "user", "content": f"{GRADE_PROMPT}\n\nResponse:\n{str(response)[:1500]}"}],
                temperature=0.0, failover=True,
            )
            text = str(result.get("message", "5")).strip()
            digits = "".join(c for c in text if c.isdigit())
            return max(1, min(10, int(digits[:2]))) if digits else 5
        except Exception:
            return 5

    # ── Apply & Stats ──

    def apply_winner(self, experiment_id: str) -> dict:
        """Apply the winning variant's prompt to the experiment's agents."""
        exp = self.get_experiment(experiment_id)
        if not exp or exp.get("status") != "completed":
            return {"error": "Experiment not found or not completed"}
        results = exp.get("results", {})
        winner = results.get("overall_winner", "tie")
        if winner == "tie":
            return {"error": "Experiment was a tie, no winner to apply"}

        winning_prompt = exp["variant_a"] if winner == "a" else exp["variant_b"]
        team = self._sim._team
        updated = []
        for aid in exp["agent_ids"]:
            if team.update_agent(aid, {"system_prompt": winning_prompt}):
                updated.append(aid)
        logger.info("Applied variant %s to %d agents from experiment %s", winner, len(updated), experiment_id)
        return {"winner": winner, "agents_updated": updated}

    def get_stats(self) -> dict:
        """Aggregate stats across all experiments."""
        c = self._persistence.conn
        total = c.execute("SELECT COUNT(*) FROM ab_experiments").fetchone()[0]
        completed = c.execute("SELECT COUNT(*) FROM ab_experiments WHERE status='completed'").fetchone()[0]
        rows = c.execute("SELECT results FROM ab_experiments WHERE status='completed'").fetchall()
        a_wins = b_wins = 0
        for row in rows:
            r = json.loads(row[0] or "{}")
            w = r.get("overall_winner")
            if w == "a":
                a_wins += 1
            elif w == "b":
                b_wins += 1
        return {"total": total, "completed": completed, "a_wins": a_wins,
                "b_wins": b_wins, "ties": completed - a_wins - b_wins}
