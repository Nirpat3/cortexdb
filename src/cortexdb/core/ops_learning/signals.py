"""Ops Signals — Emit operational telemetry to Redis Streams.

Wraps the existing ``StreamEngine`` when available, otherwise talks to
Redis directly via a thin async client.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, Optional

logger = logging.getLogger("cortexdb.ops_learning.signals")

STREAM_KEY = "cortex:ops_signals"

# Recognised signal types (informational — the emitter does not enforce them).
SIGNAL_TYPES = frozenset({
    "ops.latency",
    "ops.error_rate",
    "ops.cache_hit",
    "ops.queue_depth",
    "ops.config_change",
})


class OpsSignalEmitter:
    """Emit operational signals to a Redis Stream.

    Parameters
    ----------
    redis_client : An ``redis.asyncio`` client (or compatible).
    stream_engine : Existing ``StreamEngine`` instance (preferred if available).
    stream_key : Override the default stream name.
    """

    def __init__(
        self,
        redis_client: Any = None,
        stream_engine: Any = None,
        stream_key: str = STREAM_KEY,
    ):
        self._redis = redis_client
        self._stream_engine = stream_engine
        self._stream_key = stream_key

    async def emit(self, signal_type: str, payload: Dict[str, Any]) -> Optional[str]:
        """Publish a signal.  Returns the Redis Stream message ID."""
        entry = {
            "type": signal_type,
            "payload": json.dumps(payload, default=str),
            "ts": str(time.time()),
        }

        # Prefer the existing StreamEngine if wired up
        if self._stream_engine is not None:
            try:
                return await self._stream_engine.publish(self._stream_key, entry)
            except Exception:
                logger.exception("StreamEngine publish failed, falling back to raw Redis")

        if self._redis is not None:
            return await self._redis.xadd(self._stream_key, entry)

        # No backend — log only (useful in tests / local dev)
        logger.warning("No Redis backend — signal %s dropped: %s", signal_type, payload)
        return None

    async def read_recent(
        self,
        count: int = 100,
        last_id: str = "0-0",
    ) -> list[Dict[str, Any]]:
        """Read recent signals from the stream (used by Meta-Agent)."""
        if self._stream_engine is not None:
            raw = await self._stream_engine.subscribe(self._stream_key, last_id=last_id, count=count)
            return _parse_stream_response(raw)

        if self._redis is not None:
            raw = await self._redis.xread({self._stream_key: last_id}, count=count)
            return _parse_stream_response(raw)

        return []


def _parse_stream_response(raw: Any) -> list[Dict[str, Any]]:
    """Normalise the nested list returned by XREAD into flat dicts."""
    results: list[Dict[str, Any]] = []
    if not raw:
        return results
    for _stream_name, messages in raw:
        for msg_id, fields in messages:
            entry = {"_id": msg_id}
            for k, v in fields.items():
                try:
                    entry[k] = json.loads(v)
                except (json.JSONDecodeError, TypeError):
                    entry[k] = v
            results.append(entry)
    return results
