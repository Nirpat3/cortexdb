"""VectorCore — Semantic Search Engine
Similarity search via Qdrant. Powers the R2 semantic cache
and agent/document embedding search.

P0 FIX: Unified embedding codepath. Previously had an incompatible hash-based
fallback that produced different vectors than EmbeddingPipeline for the same
input (byte-mapping vs struct.unpack). Now delegates all embedding to
EmbeddingPipeline as the single source of truth.
"""

import asyncio
import hashlib
import json
import logging
from typing import Any, Dict, List, Optional
from cortexdb.engines import BaseEngine
from cortexdb.core.embedding import EmbeddingPipeline

logger = logging.getLogger("cortexdb.engines.vector")

try:
    from qdrant_client import AsyncQdrantClient
    from qdrant_client.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue
except ImportError:
    AsyncQdrantClient = None

# Single embedding pipeline instance — shared across all vector operations
_embedding_pipeline: Optional[EmbeddingPipeline] = None
_embedding_lock = __import__("threading").Lock()

VECTOR_DIM = EmbeddingPipeline.EMBEDDING_DIM  # 384


def _get_pipeline() -> EmbeddingPipeline:
    """Get or create the shared EmbeddingPipeline instance (thread-safe)."""
    global _embedding_pipeline
    if _embedding_pipeline is not None:
        return _embedding_pipeline
    with _embedding_lock:
        if _embedding_pipeline is None:
            _embedding_pipeline = EmbeddingPipeline()
    return _embedding_pipeline


def embed_text(text: str) -> List[float]:
    """Embed text into a vector via the unified EmbeddingPipeline."""
    return _get_pipeline().embed(text)


class VectorEngine(BaseEngine):
    def __init__(self, config: Dict):
        self.url = config.get("url", "http://localhost:6333")
        self.client = None
        self._collections_created: set = set()
        self._collection_lock = asyncio.Lock()
        self._search_count = 0
        self._write_count = 0

    async def connect(self):
        if AsyncQdrantClient is None:
            raise ImportError("qdrant-client required: pip install qdrant-client")
        self.client = AsyncQdrantClient(url=self.url)
        collections = await self.client.get_collections()
        names = [c.name for c in collections.collections]
        self._collections_created = set(names)
        if "response_cache" not in names:
            await self.client.create_collection(
                "response_cache",
                vectors_config=VectorParams(size=VECTOR_DIM, distance=Distance.COSINE)
            )
            self._collections_created.add("response_cache")

    async def close(self):
        if self.client:
            await self.client.close()

    async def health(self) -> Dict:
        collections = await self.client.get_collections()
        pipeline = _get_pipeline()
        return {
            "engine": "Qdrant",
            "brain_region": "Hippocampus",
            "collections": len(collections.collections),
            "embedding_mode": "sentence-transformers" if pipeline.is_ml_available else "hash-fallback",
            "vector_dim": VECTOR_DIM,
            "searches": self._search_count,
            "writes": self._write_count,
        }

    async def _ensure_collection(self, collection: str):
        """Create collection if it doesn't exist. Lock-protected for concurrency."""
        if collection in self._collections_created:
            return
        async with self._collection_lock:
            # Double-check after acquiring lock
            if collection in self._collections_created:
                return
            try:
                existing = await self.client.get_collections()
                existing_names = {c.name for c in existing.collections}
                self._collections_created.update(existing_names)
                if collection in existing_names:
                    return
                await self.client.create_collection(
                    collection,
                    vectors_config=VectorParams(size=VECTOR_DIM, distance=Distance.COSINE)
                )
                self._collections_created.add(collection)
            except Exception as e:
                # Only cache if error indicates "already exists"
                err_str = str(e).lower()
                if "already exists" in err_str or "conflict" in err_str:
                    self._collections_created.add(collection)
                else:
                    logger.warning(f"Failed to create collection '{collection}': {e}")

    async def search_similar(self, collection: str, query_text: str,
                            threshold: float = 0.95, limit: int = 5,
                            tenant_id: Optional[str] = None) -> List[Dict]:
        """Semantic search via embedding + cosine similarity.

        Uses sentence-transformers if installed, else hash-based fallback.
        Returns matches above the similarity threshold.
        """
        self._search_count += 1

        await self._ensure_collection(collection)

        query_vector = embed_text(query_text)

        # Build tenant filter if provided
        query_filter = None
        if tenant_id:
            query_filter = Filter(
                must=[FieldCondition(key="tenant_id", match=MatchValue(value=tenant_id))]
            )

        try:
            results = await self.client.search(
                collection_name=collection,
                query_vector=query_vector,
                query_filter=query_filter,
                limit=limit,
                score_threshold=threshold,
            )
            return [
                {
                    "id": str(hit.id),
                    "score": round(hit.score, 4),
                    "payload": hit.payload or {},
                }
                for hit in results
            ]
        except Exception as e:
            logger.warning(f"Vector search failed in {collection}: {e}")
            return []

    async def upsert_vectors(self, collection: str, points: List[Dict]) -> int:
        """Insert or update vectors. Each point: {id, text_or_vector, payload}."""
        await self._ensure_collection(collection)

        qdrant_points = []
        skipped = 0
        for p in points:
            if "vector" in p:
                vec = p["vector"]
            elif "text" in p:
                vec = embed_text(p["text"])
            else:
                skipped += 1
                logger.warning(f"upsert_vectors: point missing 'vector' and 'text', skipped. Keys: {list(p.keys())}")
                continue
            # Use canonical JSON for deterministic ID fallback
            point_id = p.get("id") or hashlib.sha256(
                json.dumps(p, sort_keys=True, default=str).encode()).hexdigest()[:32]
            qdrant_points.append(PointStruct(
                id=point_id,
                vector=vec,
                payload=p.get("payload", {}),
            ))

        if qdrant_points:
            await self.client.upsert(collection_name=collection, points=qdrant_points)
            self._write_count += len(qdrant_points)

        return len(qdrant_points)

    async def delete_vectors(self, collection: str, ids: List[str]) -> int:
        """Delete vectors by ID."""
        if not ids:
            return 0
        await self.client.delete(collection_name=collection, points_selector=ids)
        return len(ids)

    async def get_collection_info(self, collection: str) -> Dict:
        """Get collection statistics."""
        try:
            info = await self.client.get_collection(collection)
            return {
                "name": collection,
                "vectors_count": info.vectors_count,
                "points_count": info.points_count,
                "status": info.status.value if info.status else "unknown",
            }
        except Exception as e:
            return {"name": collection, "error": str(e)}

    async def write(self, data_type: str, payload: Dict, actor: str = "system") -> Any:
        """Write handler for WriteFanOut integration."""
        # Work on a copy to avoid mutating the caller's dict
        payload = dict(payload)
        collection = payload.pop("_collection", "default")
        text = payload.pop("_text", None)
        vector = payload.pop("_vector", None)
        point_id = payload.pop("_id", hashlib.sha256(str(payload).encode()).hexdigest()[:32])

        if text:
            vec = embed_text(text)
        elif vector:
            vec = vector
        else:
            return None

        await self._ensure_collection(collection)
        point = PointStruct(id=point_id, vector=vec, payload=payload)
        await self.client.upsert(collection_name=collection, points=[point])
        self._write_count += 1
        return {"id": point_id, "collection": collection}
