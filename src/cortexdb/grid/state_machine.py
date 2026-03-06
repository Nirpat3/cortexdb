"""Grid Node State Machine - 10-State Lifecycle (DOC-015 Section 2)

States: HEALTHY -> DEGRADED -> DEAD -> QUARANTINE -> REPAIRING ->
        PROBATION -> DRAINING -> REMOVED -> TOMBSTONED -> PURGED
"""

import time
import logging
from enum import Enum
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

logger = logging.getLogger("cortexdb.grid")


class NodeState(Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    DEAD = "DEAD"
    QUARANTINE = "QUARANTINE"
    REPAIRING = "REPAIRING"
    PROBATION = "PROBATION"
    DRAINING = "DRAINING"
    REMOVED = "REMOVED"
    TOMBSTONED = "TOMBSTONED"
    PURGED = "PURGED"


VALID_TRANSITIONS = {
    NodeState.HEALTHY: [NodeState.DEGRADED, NodeState.DEAD],
    NodeState.DEGRADED: [NodeState.HEALTHY, NodeState.DEAD, NodeState.REPAIRING],
    NodeState.DEAD: [NodeState.QUARANTINE],
    NodeState.QUARANTINE: [NodeState.REPAIRING, NodeState.DRAINING, NodeState.PROBATION],
    NodeState.REPAIRING: [NodeState.PROBATION, NodeState.DRAINING],
    NodeState.PROBATION: [NodeState.HEALTHY, NodeState.DEAD],
    NodeState.DRAINING: [NodeState.REMOVED],
    NodeState.REMOVED: [NodeState.TOMBSTONED],
    NodeState.TOMBSTONED: [NodeState.PURGED],
    NodeState.PURGED: [],
}

STATE_COLORS = {
    NodeState.HEALTHY: "green",
    NodeState.DEGRADED: "yellow",
    NodeState.DEAD: "red",
    NodeState.QUARANTINE: "red_pulsing",
    NodeState.REPAIRING: "orange",
    NodeState.PROBATION: "blue",
    NodeState.DRAINING: "gray_fading",
    NodeState.REMOVED: "hidden",
    NodeState.TOMBSTONED: "hidden",
    NodeState.PURGED: "hidden",
}

STATE_ROUTES_TRAFFIC = {
    NodeState.HEALTHY: True,
    NodeState.DEGRADED: True,
    NodeState.DEAD: False,
    NodeState.QUARANTINE: False,
    NodeState.REPAIRING: False,
    NodeState.PROBATION: True,  # 10% canary only
    NodeState.DRAINING: False,
    NodeState.REMOVED: False,
    NodeState.TOMBSTONED: False,
    NodeState.PURGED: False,
}


@dataclass
class StateTransition:
    from_state: NodeState
    to_state: NodeState
    timestamp: float
    reason: str
    actor: str = "system"


@dataclass
class GridNode:
    node_id: str
    grid_address: str
    node_type: str
    zone: str = "default"
    state: NodeState = NodeState.HEALTHY
    health_score: float = 100.0
    metadata: Dict = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    last_heartbeat_at: float = field(default_factory=time.time)
    heartbeat_interval: float = 10.0
    failure_count: int = 0
    consecutive_failures: int = 0
    repair_attempts: List[Dict] = field(default_factory=list)
    transition_history: List[StateTransition] = field(default_factory=list)
    tombstone: Optional[Dict] = None
    removed_at: Optional[float] = None

    @property
    def is_alive(self) -> bool:
        return self.state in (NodeState.HEALTHY, NodeState.DEGRADED, NodeState.PROBATION)

    @property
    def routes_traffic(self) -> bool:
        return STATE_ROUTES_TRAFFIC.get(self.state, False)

    @property
    def dashboard_color(self) -> str:
        return STATE_COLORS.get(self.state, "hidden")

    @property
    def dead_timeout(self) -> float:
        """3x heartbeat interval per NIRLAB-GRID-002"""
        return self.heartbeat_interval * 3

    @property
    def time_since_heartbeat(self) -> float:
        return time.time() - self.last_heartbeat_at

    @property
    def lifetime_hours(self) -> float:
        end = self.removed_at or time.time()
        return (end - self.created_at) / 3600


class NodeStateMachine:
    """Manages state transitions for all grid nodes.
    Enforces valid transitions per DOC-015 Section 2."""

    def __init__(self):
        self._nodes: Dict[str, GridNode] = {}
        self._listeners: List[Callable] = []

    def register_node(self, node: GridNode) -> None:
        self._nodes[node.node_id] = node
        logger.info(f"Grid node registered: {node.grid_address} [{node.node_type}]")

    def get_node(self, node_id: str) -> Optional[GridNode]:
        return self._nodes.get(node_id)

    def get_nodes_by_state(self, state: NodeState) -> List[GridNode]:
        return [n for n in self._nodes.values() if n.state == state]

    def get_nodes_by_type(self, node_type: str) -> List[GridNode]:
        return [n for n in self._nodes.values() if n.node_type == node_type
                and n.state not in (NodeState.REMOVED, NodeState.TOMBSTONED, NodeState.PURGED)]

    @property
    def active_nodes(self) -> List[GridNode]:
        excluded = {NodeState.REMOVED, NodeState.TOMBSTONED, NodeState.PURGED}
        return [n for n in self._nodes.values() if n.state not in excluded]

    @property
    def topology_size(self) -> int:
        return len(self.active_nodes)

    def transition(self, node_id: str, new_state: NodeState,
                   reason: str, actor: str = "system") -> bool:
        node = self._nodes.get(node_id)
        if not node:
            logger.error(f"Node {node_id} not found in state machine")
            return False

        if new_state not in VALID_TRANSITIONS.get(node.state, []):
            logger.warning(
                f"Invalid transition for {node.grid_address}: "
                f"{node.state.value} -> {new_state.value} (reason: {reason})"
            )
            return False

        old_state = node.state
        transition = StateTransition(
            from_state=old_state, to_state=new_state,
            timestamp=time.time(), reason=reason, actor=actor,
        )
        node.transition_history.append(transition)
        node.state = new_state

        if new_state == NodeState.REMOVED:
            node.removed_at = time.time()

        logger.info(f"Grid node {node.grid_address}: {old_state.value} -> {new_state.value} ({reason})")

        for listener in self._listeners:
            try:
                listener(node, transition)
            except Exception as e:
                logger.error(f"State transition listener error: {e}")

        return True

    def on_transition(self, callback: Callable) -> None:
        self._listeners.append(callback)

    def record_heartbeat(self, node_id: str) -> None:
        node = self._nodes.get(node_id)
        if node:
            node.last_heartbeat_at = time.time()
            node.consecutive_failures = 0

    def record_failure(self, node_id: str) -> None:
        node = self._nodes.get(node_id)
        if node:
            node.consecutive_failures += 1
            node.failure_count += 1
            if node.consecutive_failures >= 3 and node.state in (NodeState.HEALTHY, NodeState.DEGRADED):
                self.transition(node_id, NodeState.DEAD,
                               f"3 consecutive liveness failures ({node.consecutive_failures})")

    def can_remove(self, node_id: str) -> tuple:
        """Check NIRLAB-GRID-001 (min redundancy) before removal."""
        node = self._nodes.get(node_id)
        if not node:
            return False, "Node not found"

        same_type = self.get_nodes_by_type(node.node_type)
        healthy_count = sum(1 for n in same_type if n.is_alive and n.node_id != node_id)

        if node.node_type == "PRIME":
            if healthy_count < 1:
                return False, "Cannot remove last PRIME instance. Need >= 1 standby."
            return True, "PRIME standby available"

        if healthy_count < 2:
            return False, (
                f"Cannot remove {node.grid_address}: only {healthy_count} healthy "
                f"instance(s) of '{node.node_type}' remain. NIRLAB-GRID-001 requires >= 2."
            )
        return True, f"{healthy_count} healthy instances remain"
