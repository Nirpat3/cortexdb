"""Node Resurrection Protocol - Safe Return from Dead State (DOC-015 Section 8)

Handles: QUARANTINE (safe), REPAIRING (safe), DRAINING (caution),
REMOVED (danger - ghost), TOMBSTONED (critical - security incident).
"""

import time
import logging
from enum import Enum
from dataclasses import dataclass
from typing import Optional

from cortexdb.grid.state_machine import GridNode, NodeState, NodeStateMachine

logger = logging.getLogger("cortexdb.grid.resurrection")


class ResurrectionRisk(Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass
class ResurrectionEvent:
    node_id: str
    previous_state: NodeState
    risk_level: ResurrectionRisk
    action_taken: str
    timestamp: float
    allowed: bool


class ResurrectionProtocol:
    def __init__(self, state_machine: NodeStateMachine):
        self.state_machine = state_machine
        self._events: list = []
        self._alert_callback = None

    def set_alert_callback(self, callback) -> None:
        self._alert_callback = callback

    async def handle_unexpected_heartbeat(self, node_id: str) -> ResurrectionEvent:
        node = self.state_machine.get_node(node_id)
        if not node:
            event = ResurrectionEvent(
                node_id=node_id, previous_state=NodeState.PURGED,
                risk_level=ResurrectionRisk.CRITICAL,
                action_taken="BLOCKED: Unknown node ID", timestamp=time.time(), allowed=False,
            )
            self._events.append(event)
            logger.critical(f"Resurrection: unknown node {node_id} - BLOCKED")
            return event

        handlers = {
            NodeState.QUARANTINE: self._handle_quarantine,
            NodeState.REPAIRING: self._handle_repairing,
            NodeState.DRAINING: self._handle_draining,
            NodeState.REMOVED: self._handle_removed,
            NodeState.TOMBSTONED: self._handle_tombstoned,
        }

        handler = handlers.get(node.state)
        if handler:
            event = await handler(node)
        else:
            self.state_machine.record_heartbeat(node_id)
            event = ResurrectionEvent(
                node_id=node_id, previous_state=node.state,
                risk_level=ResurrectionRisk.LOW,
                action_taken="Normal heartbeat recorded",
                timestamp=time.time(), allowed=True,
            )

        self._events.append(event)
        return event

    async def _handle_quarantine(self, node: GridNode) -> ResurrectionEvent:
        logger.info(f"Resurrection: {node.grid_address} recovered from QUARANTINE")
        self.state_machine.transition(node.node_id, NodeState.PROBATION, "Self-recovered during quarantine")
        node.last_heartbeat_at = time.time()
        return ResurrectionEvent(node.node_id, NodeState.QUARANTINE, ResurrectionRisk.LOW,
                                 "Moved to PROBATION (60s canary)", time.time(), True)

    async def _handle_repairing(self, node: GridNode) -> ResurrectionEvent:
        logger.info(f"Resurrection: {node.grid_address} self-healed during REPAIRING")
        self.state_machine.transition(node.node_id, NodeState.PROBATION, "Self-healed during repair")
        node.last_heartbeat_at = time.time()
        return ResurrectionEvent(node.node_id, NodeState.REPAIRING, ResurrectionRisk.LOW,
                                 "Cancelled repair, moved to PROBATION", time.time(), True)

    async def _handle_draining(self, node: GridNode) -> ResurrectionEvent:
        logger.warning(f"Resurrection: {node.grid_address} heartbeat while DRAINING")
        return ResurrectionEvent(node.node_id, NodeState.DRAINING, ResurrectionRisk.MEDIUM,
                                 "HALTED drain. Manual verification required.", time.time(), False)

    async def _handle_removed(self, node: GridNode) -> ResurrectionEvent:
        logger.error(f"Resurrection: GHOST - {node.grid_address} after REMOVED")
        if self._alert_callback:
            await self._alert_callback("GHOST_NODE", f"Removed node {node.grid_address} sent heartbeat")
        return ResurrectionEvent(node.node_id, NodeState.REMOVED, ResurrectionRisk.HIGH,
                                 "BLOCKED: Ghost node. Terminate immediately.", time.time(), False)

    async def _handle_tombstoned(self, node: GridNode) -> ResurrectionEvent:
        logger.critical(f"Resurrection: CRITICAL - Tombstoned {node.grid_address} alive")
        if self._alert_callback:
            await self._alert_callback("TOMBSTONED_RESURRECTION_P0",
                                       f"Tombstoned node {node.grid_address} sending heartbeats. Security incident.")
        return ResurrectionEvent(node.node_id, NodeState.TOMBSTONED, ResurrectionRisk.CRITICAL,
                                 "P0 ALERT: All communication blocked. Investigation required.", time.time(), False)

    def get_events(self, limit: int = 50) -> list:
        return [{"node_id": e.node_id, "previous_state": e.previous_state.value,
                 "risk_level": e.risk_level.value, "action_taken": e.action_taken,
                 "timestamp": e.timestamp, "allowed": e.allowed}
                for e in self._events[-limit:]]
