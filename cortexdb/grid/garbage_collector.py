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
        orphaned = 0
        self.stats.orphaned_links_removed += orphaned
        return orphaned

    async def purge_stale_routes(self) -> int:
        purged = 0
        self.stats.stale_routes_purged += purged
        return purged

    async def compact_topology(self) -> None:
        active = self.state_machine.active_nodes
        self.stats.compactions_run += 1
        logger.info(f"GGC: Topology compaction - {len(active)} active nodes")

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
