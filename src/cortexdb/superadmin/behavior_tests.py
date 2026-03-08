"""
Behavior Test Manager — Agent behavior test suites and sandbox execution.

Manages test suites of prompt/expected-response pairs. Each suite is run
through the simulation engine and evaluated with keyword matching:
  - expected_keywords must appear in the response (case-insensitive)
  - must_not_contain tokens must be absent
  - response must be non-empty

Tables: behavior_test_suites, behavior_test_runs
"""

import json
import time
import uuid
import logging
from typing import List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from cortexdb.superadmin.simulation_engine import SimulationEngine
    from cortexdb.superadmin.agent_team import AgentTeamManager
    from cortexdb.superadmin.llm_router import LLMRouter
    from cortexdb.superadmin.persistence import PersistenceStore

logger = logging.getLogger(__name__)


class BehaviorTestManager:
    """Manages agent behavior test suites and runs them via simulation."""

    def __init__(self, simulation_engine: "SimulationEngine", team: "AgentTeamManager",
                 llm_router: "LLMRouter", persistence: "PersistenceStore"):
        self._simulation = simulation_engine
        self._team = team
        self._llm = llm_router
        self._persistence = persistence

    def create_suite(self, name: str, description: str, test_cases: List[dict]) -> dict:
        """Create a new behavior test suite."""
        suite_id = f"BTS-{uuid.uuid4().hex[:8]}"
        now = time.time()
        self._persistence.conn.execute(
            "INSERT INTO behavior_test_suites (suite_id, name, description, test_cases, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (suite_id, name, description, json.dumps(test_cases), now, now),
        )
        self._persistence.conn.commit()
        logger.info("Created behavior test suite %s: %s", suite_id, name)
        return {"suite_id": suite_id, "name": name, "description": description,
                "test_cases": test_cases, "created_at": now, "updated_at": now}

    async def run_suite(self, suite_id: str, agent_ids: Optional[List[str]] = None) -> dict:
        """Run all test cases in a suite and record results."""
        suite = self.get_suite(suite_id)
        if not suite:
            return {"error": "Suite not found"}

        run_id = f"BTR-{uuid.uuid4().hex[:8]}"
        started_at = time.time()
        cases = suite["test_cases"]
        results = []

        for case in cases:
            target = case.get("agent_id")
            if agent_ids and target not in agent_ids:
                continue
            try:
                resp = await self._simulation.run_sandboxed_task(
                    agent_id=target, prompt=case["prompt"])
                response_text = resp.get("response", "") if isinstance(resp, dict) else str(resp)
            except Exception as e:
                logger.warning("Test case failed for %s: %s", target, e)
                response_text = ""

            passed, details = self._evaluate(response_text, case)
            results.append({
                "agent_id": target, "prompt": case["prompt"],
                "passed": passed, "details": details,
                "response_preview": response_text[:200],
            })

        total = len(results)
        passed_count = sum(1 for r in results if r["passed"])
        completed_at = time.time()
        summary = {"total": total, "passed": passed_count, "failed": total - passed_count,
                    "pass_rate": round(passed_count / max(total, 1) * 100, 1)}

        self._persistence.conn.execute(
            "INSERT INTO behavior_test_runs (run_id, suite_id, agent_ids, results, summary, "
            "started_at, completed_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (run_id, suite_id, json.dumps(agent_ids or []), json.dumps(results),
             json.dumps(summary), started_at, completed_at),
        )
        self._persistence.conn.commit()
        logger.info("Suite %s run %s: %d/%d passed", suite_id, run_id, passed_count, total)
        return {"run_id": run_id, "suite_id": suite_id, "summary": summary}

    def get_suite(self, suite_id: str) -> Optional[dict]:
        """Get a single suite by ID."""
        row = self._persistence.conn.execute(
            "SELECT * FROM behavior_test_suites WHERE suite_id = ?", (suite_id,),
        ).fetchone()
        if not row:
            return None
        return {**dict(row), "test_cases": json.loads(row["test_cases"])}

    def list_suites(self) -> List[dict]:
        """List all suites with last run info."""
        rows = self._persistence.conn.execute(
            "SELECT s.*, r.run_id AS last_run_id, r.summary AS last_summary, "
            "r.completed_at AS last_run_at FROM behavior_test_suites s "
            "LEFT JOIN behavior_test_runs r ON r.suite_id = s.suite_id "
            "AND r.completed_at = (SELECT MAX(completed_at) FROM behavior_test_runs WHERE suite_id = s.suite_id) "
            "ORDER BY s.created_at DESC"
        ).fetchall()
        out = []
        for row in rows:
            d = {**dict(row), "test_cases": json.loads(row["test_cases"])}
            if row["last_summary"]:
                d["last_run"] = {"run_id": row["last_run_id"],
                                 "summary": json.loads(row["last_summary"]),
                                 "completed_at": row["last_run_at"]}
            else:
                d["last_run"] = None
            d.pop("last_run_id", None)
            d.pop("last_summary", None)
            d.pop("last_run_at", None)
            out.append(d)
        return out

    def update_suite(self, suite_id: str, updates: dict) -> dict:
        """Update suite name, description, or test_cases."""
        suite = self.get_suite(suite_id)
        if not suite:
            return {"error": "Suite not found"}
        name = updates.get("name", suite["name"])
        desc = updates.get("description", suite["description"])
        cases = updates.get("test_cases", suite["test_cases"])
        now = time.time()
        self._persistence.conn.execute(
            "UPDATE behavior_test_suites SET name = ?, description = ?, test_cases = ?, updated_at = ? "
            "WHERE suite_id = ?",
            (name, desc, json.dumps(cases), now, suite_id),
        )
        self._persistence.conn.commit()
        return {"suite_id": suite_id, "name": name, "description": desc,
                "test_cases": cases, "updated_at": now}

    def get_run_results(self, run_id: str) -> Optional[dict]:
        """Get full results for a specific run."""
        row = self._persistence.conn.execute(
            "SELECT * FROM behavior_test_runs WHERE run_id = ?", (run_id,),
        ).fetchone()
        if not row:
            return None
        return {**dict(row), "results": json.loads(row["results"]),
                "summary": json.loads(row["summary"]),
                "agent_ids": json.loads(row["agent_ids"])}

    def get_suite_history(self, suite_id: str, limit: int = 20) -> List[dict]:
        """Get run history for a suite, newest first."""
        rows = self._persistence.conn.execute(
            "SELECT run_id, suite_id, agent_ids, summary, started_at, completed_at "
            "FROM behavior_test_runs WHERE suite_id = ? ORDER BY started_at DESC LIMIT ?",
            (suite_id, limit),
        ).fetchall()
        return [{**dict(r), "summary": json.loads(r["summary"]),
                 "agent_ids": json.loads(r["agent_ids"])} for r in rows]

    @staticmethod
    def _evaluate(response: str, case: dict) -> tuple:
        """Evaluate a response against expected keywords and exclusions."""
        if not response.strip():
            return False, {"reason": "empty_response"}
        lower = response.lower()
        missing = [kw for kw in case.get("expected_keywords", []) if kw.lower() not in lower]
        forbidden = [kw for kw in case.get("must_not_contain", []) if kw.lower() in lower]
        passed = not missing and not forbidden
        return passed, {"missing_keywords": missing, "forbidden_found": forbidden}
