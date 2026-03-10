"""Multi-Tier Rate Limiter (DOC-019 Section 5)

5 tiers: Global -> Per-Customer -> Per-Agent -> Per-Endpoint -> Per-LLM-Model
Token bucket algorithm via Redis INCR + TTL (sliding window).
"""

import time
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional

logger = logging.getLogger("cortexdb.rate_limit")


class RateLimitTier(Enum):
    GLOBAL = "global"
    PER_CUSTOMER = "per_customer"
    PER_AGENT = "per_agent"
    PER_ENDPOINT = "per_endpoint"
    PER_LLM_MODEL = "per_llm_model"


@dataclass
class RateLimitResult:
    allowed: bool = True
    tier: RateLimitTier = RateLimitTier.GLOBAL
    limit: int = 0
    remaining: int = 0
    reset_at: float = 0
    retry_after_seconds: int = 0

    @property
    def headers(self) -> Dict[str, str]:
        return {
            "X-RateLimit-Limit": str(self.limit),
            "X-RateLimit-Remaining": str(max(0, self.remaining)),
            "X-RateLimit-Reset": str(int(self.reset_at)),
        }


# Default limits per tier
GLOBAL_LIMITS = {"requests_per_min": 10000, "burst_per_sec": 500}

ENDPOINT_LIMITS = {
    "/v1/write": 200,
    "/v1/query": 1000,
    "/v1/a2a/task": 100,
}


class RateLimiter:
    """Multi-tier rate limiter using in-memory counters (upgradeable to Redis)."""

    def __init__(self, memory_engine: Any = None):
        self.memory_engine = memory_engine
        self._counters: Dict[str, list] = {}  # key -> [count, window_start]
        self._global_limits = GLOBAL_LIMITS.copy()

    async def check(self, tenant_id: Optional[str] = None,
                    agent_id: Optional[str] = None,
                    endpoint: Optional[str] = None,
                    tenant_limits: Optional[Dict] = None) -> RateLimitResult:
        """Check all applicable rate limit tiers. Returns first violation or allow."""
        now = time.time()

        # Tier 1: Global
        result = self._check_window(
            "global:all", self._global_limits["requests_per_min"], 60, now)
        if not result.allowed:
            result.tier = RateLimitTier.GLOBAL
            return result

        # Tier 2: Per-Customer (all tenants rate-limited, including admin)
        if tenant_id:
            if tenant_id == "__admin__":
                limit = 1000  # Admin has higher limit but IS rate-limited
            elif tenant_id == "__default__":
                limit = 200   # Default/anonymous gets lower limit
            else:
                limit = (tenant_limits or {}).get("requests_per_min", 500)
            result = self._check_window(f"customer:{tenant_id}", limit, 60, now)
            if not result.allowed:
                result.tier = RateLimitTier.PER_CUSTOMER
                return result

        # Tier 3: Per-Agent
        if agent_id:
            result = self._check_window(f"agent:{agent_id}", 100, 60, now)
            if not result.allowed:
                result.tier = RateLimitTier.PER_AGENT
                return result

        # Tier 4: Per-Endpoint
        if endpoint and endpoint in ENDPOINT_LIMITS:
            key = f"endpoint:{tenant_id or 'global'}:{endpoint}"
            result = self._check_window(key, ENDPOINT_LIMITS[endpoint], 60, now)
            if not result.allowed:
                result.tier = RateLimitTier.PER_ENDPOINT
                return result

        return RateLimitResult(allowed=True, remaining=999)

    def _check_window(self, key: str, limit: int,
                      window_seconds: int, now: float) -> RateLimitResult:
        """Sliding window counter check."""
        if key not in self._counters:
            self._counters[key] = [0, now]

        count, window_start = self._counters[key]

        # Reset window if expired
        if now - window_start >= window_seconds:
            self._counters[key] = [1, now]
            return RateLimitResult(
                allowed=True, limit=limit, remaining=limit - 1,
                reset_at=now + window_seconds)

        # Increment
        count += 1
        self._counters[key][0] = count

        if count > limit:
            retry_after = int(window_seconds - (now - window_start)) + 1
            return RateLimitResult(
                allowed=False, limit=limit, remaining=0,
                reset_at=window_start + window_seconds,
                retry_after_seconds=retry_after)

        return RateLimitResult(
            allowed=True, limit=limit, remaining=limit - count,
            reset_at=window_start + window_seconds)

    async def check_redis(self, key: str, limit: int,
                          window_seconds: int = 60) -> RateLimitResult:
        """Redis-backed sliding window (production mode)."""
        if not self.memory_engine:
            return self._check_window(key, limit, window_seconds, time.time())

        try:
            count = await self.memory_engine.incr(f"rate:{key}")
            if count == 1:
                await self.memory_engine.expire(f"rate:{key}", window_seconds)
            ttl = await self.memory_engine.ttl(f"rate:{key}")
            return RateLimitResult(
                allowed=count <= limit, limit=limit,
                remaining=max(0, limit - count),
                reset_at=time.time() + max(0, ttl),
                retry_after_seconds=max(0, ttl) if count > limit else 0)
        except Exception as e:
            logger.warning(f"Redis rate limit error: {e}, falling back to memory")
            return self._check_window(key, limit, window_seconds, time.time())

    # ── Brute Force Protection ──

    def check_auth_attempt(self, identifier: str, now: float = None) -> RateLimitResult:
        """Rate-limit authentication attempts. Lockout after 5 failures in 15 min."""
        now = now or time.time()
        key = f"auth_fail:{identifier}"
        max_attempts = 5
        lockout_window = 900  # 15 minutes

        if key not in self._counters:
            self._counters[key] = [0, now]

        count, window_start = self._counters[key]

        if now - window_start >= lockout_window:
            self._counters[key] = [1, now]
            return RateLimitResult(allowed=True, limit=max_attempts, remaining=max_attempts - 1)

        count += 1
        self._counters[key][0] = count

        if count > max_attempts:
            retry_after = int(lockout_window - (now - window_start)) + 1
            logger.warning(f"BRUTE_FORCE: Locked out {identifier} after {count} failed attempts")
            return RateLimitResult(
                allowed=False, limit=max_attempts, remaining=0,
                reset_at=window_start + lockout_window,
                retry_after_seconds=retry_after)

        return RateLimitResult(allowed=True, limit=max_attempts, remaining=max_attempts - count)

    def record_auth_success(self, identifier: str):
        """Reset auth failure counter on successful login."""
        key = f"auth_fail:{identifier}"
        if key in self._counters:
            del self._counters[key]

    def is_locked_out(self, identifier: str) -> bool:
        """Check if an identifier is currently locked out."""
        key = f"auth_fail:{identifier}"
        if key not in self._counters:
            return False
        count, window_start = self._counters[key]
        if time.time() - window_start >= 900:
            return False
        return count > 5

    def get_stats(self) -> Dict:
        active = {k: v[0] for k, v in self._counters.items() if v[0] > 0}
        lockouts = {k: v for k, v in active.items() if k.startswith("auth_fail:") and v > 5}
        return {
            "active_windows": len(active),
            "counters": active,
            "active_lockouts": len(lockouts),
        }
