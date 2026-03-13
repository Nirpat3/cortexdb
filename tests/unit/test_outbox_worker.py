"""Unit tests for OutboxWorker + Supervisor (P1.3)."""

import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock
from cortexdb.core.outbox_worker import OutboxWorker


class TestOutboxWorker:
    def test_init(self):
        pool = MagicMock()
        engines = {"relational": MagicMock(), "memory": MagicMock()}
        worker = OutboxWorker(pool=pool, engines=engines)
        assert worker._running is False

    @pytest.mark.asyncio
    async def test_start_stop(self):
        pool = MagicMock()
        engines = {"relational": MagicMock()}
        worker = OutboxWorker(pool=pool, engines=engines)
        await worker.start()
        assert worker._running is True
        await worker.stop()
        assert worker._running is False

    @pytest.mark.asyncio
    async def test_supervisor_starts_with_worker(self):
        pool = MagicMock()
        engines = {"relational": MagicMock()}
        worker = OutboxWorker(pool=pool, engines=engines)
        await worker.start()
        assert worker._supervisor_task is not None
        assert not worker._supervisor_task.done()
        await worker.stop()

    def test_task_health_property(self):
        pool = MagicMock()
        engines = {}
        worker = OutboxWorker(pool=pool, engines=engines)
        health = worker.task_health
        assert isinstance(health, dict)
        # Before start, all should be "not_started" or similar
        assert "poll" in health
        assert "supervisor" in health
