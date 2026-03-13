"""Grid Repair Engine - 5-Level Automated Repair (DOC-015 Section 3)

L1 Soft Restart -> L2 Hard Restart -> L3 Rebuild -> L4 Replace -> L5 Decommission
Total automated repair window: 10 minutes max (NIRLAB-GRID-003).
"""

import asyncio
import json
import time
import logging
from enum import IntEnum
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional
from uuid import UUID

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
    db_session_id: Optional[UUID] = None

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

    def __init__(self, state_machine: NodeStateMachine, pool=None):
        self.state_machine = state_machine
        self.pool = pool  # optional asyncpg pool for persistence
        self._active_sessions: Dict[str, RepairSession] = {}
        self._repair_handlers: Dict[RepairLevel, Callable] = {}
        self._human_alert_callback: Optional[Callable] = None

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

    # ------------------------------------------------------------------
    # DB persistence helpers
    # ------------------------------------------------------------------

    async def _db_insert_session(self, session: RepairSession) -> Optional[UUID]:
        """Insert a new repair_sessions row. Returns session_id UUID."""
        if not self.pool:
            return None
        row = await self.pool.fetchrow(
            """INSERT INTO repair_sessions
                   (node_id, started_at, starting_level, current_level, attempts)
               VALUES ($1, NOW(), $2, $3, $4::jsonb)
               RETURNING session_id""",
            session.node_id,
            int(session.starting_level),
            int(session.starting_level),
            "[]",
        )
        return row["session_id"] if row else None

    async def _db_update_attempt(self, session: RepairSession, attempt: RepairAttempt) -> None:
        """Append an attempt to the JSONB array and update current_level."""
        if not self.pool or not session.db_session_id:
            return
        attempt_dict = {
            "level": int(attempt.level),
            "started_at": attempt.started_at,
            "completed_at": attempt.completed_at,
            "success": attempt.success,
            "error_message": attempt.error_message,
            "duration_seconds": attempt.duration_seconds,
        }
        await self.pool.execute(
            """UPDATE repair_sessions
               SET attempts = attempts || $1::jsonb,
                   current_level = $2
               WHERE session_id = $3""",
            json.dumps([attempt_dict]),
            int(attempt.level),
            session.db_session_id,
        )

    async def _db_complete_session(self, session: RepairSession) -> None:
        """Mark the session as completed."""
        if not self.pool or not session.db_session_id:
            return
        await self.pool.execute(
            """UPDATE repair_sessions
               SET completed_at = NOW(),
                   final_result = $1
               WHERE session_id = $2""",
            session.final_result,
            session.db_session_id,
        )

    # ------------------------------------------------------------------
    # Core repair loop
    # ------------------------------------------------------------------

    async def start_repair(self, node_id: str) -> RepairSession:
        node = self.state_machine.get_node(node_id)
        if not node:
            raise ValueError(f"Node {node_id} not found")
        if node.state != NodeState.QUARANTINE:
            raise ValueError(f"Node must be in QUARANTINE (current: {node.state.value})")

        starting_level = self.determine_starting_level(node)
        session = RepairSession(node_id=node_id, starting_level=starting_level)
        self._active_sessions[node_id] = session

        # Persist session start
        session.db_session_id = await self._db_insert_session(session)

        self.state_machine.transition(node_id, NodeState.REPAIRING,
                                      f"Repair Engine starting at L{starting_level}")

        await self._run_repair_loop(node_id, session, starting_level)
        return session

    async def _run_repair_loop(
        self, node_id: str, session: RepairSession, from_level: RepairLevel
    ) -> None:
        """Execute repair levels starting from from_level."""
        node = self.state_machine.get_node(node_id)

        for level in RepairLevel:
            if level < from_level:
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
                await self._db_update_attempt(session, attempt)
                await self._db_complete_session(session)
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

            # Persist attempt
            await self._db_update_attempt(session, attempt)

            node.repair_attempts.append({
                "level": level.value, "started_at": attempt.started_at,
                "success": success, "error": attempt.error_message,
                "duration": attempt.duration_seconds,
            })

            if success:
                session.final_result = "repaired"
                session.completed_at = time.time()
                await self._db_complete_session(session)
                self.state_machine.transition(node_id, NodeState.PROBATION,
                                              f"L{level} repair successful")
                break

        if not session.completed_at:
            session.final_result = "unrepairable"
            session.completed_at = time.time()
            await self._db_complete_session(session)
            self.state_machine.transition(node_id, NodeState.DRAINING, "Repair window exhausted")

        self._active_sessions.pop(node_id, None)

    # ------------------------------------------------------------------
    # Resume incomplete sessions after restart
    # ------------------------------------------------------------------

    async def resume_incomplete_sessions(self) -> List[RepairSession]:
        """Query repair_sessions WHERE completed_at IS NULL and resume each.

        Returns a list of resumed (and now completed) RepairSessions.
        """
        if not self.pool:
            logger.warning("Cannot resume sessions: no database pool configured")
            return []

        rows = await self.pool.fetch(
            """SELECT session_id, node_id, starting_level, current_level, attempts
               FROM repair_sessions
               WHERE completed_at IS NULL
               ORDER BY started_at ASC"""
        )

        if not rows:
            logger.info("No incomplete repair sessions to resume")
            return []

        logger.info(f"Found {len(rows)} incomplete repair session(s) to resume")
        resumed: List[RepairSession] = []

        for row in rows:
            node_id = row["node_id"]
            resume_level = RepairLevel(row["current_level"])
            db_session_id = row["session_id"]

            node = self.state_machine.get_node(node_id)
            if not node:
                logger.warning(f"Resume skipped: node {node_id} no longer exists")
                # Mark as abandoned in DB
                await self.pool.execute(
                    """UPDATE repair_sessions
                       SET completed_at = NOW(), final_result = 'abandoned_node_gone'
                       WHERE session_id = $1""",
                    db_session_id,
                )
                continue

            # Rebuild in-memory session from DB state
            prior_attempts_raw = row["attempts"] if row["attempts"] else []
            prior_attempts = [
                RepairAttempt(
                    level=RepairLevel(a["level"]),
                    started_at=a["started_at"],
                    completed_at=a.get("completed_at"),
                    success=a.get("success", False),
                    error_message=a.get("error_message"),
                    duration_seconds=a.get("duration_seconds", 0),
                )
                for a in prior_attempts_raw
            ]

            session = RepairSession(
                node_id=node_id,
                starting_level=RepairLevel(row["starting_level"]),
                attempts=prior_attempts,
            )
            session.db_session_id = db_session_id
            self._active_sessions[node_id] = session

            # Advance past already-completed levels
            # If current_level attempt already succeeded/failed, start from next level
            next_level = resume_level
            if prior_attempts and prior_attempts[-1].level == resume_level:
                last = prior_attempts[-1]
                if last.completed_at is not None and not last.success:
                    # Last attempt at this level failed, move to next
                    next_val = int(resume_level) + 1
                    if next_val <= RepairLevel.L5_DECOMMISSION:
                        next_level = RepairLevel(next_val)

            logger.info(f"Resuming repair for {node_id} at L{next_level} "
                        f"(session {db_session_id})")

            # Ensure node is in REPAIRING state for the loop
            if node.state != NodeState.REPAIRING:
                try:
                    self.state_machine.transition(
                        node_id, NodeState.REPAIRING,
                        f"Resuming repair at L{next_level}")
                except Exception as e:
                    logger.error(f"Cannot resume {node_id}: state transition failed: {e}")
                    await self.pool.execute(
                        """UPDATE repair_sessions
                           SET completed_at = NOW(), final_result = 'abandoned_bad_state'
                           WHERE session_id = $1""",
                        db_session_id,
                    )
                    self._active_sessions.pop(node_id, None)
                    continue

            await self._run_repair_loop(node_id, session, next_level)
            resumed.append(session)

        return resumed

    def get_active_session(self, node_id: str) -> Optional[RepairSession]:
        return self._active_sessions.get(node_id)

    def cancel_repair(self, node_id: str, reason: str = "self_healed") -> None:
        session = self._active_sessions.pop(node_id, None)
        if session:
            session.final_result = reason
            session.completed_at = time.time()
            logger.info(f"Repair cancelled for {node_id}: {reason}")
