"""Unit tests for BaseEngine auto-reconnect (P2.2)."""

import asyncio
import pytest
from cortexdb.engines import BaseEngine


class ConcreteEngine(BaseEngine):
    """Minimal concrete engine for testing reconnect logic."""

    RECONNECT_ERRORS = (ConnectionError, TimeoutError)

    def __init__(self):
        super().__init__()
        self.connect_count = 0
        self.call_count = 0

    async def connect(self):
        self.connect_count += 1

    async def close(self):
        pass

    async def health(self):
        return {"status": "ok"}

    async def write(self, data_type, payload, actor):
        return None


class TestBaseEngineReconnect:
    @pytest.mark.asyncio
    async def test_successful_call_no_retry(self):
        engine = ConcreteEngine()
        # Override delays for fast tests
        engine.RECONNECT_BASE_DELAY = 0.01

        async def success():
            engine.call_count += 1
            return "ok"

        result = await engine._with_reconnect("test", success,
                                               reconnect_errors=engine.RECONNECT_ERRORS)
        assert result == "ok"
        assert engine.call_count == 1

    @pytest.mark.asyncio
    async def test_retry_on_connection_error(self):
        engine = ConcreteEngine()
        engine.RECONNECT_BASE_DELAY = 0.01
        attempts = []

        async def flaky():
            attempts.append(1)
            if len(attempts) < 3:
                raise ConnectionError("connection lost")
            return "recovered"

        result = await engine._with_reconnect("test", flaky,
                                               reconnect_errors=engine.RECONNECT_ERRORS)
        assert result == "recovered"
        assert len(attempts) == 3

    @pytest.mark.asyncio
    async def test_gives_up_after_max_retries(self):
        engine = ConcreteEngine()
        engine.RECONNECT_BASE_DELAY = 0.01

        async def always_fail():
            raise ConnectionError("permanently down")

        with pytest.raises(ConnectionError):
            await engine._with_reconnect("test", always_fail,
                                          reconnect_errors=engine.RECONNECT_ERRORS)

    @pytest.mark.asyncio
    async def test_non_reconnect_error_not_retried(self):
        engine = ConcreteEngine()
        engine.RECONNECT_BASE_DELAY = 0.01
        attempts = []

        async def value_error():
            attempts.append(1)
            raise ValueError("bad input")

        with pytest.raises(ValueError):
            await engine._with_reconnect("test", value_error,
                                          reconnect_errors=engine.RECONNECT_ERRORS)
        assert len(attempts) == 1

    def test_reconnect_stats(self):
        engine = ConcreteEngine()
        stats = engine.reconnect_stats
        assert stats["reconnect_count"] == 0
        assert stats["last_error"] is None
