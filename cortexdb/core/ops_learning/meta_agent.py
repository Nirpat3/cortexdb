"""Meta-Agent — Scheduled job that reads signals and proposes config patches.

v1 uses a simple rule table.  Future versions may plug in ML models or
delegate to a full Temporal workflow.

The loop is **opt-in** — gated by ``OPS_LEARNING_ENABLED`` env var.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any, Dict, List, Optional

from cortexdb.core.ops_learning.config_store import ConfigStore
from cortexdb.core.ops_learning.signals import OpsSignalEmitter

logger = logging.getLogger("cortexdb.ops_learning.meta_agent")

# ---------------------------------------------------------------------------
# Rule table (v1) — kept intentionally simple
# ---------------------------------------------------------------------------

RULES: List[Dict[str, Any]] = [
    {
        "name": "high_p95_latency",
        "signal": "ops.latency",
        "condition": lambda payload: payload.get("p95", 0) > 2000,
        "patch": {"query.timeout_ms": 8000, "query.max_concurrent": 30},
        "reason": "p95 latency exceeds 2 s — reducing concurrency & extending timeout",
    },
    {
        "name": "low_cache_hit_ratio",
        "signal": "ops.cache_hit",
        "condition": lambda payload: payload.get("ratio", 1.0) < 0.3,
        "patch": {"cache.ttl_seconds": 600, "cache.semantic_threshold": 0.75},
        "reason": "Cache hit ratio below 30 % — extending TTL & lowering threshold",
    },
    {
        "name": "queue_backpressure",
        "signal": "ops.queue_depth",
        "condition": lambda payload: (
            payload.get("depth", 0) > 0.8 * payload.get("max", 1000)
        ),
        "patch": {"stream.batch_size": 200},
        "reason": "Queue depth > 80 % capacity — increasing batch size",
    },
]


class MetaAgent:
    """Periodically evaluates ops signals and proposes config patches.

    Parameters
    ----------
    config_store : The active ``ConfigStore``.
    signal_emitter : ``OpsSignalEmitter`` for reading recent signals.
    interval_sec : Seconds between evaluation cycles.
    enabled : Override the ``OPS_LEARNING_ENABLED`` env var.
    """

    def __init__(
        self,
        config_store: ConfigStore,
        signal_emitter: OpsSignalEmitter,
        interval_sec: float = 60.0,
        enabled: Optional[bool] = None,
    ):
        self.config_store = config_store
        self.signal_emitter = signal_emitter
        self.interval_sec = interval_sec
        self.enabled = enabled if enabled is not None else (
            os.getenv("OPS_LEARNING_ENABLED", "false").lower() in ("1", "true", "yes")
        )
        self._last_stream_id = "0-0"
        self._task: Optional[asyncio.Task] = None

    # -- lifecycle -----------------------------------------------------------

    async def start(self) -> None:
        """Start the background evaluation loop."""
        if not self.enabled:
            logger.info("Meta-Agent disabled (OPS_LEARNING_ENABLED != true)")
            return
        self._task = asyncio.create_task(self._loop(), name="ops-meta-agent")
        logger.info("Meta-Agent started (interval=%ss)", self.interval_sec)

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
            logger.info("Meta-Agent stopped")

    # -- core loop -----------------------------------------------------------

    async def _loop(self) -> None:
        while True:
            try:
                await self._evaluate_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Meta-Agent evaluation error")
            await asyncio.sleep(self.interval_sec)

    async def _evaluate_once(self) -> Dict[str, Any]:
        """Run one evaluation cycle.  Returns the applied patch (if any)."""
        signals = await self.signal_emitter.read_recent(
            count=200, last_id=self._last_stream_id
        )

        if signals:
            self._last_stream_id = signals[-1].get("_id", self._last_stream_id)

        patch = self._propose_patch(signals)
        if not patch:
            return {}

        # Snapshot before applying
        await self.config_store.snapshot(actor="meta-agent", note="pre-patch")

        applied: Dict[str, Any] = {}
        for key, value in patch.items():
            try:
                await self.config_store.set(key, value, actor="meta-agent")
                applied[key] = value
            except ValueError as exc:
                logger.warning("Patch rejected for %s: %s", key, exc)

        if applied:
            logger.info("Meta-Agent applied patch: %s", applied)

        return applied

    # -- rule evaluation -----------------------------------------------------

    def _propose_patch(self, signals: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Evaluate the rule table against recent signals.

        Returns a merged patch dict (last rule wins per key).
        """
        patch: Dict[str, Any] = {}

        for rule in RULES:
            target_type = rule["signal"]
            matching = [
                s for s in signals
                if s.get("type") == target_type
            ]
            for sig in matching:
                payload = sig.get("payload", {})
                if isinstance(payload, str):
                    import json
                    try:
                        payload = json.loads(payload)
                    except Exception:
                        continue
                try:
                    if rule["condition"](payload):
                        patch.update(rule["patch"])
                        logger.debug("Rule %s triggered: %s", rule["name"], rule["reason"])
                except Exception:
                    logger.debug("Rule %s eval error", rule["name"], exc_info=True)

        return patch
