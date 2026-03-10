"""ImmutableCore — Tamper-Evident Audit Ledger (PostgreSQL-backed)

Append-only ledger with SHA-256 hash chain stored in the `immutable_ledger`
PostgreSQL table. The DB has triggers that prevent UPDATE/DELETE, and a
server-side `append_to_ledger()` function that computes the hash chain.

P0 FIX: Removed file-based storage which had no file locking and corrupted
under concurrent writes. PostgreSQL provides the necessary ACID guarantees.
"""

import json
import logging
from typing import Any, Dict, Optional
from cortexdb.engines import BaseEngine

logger = logging.getLogger("cortexdb.engines.immutable")


class ImmutableEngine(BaseEngine):
    def __init__(self, config: Dict):
        # Accept a relational engine reference, or fall back to pool URL
        self._relational = config.get("relational_engine")
        self._pool = None

    async def connect(self):
        """Connect using the shared relational engine pool if available."""
        if self._relational and hasattr(self._relational, "pool"):
            self._pool = self._relational.pool
        else:
            # Standalone mode: create our own pool
            try:
                import asyncpg
                import os
                url = os.getenv(
                    "RELATIONAL_CORE_URL",
                    "postgresql://cortex:cortex_secret@localhost:5432/cortexdb")
                self._pool = await asyncpg.create_pool(url, min_size=1, max_size=5)
            except Exception as e:
                logger.error(f"ImmutableCore failed to connect to PostgreSQL: {e}")
                raise

    async def close(self):
        # Only close the pool if we created it ourselves (not shared)
        if self._pool and not self._relational:
            await self._pool.close()

    async def health(self) -> Dict:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT COUNT(*) as cnt FROM immutable_ledger")
            integrity = await conn.fetchrow(
                "SELECT * FROM verify_ledger_integrity()")
            return {
                "engine": "PostgreSQL Immutable Ledger",
                "brain_region": "Declarative Memory",
                "entries": row["cnt"],
                "chain_intact": integrity["is_valid"] if integrity else False,
            }

    async def append(self, entry_type: str, payload: Dict, actor: str = "system") -> Dict:
        """Append immutable entry via the PostgreSQL append_to_ledger() function.

        The DB function computes the SHA-256 hash chain server-side, ensuring
        atomicity even under concurrent writes.
        """
        async with self._pool.acquire() as conn:
            entry_id = await conn.fetchval(
                "SELECT append_to_ledger($1, $2::jsonb, $3)",
                entry_type,
                json.dumps(payload, sort_keys=True, default=str),
                actor,
            )
            # Return the full entry for callers that need it
            row = await conn.fetchrow(
                "SELECT * FROM immutable_ledger WHERE entry_id = $1", entry_id)
            return {
                "sequence": row["sequence_id"],
                "entry_id": str(row["entry_id"]),
                "type": row["entry_type"],
                "payload": row["payload"],
                "actor": row["actor"],
                "prev_hash": row["prev_hash"],
                "hash": row["entry_hash"],
                "timestamp": row["created_at"].timestamp(),
            }

    async def verify_chain(self) -> bool:
        """Verify entire hash chain integrity using the PG server-side function."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM verify_ledger_integrity()")
            if row is None:
                return True  # Empty ledger is valid
            return row["is_valid"]

    async def write(self, data_type: str, payload: Dict, actor: str = "system") -> Any:
        """BaseEngine interface — delegates to append()."""
        return await self.append(data_type, payload, actor)
