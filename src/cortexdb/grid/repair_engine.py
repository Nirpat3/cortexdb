"""Grid Repair Engine - 5-Level Automated Repair (DOC-015 Section 3)

L1 Soft Restart -> L2 Hard Restart -> L3 Rebuild -> L4 Replace -> L5 Decommission
Total automated repair window: 10 minutes max (NIRLAB-GRID-003).
"""

import asyncio
import time
import logging
from enum import IntEnum
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from cortexdb.grid.state_machine import GridNode, NodeState, NodeStateMachine

logger = logging.getLogger("cortexdb.grid.repair")


class RepairLevel(IntEnum):
    L1_SOFT_RESTART = 1
    L2_HARD_RESTART = 2
    L3_REBUILD_CONTAINER = 3
    L4_REPLACE_INSTANCE = 4
    L5_DECOMMISSION = 5


REPAIR_TIMEOUTS = {
    RepairLevel.L1_SOFT_RESTART: 15,
    RepairLevel.L2_HARD_RESTART: 60,
    RepairLevel.L3_REBUILD_CONTAINER: 180,
    RepairLevel.L4_REPLACE_INSTANCE: 300,
    RepairLevel.L5_DECOMMISSION: 0,
}

REPAIR_DESCRIPTIONS = {
    RepairLevel.L1_SOFT_RESTART: "Soft Restart: kill and restart process within container",
    RepairLevel.L2_HARD_RESTART: "Hard Restart: delete pod, recreate with fresh config",
    RepairLevel.L3_REBUILD_CONTAINER: "Rebuild Container: pull fresh image, clear PVs",
    RepairLevel.L4_REPLACE_INSTANCE: "Replace Instance: spin up new node, migrate traffic",
    RepairLevel.L5_DECOMMISSION: "Decommission: automated repair failed, alerting human",
}

MAX_REPAIR_WINDOW = 600


@dataclass
class RepairAttempt:
    level: RepairLevel
    started_at: float
    completed_at: Optional[float] = None
    success: bool = False
    error_message: Optional[str] = None
    duration_seconds: float = 0


@dataclass
class RepairSession:
    node_id: str
    started_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    attempts: List[RepairAttempt] = field(default_factory=list)
    starting_level: RepairLevel = RepairLevel.L1_SOFT_RESTART
    final_result: Optional[str] = None

    @property
    def elapsed(self) -> float:
        return (self.completed_at or time.time()) - self.started_at

    @property
    def exceeded_window(self) -> bool:
        return self.elapsed > MAX_REPAIR_WINDOW


