"""Tests for Ops Learning Loop — config store + safe range validation."""

from __future__ import annotations

import json
import pytest

from cortexdb.core.ops_learning.config_store import (
    ConfigStore,
    SafeRange,
    DEFAULT_CONFIG,
    SAFE_RANGES,
)
from cortexdb.core.ops_learning.signals import OpsSignalEmitter


# ---------------------------------------------------------------------------
# SafeRange unit tests
# ---------------------------------------------------------------------------

class TestSafeRange:
    def test_numeric_within_range(self):
        sr = SafeRange(min_val=10, max_val=100)
        assert sr.validate(50) is True

    def test_numeric_below_min(self):
        sr = SafeRange(min_val=10, max_val=100)
        assert sr.validate(5) is False

    def test_numeric_above_max(self):
        sr = SafeRange(min_val=10, max_val=100)
        assert sr.validate(200) is False

    def test_numeric_at_boundaries(self):
        sr = SafeRange(min_val=10, max_val=100)
        assert sr.validate(10) is True
        assert sr.validate(100) is True

    def test_enum_valid(self):
        sr = SafeRange(allowed_values=["a", "b", "c"])
        assert sr.validate("b") is True

    def test_enum_invalid(self):
        sr = SafeRange(allowed_values=["a", "b", "c"])
        assert sr.validate("z") is False

    def test_clamp_below(self):
        sr = SafeRange(min_val=10, max_val=100)
        assert sr.clamp(5) == 10

    def test_clamp_above(self):
        sr = SafeRange(min_val=10, max_val=100)
        assert sr.clamp(200) == 100

    def test_clamp_within(self):
        sr = SafeRange(min_val=10, max_val=100)
        assert sr.clamp(50) == 50

    def test_no_bounds_anything_valid(self):
        sr = SafeRange()
        assert sr.validate(999999) is True
        assert sr.validate(-999999) is True

    def test_only_min(self):
        sr = SafeRange(min_val=0)
        assert sr.validate(-1) is False
        assert sr.validate(0) is True
        assert sr.validate(999) is True

    def test_only_max(self):
        sr = SafeRange(max_val=100)
        assert sr.validate(101) is False
        assert sr.validate(100) is True
        assert sr.validate(-999) is True


# ---------------------------------------------------------------------------
# Default config sanity
# ---------------------------------------------------------------------------

class TestDefaultConfig:
    def test_all_defaults_within_safe_ranges(self):
        for key, spec in DEFAULT_CONFIG.items():
            sr = SAFE_RANGES[key]
            assert sr.validate(spec["value"]), f"Default for {key} is outside safe range"

    def test_safe_ranges_have_all_default_keys(self):
        assert set(SAFE_RANGES.keys()) == set(DEFAULT_CONFIG.keys())


# ---------------------------------------------------------------------------
# ConfigStore (no Redis/Postgres — pure in-memory fallback)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestConfigStoreNoBackend:
    """Test ConfigStore with no Redis or Postgres (fallback to defaults)."""

    async def test_get_returns_default(self):
        store = ConfigStore()
        val = await store.get("cache.ttl_seconds")
        assert val == 300

    async def test_get_unknown_returns_none(self):
        store = ConfigStore()
        val = await store.get("nonexistent")
        assert val is None

    async def test_get_all_returns_defaults(self):
        store = ConfigStore()
        all_cfg = await store.get_all()
        assert "cache.ttl_seconds" in all_cfg
        assert all_cfg["cache.ttl_seconds"] == 300


# ---------------------------------------------------------------------------
# ConfigStore with fake Redis
# ---------------------------------------------------------------------------

class FakeRedis:
    """Minimal async Redis mock for testing."""

    def __init__(self):
        self._data: dict[str, dict[str, str]] = {}

    async def hexists(self, key, field):
        return field in self._data.get(key, {})

    async def hget(self, key, field):
        return self._data.get(key, {}).get(field)

    async def hset(self, key, field, value):
        self._data.setdefault(key, {})[field] = value

    async def hgetall(self, key):
        return dict(self._data.get(key, {}))

    async def delete(self, key):
        self._data.pop(key, None)

    def pipeline(self):
        return FakePipeline(self)

    async def xadd(self, stream, fields):
        return "fake-id"


class FakePipeline:
    def __init__(self, redis: FakeRedis):
        self._redis = redis
        self._ops = []

    def delete(self, key):
        self._ops.append(("delete", key))
        return self

    def hset(self, key, field, value):
        self._ops.append(("hset", key, field, value))
        return self

    async def execute(self):
        for op in self._ops:
            if op[0] == "delete":
                await self._redis.delete(op[1])
            elif op[0] == "hset":
                await self._redis.hset(op[1], op[2], op[3])


class _Collected:
    """Collects emitted signals for assertions."""
    def __init__(self):
        self.signals = []

    async def emit(self, signal_type, payload):
        self.signals.append((signal_type, payload))
        return "fake-id"


@pytest.fixture
def fake_redis():
    return FakeRedis()


@pytest.fixture
def collected_emitter():
    return _Collected()


@pytest.mark.asyncio
class TestConfigStoreWithRedis:

    async def test_set_and_get(self, fake_redis):
        store = ConfigStore(redis_client=fake_redis)
        await store.connect()
        await store.set("cache.ttl_seconds", 120)
        val = await store.get("cache.ttl_seconds")
        assert val == 120

    async def test_set_rejects_out_of_range(self, fake_redis):
        store = ConfigStore(redis_client=fake_redis)
        await store.connect()
        with pytest.raises(ValueError, match="outside safe range"):
            await store.set("cache.ttl_seconds", 10)  # min is 60

    async def test_set_rejects_above_max(self, fake_redis):
        store = ConfigStore(redis_client=fake_redis)
        await store.connect()
        with pytest.raises(ValueError, match="outside safe range"):
            await store.set("cache.ttl_seconds", 99999)  # max is 3600

    async def test_set_emits_signal(self, fake_redis):
        emitter = _Collected()
        store = ConfigStore(redis_client=fake_redis, signal_emitter=emitter)
        await store.connect()
        await store.set("cache.ttl_seconds", 120)
        assert len(emitter.signals) == 1
        sig_type, payload = emitter.signals[0]
        assert sig_type == "ops.config_change"
        assert payload["key"] == "cache.ttl_seconds"
        assert payload["new"] == 120

    async def test_defaults_loaded_on_connect(self, fake_redis):
        store = ConfigStore(redis_client=fake_redis)
        await store.connect()
        val = await store.get("query.timeout_ms")
        assert val == 5000

    async def test_get_all(self, fake_redis):
        store = ConfigStore(redis_client=fake_redis)
        await store.connect()
        all_cfg = await store.get_all()
        assert len(all_cfg) >= len(DEFAULT_CONFIG)

    async def test_custom_safe_range(self, fake_redis):
        custom = {"my.key": SafeRange(min_val=1, max_val=10)}
        store = ConfigStore(redis_client=fake_redis, safe_ranges=custom)
        await store.set("my.key", 5)
        with pytest.raises(ValueError):
            await store.set("my.key", 99)


# ---------------------------------------------------------------------------
# OpsSignalEmitter (no backend)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestOpsSignalEmitterNoBackend:
    async def test_emit_without_backend_returns_none(self):
        emitter = OpsSignalEmitter()
        result = await emitter.emit("ops.latency", {"p95": 100})
        assert result is None

    async def test_read_recent_without_backend(self):
        emitter = OpsSignalEmitter()
        result = await emitter.read_recent()
        assert result == []
