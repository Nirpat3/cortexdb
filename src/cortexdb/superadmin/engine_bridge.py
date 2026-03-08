"""
Engine Bridge — Connects the SuperAdmin intelligence layer to CortexDB's 7 core engines.

Before Phase 7, all agent data lived in SQLite. Now:
  - VectorCore (Qdrant): Semantic memory recall via embeddings
  - StreamCore (Redis Streams): Real-time task lifecycle events
  - ImmutableCore (Hash chain): Tamper-proof execution audit trail

This module provides a unified interface for the intelligence layer
to read/write through the core engines.
"""

import time
import hashlib
import logging
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


class EngineBridge:
    """Bridges SuperAdmin intelligence layer to CortexDB core engines."""

    def __init__(self, engines: Dict[str, Any]):
        self._engines = engines
        self._available = set(engines.keys())
        logger.info("EngineBridge initialized with engines: %s", list(self._available))

    @property
    def has_vector(self) -> bool:
        return "vector" in self._available

    @property
    def has_stream(self) -> bool:
        return "stream" in self._available

    @property
    def has_immutable(self) -> bool:
        return "immutable" in self._available

    # ── VectorCore: Semantic Agent Memory ──

    async def store_memory_vector(self, agent_id: str, fact: str,
                                   category: str = "general",
                                   metadata: dict = None) -> Optional[str]:
        """Store a fact as a semantic vector in Qdrant for similarity recall."""
        if not self.has_vector:
            return None

        vector_engine = self._engines["vector"]
        point_id = hashlib.sha256(f"{agent_id}:{fact}:{time.time()}".encode()).hexdigest()[:32]

        payload = {
            "agent_id": agent_id,
            "fact": fact,
            "category": category,
            "timestamp": time.time(),
            **(metadata or {}),
        }

        try:
            await vector_engine.upsert_vectors("agent_memory", [{
                "id": point_id,
                "text": fact,
                "payload": payload,
            }])
            return point_id
        except Exception as e:
            logger.warning("Failed to store memory vector for %s: %s", agent_id, e)
            return None

    async def recall_similar(self, agent_id: str, query: str,
                             limit: int = 5, threshold: float = 0.6) -> List[dict]:
        """Semantic recall: find facts similar to a query using vector search."""
        if not self.has_vector:
            return []

        vector_engine = self._engines["vector"]
        try:
            from qdrant_client.models import Filter, FieldCondition, MatchValue
            # Search with agent filter
            results = await vector_engine.search_similar(
                collection="agent_memory",
                query_text=query,
                threshold=threshold,
                limit=limit,
            )
            # Filter to this agent's facts
            return [
                {
                    "fact": r["payload"].get("fact", ""),
                    "category": r["payload"].get("category", ""),
                    "score": r["score"],
                    "timestamp": r["payload"].get("timestamp"),
                }
                for r in results
                if r["payload"].get("agent_id") == agent_id
            ]
        except Exception as e:
            logger.warning("Semantic recall failed for %s: %s", agent_id, e)
            return []

    async def recall_global(self, query: str, limit: int = 10,
                            threshold: float = 0.5) -> List[dict]:
        """Global semantic search across all agent memories."""
        if not self.has_vector:
            return []

        vector_engine = self._engines["vector"]
        try:
            results = await vector_engine.search_similar(
                collection="agent_memory",
                query_text=query,
                threshold=threshold,
                limit=limit,
            )
            return [
                {
                    "agent_id": r["payload"].get("agent_id", ""),
                    "fact": r["payload"].get("fact", ""),
                    "category": r["payload"].get("category", ""),
                    "score": r["score"],
                }
                for r in results
            ]
        except Exception as e:
            logger.warning("Global recall failed: %s", e)
            return []

    # ── StreamCore: Real-time Task Events ──

    async def publish_event(self, event_type: str, data: dict) -> Optional[str]:
        """Publish a task lifecycle event to Redis Streams."""
        if not self.has_stream:
            return None

        stream_engine = self._engines["stream"]
        try:
            event = {
                "event_type": event_type,
                "timestamp": str(time.time()),
                **{k: str(v) if not isinstance(v, str) else v for k, v in data.items()},
            }
            return await stream_engine.publish("cortex:agent_events", event)
        except Exception as e:
            logger.warning("Failed to publish event %s: %s", event_type, e)
            return None

    async def read_events(self, last_id: str = "0", count: int = 20) -> List[dict]:
        """Read recent agent events from the stream."""
        if not self.has_stream:
            return []

        stream_engine = self._engines["stream"]
        try:
            raw = await stream_engine.subscribe("cortex:agent_events",
                                                 last_id=last_id, count=count)
            events = []
            for stream_data in (raw or []):
                for msg_id, fields in stream_data[1]:
                    events.append({"id": msg_id, **fields})
            return events
        except Exception as e:
            logger.warning("Failed to read events: %s", e)
            return []

    # ── ImmutableCore: Tamper-proof Execution Audit ──

    async def log_execution(self, task_id: str, agent_id: str,
                            action: str, details: dict) -> Optional[dict]:
        """Append an execution record to the immutable hash chain."""
        if not self.has_immutable:
            return None

        immutable_engine = self._engines["immutable"]
        try:
            entry = await immutable_engine.append(
                entry_type="agent_execution",
                payload={
                    "task_id": task_id,
                    "agent_id": agent_id,
                    "action": action,
                    "timestamp": time.time(),
                    **details,
                },
                actor=agent_id or "system",
            )
            return {"sequence": entry["sequence"], "hash": entry["hash"]}
        except Exception as e:
            logger.warning("Failed to log execution: %s", e)
            return None

    async def verify_audit_chain(self) -> dict:
        """Verify the integrity of the immutable audit chain."""
        if not self.has_immutable:
            return {"available": False}

        immutable_engine = self._engines["immutable"]
        try:
            intact = await immutable_engine.verify_chain()
            return {
                "available": True,
                "chain_intact": intact,
                "entries": len(immutable_engine._chain),
            }
        except Exception as e:
            return {"available": True, "error": str(e)}

    # ── Status ──

    def get_status(self) -> dict:
        return {
            "engines_available": list(self._available),
            "vector_connected": self.has_vector,
            "stream_connected": self.has_stream,
            "immutable_connected": self.has_immutable,
        }
