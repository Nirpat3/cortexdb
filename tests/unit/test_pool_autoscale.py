"""Unit tests for Connection Pool Auto-Scaling (P2.4)."""

import time
import pytest
from unittest.mock import MagicMock
from cortexdb.core.pool import ConnectionPoolManager


class TestPoolAutoScale:
    def _make_pool(self):
        """Create a ConnectionPoolManager with mocked internals."""
        pool = ConnectionPoolManager.__new__(ConnectionPoolManager)
        pool._pool = MagicMock()
        pool._pool.get_size.return_value = 10
        pool._pool.get_idle_size.return_value = 5
        pool._pool.get_min_size.return_value = 2
        pool._pool.get_max_size.return_value = 20
        pool._max_size = 20
        pool._min_size = 2
        pool._dsn = "postgresql://test"
        pool._original_max_size = 20
        pool._max_pool_ceiling = 100
        pool._high_util_count = 0
        pool._low_util_count = 0
        pool._auto_scale_task = None
        pool._scale_check_interval = 30.0
        pool._acquire_count = 0
        pool._error_count = 0
        pool._created_at = time.time()
        return pool

    def test_init_tracking_fields(self):
        pool = self._make_pool()
        assert pool._original_max_size == 20
        assert pool._max_pool_ceiling == 100

    def test_stats_include_autoscaling(self):
        pool = self._make_pool()
        stats = pool.stats()
        assert "auto_scaling" in stats
        assert stats["auto_scaling"]["original_max_size"] == 20
        assert stats["auto_scaling"]["max_pool_ceiling"] == 100
        assert stats["auto_scaling"]["enabled"] is False

    def test_stats_utilization(self):
        pool = self._make_pool()
        stats = pool.stats()
        assert stats["pool_size"] == 10
        assert stats["free_connections"] == 5
        assert stats["used_connections"] == 5
        assert stats["utilization_pct"] == 50.0

    def test_stats_uninitialized(self):
        pool = ConnectionPoolManager.__new__(ConnectionPoolManager)
        pool._pool = None
        stats = pool.stats()
        assert stats["initialized"] is False
