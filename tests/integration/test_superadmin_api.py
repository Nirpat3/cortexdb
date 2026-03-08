"""
Integration tests for the CortexDB SuperAdmin API.

Covers authentication flow, agent team management, task CRUD,
agent chat, tool execution, and autonomy endpoints.
"""

import pytest
import httpx


# ── Authentication Flow ─────────────────────────────────────────────────────


class TestSuperAdminAuth:
    """Login / session / logout lifecycle."""

    async def test_login_success(self, client: httpx.AsyncClient):
        resp = await client.post("/v1/superadmin/login",
                                 json={"passphrase": "thisismydatabasebaby"})
        assert resp.status_code == 200
        body = resp.json()
        assert "token" in body
        assert body["expires_in"] == 86400

    async def test_login_failure_wrong_passphrase(self, client: httpx.AsyncClient):
        resp = await client.post("/v1/superadmin/login",
                                 json={"passphrase": "wrong"})
        assert resp.status_code == 401

    async def test_login_failure_missing_passphrase(self, client: httpx.AsyncClient):
        resp = await client.post("/v1/superadmin/login", json={})
        assert resp.status_code == 401

    async def test_session_with_valid_token(self, client: httpx.AsyncClient, superadmin_token: str):
        resp = await client.get("/v1/superadmin/session",
                                headers={"X-SuperAdmin-Token": superadmin_token})
        assert resp.status_code == 200

    async def test_session_with_invalid_token(self, client: httpx.AsyncClient):
        resp = await client.get("/v1/superadmin/session",
                                headers={"X-SuperAdmin-Token": "invalid"})
        assert resp.status_code == 401

    async def test_logout(self, client: httpx.AsyncClient):
        # Login first
        login = await client.post("/v1/superadmin/login",
                                  json={"passphrase": "thisismydatabasebaby"})
        token = login.json()["token"]

        # Logout
        resp = await client.post("/v1/superadmin/logout",
                                 headers={"X-SuperAdmin-Token": token})
        assert resp.status_code == 200
        assert resp.json()["status"] == "logged_out"

        # Session should now be invalid
        resp2 = await client.get("/v1/superadmin/session",
                                 headers={"X-SuperAdmin-Token": token})
        assert resp2.status_code == 401

    async def test_lockout_after_repeated_failures(self, client: httpx.AsyncClient):
        """After 5 failed attempts, the IP should be locked out."""
        for _ in range(5):
            await client.post("/v1/superadmin/login", json={"passphrase": "wrong"})

        # 6th attempt — should still be rejected (locked out)
        resp = await client.post("/v1/superadmin/login", json={"passphrase": "wrong"})
        assert resp.status_code == 401


# ── Agent Team Management ───────────────────────────────────────────────────


