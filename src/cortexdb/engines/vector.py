"""VectorCore - Brain Region: Hippocampus (Pattern Completion)
Semantic similarity search. Recall full context from fragments.
REPLACES: Pinecone (self-hosted Qdrant = free, no API limits)"""

import hashlib
import logging
from typing import Any, Dict, List, Optional
from cortexdb.engines import BaseEngine

logger = logging.getLogger("cortexdb.engines.vector")

try:
    from qdrant_client import AsyncQdrantClient
    from qdrant_client.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue
except ImportError:
    AsyncQdrantClient = None

# Lightweight embedding: hash-based vector for deterministic similarity.
# Swap for sentence-transformers in production for true semantic search.
VECTOR_DIM = 384

_transformer_model = None


def _load_transformer():
    """Lazy-load sentence-transformers model if available."""
    global _transformer_model
    if _transformer_model is not None:
        return _transformer_model
    try:
        from sentence_transformers import SentenceTransformer
        _transformer_model = SentenceTransformer("all-MiniLM-L6-v2")
        logger.info("Loaded sentence-transformers model: all-MiniLM-L6-v2")
        return _transformer_model
    except ImportError:
        _transformer_model = False  # Mark as unavailable
        return False


def _hash_embed(text: str) -> List[float]:
    """Deterministic hash-based embedding (fallback when no ML model).

    Produces a consistent 384-dim vector from text via iterative SHA-256.
    Not semantically meaningful, but enables exact-match and near-duplicate
    detection in the vector cache.
    """
    vector = []
    for i in range(0, VECTOR_DIM, 8):
        chunk_hash = hashlib.sha256(f"{text}:{i}".encode()).digest()
        for j in range(min(8, VECTOR_DIM - i)):
            # Map byte to [-1, 1] range
            vector.append((chunk_hash[j] - 128) / 128.0)
    return vector[:VECTOR_DIM]


def embed_text(text: str) -> List[float]:
    """Embed text into a vector. Uses ML model if available, else hash fallback."""
    model = _load_transformer()
    if model and model is not False:
        return model.encode(text).tolist()
    return _hash_embed(text)


class VectorEngine(BaseEngine):
    def __init__(self, config: Dict):
        self.url = config.get("url", "http://localhost:6333")
        self.client = None
        self._collections_created: set = set()
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
        model = _load_transformer()
        return {
            "engine": "Qdrant",
            "brain_region": "Hippocampus",
            "collections": len(collections.collections),
            "embedding_mode": "sentence-transformers" if model and model is not False else "hash-fallback",
            "vector_dim": VECTOR_DIM,
            "searches": self._search_count,
            "writes": self._write_count,
        }

    async def _ensure_collection(self, collection: str):
        """Create collection if it doesn't exist."""
        if collection in self._collections_created:
            return
        try:
            await self.client.create_collection(
                collection,
                vectors_config=VectorParams(size=VECTOR_DIM, distance=Distance.COSINE)
            )
        except Exception:
            pass  # May already exist from another process
        self._collections_created.add(collection)

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
        for p in points:
            if "vector" in p:
                vec = p["vector"]
            elif "text" in p:
                vec = embed_text(p["text"])
            else:
                continue
            qdrant_points.append(PointStruct(
                id=p.get("id", hashlib.sha256(str(p).encode()).hexdigest()[:32]),
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
