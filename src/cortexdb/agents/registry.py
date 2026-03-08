"""
Agent Registry — Central registry tracking all active agents, their roles,
responsibilities, status, and the microservices they manage.
"""

import time
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass, field, asdict
from enum import Enum

logger = logging.getLogger(__name__)


class AgentStatus(str, Enum):
    ACTIVE = "active"
    IDLE = "idle"
    RUNNING = "running"
    ERROR = "error"
    STOPPED = "stopped"


@dataclass
class AgentInfo:
    agent_id: str
    title: str
    role: str
    responsibilities: List[str]
    microservice: str
    category: str
    status: AgentStatus = AgentStatus.IDLE
    last_run: float = 0
    run_count: int = 0
    errors: int = 0
    avg_run_ms: float = 0
    metadata: Dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["uptime_since"] = self.metadata.get("started_at", 0)
        return d


class AgentRegistry:
    """Central registry for all CortexDB agents."""

    def __init__(self):
        self._agents: Dict[str, AgentInfo] = {}
        self._started_at = time.time()

    def register(self, agent: AgentInfo):
        agent.metadata["started_at"] = time.time()
        self._agents[agent.agent_id] = agent
        logger.info("Agent registered: %s (%s)", agent.agent_id, agent.title)

    def update_status(self, agent_id: str, status: AgentStatus):
        if agent_id in self._agents:
            self._agents[agent_id].status = status

    def record_run(self, agent_id: str, duration_ms: float, error: bool = False):
        if agent_id not in self._agents:
            return
        a = self._agents[agent_id]
        a.run_count += 1
        a.last_run = time.time()
        if error:
            a.errors += 1
        # Running average
        a.avg_run_ms = round(
            (a.avg_run_ms * (a.run_count - 1) + duration_ms) / a.run_count, 1
        )

    def get_agent(self, agent_id: str) -> Optional[dict]:
        a = self._agents.get(agent_id)
        return a.to_dict() if a else None

    def get_all_agents(self) -> List[dict]:
        return [a.to_dict() for a in self._agents.values()]

    def get_summary(self) -> dict:
        agents = list(self._agents.values())
        return {
            "total_agents": len(agents),
            "active": sum(1 for a in agents if a.status in (AgentStatus.ACTIVE, AgentStatus.RUNNING)),
            "idle": sum(1 for a in agents if a.status == AgentStatus.IDLE),
            "error": sum(1 for a in agents if a.status == AgentStatus.ERROR),
            "stopped": sum(1 for a in agents if a.status == AgentStatus.STOPPED),
            "total_runs": sum(a.run_count for a in agents),
            "total_errors": sum(a.errors for a in agents),
            "registry_uptime": round(time.time() - self._started_at, 1),
            "categories": list(set(a.category for a in agents)),
        }
