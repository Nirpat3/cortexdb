"""Config Store — Live configuration with Redis + Postgres snapshots.

Redis Hash ``system:config`` is the hot path.  Point-in-time snapshots are
persisted to the ``config_snapshots`` table in PostgreSQL for audit / rollback.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Union

logger = logging.getLogger("cortexdb.ops_learning.config_store")

# ---------------------------------------------------------------------------
# Safe-range definitions
# ---------------------------------------------------------------------------

@dataclass
class SafeRange:
    """Declares the acceptable bounds for a config key.

    For numeric keys supply *min_val* / *max_val*.
    For enum keys supply *allowed_values*.
    """

    min_val: Optional[float] = None
    max_val: Optional[float] = None
    allowed_values: Optional[List[Any]] = None

    def validate(self, value: Any) -> bool:
        """Return True when *value* is within the declared safe range."""
        if self.allowed_values is not None:
            return value in self.allowed_values
        if self.min_val is not None and value < self.min_val:
            return False
        if self.max_val is not None and value > self.max_val:
            return False
        return True

    def clamp(self, value: float) -> float:
        """Clamp a numeric *value* to the safe range (no-op for enum ranges)."""
        if self.allowed_values is not None:
            return value  # can't clamp enums
        if self.min_val is not None:
            value = max(value, self.min_val)
        if self.max_val is not None:
            value = min(value, self.max_val)
        return value


# ---------------------------------------------------------------------------
# Default configuration shipped with CortexDB
# ---------------------------------------------------------------------------

DEFAULT_CONFIG: Dict[str, Dict[str, Any]] = {
    "cache.ttl_seconds":        {"value": 300,   "min": 60,    "max": 3600},
    "cache.semantic_threshold":  {"value": 0.82,  "min": 0.5,   "max": 0.99},
    "query.timeout_ms":         {"value": 5000,  "min": 500,   "max": 30000},
    "query.max_concurrent":     {"value": 50,    "min": 5,     "max": 500},
    "stream.batch_size":        {"value": 100,   "min": 10,    "max": 1000},
}


def _build_safe_ranges(defaults: Dict[str, Dict]) -> Dict[str, SafeRange]:
    """Derive SafeRange objects from the defaults table."""
    ranges: Dict[str, SafeRange] = {}
    for key, spec in defaults.items():
        if "allowed" in spec:
            ranges[key] = SafeRange(allowed_values=spec["allowed"])
        else:
            ranges[key] = SafeRange(min_val=spec.get("min"), max_val=spec.get("max"))
    return ranges


SAFE_RANGES: Dict[str, SafeRange] = _build_safe_ranges(DEFAULT_CONFIG)


# ---------------------------------------------------------------------------
# Config Store
# ---------------------------------------------------------------------------

MIGRATION_SQL = """\
CREATE TABLE IF NOT EXISTS config_snapshots (
    id          BIGSERIAL PRIMARY KEY,
    version     INTEGER NOT NULL UNIQUE,
    config_data JSONB   NOT NULL,
    created_by  TEXT    NOT NULL DEFAULT 'system',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    note        TEXT
);
CREATE INDEX IF NOT EXISTS idx_config_snapshots_version
    ON config_snapshots (version DESC);
