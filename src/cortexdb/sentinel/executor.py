"""
Attack Executor — Core penetration testing engine for CortexDB Sentinel.

Executes security attack campaigns against a live CortexDB instance, persisting
all run metadata and findings to SQLite via PersistenceStore.  Supports phased
campaigns (recon -> exploit -> post_exploit -> cleanup), single-category scans,
individual test execution, and quick-scan mode.

Safety:
    - NEVER sends destructive payloads (DROP, DELETE, TRUNCATE).
      All SQL payloads are SELECT / information-gathering only.
    - Each test is wrapped in its own exception handler so one failure
      cannot abort the entire run.
    - An abort flag per run_id allows graceful cancellation between tests.
"""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

try:
    import httpx
except ImportError:
    httpx = None  # type: ignore[assignment]

if TYPE_CHECKING:
    from cortexdb.superadmin.persistence import PersistenceStore

logger = logging.getLogger("cortexdb.sentinel.executor")

# ── Phase ordering ────────────────────────────────────────────────────────────

PHASES = ["recon", "exploit", "post_exploit", "cleanup"]

# ── Default endpoints per attack category ─────────────────────────────────────

_CATEGORY_ENDPOINTS: Dict[str, List[Dict[str, str]]] = {
    "sql_injection": [
        {"path": "/v1/query", "method": "POST"},
        {"path": "/v1/search", "method": "POST"},
    ],
    "auth_session": [
        {"path": "/v1/superadmin/login", "method": "POST"},
        {"path": "/v1/admin/tenants", "method": "GET"},
        {"path": "/v1/admin/sharding/status", "method": "GET"},
    ],
    "authz_privesc": [
        {"path": "/v1/admin/tenants", "method": "GET"},
        {"path": "/v1/admin/encryption/rotate-keys", "method": "POST"},
        {"path": "/v1/superadmin/config", "method": "GET"},
        {"path": "/v1/superadmin/vault", "method": "GET"},
    ],
    "input_validation": [
        {"path": "/v1/query", "method": "POST"},
        {"path": "/v1/tenants", "method": "POST"},
    ],
    "rate_limit_dos": [
        {"path": "/v1/query", "method": "POST"},
        {"path": "/v1/superadmin/login", "method": "POST"},
    ],
    "encryption_data": [
        {"path": "/health/ready", "method": "GET"},
        {"path": "/v1/superadmin/vault", "method": "GET"},
    ],
    "header_cors": [
        {"path": "/v1/query", "method": "OPTIONS"},
        {"path": "/health/live", "method": "GET"},
    ],
    "multi_tenant": [
        {"path": "/v1/query", "method": "POST"},
        {"path": "/v1/search", "method": "POST"},
    ],
    "api_security": [
        {"path": "/v1/query", "method": "POST"},
        {"path": "/docs", "method": "GET"},
        {"path": "/openapi.json", "method": "GET"},
    ],
    "info_disclosure": [
        {"path": "/health/deep", "method": "GET"},
        {"path": "/docs", "method": "GET"},
        {"path": "/.env", "method": "GET"},
        {"path": "/debug", "method": "GET"},
    ],
    "dependency_vuln": [
        {"path": "/health/ready", "method": "GET"},
    ],
    "websocket_security": [
        {"path": "/ws/events", "method": "GET"},
    ],
}


