"""Unit tests for CollaborationManager — sessions, rounds, synthesis."""

import pytest
from unittest.mock import MagicMock, AsyncMock


class FakePersistence:
    def __init__(self):
        self._store = {}

    def kv_get(self, key, default=None):
        return self._store.get(key, default)

    def kv_set(self, key, value):
        self._store[key] = value


def make_team_mock():
    team = MagicMock()
    agents = {
        "a-1": {"agent_id": "a-1", "name": "Architect", "title": "Lead Architect",
                "department": "engineering", "system_prompt": "You are an architect.",
                "llm_provider": "ollama", "llm_model": ""},
        "a-2": {"agent_id": "a-2", "name": "QA Lead", "title": "Quality Analyst",
                "department": "qa", "system_prompt": "You are a QA analyst.",
                "llm_provider": "ollama", "llm_model": ""},
        "a-3": {"agent_id": "a-3", "name": "Security", "title": "Security Analyst",
                "department": "security", "system_prompt": "You are a security analyst.",
                "llm_provider": "ollama", "llm_model": ""},
    }
    team.get_agent = lambda aid: agents.get(aid)
    return team


@pytest.fixture
def collab():
    from cortexdb.superadmin.collaboration import CollaborationManager
    team = make_team_mock()
    router = MagicMock()
    router.chat = AsyncMock(return_value={
        "success": True, "message": "Here is my contribution.", "model": "test",
    })
    memory = MagicMock()
    memory.add_turn = MagicMock()
    persistence = FakePersistence()
    return CollaborationManager(team, router, memory, persistence)


class TestCreateSession:
    def test_create_valid(self, collab):
        result = collab.create_session("Review the code", ["a-1", "a-2"])
        assert result["session_id"].startswith("collab-")
        assert result["status"] == "active"
        assert len(result["agent_ids"]) == 2

    def test_create_with_coordinator(self, collab):
        result = collab.create_session("Plan sprint", ["a-1", "a-2", "a-3"], "a-3")
        assert result["coordinator_id"] == "a-3"

    def test_create_needs_2_agents(self, collab):
        result = collab.create_session("Solo task", ["a-1"])
        assert "error" in result

    def test_create_filters_invalid_agents(self, collab):
        result = collab.create_session("Task", ["a-1", "fake-agent", "a-2"])
        assert len(result["agent_ids"]) == 2  # fake-agent filtered out

    def test_create_fails_if_too_few_valid(self, collab):
        result = collab.create_session("Task", ["a-1", "fake-1", "fake-2"])
        assert "error" in result


class TestRunRound:
    @pytest.mark.asyncio
    async def test_run_round(self, collab):
        session = collab.create_session("Review code", ["a-1", "a-2"])
        result = await collab.run_round(session["session_id"])
        assert result["turn_count"] == 2  # One per agent
        assert result["turns"][0]["agent_id"] == "a-1"
        assert result["turns"][1]["agent_id"] == "a-2"

    @pytest.mark.asyncio
    async def test_run_multiple_rounds(self, collab):
        session = collab.create_session("Plan", ["a-1", "a-2"])
        result = await collab.run_round(session["session_id"], rounds=2)
        assert result["turn_count"] == 4

    @pytest.mark.asyncio
    async def test_run_invalid_session(self, collab):
        result = await collab.run_round("nonexistent")
        assert "error" in result


class TestSynthesize:
    @pytest.mark.asyncio
    async def test_synthesize(self, collab):
        session = collab.create_session("Review code", ["a-1", "a-2"])
        await collab.run_round(session["session_id"])
        result = await collab.synthesize(session["session_id"])
        assert result["status"] == "completed"
        assert result["synthesis"]

    @pytest.mark.asyncio
    async def test_synthesize_empty(self, collab):
        session = collab.create_session("Review", ["a-1", "a-2"])
        result = await collab.synthesize(session["session_id"])
        assert "error" in result


class TestSessionManagement:
    def test_list_sessions(self, collab):
        collab.create_session("Task 1", ["a-1", "a-2"])
        collab.create_session("Task 2", ["a-2", "a-3"])
        sessions = collab.get_all_sessions()
        assert len(sessions) == 2

    def test_close_session(self, collab):
        session = collab.create_session("Task", ["a-1", "a-2"])
        result = collab.close_session(session["session_id"])
        assert result["status"] == "closed"

    def test_filter_by_status(self, collab):
        s1 = collab.create_session("Active", ["a-1", "a-2"])
        collab.create_session("Also active", ["a-2", "a-3"])
        collab.close_session(s1["session_id"])
        active = collab.get_all_sessions(status="active")
        assert len(active) == 1


class TestSharedContext:
    def test_context_includes_goal(self, collab):
        from cortexdb.superadmin.collaboration import CollaborationSession
        session = CollaborationSession("s-1", "Fix the bug", ["a-1", "a-2"])
        ctx = session.get_shared_context()
        assert "Fix the bug" in ctx

    def test_context_includes_turns(self, collab):
        from cortexdb.superadmin.collaboration import CollaborationSession
        session = CollaborationSession("s-1", "Goal", ["a-1"])
        session.turns.append({
            "agent_id": "a-1", "agent_name": "Architect", "content": "My analysis says..."
        })
        ctx = session.get_shared_context()
        assert "My analysis says" in ctx
