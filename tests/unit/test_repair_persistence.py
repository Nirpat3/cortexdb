"""Unit tests for RepairEngine session persistence (P2.3)."""

import asyncio
import time
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from contextlib import asynccontextmanager
from cortexdb.grid.repair_engine import (
    RepairEngine, RepairSession, RepairLevel, RepairAttempt,
)
from cortexdb.grid.state_machine import NodeState


class FakeStateMachine:
    """Minimal state machine for testing repair engine."""

    def __init__(self):
        self._nodes = {}

    def add_node(self, node_id, state=NodeState.QUARANTINE):
        node = MagicMock()
        node.state = state
        node.repair_attempts = []
        node.metadata = {}
        self._nodes[node_id] = node

    def get_node(self, node_id):
        return self._nodes.get(node_id)

    def transition(self, node_id, state, reason=""):
        if node_id in self._nodes:
            self._nodes[node_id].state = state


def make_fake_pool(conn):
    """Create a fake asyncpg pool with proper async context manager."""
    pool = MagicMock()

    @asynccontextmanager
    async def fake_acquire():
        yield conn

    pool.acquire = fake_acquire
    return pool


class TestRepairSessionPersistence:
    def test_init_with_db_pool(self):
        sm = FakeStateMachine()
        pool = MagicMock()
        engine = RepairEngine(sm, db_pool=pool)
        assert engine._db_pool is pool

    def test_init_without_db_pool(self):
        sm = FakeStateMachine()
        engine = RepairEngine(sm)
        assert engine._db_pool is None

    @pytest.mark.asyncio
    async def test_persist_session_noop_without_pool(self):
        sm = FakeStateMachine()
        engine = RepairEngine(sm, db_pool=None)
        session = RepairSession(node_id="test-node")
        # Should not raise
        await engine._persist_session(session)

    @pytest.mark.asyncio
    async def test_persist_session_calls_db(self):
        sm = FakeStateMachine()
        conn = AsyncMock()
        pool = make_fake_pool(conn)
        engine = RepairEngine(sm, db_pool=pool)

        session = RepairSession(node_id="node-1", starting_level=RepairLevel.L1_SOFT_RESTART)
        session.attempts.append(RepairAttempt(
            level=RepairLevel.L1_SOFT_RESTART,
            started_at=time.time(),
            completed_at=time.time(),
            success=True,
        ))
        await engine._persist_session(session)
        conn.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_repair_persists_session(self):
        sm = FakeStateMachine()
        sm.add_node("node-1", NodeState.QUARANTINE)

        conn = AsyncMock()
        pool = make_fake_pool(conn)

        engine = RepairEngine(sm, db_pool=pool)

        async def quick_fix(node):
            return True
        engine.register_handler(RepairLevel.L1_SOFT_RESTART, quick_fix)

        session = await engine.start_repair("node-1")
        assert session.final_result == "repaired"
        # Should have been called multiple times (initial + after attempt + on completion)
        assert conn.execute.call_count >= 2

    @pytest.mark.asyncio
    async def test_cancel_repair_persists(self):
        sm = FakeStateMachine()
        conn = AsyncMock()
        pool = make_fake_pool(conn)

        engine = RepairEngine(sm, db_pool=pool)
        session = RepairSession(node_id="node-2")
        engine._active_sessions["node-2"] = session

        await engine.cancel_repair("node-2", "self_healed")
        assert "node-2" not in engine._active_sessions
        conn.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_resume_incomplete_sessions(self):
        sm = FakeStateMachine()
        sm.add_node("node-resume", NodeState.QUARANTINE)

        conn = AsyncMock()
        conn.fetch.return_value = [
            {"node_id": "node-resume", "starting_level": 1},
        ]
        pool = make_fake_pool(conn)

        engine = RepairEngine(sm, db_pool=pool)

        async def quick_fix(node):
            return True
        engine.register_handler(RepairLevel.L1_SOFT_RESTART, quick_fix)

        resumed = await engine.resume_incomplete_sessions()
        assert "node-resume" in resumed