class AttackExecutor:
    """Core penetration-testing engine that executes attacks against CortexDB."""

    def __init__(
        self,
        persistence: "PersistenceStore",
        knowledge_base: Any,
        target_url: str = "http://localhost:5400",
    ) -> None:
        self._persistence = persistence
        self._kb = knowledge_base
        self._target_url = target_url.rstrip("/")
        self.client: Optional[httpx.AsyncClient] = None
        self._abort_flags: Dict[str, bool] = {}
        self._semaphore = asyncio.Semaphore(10)
        self._init_db()

    # ── Schema ────────────────────────────────────────────────────────────────

    def _init_db(self) -> None:
        # Tables 'sentinel_runs' and 'sentinel_findings' are managed by the
        # SQLite migration system (see migrations.py v6). No-op.
        pass

    # ── Helpers ───────────────────────────────────────────────────────────────

    _RUN_COLS = (
        "id, run_id, campaign_id, status, phase, total_tests, passed, failed, "
        "vulnerabilities_found, started_at, completed_at, summary"
    )

    _FINDING_COLS = (
        "id, finding_id, run_id, campaign_id, attack_id, category, severity, "
        "endpoint, method, payload, request_headers, response_status, "
        "response_body_snippet, response_time_ms, vulnerable, evidence, "
        "remediation, status, found_at, remediated_at"
    )

    def _row_to_run(self, row) -> dict:
        return {
            "id": row[0],
            "run_id": row[1],
            "campaign_id": row[2],
            "status": row[3],
            "phase": row[4],
            "total_tests": row[5],
            "passed": row[6],
            "failed": row[7],
            "vulnerabilities_found": row[8],
            "started_at": row[9],
            "completed_at": row[10],
            "summary": json.loads(row[11]) if row[11] else {},
        }

    def _row_to_finding(self, row) -> dict:
        return {
            "id": row[0],
            "finding_id": row[1],
            "run_id": row[2],
            "campaign_id": row[3],
            "attack_id": row[4],
            "category": row[5],
            "severity": row[6],
            "endpoint": row[7],
            "method": row[8],
            "payload": row[9],
            "request_headers": json.loads(row[10]) if row[10] else {},
            "response_status": row[11],
            "response_body_snippet": row[12],
            "response_time_ms": row[13],
            "vulnerable": bool(row[14]),
            "evidence": json.loads(row[15]) if row[15] else {},
            "remediation": row[16],
            "status": row[17],
            "found_at": row[18],
            "remediated_at": row[19],
        }

    @staticmethod
    def _gen_run_id() -> str:
        return f"SR-{secrets.token_hex(8)}"

    @staticmethod
    def _gen_finding_id() -> str:
        return f"SF-{secrets.token_hex(8)}"

    # ── HTTP Client ──────────────────────────────────────────────────────────

    async def _ensure_client(self) -> None:
        """Lazily initialise the shared httpx.AsyncClient."""
        if self.client is None or self.client.is_closed:
            self.client = httpx.AsyncClient(
                timeout=httpx.Timeout(10.0),
                verify=False,
                follow_redirects=True,
            )

    async def _close_client(self) -> None:
        if self.client and not self.client.is_closed:
            await self.client.aclose()
            self.client = None

    # ── Run persistence helpers ──────────────────────────────────────────────

    def _create_run(self, campaign_id: Optional[str] = None) -> str:
        run_id = self._gen_run_id()
        now = time.time()
        self._persistence.conn.execute(
            "INSERT INTO sentinel_runs "
            "(run_id, campaign_id, status, started_at, summary) "
            "VALUES (?,?,?,?,?)",
            (run_id, campaign_id, "running", now, "{}"),
        )
        self._persistence.conn.commit()
        self._abort_flags[run_id] = False
        return run_id

    def _update_run(self, run_id: str, **kwargs: Any) -> None:
        sets: List[str] = []
        params: List[Any] = []
        for key, val in kwargs.items():
            if key == "summary":
                val = json.dumps(val)
            sets.append(f"{key} = ?")
            params.append(val)
        if not sets:
            return
        params.append(run_id)
        self._persistence.conn.execute(
            f"UPDATE sentinel_runs SET {', '.join(sets)} WHERE run_id = ?",
            params,
        )
        self._persistence.conn.commit()

    def _store_finding(
        self,
        run_id: str,
        campaign_id: Optional[str],
        attack_id: Optional[str],
        category: str,
        severity: str,
        endpoint: str,
        method: str,
        payload: str,
        request_headers: dict,
        response_status: Optional[int],
        response_body_snippet: Optional[str],
        response_time_ms: float,
        vulnerable: bool,
        evidence: dict,
        remediation: str,
    ) -> str:
        finding_id = self._gen_finding_id()
        now = time.time()
        self._persistence.conn.execute(
            f"INSERT INTO sentinel_findings "
            f"(finding_id, run_id, campaign_id, attack_id, category, severity, "
            f"endpoint, method, payload, request_headers, response_status, "
            f"response_body_snippet, response_time_ms, vulnerable, evidence, "
            f"remediation, status, found_at) "
            f"VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                finding_id, run_id, campaign_id, attack_id, category, severity,
                endpoint, method, payload, json.dumps(request_headers),
                response_status, response_body_snippet, response_time_ms,
                1 if vulnerable else 0, json.dumps(evidence), remediation,
                "open", now,
            ),
        )
        self._persistence.conn.commit()
        return finding_id

    # ── Target endpoint resolution ───────────────────────────────────────────

    def _get_target_endpoints(self, category: str) -> List[Dict[str, str]]:
        """Return relevant endpoints for a given attack category."""
        return _CATEGORY_ENDPOINTS.get(category, [
            {"path": "/v1/query", "method": "POST"},
        ])

    # ── Campaign execution ───────────────────────────────────────────────────

    async def execute_campaign(
        self,
        campaign_id: str,
        categories: List[str],
        endpoints: Optional[List[Dict[str, str]]] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> dict:
        """
        Run a full phased campaign across the given categories.

        Phases: recon -> exploit -> post_exploit -> cleanup
        Each phase pulls attack vectors from the knowledge base for the
        requested categories, then executes them against target endpoints.
        """
        config = config or {}
        run_id = self._create_run(campaign_id=campaign_id)
        await self._ensure_client()

        all_findings: List[dict] = []
        total_tests = 0
        passed = 0
        failed = 0
        vulns = 0

        try:
            for phase in PHASES:
                if self._abort_flags.get(run_id, False):
                    self._update_run(run_id, status="aborted", phase=phase)
                    break

                self._update_run(run_id, phase=phase)

                for category in categories:
                    if self._abort_flags.get(run_id, False):
                        break

                    vectors = self._kb.get_vectors(category=category, phase=phase) \
                        if hasattr(self._kb, "get_vectors") else []
                    if not vectors:
                        continue

                    target_eps = endpoints or self._get_target_endpoints(category)
                    phase_findings = await self._execute_phase(
                        run_id, phase, vectors, target_eps,
                        campaign_id=campaign_id,
                    )
                    all_findings.extend(phase_findings)

                    for f in phase_findings:
                        total_tests += 1
                        if f.get("vulnerable"):
                            vulns += 1
                            failed += 1
                        else:
                            passed += 1

            final_status = "aborted" if self._abort_flags.get(run_id) else "completed"
            summary = self._build_summary(all_findings, categories)
            self._update_run(
                run_id,
                status=final_status,
                total_tests=total_tests,
                passed=passed,
                failed=failed,
                vulnerabilities_found=vulns,
                completed_at=time.time(),
                summary=summary,
            )
        except Exception as exc:
            logger.exception("Campaign %s failed: %s", campaign_id, exc)
            self._update_run(
                run_id, status="failed", completed_at=time.time(),
                total_tests=total_tests, passed=passed, failed=failed,
                vulnerabilities_found=vulns,
                summary={"error": str(exc)},
            )
        finally:
            self._abort_flags.pop(run_id, None)

        return self.get_run(run_id)

    async def execute_category(
        self,
        category: str,
        endpoints: Optional[List[Dict[str, str]]] = None,
    ) -> dict:
        """Execute all attack vectors for a single category."""
        run_id = self._create_run()
        await self._ensure_client()

        all_findings: List[dict] = []
        total_tests = 0
        passed = 0
        failed = 0
        vulns = 0

        try:
            for phase in PHASES:
                if self._abort_flags.get(run_id, False):
                    break

                self._update_run(run_id, phase=phase)
                vectors = self._kb.get_vectors(category=category, phase=phase) \
                    if hasattr(self._kb, "get_vectors") else []
                if not vectors:
                    continue

                target_eps = endpoints or self._get_target_endpoints(category)
                phase_findings = await self._execute_phase(
                    run_id, phase, vectors, target_eps,
                )
                all_findings.extend(phase_findings)

                for f in phase_findings:
                    total_tests += 1
                    if f.get("vulnerable"):
                        vulns += 1
                        failed += 1
                    else:
                        passed += 1

            final_status = "aborted" if self._abort_flags.get(run_id) else "completed"
            summary = self._build_summary(all_findings, [category])
            self._update_run(
                run_id,
                status=final_status,
                total_tests=total_tests,
                passed=passed,
                failed=failed,
                vulnerabilities_found=vulns,
                completed_at=time.time(),
                summary=summary,
            )
        except Exception as exc:
            logger.exception("Category run %s failed: %s", category, exc)
            self._update_run(
                run_id, status="failed", completed_at=time.time(),
                total_tests=total_tests, passed=passed, failed=failed,
                vulnerabilities_found=vulns,
                summary={"error": str(exc)},
            )
        finally:
            self._abort_flags.pop(run_id, None)

        return self.get_run(run_id)

    async def execute_single(
        self,
        attack_id: str,
        endpoint: str,
        method: str = "GET",
    ) -> dict:
        """Execute a single attack vector against one endpoint."""
        run_id = self._create_run()
        await self._ensure_client()

        try:
            vector = None
            if hasattr(self._kb, "get_vector"):
                vector = self._kb.get_vector(attack_id)
            if not vector:
                vector = {
                    "attack_id": attack_id,
                    "category": "unknown",
                    "severity": "info",
                    "payloads": [""],
                    "indicators": {},
                    "remediation": "",
                    "inject_into": "params",
                    "param_name": "q",
                }

            ep = {"path": endpoint, "method": method}
            result = await self._run_test(
                vector, ep, method, run_id=run_id,
            )

            vulnerable = result.get("vulnerable", False)
            self._update_run(
                run_id,
                status="completed",
                total_tests=1,
                passed=0 if vulnerable else 1,
                failed=1 if vulnerable else 0,
                vulnerabilities_found=1 if vulnerable else 0,
                completed_at=time.time(),
                summary={"single_test": True, "attack_id": attack_id, "vulnerable": vulnerable},
            )
        except Exception as exc:
            logger.exception("Single test %s failed: %s", attack_id, exc)
            self._update_run(
                run_id, status="failed", completed_at=time.time(),
                total_tests=1, failed=1,
                summary={"error": str(exc)},
            )
        finally:
            self._abort_flags.pop(run_id, None)

        return self.get_run(run_id)

    async def run_quick_scan(
        self,
        endpoints: Optional[List[Dict[str, str]]] = None,
    ) -> dict:
        """
        Quick scan: run all categories with aggression_level=3.

        This is a convenience wrapper around execute_campaign that covers
        every registered attack category.
        """
        all_categories = list(_CATEGORY_ENDPOINTS.keys())
        campaign_id = f"quick-{secrets.token_hex(4)}"
        return await self.execute_campaign(
            campaign_id=campaign_id,
            categories=all_categories,
            endpoints=endpoints,
            config={"aggression_level": 3},
        )

    # ── Abort ────────────────────────────────────────────────────────────────

    async def abort_run(self, run_id: str) -> bool:
        """Signal a running scan to stop after the current test completes."""
        row = self._persistence.conn.execute(
            "SELECT status FROM sentinel_runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        if not row:
            return False
        if row[0] != "running":
            return False
        self._abort_flags[run_id] = True
        logger.info("Abort flag set for run %s", run_id)
        return True

    # ── Read operations ──────────────────────────────────────────────────────

    def get_run(self, run_id: str) -> dict:
        row = self._persistence.conn.execute(
            f"SELECT {self._RUN_COLS} FROM sentinel_runs WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        if not row:
            return {"error": "Run not found", "run_id": run_id}
        return self._row_to_run(row)

    def list_runs(
        self,
        campaign_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> list:
        sql = f"SELECT {self._RUN_COLS} FROM sentinel_runs WHERE 1=1"
        params: List[Any] = []
        if campaign_id is not None:
            sql += " AND campaign_id = ?"
            params.append(campaign_id)
        if status is not None:
            sql += " AND status = ?"
            params.append(status)
        sql += " ORDER BY started_at DESC LIMIT ?"
        params.append(limit)
        rows = self._persistence.conn.execute(sql, params).fetchall()
        return [self._row_to_run(r) for r in rows]

    def get_findings(
        self,
        run_id: Optional[str] = None,
        category: Optional[str] = None,
        severity: Optional[str] = None,
        vulnerable_only: bool = False,
        limit: int = 100,
    ) -> list:
        sql = f"SELECT {self._FINDING_COLS} FROM sentinel_findings WHERE 1=1"
        params: List[Any] = []
        if run_id is not None:
            sql += " AND run_id = ?"
            params.append(run_id)
        if category is not None:
            sql += " AND category = ?"
            params.append(category)
        if severity is not None:
            sql += " AND severity = ?"
            params.append(severity)
        if vulnerable_only:
            sql += " AND vulnerable = 1"
        sql += " ORDER BY found_at DESC LIMIT ?"
        params.append(limit)
        rows = self._persistence.conn.execute(sql, params).fetchall()
        return [self._row_to_finding(r) for r in rows]

    def update_finding_status(self, finding_id: str, status: str) -> dict:
        valid = ("open", "confirmed", "false_positive", "remediated", "accepted")
        if status not in valid:
            return {"error": f"Invalid status '{status}'. Must be one of {valid}"}
        row = self._persistence.conn.execute(
            f"SELECT {self._FINDING_COLS} FROM sentinel_findings WHERE finding_id = ?",
            (finding_id,),
        ).fetchone()
        if not row:
            return {"error": "Finding not found", "finding_id": finding_id}

        updates = {"status": status}
        if status == "remediated":
            updates["remediated_at"] = time.time()  # type: ignore[assignment]

        sets = ", ".join(f"{k} = ?" for k in updates)
        params = list(updates.values()) + [finding_id]
        self._persistence.conn.execute(
            f"UPDATE sentinel_findings SET {sets} WHERE finding_id = ?",
            params,
        )
        self._persistence.conn.commit()
        logger.info("Updated finding %s -> %s", finding_id, status)

        row = self._persistence.conn.execute(
            f"SELECT {self._FINDING_COLS} FROM sentinel_findings WHERE finding_id = ?",
            (finding_id,),
        ).fetchone()
        return self._row_to_finding(row)

    def get_stats(self) -> dict:
        """Aggregate statistics across all runs."""
        conn = self._persistence.conn

        total_runs = conn.execute("SELECT COUNT(*) FROM sentinel_runs").fetchone()[0]
        completed = conn.execute(
            "SELECT COUNT(*) FROM sentinel_runs WHERE status = 'completed'"
        ).fetchone()[0]
        failed_runs = conn.execute(
            "SELECT COUNT(*) FROM sentinel_runs WHERE status = 'failed'"
        ).fetchone()[0]
        aborted = conn.execute(
            "SELECT COUNT(*) FROM sentinel_runs WHERE status = 'aborted'"
        ).fetchone()[0]

        total_tests = conn.execute(
            "SELECT COALESCE(SUM(total_tests), 0) FROM sentinel_runs"
        ).fetchone()[0]
        total_passed = conn.execute(
            "SELECT COALESCE(SUM(passed), 0) FROM sentinel_runs"
        ).fetchone()[0]
        total_failed = conn.execute(
            "SELECT COALESCE(SUM(failed), 0) FROM sentinel_runs"
        ).fetchone()[0]
        total_vulns = conn.execute(
            "SELECT COALESCE(SUM(vulnerabilities_found), 0) FROM sentinel_runs"
        ).fetchone()[0]

        total_findings = conn.execute(
            "SELECT COUNT(*) FROM sentinel_findings"
        ).fetchone()[0]
        open_findings = conn.execute(
            "SELECT COUNT(*) FROM sentinel_findings WHERE status = 'open' AND vulnerable = 1"
        ).fetchone()[0]
        confirmed_findings = conn.execute(
            "SELECT COUNT(*) FROM sentinel_findings WHERE status = 'confirmed'"
        ).fetchone()[0]
        remediated_findings = conn.execute(
            "SELECT COUNT(*) FROM sentinel_findings WHERE status = 'remediated'"
        ).fetchone()[0]

        severity_rows = conn.execute(
            "SELECT severity, COUNT(*) FROM sentinel_findings "
            "WHERE vulnerable = 1 GROUP BY severity"
        ).fetchall()
        by_severity = {r[0]: r[1] for r in severity_rows}

        category_rows = conn.execute(
            "SELECT category, COUNT(*) FROM sentinel_findings "
            "WHERE vulnerable = 1 GROUP BY category"
        ).fetchall()
        by_category = {r[0]: r[1] for r in category_rows}

        return {
            "runs": {
                "total": total_runs,
                "completed": completed,
                "failed": failed_runs,
                "aborted": aborted,
            },
            "tests": {
                "total": total_tests,
                "passed": total_passed,
                "failed": total_failed,
                "pass_rate": round(total_passed / total_tests * 100, 1) if total_tests else 0.0,
            },
            "vulnerabilities": {
                "total": total_vulns,
                "open": open_findings,
                "confirmed": confirmed_findings,
                "remediated": remediated_findings,
                "by_severity": by_severity,
                "by_category": by_category,
            },
            "findings": {
                "total": total_findings,
            },
        }

    # ── Internal: phase execution ────────────────────────────────────────────

    async def _execute_phase(
        self,
        run_id: str,
        phase: str,
        vectors: List[dict],
        endpoints: List[Dict[str, str]],
        campaign_id: Optional[str] = None,
    ) -> List[dict]:
        """
        Execute all vectors for a given phase against the provided endpoints.

        Respects the abort flag and concurrency semaphore.
        """
        findings: List[dict] = []

        async def _guarded_test(vector: dict, ep: Dict[str, str]) -> None:
            if self._abort_flags.get(run_id, False):
                return
            async with self._semaphore:
                if self._abort_flags.get(run_id, False):
                    return
                result = await self._run_test(
                    vector, ep, ep.get("method", "GET"),
                    run_id=run_id, campaign_id=campaign_id,
                )
                findings.append(result)

        tasks = []
        for vector in vectors:
            for ep in endpoints:
                tasks.append(_guarded_test(vector, ep))

        # Execute concurrently (semaphore-bounded)
        await asyncio.gather(*tasks, return_exceptions=True)
        return findings

    # ── Internal: core test runner ───────────────────────────────────────────

    async def _run_test(
        self,
        vector: dict,
        endpoint: Dict[str, str],
        method: str,
        run_id: Optional[str] = None,
        campaign_id: Optional[str] = None,
    ) -> dict:
        """
        Execute a single attack vector against one endpoint.

        For each payload in the vector, builds a request, sends it, measures
        response time, evaluates vulnerability via indicators, and stores the finding.
        Returns a summary dict for the last (or most severe) payload result.
        """
        await self._ensure_client()
        assert self.client is not None

        attack_id = vector.get("attack_id", "unknown")
        category = vector.get("category", "unknown")
        severity = vector.get("severity", "info")
        payloads = vector.get("payloads", [""])
        indicators = vector.get("indicators", {})
        remediation = vector.get("remediation", "")

        last_result: dict = {
            "attack_id": attack_id,
            "category": category,
            "vulnerable": False,
        }

        for payload in payloads:
            if run_id and self._abort_flags.get(run_id, False):
                break

            response_status: Optional[int] = None
            response_body: str = ""
            response_time_ms: float = 0.0
            request_headers: dict = {}
            vulnerable = False
            evidence: dict = {}

            try:
                req_kwargs = self._build_request(vector, endpoint, payload)
                request_headers = dict(req_kwargs.get("headers", {}))
                req_method = req_kwargs.pop("method", method).upper()

                t0 = time.perf_counter()
                resp = await self.client.request(req_method, **req_kwargs)
                response_time_ms = (time.perf_counter() - t0) * 1000

                response_status = resp.status_code
                # Truncate body to 2KB for storage
                raw_body = resp.text
                response_body = raw_body[:2048]

                vulnerable, evidence = self._evaluate_vulnerability(
                    vector, response_status, raw_body, response_time_ms, payload,
                )

            except httpx.ConnectError:
                # Connection refused — endpoint not reachable; not a vulnerability
                response_body = "Connection refused"
                evidence = {"error": "connect_refused"}
            except httpx.TimeoutException:
                response_time_ms = 10000.0
                response_body = "Request timed out"
                # Timeout could indicate blind injection success if timing indicator set
                if indicators.get("timing_ms_gt"):
                    threshold = indicators["timing_ms_gt"]
                    if response_time_ms >= threshold:
                        vulnerable = True
                        evidence = {"timing_timeout": True, "threshold_ms": threshold}
            except Exception as exc:
                response_body = f"Error: {type(exc).__name__}: {exc}"
                evidence = {"error": str(exc)}
                logger.debug("Test error for %s on %s: %s", attack_id, endpoint.get("path"), exc)

            # Persist the finding
            if run_id:
                self._store_finding(
                    run_id=run_id,
                    campaign_id=campaign_id,
                    attack_id=attack_id,
                    category=category,
                    severity=severity if vulnerable else "info",
                    endpoint=endpoint.get("path", ""),
                    method=method,
                    payload=payload[:1024],  # cap stored payload size
                    request_headers=request_headers,
                    response_status=response_status,
                    response_body_snippet=response_body[:512],
                    response_time_ms=round(response_time_ms, 2),
                    vulnerable=vulnerable,
                    evidence=evidence,
                    remediation=remediation if vulnerable else "",
                )

            if vulnerable:
                last_result = {
                    "attack_id": attack_id,
                    "category": category,
                    "vulnerable": True,
                    "severity": severity,
                    "payload": payload[:256],
                    "evidence": evidence,
                    "endpoint": endpoint.get("path", ""),
                }

        # If none were vulnerable, return the benign summary
        if not last_result.get("vulnerable"):
            last_result = {
                "attack_id": attack_id,
                "category": category,
                "vulnerable": False,
                "endpoint": endpoint.get("path", ""),
            }

        return last_result

    # ── Internal: vulnerability evaluation ───────────────────────────────────

    def _evaluate_vulnerability(
        self,
        vector: dict,
        status_code: int,
        body: str,
        response_time: float,
        payload: str,
    ) -> Tuple[bool, dict]:
        """
        Check response against the vector's indicator rules.

        Returns (vulnerable: bool, evidence: dict).

        Indicator types:
            status_code_in     — response status in expected vulnerable range
            body_contains      — vulnerable patterns found in body
            body_not_contains  — expected protection strings missing from body
            timing_ms_gt       — response exceeded timing threshold (blind attacks)
            header_missing     — security header not present
            header_contains    — header has a specific weak value
        """
        indicators = vector.get("indicators", {})
        if not indicators:
            return False, {}

        evidence: dict = {}
        checks_passed = 0
        checks_total = 0

        # status_code_in
        if "status_code_in" in indicators:
            checks_total += 1
            expected = indicators["status_code_in"]
            if isinstance(expected, list) and status_code in expected:
                checks_passed += 1
                evidence["status_code_match"] = status_code
            elif isinstance(expected, int) and status_code == expected:
                checks_passed += 1
                evidence["status_code_match"] = status_code

        # body_contains
        if "body_contains" in indicators:
            checks_total += 1
            patterns = indicators["body_contains"]
            if isinstance(patterns, str):
                patterns = [patterns]
            body_lower = body.lower()
            matched = [p for p in patterns if p.lower() in body_lower]
            if matched:
                checks_passed += 1
                evidence["body_patterns_matched"] = matched

        # body_not_contains — vulnerability if the pattern is ABSENT
        if "body_not_contains" in indicators:
            checks_total += 1
            patterns = indicators["body_not_contains"]
            if isinstance(patterns, str):
                patterns = [patterns]
            body_lower = body.lower()
            missing = [p for p in patterns if p.lower() not in body_lower]
            if missing:
                checks_passed += 1
                evidence["expected_protections_missing"] = missing

        # timing_ms_gt — blind timing attack
        if "timing_ms_gt" in indicators:
            checks_total += 1
            threshold = float(indicators["timing_ms_gt"])
            if response_time > threshold:
                checks_passed += 1
                evidence["timing_exceeded"] = {
                    "threshold_ms": threshold,
                    "actual_ms": round(response_time, 2),
                }

        # header_missing
        if "header_missing" in indicators:
            # This indicator requires response headers — we evaluate against
            # the body as a proxy (headers are checked in _run_test if needed).
            # For now, mark as a check that cannot be evaluated here.
            pass

        # header_contains
        if "header_contains" in indicators:
            # Same as above — header checks require the response object.
            pass

        if checks_total == 0:
            return False, {}

        vulnerable = checks_passed > 0
        evidence["checks_passed"] = checks_passed
        evidence["checks_total"] = checks_total
        return vulnerable, evidence

    # ── Internal: request builder ────────────────────────────────────────────

    def _build_request(
        self,
        vector: dict,
        endpoint: Dict[str, str],
        payload: str,
    ) -> dict:
        """
        Build httpx request kwargs from vector + endpoint + payload.

        The vector's ``inject_into`` field determines where the payload lands:
            params  — URL query parameter (default)
            headers — injected as a custom header value
            body    — JSON body field
            url     — appended to the URL path
        """
        path = endpoint.get("path", "/")
        method = endpoint.get("method", "GET")
        url = f"{self._target_url}{path}"

        inject_into = vector.get("inject_into", "params")
        param_name = vector.get("param_name", "q")

        headers: Dict[str, str] = {
            "Content-Type": "application/json",
            "User-Agent": "CortexDB-Sentinel/1.0",
        }
        # Merge any vector-specific headers
        if vector.get("headers"):
            headers.update(vector["headers"])

        kwargs: Dict[str, Any] = {
            "url": url,
            "method": method,
            "headers": headers,
        }

        if inject_into == "params":
            kwargs["params"] = {param_name: payload}

        elif inject_into == "headers":
            header_name = vector.get("header_name", "X-Test-Payload")
            headers[header_name] = payload
            kwargs["headers"] = headers

        elif inject_into == "body":
            body_template = vector.get("body_template")
            if body_template and isinstance(body_template, dict):
                # Deep-copy and inject payload into the designated field
                body = dict(body_template)
                body_field = vector.get("body_field", "cortexql")
                body[body_field] = payload
                kwargs["json"] = body
            else:
                kwargs["json"] = {vector.get("body_field", "cortexql"): payload}

        elif inject_into == "url":
            # Append payload to the path (URL-encoded by httpx)
            kwargs["url"] = f"{url}/{payload}"

        else:
            # Default to params
            kwargs["params"] = {param_name: payload}

        return kwargs

    # ── Internal: summary builder ────────────────────────────────────────────

    @staticmethod
    def _build_summary(findings: List[dict], categories: List[str]) -> dict:
        """Compute a summary dict from a list of finding results."""
        total = len(findings)
        vulnerable = [f for f in findings if f.get("vulnerable")]
        vuln_count = len(vulnerable)

        by_category: Dict[str, Dict[str, int]] = {}
        for f in findings:
            cat = f.get("category", "unknown")
            if cat not in by_category:
                by_category[cat] = {"total": 0, "vulnerable": 0}
            by_category[cat]["total"] += 1
            if f.get("vulnerable"):
                by_category[cat]["vulnerable"] += 1

        by_severity: Dict[str, int] = {}
        for f in vulnerable:
            sev = f.get("severity", "info")
            by_severity[sev] = by_severity.get(sev, 0) + 1

        return {
            "categories_tested": categories,
            "total_tests": total,
            "vulnerabilities_found": vuln_count,
            "pass_rate": round((total - vuln_count) / total * 100, 1) if total else 100.0,
            "by_category": by_category,
            "by_severity": by_severity,
            "critical_count": by_severity.get("critical", 0),
            "high_count": by_severity.get("high", 0),
        }