"""

REDIS_KEY = "system:config"


class ConfigStore:
    """Ops Learning config store backed by Redis (hot) + Postgres (snapshots).

    Parameters
    ----------
    redis_client : aioredis connection (``redis.asyncio``).
    pg_pool : asyncpg connection pool (optional — snapshots disabled if None).
    signal_emitter : optional ``OpsSignalEmitter`` for change notifications.
    """

    def __init__(
        self,
        redis_client: Any = None,
        pg_pool: Any = None,
        signal_emitter: Any = None,
        safe_ranges: Optional[Dict[str, SafeRange]] = None,
    ):
        self._redis = redis_client
        self._pg = pg_pool
        self._emitter = signal_emitter
        self._safe_ranges = safe_ranges or dict(SAFE_RANGES)
        self._migrated = False

    # -- lifecycle -----------------------------------------------------------

    async def connect(self) -> None:
        """Ensure Redis has defaults and Postgres migration is applied."""
        await self._ensure_defaults()
        await self._ensure_migration()

    async def _ensure_defaults(self) -> None:
        if self._redis is None:
            return
        for key, spec in DEFAULT_CONFIG.items():
            exists = await self._redis.hexists(REDIS_KEY, key)
            if not exists:
                await self._redis.hset(REDIS_KEY, key, json.dumps(spec["value"]))
        logger.info("Config defaults ensured in Redis")

    async def _ensure_migration(self) -> None:
        if self._pg is None or self._migrated:
            return
        async with self._pg.acquire() as conn:
            await conn.execute(MIGRATION_SQL)
        self._migrated = True
        logger.info("config_snapshots table ensured")

    # -- read / write --------------------------------------------------------

    async def get(self, key: str) -> Any:
        """Return the current value for *key*, or None."""
        if self._redis is None:
            return DEFAULT_CONFIG.get(key, {}).get("value")
        raw = await self._redis.hget(REDIS_KEY, key)
        if raw is None:
            return None
        return json.loads(raw)

    async def get_all(self) -> Dict[str, Any]:
        """Return all current config as ``{key: value}``."""
        if self._redis is None:
            return {k: v["value"] for k, v in DEFAULT_CONFIG.items()}
        raw = await self._redis.hgetall(REDIS_KEY)
        return {k: json.loads(v) for k, v in raw.items()}

    async def set(self, key: str, value: Any, actor: str = "system") -> bool:
        """Set *key* to *value* after safe-range validation.

        Returns True on success, raises ValueError on range violation.
        """
        sr = self._safe_ranges.get(key)
        if sr and not sr.validate(value):
            raise ValueError(
                f"Value {value!r} for {key!r} is outside safe range "
                f"(min={sr.min_val}, max={sr.max_val}, allowed={sr.allowed_values})"
            )

        old = await self.get(key)

        if self._redis is not None:
            await self._redis.hset(REDIS_KEY, key, json.dumps(value))

        # emit change signal
        if self._emitter:
            await self._emitter.emit("ops.config_change", {
                "key": key,
                "old": old,
                "new": value,
                "actor": actor,
            })

        logger.info("Config %s updated: %s → %s (by %s)", key, old, value, actor)
        return True

    # -- snapshots -----------------------------------------------------------

    async def snapshot(self, actor: str = "system", note: str = "") -> int:
        """Persist current config to Postgres.  Returns the snapshot version."""
        config = await self.get_all()

        if self._pg is None:
            logger.warning("Postgres not configured — snapshot skipped")
            return -1

        async with self._pg.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT COALESCE(MAX(version), 0) AS v FROM config_snapshots"
            )
            next_version = row["v"] + 1
            await conn.execute(
                """INSERT INTO config_snapshots (version, config_data, created_by, note)
                   VALUES ($1, $2::jsonb, $3, $4)""",
                next_version,
                json.dumps(config),
                actor,
                note,
            )

        logger.info("Snapshot v%d created by %s", next_version, actor)
        return next_version

    async def rollback(self, version: int, actor: str = "healer") -> bool:
        """Restore config from a Postgres snapshot."""
        if self._pg is None:
            logger.error("Cannot rollback — Postgres not configured")
            return False

        async with self._pg.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT config_data FROM config_snapshots WHERE version = $1",
                version,
            )

        if row is None:
            logger.error("Snapshot v%d not found", version)
            return False

        config = json.loads(row["config_data"]) if isinstance(row["config_data"], str) else row["config_data"]

        if self._redis is not None:
            pipe = self._redis.pipeline()
            pipe.delete(REDIS_KEY)
            for k, v in config.items():
                pipe.hset(REDIS_KEY, k, json.dumps(v))
            await pipe.execute()

        if self._emitter:
            await self._emitter.emit("ops.config_change", {
                "key": "__rollback__",
                "old": None,
                "new": version,
                "actor": actor,
            })

        logger.info("Rolled back to snapshot v%d (by %s)", version, actor)
        return True

    # -- introspection -------------------------------------------------------

    def get_safe_range(self, key: str) -> Optional[SafeRange]:
        return self._safe_ranges.get(key)

    def register_safe_range(self, key: str, sr: SafeRange) -> None:
        self._safe_ranges[key] = sr