class RepairEngine:
    """5-Level automated repair system per DOC-015.

    Decision logic (Section 3.1):
    - First failure: start at L1
    - Second failure within 1 hour: start at L2
    - Third failure within 24 hours: start at L3
    - Fourth failure within 7 days: start at L4
    - Previously L5'd: skip to L5 immediately
    - Security-related: skip ALL, quarantine with forensics
    """

    def __init__(self, state_machine: NodeStateMachine, db_pool=None):
        self.state_machine = state_machine
        self._active_sessions: Dict[str, RepairSession] = {}
        self._repair_handlers: Dict[RepairLevel, Callable] = {}
        self._human_alert_callback: Optional[Callable] = None
        self._db_pool = db_pool  # asyncpg pool for session persistence

    def register_handler(self, level: RepairLevel, handler: Callable) -> None:
        self._repair_handlers[level] = handler

    def set_human_alert(self, callback: Callable) -> None:
        self._human_alert_callback = callback

    def determine_starting_level(self, node: GridNode) -> RepairLevel:
        recent_repairs = [
            a for a in node.repair_attempts
            if time.time() - a.get("started_at", 0) < 604800
        ]

        if node.metadata.get("security_incident"):
            return RepairLevel.L5_DECOMMISSION

        l5_history = [a for a in recent_repairs if a.get("level") == 5]
        if l5_history:
            return RepairLevel.L5_DECOMMISSION

        failures_7d = len(recent_repairs)
        failures_24h = len([a for a in recent_repairs if time.time() - a.get("started_at", 0) < 86400])
        failures_1h = len([a for a in recent_repairs if time.time() - a.get("started_at", 0) < 3600])

        if failures_7d >= 4:
            return RepairLevel.L4_REPLACE_INSTANCE
        if failures_24h >= 3:
            return RepairLevel.L3_REBUILD_CONTAINER
        if failures_1h >= 2:
            return RepairLevel.L2_HARD_RESTART
        return RepairLevel.L1_SOFT_RESTART

    async def _persist_session(self, session: RepairSession) -> None:
        """Persist repair session to DB for crash recovery."""
        if not self._db_pool:
            return
        try:
            import json
            attempts_json = json.dumps([
                {"level": a.level.value, "started_at": a.started_at,
                 "completed_at": a.completed_at, "success": a.success,
                 "error_message": a.error_message, "duration_seconds": a.duration_seconds}
                for a in session.attempts
            ])
            async with self._db_pool.acquire() as conn:
                await conn.execute(
                    """INSERT INTO repair_sessions
                       (session_id, node_id, started_at, completed_at,
                        starting_level, current_level, final_result, attempts)
                       VALUES ($1, $2, to_timestamp($3), $4, $5, $6, $7, $8::jsonb)
                       ON CONFLICT (session_id) DO UPDATE SET
                         completed_at = EXCLUDED.completed_at,
                         current_level = EXCLUDED.current_level,
                         final_result = EXCLUDED.final_result,
                         attempts = EXCLUDED.attempts""",
                    f"{session.node_id}_{int(session.started_at)}",
                    session.node_id,
                    session.started_at,
                    time.time() if session.completed_at else None,
                    session.starting_level.value,
                    session.attempts[-1].level.value if session.attempts else session.starting_level.value,
                    session.final_result,
                    attempts_json,
                )
        except Exception as e:
            logger.warning(f"Failed to persist repair session: {e}")

    async def resume_incomplete_sessions(self) -> List[str]:
        """Resume incomplete repair sessions from DB after restart."""
        if not self._db_pool:
            return []
        resumed = []
        try:
            async with self._db_pool.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT node_id, starting_level FROM repair_sessions "
                    "WHERE completed_at IS NULL ORDER BY started_at"
                )
            for row in rows:
                node_id = row["node_id"]
                node = self.state_machine.get_node(node_id)
                if node and node.state in (NodeState.QUARANTINE, NodeState.REPAIRING):
                    logger.info(f"Resuming incomplete repair for {node_id}")
                    asyncio.create_task(self.start_repair(node_id))
                    resumed.append(node_id)
                else:
                    # Node no longer needs repair — mark session complete
                    await self._mark_session_complete(node_id, "stale_on_restart")
        except Exception as e:
            logger.warning(f"Failed to resume repair sessions: {e}")
        return resumed

    async def _mark_session_complete(self, node_id: str, result: str) -> None:
        if not self._db_pool:
            return
        try:
            async with self._db_pool.acquire() as conn:
                await conn.execute(
                    "UPDATE repair_sessions SET completed_at = now(), final_result = $1 "
                    "WHERE node_id = $2 AND completed_at IS NULL",
                    result, node_id,
                )
        except Exception as e:
            logger.warning(f"Failed to mark session complete: {e}")

    async def start_repair(self, node_id: str) -> RepairSession:
        node = self.state_machine.get_node(node_id)
        if not node:
            raise ValueError(f"Node {node_id} not found")
        if node.state != NodeState.QUARANTINE:
            raise ValueError(f"Node must be in QUARANTINE (current: {node.state.value})")

        starting_level = self.determine_starting_level(node)
        session = RepairSession(node_id=node_id, starting_level=starting_level)
        self._active_sessions[node_id] = session

        self.state_machine.transition(node_id, NodeState.REPAIRING,
                                      f"Repair Engine starting at L{starting_level}")
        await self._persist_session(session)

        for level in RepairLevel:
            if level < starting_level:
                continue
            if session.exceeded_window:
                logger.warning(f"Repair window exceeded for {node_id}")
                break

            attempt = RepairAttempt(level=level, started_at=time.time())
            session.attempts.append(attempt)
            logger.info(f"Repair {node_id}: L{level} - {REPAIR_DESCRIPTIONS[level]}")

            if level == RepairLevel.L5_DECOMMISSION:
                attempt.completed_at = time.time()
                attempt.duration_seconds = attempt.completed_at - attempt.started_at
                session.final_result = "unrepairable"
                session.completed_at = time.time()
                await self._persist_session(session)
                if self._human_alert_callback:
                    await self._human_alert_callback(node, session)
                self.state_machine.transition(node_id, NodeState.DRAINING,
                                              "All repair levels exhausted")
                break

            success = False
            handler = self._repair_handlers.get(level)
            if handler:
                try:
                    success = await asyncio.wait_for(handler(node), timeout=REPAIR_TIMEOUTS[level])
                except asyncio.TimeoutError:
                    attempt.error_message = f"L{level} timed out after {REPAIR_TIMEOUTS[level]}s"
                except Exception as e:
                    attempt.error_message = str(e)
            else:
                attempt.error_message = f"No handler for L{level}"

            attempt.success = success
            attempt.completed_at = time.time()
            attempt.duration_seconds = attempt.completed_at - attempt.started_at

            node.repair_attempts.append({
                "level": level.value, "started_at": attempt.started_at,
                "success": success, "error": attempt.error_message,
                "duration": attempt.duration_seconds,
            })

            await self._persist_session(session)

            if success:
                session.final_result = "repaired"
                session.completed_at = time.time()
                await self._persist_session(session)
                self.state_machine.transition(node_id, NodeState.PROBATION,
                                              f"L{level} repair successful")
                break

        if not session.completed_at:
            session.final_result = "unrepairable"
            session.completed_at = time.time()
            await self._persist_session(session)
            self.state_machine.transition(node_id, NodeState.DRAINING, "Repair window exhausted")

        self._active_sessions.pop(node_id, None)
        return session

    def get_active_session(self, node_id: str) -> Optional[RepairSession]:
        return self._active_sessions.get(node_id)

    async def cancel_repair(self, node_id: str, reason: str = "self_healed") -> None:
        session = self._active_sessions.pop(node_id, None)
        if session:
            session.final_result = reason
            session.completed_at = time.time()
            await self._persist_session(session)
            logger.info(f"Repair cancelled for {node_id}: {reason}")
