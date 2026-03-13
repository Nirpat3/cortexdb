"""Unit tests for Tenant Hot-Reload (P2.5)."""

import asyncio
import time
import pytest
from unittest.mock import MagicMock, AsyncMock
from cortexdb.tenant.manager import TenantManager, TenantPlan, TenantStatus


class TestTenantHotReload:
    def test_init_has_reload_fields(self):
        mgr = TenantManager()
        assert mgr._last_reload_check == 0.0
        assert mgr._reload_task is None
        assert mgr._reload_interval == 60.0

    @pytest.mark.asyncio
    async def test_reload_noop_without_relational(self):
        mgr = TenantManager(engines={})
        count = await mgr.reload_from_db()
        assert count == 0

    @pytest.mark.asyncio
    async def test_reload_inserts_new_tenants(self):
        """reload_from_db should create in-memory tenants from DB rows."""
        import json
        mock_pool = AsyncMock()
        mock_pool.fetch.return_value = [
            {
                "tenant_id": "t-001", "name": "Acme Corp",
                "plan": "growth", "status": "active",
                "api_key_hash": "abc123hash", "config": json.dumps({"feature_x": True}),
                "updated_epoch": time.time(),
            }
        ]
        mock_engine = MagicMock()
        mock_engine.pool = mock_pool

        mgr = TenantManager(engines={"relational": mock_engine})
        count = await mgr.reload_from_db()
        assert count == 1
        tenant = mgr.get_tenant("t-001")
        assert tenant is not None
        assert tenant.name == "Acme Corp"
        assert tenant.plan == TenantPlan.GROWTH
        assert tenant.status == TenantStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_reload_updates_existing_tenant(self):
        import json
        mgr = TenantManager(engines={})
        # Pre-populate a tenant
        from cortexdb.tenant.manager import Tenant
        mgr._tenants["t-002"] = Tenant(
            tenant_id="t-002", name="Old Name", plan=TenantPlan.FREE,
            status=TenantStatus.ACTIVE, api_key_hash="oldhash",
        )
        mgr._api_key_index["oldhash"] = "t-002"

        mock_pool = AsyncMock()
        mock_pool.fetch.return_value = [
            {
                "tenant_id": "t-002", "name": "New Name",
                "plan": "enterprise", "status": "active",
                "api_key_hash": "newhash", "config": json.dumps({}),
                "updated_epoch": time.time(),
            }
        ]
        mock_engine = MagicMock()
        mock_engine.pool = mock_pool
        mgr.engines = {"relational": mock_engine}

        count = await mgr.reload_from_db()
        assert count == 1
        tenant = mgr.get_tenant("t-002")
        assert tenant.plan == TenantPlan.ENTERPRISE
        # API key index should be updated
        assert "oldhash" not in mgr._api_key_index
        assert mgr._api_key_index["newhash"] == "t-002"

    @pytest.mark.asyncio
    async def test_start_stop_reload_loop(self):
        mgr = TenantManager(engines={})
        mgr._reload_interval = 0.1  # Fast for testing
        await mgr.start_reload_loop()
        assert mgr._reload_task is not None
        assert not mgr._reload_task.done()
        await mgr.stop_reload_loop()

    @pytest.mark.asyncio
    async def test_delta_query_uses_last_check(self):
        """Second reload should use WHERE updated_at > last_check."""
        import json
        mock_pool = AsyncMock()
        mock_pool.fetch.return_value = []
        mock_engine = MagicMock()
        mock_engine.pool = mock_pool

        mgr = TenantManager(engines={"relational": mock_engine})

        # First call — full load
        await mgr.reload_from_db()
        assert mgr._last_reload_check > 0

        # Second call — should pass the timestamp
        await mgr.reload_from_db()
        # The second fetch call should have 1 argument (the timestamp)
        calls = mock_pool.fetch.call_args_list
        assert len(calls) == 2
        # First call: no WHERE clause (full load)
        first_sql = calls[0][0][0]
        assert "updated_at >" not in first_sql
        # Second call: delta query
        second_sql = calls[1][0][0]
        assert "updated_at >" in second_sql
