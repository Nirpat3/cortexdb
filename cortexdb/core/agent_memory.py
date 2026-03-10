"""Agent Memory Protocol — Persistent memory layer for AI agents.

Cognitive science inspired:
  - Episodic memory: specific events/interactions (auto-decays)
  - Semantic memory: facts/knowledge (stable, long-term)
  - Working memory: current task context (short TTL, Redis-backed)

Storage:
  - PostgreSQL: structured memory records (source of truth)
  - Qdrant: vector embeddings for semantic recall
  - Redis: working memory cache (fast access, auto-expire)

Access control:
  - Each memory has an owner (agent_id)
  - Shared memories have explicit ACL (list of agent_ids)
  - Tenant isolation via tenant_id

Operations:
  cortexdb.memory.store   — Agent stores a memory (auto-vectorized, auto-indexed)
  cortexdb.memory.recall  — Agent recalls relevant memories (semantic search + time decay)
  cortexdb.memory.forget  — GDPR-compliant memory deletion (removes from PG + Qdrant)
  cortexdb.memory.share   — Share memory with another agent (access-controlled)
"""

import json
import logging
import math
import time
import uuid
from typing import Any, Dict, List, Optional

logger = logging.getLogger("cortexdb.core.agent_memory")

# Qdrant collection name for agent memories
AGENT_MEMORY_COLLECTION = "agent_memory"

# Time decay constant: memories lose ~50% relevance after 30 days
TIME_DECAY_LAMBDA = math.log(2) / 30.0

# Default TTL for working memory (10 minutes)
WORKING_MEMORY_TTL = 600

# Valid memory types
VALID_MEMORY_TYPES = {"episodic", "semantic", "working"}


