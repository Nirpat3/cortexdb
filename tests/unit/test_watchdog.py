"""Unit tests for Watchdog (P2.1)."""

import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from cortexdb.core.watchdog import Watchdog


class TestWatchdog:
    def test_init(self):
        wd = Watchdog(db=MagicMock())
        assert wd._running is False

    @pytest.mark.asyncio
    async def test_start_stop(self):
        wd = Watchdog(db=MagicMock())
        await wd.start()
        assert wd._running is True
        await wd.stop()
        assert wd._running is False

    def test_get_status_before_start(self):
        wd = Watchdog(db=MagicMock())
        status = wd.get_status()
        assert "running" in status
        assert status["running"] is False

    @pytest.mark.asyncio
    async def test_get_status_after_start(self):
        wd = Watchdog(db=MagicMock())
        await wd.start()
        status = wd.get_status()
        assert status["running"] is True
        await wd.stop()

    def test_circuits_wiring(self):
        wd = Watchdog(db=MagicMock())
        circuits = MagicMock()
        wd._circuits = circuits
        assert wd._circuits is circuits
