"""Tenant Middleware - Extract tenant_id from API key, enforce isolation (DOC-019 Section 6.1)

Every request: Authorization: Bearer ctx_live_... -> resolve tenant -> set RLS context.
"""

import logging
from contextvars import ContextVar
from typing import Optional

from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

logger = logging.getLogger("cortexdb.tenant.middleware")

# Context variable for current tenant (async-safe)
_current_tenant: ContextVar[Optional[str]] = ContextVar("current_tenant", default=None)

# Paths that don't require tenant auth
PUBLIC_PATHS = {
    "/health/live", "/health/ready", "/health/deep", "/health/metrics",
    "/docs", "/openapi.json", "/redoc",
}


def get_current_tenant() -> Optional[str]:
    """Get current tenant_id from async context."""
    return _current_tenant.get()


def set_current_tenant(tenant_id: Optional[str]):
    """Set current tenant_id in async context."""
    _current_tenant.set(tenant_id)


class TenantMiddleware(BaseHTTPMiddleware):
    """Extracts tenant from API key and sets context for RLS.

    Flow:
    1. Extract Bearer token from Authorization header
    2. Resolve to tenant via TenantManager
    3. Verify tenant is active
    4. Set tenant context (ContextVar + PostgreSQL SET app.current_tenant)
    5. Inject tenant_id into request state for downstream use
    """

    def __init__(self, app, tenant_manager=None):
        super().__init__(app)
        self.tenant_manager = tenant_manager

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Public paths skip tenant auth
        if path in PUBLIC_PATHS or path.startswith("/health/"):
            set_current_tenant(None)
            return await call_next(request)

        # Admin paths require admin auth token
        if path.startswith("/admin/") or path.startswith("/v1/admin/") or \
           path.endswith("/rotate-keys") or path.endswith("/purge"):
            import os, hashlib
            admin_token = os.environ.get("CORTEX_ADMIN_TOKEN", "")
            provided = request.headers.get("X-Admin-Token", "")
            if not admin_token:
                # No admin token configured — require Authorization header
                auth = request.headers.get("Authorization", "")
                if not auth.startswith("Bearer "):
                    return JSONResponse(status_code=401, content={
                        "error": "admin_auth_required",
                        "message": "Admin endpoints require X-Admin-Token header"})
            elif not provided or not __import__('secrets').compare_digest(
                hashlib.sha256(provided.encode()).hexdigest(),
                hashlib.sha256(admin_token.encode()).hexdigest()):
                return JSONResponse(status_code=403, content={
                    "error": "forbidden", "message": "Invalid admin token"})
            set_current_tenant("__admin__")
            request.state.tenant_id = "__admin__"
            return await call_next(request)

        # Extract API key
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            # Allow unauthenticated for dev mode
            if not self.tenant_manager:
                set_current_tenant("__default__")
                request.state.tenant_id = "__default__"
                return await call_next(request)
            return JSONResponse(status_code=401, content={
                "error": "missing_auth",
                "message": "Authorization: Bearer <api_key> required"})

        api_key = auth[7:]  # Strip "Bearer "

        # Resolve tenant
        if not self.tenant_manager:
            set_current_tenant("__default__")
            request.state.tenant_id = "__default__"
            return await call_next(request)

        # Brute force protection: check if this IP is locked out
        client_ip = request.client.host if request.client else "unknown"
        if hasattr(self.tenant_manager, 'rate_limiter') and self.tenant_manager.rate_limiter:
            if self.tenant_manager.rate_limiter.is_locked_out(client_ip):
                return JSONResponse(status_code=429, content={
                    "error": "too_many_attempts",
                    "message": "Too many failed auth attempts. Try again later.",
                    "retry_after_seconds": 900})

        tenant = self.tenant_manager.resolve_tenant(api_key)
        if not tenant:
            # Record failed auth attempt for brute force protection
            if hasattr(self.tenant_manager, 'rate_limiter') and self.tenant_manager.rate_limiter:
                result = self.tenant_manager.rate_limiter.check_auth_attempt(client_ip)
                if not result.allowed:
                    return JSONResponse(status_code=429, content={
                        "error": "too_many_attempts",
                        "message": "Account locked due to repeated failures",
                        "retry_after_seconds": result.retry_after_seconds})
            return JSONResponse(status_code=401, content={
                "error": "invalid_api_key",
                "message": "API key not recognized"})

        if not tenant.is_active:
            return JSONResponse(status_code=403, content={
                "error": "tenant_inactive",
                "message": f"Tenant is {tenant.status.value}",
                "tenant_id": tenant.tenant_id})

        # Set tenant context
        set_current_tenant(tenant.tenant_id)
        request.state.tenant_id = tenant.tenant_id
        request.state.tenant = tenant

        response = await call_next(request)

        # Add tenant headers
        response.headers["X-Tenant-ID"] = tenant.tenant_id
        response.headers["X-Tenant-Plan"] = tenant.plan.value

        return response
