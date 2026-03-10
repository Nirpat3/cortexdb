"""Universal Heartbeat Protocol (DOC-014 Section 2)

Every service MUST implement: /health/live, /health/ready, /health/deep, /health/metrics
Agent signals: heartbeat(30s), progress, budget_warning, escalation, lifecycle
"""

import time
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional
from enum import Enum

logger = logging.getLogger("cortexdb.heartbeat")


class ServiceState(Enum):
    ALIVE = "alive"
    READY = "ready"
    DEGRADED = "degraded"
    NOT_READY = "not_ready"
    UNHEALTHY = "unhealthy"


@dataclass
class HeartbeatSignal:
    source_id: str
    source_type: str
    state: ServiceState
    timestamp: float = field(default_factory=time.time)
    uptime_seconds: float = 0
    checks: Dict[str, str] = field(default_factory=dict)
    metrics: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)


@dataclass
class AgentHeartbeat:
    agent_id: str
    state: str
    task_id: Optional[str] = None
    progress_pct: float = 0
    tokens_used: int = 0
    budget_remaining_pct: float = 100
    current_action: str = ""
    last_tool_call: Optional[str] = None
    memory_mb: float = 0
    timestamp: float = field(default_factory=time.time)


class HeartbeatProtocol:
    """Manages heartbeat collection and failure detection."""

    def __init__(self):
        self._services: Dict[str, Dict] = {}
        self._last_heartbeats: Dict[str, HeartbeatSignal] = {}
        self._agent_heartbeats: Dict[str, AgentHeartbeat] = {}
        self._failure_counts: Dict[str, int] = {}
        self._degraded_since: Dict[str, float] = {}
        self._listeners: List[Callable] = []

    def register_service(self, service_id: str, service_type: str,
                         heartbeat_interval: float = 10.0,
                         dependencies: List[str] = None) -> None:
        self._services[service_id] = {
            "type": service_type, "interval": heartbeat_interval,
            "dependencies": dependencies or [], "registered_at": time.time(),
        }
        self._failure_counts[service_id] = 0

    def record_heartbeat(self, signal: HeartbeatSignal) -> None:
        self._last_heartbeats[signal.source_id] = signal
        self._failure_counts[signal.source_id] = 0

        if signal.state == ServiceState.DEGRADED:
            if signal.source_id not in self._degraded_since:
                self._degraded_since[signal.source_id] = time.time()
        else:
            self._degraded_since.pop(signal.source_id, None)

        for listener in self._listeners:
            try: listener("heartbeat", signal)
            except Exception: pass

    def record_agent_heartbeat(self, heartbeat: AgentHeartbeat) -> None:
        self._agent_heartbeats[heartbeat.agent_id] = heartbeat
        if heartbeat.budget_remaining_pct <= 5:
            logger.warning(f"Agent {heartbeat.agent_id}: budget {heartbeat.budget_remaining_pct}% - CRITICAL")
        elif heartbeat.budget_remaining_pct <= 20:
            logger.warning(f"Agent {heartbeat.agent_id}: budget {heartbeat.budget_remaining_pct}% - WARNING")

    def record_failure(self, service_id: str) -> int:
        self._failure_counts[service_id] = self._failure_counts.get(service_id, 0) + 1
        count = self._failure_counts[service_id]
        if count >= 3:
            logger.error(f"Heartbeat: {service_id} {count} consecutive failures - DEAD")
            for listener in self._listeners:
                try: listener("dead", {"service_id": service_id, "failures": count})
                except Exception: pass
        return count

    def check_stuck_agents(self, timeout_seconds: float = 180) -> List[str]:
        now = time.time()
        return [aid for aid, hb in self._agent_heartbeats.items()
                if now - hb.timestamp > timeout_seconds]

    def check_missed_heartbeats(self) -> List[str]:
        missed = []
        now = time.time()
        for sid, info in self._services.items():
            last_hb = self._last_heartbeats.get(sid)
            if last_hb:
                if now - last_hb.timestamp > info["interval"] * 3:
                    missed.append(sid)
            elif now - info["registered_at"] > info["interval"] * 3:
                missed.append(sid)
        return missed

    def on_event(self, callback: Callable) -> None:
        self._listeners.append(callback)

    def get_status(self) -> Dict:
        now = time.time()
        services = {}
        for sid, info in self._services.items():
            last_hb = self._last_heartbeats.get(sid)
            services[sid] = {
                "type": info["type"],
                "state": last_hb.state.value if last_hb else "unknown",
                "last_heartbeat": last_hb.timestamp if last_hb else None,
                "seconds_ago": round(now - last_hb.timestamp, 1) if last_hb else None,
                "consecutive_failures": self._failure_counts.get(sid, 0),
            }
        return {
            "services": services,
            "total_registered": len(self._services),
            "total_agents": len(self._agent_heartbeats),
            "stuck_agents": self.check_stuck_agents(),
            "missed_heartbeats": self.check_missed_heartbeats(),
        }