class AgentMemory:
    """Persistent, shared, access-controlled memory layer for AI agents.

    Stores memories across PostgreSQL (structured records), Qdrant (vector
    embeddings for semantic recall), and Redis (working memory cache).
    """

    def __init__(self, engines: Dict[str, Any], embedding):
        """Initialize AgentMemory with engine references.

        Args:
            engines: Dict of engine name -> engine instance. Expected keys:
                     "relational" (RelationalEngine), "vector" (VectorEngine),
                     "memory" (MemoryEngine).
            embedding: EmbeddingPipeline instance for text vectorization.
        """
        self.engines = engines
        self.embedding = embedding
        self._schema_initialized = False

    async def _ensure_schema(self):
        """Create the agent_memories table if it does not exist.

        Runs the schema SQL idempotently on first use.
        """
        if self._schema_initialized:
            return

        relational = self.engines.get("relational")
        if not relational or not relational.pool:
            return

        import pathlib
        schema_path = pathlib.Path(__file__).parent / "agent_memory_schema.sql"
        if schema_path.exists():
            schema_sql = schema_path.read_text(encoding="utf-8")
            async with relational.pool.acquire() as conn:
                await conn.execute(schema_sql)
            logger.info("Agent memory schema initialized")

        self._schema_initialized = True

    async def _ensure_vector_collection(self):
        """Ensure the Qdrant collection for agent memories exists."""
        vector = self.engines.get("vector")
        if vector:
            await vector._ensure_collection(AGENT_MEMORY_COLLECTION)

    # ─── store ────────────────────────────────────────────────────────────

    async def store(
        self,
        agent_id: str,
        content: str,
        memory_type: str = "episodic",
        metadata: Optional[Dict] = None,
        tenant_id: Optional[str] = None,
        ttl_seconds: Optional[int] = None,
        importance: float = 0.5,
    ) -> Dict:
        """Store a memory. Auto-embeds content and indexes across engines.

        Args:
            agent_id: Owner agent identifier.
            content: Text content of the memory.
            memory_type: One of "episodic", "semantic", "working".
            metadata: Optional JSON-serializable metadata dict.
            tenant_id: Tenant identifier for isolation.
            ttl_seconds: Time-to-live in seconds. Auto-set for working memory
                         if not provided. None means no expiration.
            importance: Relevance weight between 0.0 and 1.0.

        Returns:
            Dict with memory_id, agent_id, memory_type, created_at.
        """
        if memory_type not in VALID_MEMORY_TYPES:
            raise ValueError(
                f"Invalid memory_type '{memory_type}'. "
                f"Must be one of: {', '.join(sorted(VALID_MEMORY_TYPES))}"
            )
        importance = max(0.0, min(1.0, importance))
        metadata = metadata or {}

        await self._ensure_schema()

        memory_id = str(uuid.uuid4())
        now = time.time()

        # If working memory and no TTL specified, use the default
        if memory_type == "working" and ttl_seconds is None:
            ttl_seconds = WORKING_MEMORY_TTL

        # 1. Generate embedding
        embedding_vector = self.embedding.embed(content)

        # 2. Store in PostgreSQL (source of truth)
        created_at = await self._store_pg(
            memory_id=memory_id,
            agent_id=agent_id,
            tenant_id=tenant_id,
            memory_type=memory_type,
            content=content,
            metadata=metadata,
            importance=importance,
            ttl_seconds=ttl_seconds,
        )

        # 3. Upsert to Qdrant for semantic recall
        await self._store_qdrant(
            memory_id=memory_id,
            agent_id=agent_id,
            tenant_id=tenant_id,
            memory_type=memory_type,
            content=content,
            metadata=metadata,
            importance=importance,
            embedding_vector=embedding_vector,
            created_at=now,
        )

        # 4. If working memory, also cache in Redis with TTL
        if memory_type == "working":
            await self._store_redis(
                memory_id=memory_id,
                agent_id=agent_id,
                tenant_id=tenant_id,
                content=content,
                metadata=metadata,
                ttl_seconds=ttl_seconds or WORKING_MEMORY_TTL,
            )

        logger.info(
            "Stored %s memory %s for agent %s",
            memory_type, memory_id, agent_id,
        )
        return {
            "memory_id": memory_id,
            "agent_id": agent_id,
            "memory_type": memory_type,
            "created_at": created_at or now,
        }

    async def _store_pg(
        self,
        memory_id: str,
        agent_id: str,
        tenant_id: Optional[str],
        memory_type: str,
        content: str,
        metadata: Dict,
        importance: float,
        ttl_seconds: Optional[int],
    ) -> Optional[str]:
        """Insert a memory record into PostgreSQL."""
        relational = self.engines.get("relational")
        if not relational or not relational.pool:
            return None

        async with relational.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO agent_memories
                    (id, agent_id, tenant_id, memory_type, content, metadata,
                     importance, expires_at)
                VALUES
                    ($1::uuid, $2, $3, $4, $5, $6::jsonb, $7,
                     CASE WHEN $8::int IS NOT NULL
                          THEN NOW() + ($8::int || ' seconds')::interval
                          ELSE NULL END)
                RETURNING created_at
                """,
                memory_id,
                agent_id,
                tenant_id,
                memory_type,
                content,
                json.dumps(metadata),
                importance,
                ttl_seconds,
            )
            return str(row["created_at"]) if row else None

    async def _store_qdrant(
        self,
        memory_id: str,
        agent_id: str,
        tenant_id: Optional[str],
        memory_type: str,
        content: str,
        metadata: Dict,
        importance: float,
        embedding_vector: List[float],
        created_at: float,
    ):
        """Upsert memory embedding into Qdrant."""
        vector = self.engines.get("vector")
        if not vector:
            return

        await self._ensure_vector_collection()

        payload = {
            "agent_id": agent_id,
            "memory_type": memory_type,
            "content": content,
            "importance": importance,
            "created_at": created_at,
            "shared_with": [],
        }
        if tenant_id:
            payload["tenant_id"] = tenant_id
        if metadata:
            payload["metadata"] = metadata

        await vector.upsert_vectors(
            collection=AGENT_MEMORY_COLLECTION,
            points=[{
                "id": memory_id,
                "vector": embedding_vector,
                "payload": payload,
            }],
        )

    async def _store_redis(
        self,
        memory_id: str,
        agent_id: str,
        tenant_id: Optional[str],
        content: str,
        metadata: Dict,
        ttl_seconds: int,
    ):
        """Cache working memory in Redis with TTL."""
        mem_engine = self.engines.get("memory")
        if not mem_engine:
            return

        redis_key = self._redis_key(agent_id, memory_id, tenant_id)
        value = json.dumps({
            "memory_id": memory_id,
            "agent_id": agent_id,
            "content": content,
            "metadata": metadata,
            "memory_type": "working",
        })
        await mem_engine.set(redis_key, value, ex=ttl_seconds)

    # ─── recall ───────────────────────────────────────────────────────────

    async def recall(
        self,
        agent_id: str,
        query: str,
        memory_type: Optional[str] = None,
        limit: int = 10,
        time_decay: bool = True,
        include_shared: bool = True,
        tenant_id: Optional[str] = None,
    ) -> List[Dict]:
        """Recall relevant memories via semantic search + time decay.

        Args:
            agent_id: The requesting agent's identifier.
            query: Natural-language query to match against memories.
            memory_type: Optionally filter by memory type.
            limit: Maximum number of memories to return.
            time_decay: If True, newer memories score higher.
            include_shared: If True, include memories shared with this agent.
            tenant_id: Tenant identifier for isolation.

        Returns:
            List of memory dicts sorted by relevance, each containing
            memory_id, content, similarity, memory_type, created_at, etc.
        """
        if memory_type and memory_type not in VALID_MEMORY_TYPES:
            raise ValueError(
                f"Invalid memory_type '{memory_type}'. "
                f"Must be one of: {', '.join(sorted(VALID_MEMORY_TYPES))}"
            )

        limit = max(1, min(limit, 100))
        results: List[Dict] = []

        # 1. Check working memory (Redis) first for hot data
        redis_memories = await self._recall_redis(agent_id, tenant_id)
        for mem in redis_memories:
            if memory_type and mem.get("memory_type") != memory_type:
                continue
            # Compute similarity for Redis-cached items
            query_vec = self.embedding.embed(query)
            content_vec = self.embedding.embed(mem["content"])
            similarity = self.embedding.similarity(query_vec, content_vec)
            mem["similarity"] = round(similarity, 4)
            mem["source"] = "working_memory"
            results.append(mem)

        # 2. Semantic search via Qdrant
        vector_results = await self._recall_qdrant(
            agent_id=agent_id,
            query=query,
            memory_type=memory_type,
            limit=limit * 2,  # fetch extra for post-filtering
            include_shared=include_shared,
            tenant_id=tenant_id,
        )
        results.extend(vector_results)

        # 3. Deduplicate by memory_id (prefer Qdrant results over Redis)
        seen = set()
        deduped = []
        for mem in results:
            mid = mem.get("memory_id")
            if mid and mid not in seen:
                seen.add(mid)
                deduped.append(mem)
        results = deduped

        # 4. Apply time decay: score *= exp(-lambda * age_days)
        now = time.time()
        for mem in results:
            raw_similarity = mem.get("similarity", 0.0)
            if time_decay:
                created = mem.get("created_at_epoch", now)
                age_days = max(0, (now - created) / 86400.0)
                decay_factor = math.exp(-TIME_DECAY_LAMBDA * age_days)
            else:
                decay_factor = 1.0

            importance = mem.get("importance", 0.5)
            # Combined score: similarity * decay * (0.5 + 0.5 * importance)
            mem["score"] = round(
                raw_similarity * decay_factor * (0.5 + 0.5 * importance), 4
            )

        # 5. Sort by combined score and truncate
        results.sort(key=lambda m: m.get("score", 0), reverse=True)
        results = results[:limit]

        # 6. Update access counts in PostgreSQL (fire-and-forget)
        memory_ids = [m["memory_id"] for m in results if m.get("memory_id")]
        if memory_ids:
            await self._touch_access(memory_ids)

        return results

    async def _recall_redis(
        self, agent_id: str, tenant_id: Optional[str]
    ) -> List[Dict]:
        """Scan Redis for cached working memories belonging to this agent."""
        mem_engine = self.engines.get("memory")
        if not mem_engine or not mem_engine.client:
            return []

        pattern = self._redis_key(agent_id, "*", tenant_id)
        memories = []
        try:
            cursor = "0"
            while True:
                cursor, keys = await mem_engine.client.scan(
                    cursor=cursor, match=pattern, count=50
                )
                for key in keys:
                    raw = await mem_engine.client.get(key)
                    if raw:
                        try:
                            memories.append(json.loads(raw))
                        except json.JSONDecodeError:
                            pass
                if cursor == 0 or cursor == "0":
                    break
        except Exception as e:
            logger.warning("Redis recall scan failed: %s", e)

        return memories

    async def _recall_qdrant(
        self,
        agent_id: str,
        query: str,
        memory_type: Optional[str],
        limit: int,
        include_shared: bool,
        tenant_id: Optional[str],
    ) -> List[Dict]:
        """Semantic search for memories in Qdrant."""
        vector = self.engines.get("vector")
        if not vector or not vector.client:
            return []

        await self._ensure_vector_collection()

        try:
            from qdrant_client.models import (
                Filter, FieldCondition, MatchValue, MatchAny,
            )
        except ImportError:
            return []

        query_vector = self.embedding.embed(query)

        # Build filter: owned by agent OR shared with agent
        must_conditions = []

        if tenant_id:
            must_conditions.append(
                FieldCondition(key="tenant_id", match=MatchValue(value=tenant_id))
            )
        if memory_type:
            must_conditions.append(
                FieldCondition(key="memory_type", match=MatchValue(value=memory_type))
            )

        # Ownership + sharing filter: agent owns it OR it is shared with them
        if include_shared:
            should_conditions = [
                FieldCondition(key="agent_id", match=MatchValue(value=agent_id)),
                FieldCondition(key="shared_with", match=MatchAny(any=[agent_id])),
            ]
            # Qdrant Filter with should = OR semantics
            query_filter = Filter(
                must=must_conditions if must_conditions else None,
                should=should_conditions,
            )
        else:
            must_conditions.append(
                FieldCondition(key="agent_id", match=MatchValue(value=agent_id))
            )
            query_filter = Filter(must=must_conditions) if must_conditions else None

        try:
            hits = await vector.client.search(
                collection_name=AGENT_MEMORY_COLLECTION,
                query_vector=query_vector,
                query_filter=query_filter,
                limit=limit,
                score_threshold=0.0,
            )
        except Exception as e:
            logger.warning("Qdrant recall search failed: %s", e)
            return []

        results = []
        for hit in hits:
            payload = hit.payload or {}
            results.append({
                "memory_id": str(hit.id),
                "content": payload.get("content", ""),
                "similarity": round(hit.score, 4),
                "memory_type": payload.get("memory_type", "episodic"),
                "agent_id": payload.get("agent_id", ""),
                "importance": payload.get("importance", 0.5),
                "created_at_epoch": payload.get("created_at", time.time()),
                "metadata": payload.get("metadata", {}),
                "shared_with": payload.get("shared_with", []),
                "source": "vector_search",
            })
        return results

    async def _touch_access(self, memory_ids: List[str]):
        """Increment access count and update last_accessed_at in PostgreSQL."""
        relational = self.engines.get("relational")
        if not relational or not relational.pool:
            return

        try:
            async with relational.pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE agent_memories
                    SET access_count = access_count + 1,
                        last_accessed_at = NOW()
                    WHERE id = ANY($1::uuid[])
                    """,
                    memory_ids,
                )
        except Exception as e:
            logger.warning("Failed to update memory access counts: %s", e)

    # ─── forget ───────────────────────────────────────────────────────────

    async def forget(
        self,
        agent_id: str,
        memory_id: Optional[str] = None,
        before: Optional[float] = None,
        memory_type: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ) -> Dict:
        """GDPR-compliant memory deletion from all storage engines.

        At least one of memory_id, before, or memory_type must be specified
        to prevent accidental deletion of all memories.

        Args:
            agent_id: The agent whose memories to delete.
            memory_id: Delete a specific memory by ID.
            before: Delete all memories created before this Unix timestamp.
            memory_type: Delete all memories of this type.
            tenant_id: Tenant identifier for isolation.

        Returns:
            Dict with deleted_count.
        """
        if memory_type and memory_type not in VALID_MEMORY_TYPES:
            raise ValueError(
                f"Invalid memory_type '{memory_type}'. "
                f"Must be one of: {', '.join(sorted(VALID_MEMORY_TYPES))}"
            )

        if memory_id is None and before is None and memory_type is None:
            raise ValueError(
                "At least one of memory_id, before, or memory_type must be "
                "specified to prevent accidental bulk deletion."
            )

        await self._ensure_schema()

        # 1. Find matching memory IDs from PostgreSQL
        memory_ids = await self._find_memory_ids(
            agent_id=agent_id,
            memory_id=memory_id,
            before=before,
            memory_type=memory_type,
            tenant_id=tenant_id,
        )

        if not memory_ids:
            return {"deleted_count": 0}

        # 2. Delete from PostgreSQL
        pg_deleted = await self._delete_pg(memory_ids)

        # 3. Delete from Qdrant
        await self._delete_qdrant(memory_ids)

        # 4. Delete from Redis
        await self._delete_redis(agent_id, memory_ids, tenant_id)

        logger.info(
            "Forgot %d memories for agent %s", pg_deleted, agent_id
        )
        return {"deleted_count": pg_deleted}

    async def _find_memory_ids(
        self,
        agent_id: str,
        memory_id: Optional[str],
        before: Optional[float],
        memory_type: Optional[str],
        tenant_id: Optional[str],
    ) -> List[str]:
        """Query PostgreSQL for memory IDs matching the deletion criteria."""
        relational = self.engines.get("relational")
        if not relational or not relational.pool:
            return [memory_id] if memory_id else []

        conditions = ["agent_id = $1"]
        params: list = [agent_id]
        idx = 2

        if memory_id is not None:
            conditions.append(f"id = ${idx}::uuid")
            params.append(memory_id)
            idx += 1

        if before is not None:
            conditions.append(
                f"created_at < to_timestamp(${idx})"
            )
            params.append(before)
            idx += 1

        if memory_type is not None:
            conditions.append(f"memory_type = ${idx}")
            params.append(memory_type)
            idx += 1

        if tenant_id is not None:
            conditions.append(f"tenant_id = ${idx}")
            params.append(tenant_id)
            idx += 1

        where_clause = " AND ".join(conditions)
        query = f"SELECT id FROM agent_memories WHERE {where_clause}"

        async with relational.pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
            return [str(row["id"]) for row in rows]

    async def _delete_pg(self, memory_ids: List[str]) -> int:
        """Delete memory records from PostgreSQL."""
        relational = self.engines.get("relational")
        if not relational or not relational.pool:
            return 0

        async with relational.pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM agent_memories WHERE id = ANY($1::uuid[])",
                memory_ids,
            )
            # asyncpg returns e.g. "DELETE 3"
            try:
                return int(result.split()[-1])
            except (ValueError, IndexError):
                return len(memory_ids)

    async def _delete_qdrant(self, memory_ids: List[str]):
        """Delete memory vectors from Qdrant."""
        vector = self.engines.get("vector")
        if not vector:
            return

        try:
            await vector.delete_vectors(AGENT_MEMORY_COLLECTION, memory_ids)
        except Exception as e:
            logger.warning("Qdrant deletion failed: %s", e)

    async def _delete_redis(
        self, agent_id: str, memory_ids: List[str], tenant_id: Optional[str]
    ):
        """Delete working memory entries from Redis."""
        mem_engine = self.engines.get("memory")
        if not mem_engine:
            return

        for mid in memory_ids:
            try:
                key = self._redis_key(agent_id, mid, tenant_id)
                await mem_engine.delete(key)
            except Exception as e:
                logger.warning("Redis deletion failed for %s: %s", mid, e)

    # ─── share ────────────────────────────────────────────────────────────

    async def share(
        self,
        agent_id: str,
        memory_id: str,
        target_agent_ids: List[str],
        tenant_id: Optional[str] = None,
    ) -> Dict:
        """Share a memory with other agents.

        Only the owning agent can share a memory. The target agents are added
        to the ACL (shared_with) in both PostgreSQL and Qdrant.

        Args:
            agent_id: The owning agent's identifier.
            memory_id: The memory to share.
            target_agent_ids: List of agent IDs to grant access to.
            tenant_id: Tenant identifier for isolation.

        Returns:
            Dict with memory_id and updated shared_with list.

        Raises:
            PermissionError: If the requesting agent does not own the memory.
            ValueError: If the memory is not found.
        """
        if not target_agent_ids:
            raise ValueError("target_agent_ids must be a non-empty list")

        await self._ensure_schema()

        # 1. Verify ownership in PostgreSQL
        relational = self.engines.get("relational")
        if not relational or not relational.pool:
            raise RuntimeError("Relational engine not available")

        async with relational.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT agent_id, shared_with
                FROM agent_memories
                WHERE id = $1::uuid
                """,
                memory_id,
            )

        if not row:
            raise ValueError(f"Memory {memory_id} not found")

        if row["agent_id"] != agent_id:
            raise PermissionError(
                f"Agent {agent_id} does not own memory {memory_id}"
            )

        # Merge existing shared_with and new targets (deduplicate)
        existing_shared = list(row["shared_with"] or [])
        updated_shared = list(set(existing_shared + target_agent_ids))

        # 2. Update ACL in PostgreSQL
        async with relational.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE agent_memories
                SET shared_with = $1
                WHERE id = $2::uuid
                """,
                updated_shared,
                memory_id,
            )

        # 3. Update Qdrant metadata (add shared_with field)
        await self._update_qdrant_shared(memory_id, updated_shared)

        logger.info(
            "Agent %s shared memory %s with %s",
            agent_id, memory_id, target_agent_ids,
        )
        return {
            "memory_id": memory_id,
            "shared_with": updated_shared,
        }

    async def _update_qdrant_shared(
        self, memory_id: str, shared_with: List[str]
    ):
        """Update the shared_with payload field in Qdrant."""
        vector = self.engines.get("vector")
        if not vector or not vector.client:
            return

        try:
            await vector.client.set_payload(
                collection_name=AGENT_MEMORY_COLLECTION,
                payload={"shared_with": shared_with},
                points=[memory_id],
            )
        except Exception as e:
            logger.warning("Qdrant shared_with update failed: %s", e)

    # ─── helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _redis_key(
        agent_id: str, memory_id: str, tenant_id: Optional[str] = None
    ) -> str:
        """Build a consistent Redis key for working memory entries."""
        prefix = f"tenant:{tenant_id}:" if tenant_id else ""
        return f"{prefix}agent_memory:{agent_id}:{memory_id}"

    def get_info(self) -> Dict:
        """Return diagnostic information about the agent memory subsystem."""
        return {
            "status": "active",
            "schema_initialized": self._schema_initialized,
            "vector_collection": AGENT_MEMORY_COLLECTION,
            "time_decay_lambda": TIME_DECAY_LAMBDA,
            "working_memory_ttl": WORKING_MEMORY_TTL,
            "embedding": self.embedding.get_info() if self.embedding else None,
            "engines_available": {
                "relational": "relational" in self.engines,
                "vector": "vector" in self.engines,
                "memory": "memory" in self.engines,
            },
        }