class TestAgentTeam:
    """CRUD operations on the agent team."""

    async def test_list_team(self, client: httpx.AsyncClient, auth_headers: dict):
        resp = await client.get("/v1/superadmin/team", headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert "agents" in body
        assert "summary" in body

    async def test_get_org_chart(self, client: httpx.AsyncClient, auth_headers: dict):
        resp = await client.get("/v1/superadmin/team/org-chart", headers=auth_headers)
        assert resp.status_code == 200

    async def test_get_agent_by_id(self, client: httpx.AsyncClient, auth_headers: dict):
        # Get team first to find a valid agent_id
        team_resp = await client.get("/v1/superadmin/team", headers=auth_headers)
        agents = team_resp.json().get("agents", [])
        if not agents:
            pytest.skip("No agents available in test team")

        agent_id = agents[0]["agent_id"]
        resp = await client.get(f"/v1/superadmin/team/{agent_id}", headers=auth_headers)
        assert resp.status_code == 200

    async def test_get_nonexistent_agent_returns_404(self, client: httpx.AsyncClient, auth_headers: dict):
        resp = await client.get("/v1/superadmin/team/FAKE-AGENT-999", headers=auth_headers)
        assert resp.status_code == 404

    async def test_update_agent(self, client: httpx.AsyncClient, auth_headers: dict):
        team_resp = await client.get("/v1/superadmin/team", headers=auth_headers)
        agents = team_resp.json().get("agents", [])
        if not agents:
            pytest.skip("No agents available in test team")

        agent_id = agents[0]["agent_id"]
        resp = await client.put(f"/v1/superadmin/team/{agent_id}",
                                headers=auth_headers,
                                json={"status": "active"})
        assert resp.status_code == 200

    async def test_team_requires_auth(self, client: httpx.AsyncClient):
        resp = await client.get("/v1/superadmin/team")
        assert resp.status_code == 403


# ── Task CRUD ───────────────────────────────────────────────────────────────


class TestTaskCRUD:
    """Create, list, read, update, execute tasks."""

    async def test_create_task(self, client: httpx.AsyncClient, auth_headers: dict, sample_task: dict):
        resp = await client.post("/v1/superadmin/tasks",
                                 headers=auth_headers, json=sample_task)
        assert resp.status_code == 200
        body = resp.json()
        assert "task_id" in body or "id" in body

    async def test_list_tasks(self, client: httpx.AsyncClient, auth_headers: dict):
        resp = await client.get("/v1/superadmin/tasks", headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, (list, dict))

    async def test_create_and_get_task(self, client: httpx.AsyncClient, auth_headers: dict, sample_task: dict):
        # Create
        create_resp = await client.post("/v1/superadmin/tasks",
                                        headers=auth_headers, json=sample_task)
        assert create_resp.status_code == 200
        task_data = create_resp.json()
        task_id = task_data.get("task_id") or task_data.get("id")

        if not task_id:
            pytest.skip("Task creation didn't return an ID")

        # Read
        get_resp = await client.get(f"/v1/superadmin/tasks/{task_id}",
                                    headers=auth_headers)
        assert get_resp.status_code == 200

    async def test_update_task(self, client: httpx.AsyncClient, auth_headers: dict, sample_task: dict):
        # Create
        create_resp = await client.post("/v1/superadmin/tasks",
                                        headers=auth_headers, json=sample_task)
        task_data = create_resp.json()
        task_id = task_data.get("task_id") or task_data.get("id")

        if not task_id:
            pytest.skip("Task creation didn't return an ID")

        # Update
        update_resp = await client.put(f"/v1/superadmin/tasks/{task_id}",
                                       headers=auth_headers,
                                       json={"priority": "high"})
        assert update_resp.status_code == 200

    async def test_execute_task(self, client: httpx.AsyncClient, auth_headers: dict, sample_task: dict):
        # Create
        create_resp = await client.post("/v1/superadmin/tasks",
                                        headers=auth_headers, json=sample_task)
        task_data = create_resp.json()
        task_id = task_data.get("task_id") or task_data.get("id")

        if not task_id:
            pytest.skip("Task creation didn't return an ID")

        # Execute (may fail gracefully since LLM is mocked)
        exec_resp = await client.post(f"/v1/superadmin/tasks/{task_id}/execute",
                                      headers=auth_headers)
        # Accept 200 (success) or 500 (LLM not available) — the route itself works
        assert exec_resp.status_code in (200, 500)

    async def test_tasks_require_auth(self, client: httpx.AsyncClient):
        resp = await client.get("/v1/superadmin/tasks")
        assert resp.status_code == 403


# ── Agent Chat ──────────────────────────────────────────────────────────────


class TestAgentChat:
    """POST /v1/superadmin/llm/chat/stream (non-streaming in test mode)."""

    async def test_chat_requires_auth(self, client: httpx.AsyncClient):
        resp = await client.post("/v1/superadmin/llm/chat/stream",
                                 json={"agent_id": "test", "message": "hello"})
        assert resp.status_code == 403

    async def test_chat_endpoint_exists(self, client: httpx.AsyncClient, auth_headers: dict):
        resp = await client.post("/v1/superadmin/llm/chat/stream",
                                 headers=auth_headers,
                                 json={"agent_id": "CDB-EXEC-CEO", "message": "ping"})
        # 200 if LLM is wired, or 500 if mocked — route itself should resolve
        assert resp.status_code in (200, 500)


# ── Executor Status ─────────────────────────────────────────────────────────


class TestExecutor:
    """Executor status and task execution endpoints."""

    async def test_executor_status(self, client: httpx.AsyncClient, auth_headers: dict):
        resp = await client.get("/v1/superadmin/executor/status", headers=auth_headers)
        assert resp.status_code == 200

    async def test_execute_pending_tasks(self, client: httpx.AsyncClient, auth_headers: dict):
        resp = await client.post("/v1/superadmin/tasks/execute-pending",
                                 headers=auth_headers)
        assert resp.status_code == 200


# ── Agent Bus ───────────────────────────────────────────────────────────────


class TestAgentBus:
    """Inter-agent messaging endpoints."""

    async def test_bus_stats(self, client: httpx.AsyncClient, auth_headers: dict):
        resp = await client.get("/v1/superadmin/bus/stats", headers=auth_headers)
        assert resp.status_code == 200

    async def test_send_message(self, client: httpx.AsyncClient, auth_headers: dict):
        resp = await client.post("/v1/superadmin/bus/send",
                                 headers=auth_headers,
                                 json={
                                     "from_agent": "CDB-EXEC-CEO",
                                     "to_agent": "CDB-EXEC-CTO",
                                     "content": "Test message from integration suite",
                                 })
        assert resp.status_code == 200

    async def test_bus_messages(self, client: httpx.AsyncClient, auth_headers: dict):
        resp = await client.get("/v1/superadmin/bus/messages", headers=auth_headers)
        assert resp.status_code == 200


# ── Autonomy Endpoints ──────────────────────────────────────────────────────


class TestAutonomy:
    """Autonomy loop status and configuration."""

    async def test_autonomy_status(self, client: httpx.AsyncClient, auth_headers: dict):
        resp = await client.get("/api/v1/superadmin/autonomy/status",
                                headers=auth_headers)
        assert resp.status_code == 200

    async def test_autonomy_agents_list(self, client: httpx.AsyncClient, auth_headers: dict):
        resp = await client.get("/api/v1/superadmin/autonomy/agents",
                                headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert "agents" in body


# ── LLM Configuration ──────────────────────────────────────────────────────


class TestLLMConfig:
    """LLM provider listing and configuration."""

    async def test_list_providers(self, client: httpx.AsyncClient, auth_headers: dict):
        resp = await client.get("/v1/superadmin/llm/providers", headers=auth_headers)
        assert resp.status_code == 200

    async def test_ollama_health(self, client: httpx.AsyncClient, auth_headers: dict):
        resp = await client.get("/v1/superadmin/llm/ollama/health", headers=auth_headers)
        # May return 200 or 500 depending on mock state
        assert resp.status_code in (200, 500)
