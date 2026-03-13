"""
CortexDB Health-Driven Traffic Controller.

Middleware that integrates circuit breaker states + health scores to control traffic:
- All healthy → accept all traffic
- Degraded → reads only, writes get 503
- Critical (multiple engines down) → 503 + Retry-After header
"""

import logging
import time
from typing import Any, Dict, Optional

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("cortexdb.traffic")


class TrafficState:
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    CRITICAL = "critical"


class TrafficController:
    """Determines traffic acceptance based on system health."""

    CRITICAL_ENGINE_THRESHOLD = 3  # engines down to trigger critical
    WRITE_ENDPOINTS = {"/v1/write", "/v1/bulk-write"}
    ALWAYS_ALLOW = {"/health", "/health/live", "/health/ready", "/health/deep",
                    "/health/watchdog", "/health/degradation", "/health/metrics"}

    def __init__(self, db: Any = None, circuits: Any = None):
        self._db = db
        self._circuits = circuits
        self._state = TrafficState.HEALTHY
        self._state_since = time.time()
        self._rejected_total = 0
        self._last_check = 0.0
        self._check_interval = 5.0  # seconds between state recalculations

    def _recalculate_state(self):
        """Recalculate traffic state from circuit breakers and DB health."""
        now = time.time()
        if now - self._last_check < self._check_interval:
            return
        self._last_check = now

        # Check degraded mode from DB
        if self._db and self._db._degraded_mode:
            self._set_state(TrafficState.DEGRADED)
            return

        # Check circuit breakers
        if self._circuits:
            try:
                states = self._circuits.get_all_states()
                open_count = sum(1 for s in states.values()
                                 if s.get("state") == "open")
                if open_count >= self.CRITICAL_ENGINE_THRESHOLD:
                    self._set_state(TrafficState.CRITICAL)
                    return
                elif open_count > 0:
                    self._set_state(TrafficState.DEGRADED)
                    return
            except Exception:
                pass

        # Check engine count
        if self._db:
            online = len(self._db.engines)
            if online < 4:  # Less than 4 of 7 engines
                self._set_state(TrafficState.CRITICAL)
                return
            elif online < 6:
                self._set_state(TrafficState.DEGRADED)
                return

        self._set_state(TrafficState.HEALTHY)

    def _set_state(self, new_state: str):
        if new_state != self._state:
            logger.warning(f"Traffic state: {self._state} → {new_state}")
            self._state = new_state
            self._state_since = time.time()

    def should_accept(self, path: str, method: str) -> tuple:
        """Check if a request should be accepted.

        Returns:
            (accept: bool, status_code: int, retry_after: Optional[int])
        """
        # Always allow health endpoints
        if any(path.startswith(p) for p in self.ALWAYS_ALLOW):
            return (True, 200, None)

        self._recalculate_state()

        if self._state == TrafficState.HEALTHY:
            return (True, 200, None)

        if self._state == TrafficState.DEGRADED:
            # Allow reads, reject writes
            is_write = (method in ("POST", "PUT", "PATCH", "DELETE")
                        and any(path.startswith(wp) for wp in self.WRITE_ENDPOINTS))
            if is_write:
                self._rejected_total += 1
                return (False, 503, 30)
            return (True, 200, None)

        if self._state == TrafficState.CRITICAL:
            self._rejected_total += 1
            return (False, 503, 60)

        return (True, 200, None)

    def get_status(self) -> Dict:
        self._recalculate_state()
        return {
            "state": self._state,
            "since": self._state_since,
            "duration_seconds": round(time.time() - self._state_since, 1),
            "rejected_total": self._rejected_total,
        }


class TrafficControlMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware that enforces traffic control decisions.

    Uses app.state.traffic_controller (set in lifespan) so it works
    even though middleware is registered before the controller exists.
    """

    async def dispatch(self, request: Request, call_next):
        controller = getattr(request.app.state, "traffic_controller", None)
        if controller is None:
            return await call_next(request)

        accept, status_code, retry_after = controller.should_accept(
            request.url.path, request.method)

        if not accept:
            headers = {}
            if retry_after:
                headers["Retry-After"] = str(retry_after)
            return JSONResponse(
                status_code=status_code,
                content={
                    "error": "SERVICE_UNAVAILABLE",
                    "state": controller._state,
                    "message": (
                        "CortexDB is in degraded mode — writes temporarily unavailable"
                        if controller._state == TrafficState.DEGRADED
                        else "CortexDB is in critical state — service temporarily unavailable"
                    ),
                    "retry_after": retry_after,
                },
                headers=headers,
            )

        return await call_next(request)
