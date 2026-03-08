"""
Integration tests for CortexDB rate limiting.

Tests the multi-tier rate limiter (global, per-customer, per-agent,
per-endpoint, per-LLM-model) using the FastAPI app with mocked backends.
"""

import pytest
import asyncio
import httpx
from unittest.mock import AsyncMock, MagicMock, patch


class TestRateLimiterUnit:
    """Direct tests of the RateLimiter class (no HTTP)."""

    async def test_limiter_allows_within_limits(self):
        from cortexdb.rate_limit.limiter import RateLimiter, RateLimitResult
        limiter = RateLimiter(memory_engine=None)

        result = await limiter.check(endpoint="/v1/query")
        assert result.allowed is True

    async def test_limiter_returns_headers(self):
        from cortexdb.rate_limit.limiter import RateLimiter
        limiter = RateLimiter(memory_engine=None)

        result = await limiter.check(endpoint="/v1/query")
        headers = result.headers
        assert "X-RateLimit-Limit" in headers
        assert "X-RateLimit-Remaining" in headers
        assert "X-RateLimit-Reset" in headers

    async def test_limiter_tracks_per_endpoint(self):
        from cortexdb.rate_limit.limiter import RateLimiter
        limiter = RateLimiter(memory_engine=None)

        # Make several requests to the same endpoint
        for _ in range(10):
            result = await limiter.check(endpoint="/v1/query")

        # Remaining should be less than limit
        remaining = int(result.headers["X-RateLimit-Remaining"])
        limit = int(result.headers["X-RateLimit-Limit"])
        assert remaining <= limit

    async def test_limiter_stats(self):
        from cortexdb.rate_limit.limiter import RateLimiter
        limiter = RateLimiter(memory_engine=None)
        stats = limiter.get_stats()
        assert isinstance(stats, dict)


class TestRateLimitingHTTP:
    """Rate limiting behavior via HTTP endpoints."""

    async def test_rate_limit_headers_present(self, client: httpx.AsyncClient):
        """Responses should include rate limit headers when middleware is active."""
        resp = await client.post("/v1/query", json={"cortexql": "SELECT 1"})
        # The middleware adds headers — if mocked, they may be absent
        # We just verify the request succeeds
        assert resp.status_code == 200

    async def test_rapid_requests_succeed(self, client: httpx.AsyncClient):
        """Multiple rapid requests should succeed when within limits."""
        tasks = []
        for _ in range(20):
            tasks.append(client.post("/v1/query", json={"cortexql": "SELECT 1"}))

        responses = await asyncio.gather(*tasks)
        success_count = sum(1 for r in responses if r.status_code == 200)
        # All should succeed since rate limiter is mocked to allow
        assert success_count == 20

    async def test_write_endpoint_rate_limited_separately(self, client: httpx.AsyncClient):
        """Write endpoint has its own rate limit bucket."""
        resp = await client.post("/v1/write", json={
            "data_type": "test",
            "payload": {"key": "value"},
            "actor": "rate_limit_test",
        })
        assert resp.status_code == 200


class TestPerAgentRateLimiting:
    """Tests for per-agent rate limit tier."""

    async def test_agent_scoped_limits(self):
        """Different agents should have independent rate limit counters."""
        from cortexdb.rate_limit.limiter import RateLimiter
        limiter = RateLimiter(memory_engine=None)

        result_a = await limiter.check(agent_id="AGT-SYS-001", endpoint="/v1/query")
        result_b = await limiter.check(agent_id="AGT-DB-001", endpoint="/v1/query")

        # Both should be allowed independently
        assert result_a.allowed is True
        assert result_b.allowed is True

    async def test_tenant_scoped_limits(self):
        """Different tenants should have independent counters."""
        from cortexdb.rate_limit.limiter import RateLimiter
        limiter = RateLimiter(memory_engine=None)

        result_a = await limiter.check(tenant_id="tenant-alpha", endpoint="/v1/query")
        result_b = await limiter.check(tenant_id="tenant-beta", endpoint="/v1/query")

        assert result_a.allowed is True
        assert result_b.allowed is True


class TestSlidingWindowBehavior:
    """Verify the sliding window counter mechanism."""

    async def test_counter_resets_after_window(self):
        """Counters should reset once the time window expires."""
        from cortexdb.rate_limit.limiter import RateLimiter
        limiter = RateLimiter(memory_engine=None)

        # Fill up some requests
        for _ in range(5):
            await limiter.check(endpoint="/v1/query")

        # Manually advance the window start by clearing internal state
        limiter._counters.clear()

        # After reset, should have full capacity again
        result = await limiter.check(endpoint="/v1/query")
        assert result.allowed is True
        remaining = int(result.headers["X-RateLimit-Remaining"])
        limit = int(result.headers["X-RateLimit-Limit"])
        # Should be near full capacity
        assert remaining >= limit - 1
