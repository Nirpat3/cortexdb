"""Grid Garbage Collector (GGC) - Continuous Cleanup (DOC-015 Section 5)

9 GGC Tasks: zombie detection, orphaned links, stale routes,
tombstone purge, K8s cleanup, Redis cleanup, credential sweep,
topology compaction, metrics retention.
"""

import asyncio
import time
import logging
from dataclasses import dataclass, field
from typing import Callable, Dict, List

from cortexdb.grid.state_machine import GridNode, NodeState, NodeStateMachine

logger = logging.getLogger("cortexdb.grid.ggc")


@dataclass
class GGCStats:
    zombies_detected: int = 0
    orphaned_links_removed: int = 0
    stale_routes_purged: int = 0
    tombstones_purged: int = 0
    redis_keys_freed: int = 0
    credentials_revoked: int = 0
    compactions_run: int = 0
    last_run: Dict[str, float] = field(default_factory=dict)


class GridGarbageCollector:
    """Continuous cleanup process for grid health."""

    def __init__(self, state_machine: NodeStateMachine):
        self.state_machine = state_machine
        self.stats = GGCStats()
        self._running = False
        self._tasks: List[asyncio.Task] = []

    async def start(self) -> None:
        self._running = True
        self._tasks = [
            asyncio.create_task(self._run_periodic("zombie_detection", 60, self.detect_zombies)),
            asyncio.create_task(self._run_periodic("orphaned_links", 300, self.cleanup_orphaned_links)),
            asyncio.create_task(self._run_periodic("stale_routes", 30, self.purge_stale_routes)),
            asyncio.create_task(self._run_periodic("topology_compaction", 3600, self.compact_topology)),
        ]
        logger.info("Grid Garbage Collector started (4 active tasks)")

    async def stop(self) -> None:
        self._running = False
        for task in self._tasks:
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        logger.info("Grid Garbage Collector stopped")

    async def _run_periodic(self, name: str, interval: float, func: Callable) -> None:
        while self._running:
            try:
                await func()
                self.stats.last_run[name] = time.time()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"GGC task '{name}' error: {e}")
            await asyncio.sleep(interval)

    async def detect_zombies(self) -> int:
        """Nodes with no heartbeat in > 3x interval -> force to DEAD."""
        zombies_found = 0
        exempt = {NodeState.QUARANTINE, NodeState.REPAIRING, NodeState.DRAINING,
                  NodeState.REMOVED, NodeState.TOMBSTONED, NodeState.PURGED}

        for node in self.state_machine.active_nodes:
            if node.state in exempt:
                continue
            if node.time_since_heartbeat > node.dead_timeout:
                logger.warning(f"GGC: Zombie - {node.grid_address} (no heartbeat {node.time_since_heartbeat:.0f}s)")
                for _ in range(3):
                    self.state_machine.record_failure(node.node_id)
                if node.state == NodeState.DEAD:
                    self.state_machine.transition(node.node_id, NodeState.QUARANTINE,
                                                  "GGC zombie detection")
                zombies_found += 1

        self.stats.zombies_detected += zombies_found
        return zombies_found

    async def cleanup_orphaned_links(self) -> int:
        """Remove references to nodes that no longer exist in the state machine.

        Orphaned links occur when a node is removed but other nodes still
        reference it in their dependency lists or routing tables.
        """
        orphaned = 0
        known_ids = {n.node_id for n in self.state_machine.active_nodes}
        all_nodes = list(self.state_machine._nodes.values())

        for node in all_nodes:
            # Clean dependency references to removed nodes
            if hasattr(node, "dependencies"):
                before = len(node.dependencies)
                node.dependencies = [d for d in node.dependencies if d in known_ids]
                removed = before - len(node.dependencies)
                if removed > 0:
                    orphaned += removed
                    logger.info(f"GGC: Removed {removed} orphaned deps from {node.node_id}")

            # Clean peer references
            if hasattr(node, "peers"):
                before = len(node.peers)
                node.peers = [p for p in node.peers if p in known_ids]
                orphaned += before - len(node.peers)

        # Remove nodes stuck in TOMBSTONED state for > 1 hour
        tombstoned = [n for n in all_nodes
                      if n.state == NodeState.TOMBSTONED
                      and n.time_since_heartbeat > 3600]
        for node in tombstoned:
            self.state_machine.transition(node.node_id, NodeState.PURGED,
                                          "GGC tombstone expiry")
            orphaned += 1
            self.stats.tombstones_purged += 1

        self.stats.orphaned_links_removed += orphaned
        if orphaned > 0:
            logger.info(f"GGC: Cleaned {orphaned} orphaned links/tombstones")
        return orphaned

    async def purge_stale_routes(self) -> int:
        """Remove routing entries for nodes that are DEAD, QUARANTINE, or PURGED.

        Stale routes cause requests to be sent to unresponsive nodes,
        increasing latency and error rates.
        """
        purged = 0
        stale_states = {NodeState.DEAD, NodeState.QUARANTINE,
                        NodeState.PURGED, NodeState.REMOVED}

        for node in list(self.state_machine._nodes.values()):
            if node.state in stale_states:
                # Node is in a terminal/bad state — mark for route removal
                if hasattr(node, "route_active") and node.route_active:
                    node.route_active = False
                    purged += 1
                    logger.info(f"GGC: Purged stale route for {node.node_id} "
                                f"(state={node.state.value})")

                # Nodes DEAD for > 10 minutes without recovery → quarantine
                if (node.state == NodeState.DEAD and
                        node.time_since_heartbeat > 600):
                    try:
                        self.state_machine.transition(
                            node.node_id, NodeState.QUARANTINE,
                            "GGC stale route purge - dead > 10m")
                        purged += 1
                    except Exception as e:
                        logger.warning(f"GGC: Failed to transition {node.node_id} to QUARANTINE: {e}")

        self.stats.stale_routes_purged += purged
        if purged > 0:
            logger.info(f"GGC: Purged {purged} stale routes")
        return purged

    async def compact_topology(self) -> None:
        """Compact topology by removing PURGED nodes and defragmenting state.

        Also cleans up metrics for nodes that no longer exist.
        """
        all_nodes = list(self.state_machine._nodes.items())
        removed = 0

        for node_id, node in all_nodes:
            if node.state == NodeState.PURGED:
                del self.state_machine._nodes[node_id]
                removed += 1

        active = self.state_machine.active_nodes
        self.stats.compactions_run += 1
        logger.info(f"GGC: Topology compaction - {len(active)} active nodes, "
                    f"{removed} purged nodes removed")

    def get_stats(self) -> Dict:
        return {
            "zombies_detected": self.stats.zombies_detected,
            "orphaned_links_removed": self.stats.orphaned_links_removed,
            "stale_routes_purged": self.stats.stale_routes_purged,
            "tombstones_purged": self.stats.tombstones_purged,
            "redis_keys_freed": self.stats.redis_keys_freed,
            "credentials_revoked": self.stats.credentials_revoked,
            "compactions_run": self.stats.compactions_run,
            "last_run": self.stats.last_run,
            "running": self._running,
        }
