"""Rate Limit Middleware for FastAPI (DOC-019 Section 5)"""

import logging
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("cortexdb.rate_limit.middleware")


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Checks rate limits before processing requests."""

    def __init__(self, app, rate_limiter=None):
        super().__init__(app)
        self.rate_limiter = rate_limiter

    async def dispatch(self, request: Request, call_next):
        if not self.rate_limiter:
            return await call_next(request)

        # Skip rate limiting for health endpoints
        if request.url.path.startswith("/health/"):
            return await call_next(request)

        tenant_id = getattr(request.state, "tenant_id", None)
        agent_id = request.headers.get("X-Agent-ID")
        tenant = getattr(request.state, "tenant", None)
        tenant_limits = tenant.effective_rate_limits if tenant else None

        result = await self.rate_limiter.check(
            tenant_id=tenant_id, agent_id=agent_id,
            endpoint=request.url.path, tenant_limits=tenant_limits)

        if not result.allowed:
            logger.warning(f"Rate limited: tenant={tenant_id} tier={result.tier.value} "
                           f"endpoint={request.url.path}")
            response = JSONResponse(
                status_code=429,
                content={
                    "error": f"{result.tier.value}_rate_limit",
                    "message": "Rate limit exceeded",
                    "limit": result.limit,
                    "retry_after_seconds": result.retry_after_seconds,
                },
                headers={**result.headers, "Retry-After": str(result.retry_after_seconds)})
            return response

        response = await call_next(request)

        # Add rate limit headers to all responses
        for k, v in result.headers.items():
            response.headers[k] = v
        return response
