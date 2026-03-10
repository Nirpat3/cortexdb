"""Embedding Pipeline (DOC-018 Gap G8)

Text -> Vector embedding for R2 semantic cache and experience vectorization.
Uses sentence-transformers (all-MiniLM-L6-v2, 80MB, runs on CPU).
Falls back to hash-based pseudo-embeddings if model not available.
"""

import hashlib
import logging
import struct
from typing import List, Optional

logger = logging.getLogger("cortexdb.core.embedding")

_model = None
_model_available = False


def _load_model():
    """Lazy-load sentence-transformers model."""
    global _model, _model_available
    if _model is not None:
        return

    try:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer("all-MiniLM-L6-v2")
        _model_available = True
        logger.info("Embedding model loaded: all-MiniLM-L6-v2 (384 dims)")
    except ImportError:
        _model_available = False
        logger.info("sentence-transformers not installed — using hash-based pseudo-embeddings. "
                     "Install: pip install sentence-transformers")


class EmbeddingPipeline:
    """Converts text to vector embeddings for semantic cache and search.

    Primary: sentence-transformers all-MiniLM-L6-v2 (384 dimensions)
    Fallback: SHA-256 hash-based pseudo-embedding (deterministic, no ML)
    """

    EMBEDDING_DIM = 384

    def __init__(self):
        _load_model()

    def embed(self, text: str) -> List[float]:
        """Embed a single text string."""
        if _model_available and _model:
            embedding = _model.encode(text, normalize_embeddings=True)
            return embedding.tolist()
        return self._hash_embedding(text)

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Embed multiple texts (batched for efficiency)."""
        if _model_available and _model:
            embeddings = _model.encode(texts, normalize_embeddings=True, batch_size=32)
            return embeddings.tolist()
        return [self._hash_embedding(t) for t in texts]

    def similarity(self, vec_a: List[float], vec_b: List[float]) -> float:
        """Cosine similarity between two vectors."""
        dot = sum(a * b for a, b in zip(vec_a, vec_b))
        norm_a = sum(a * a for a in vec_a) ** 0.5
        norm_b = sum(b * b for b in vec_b) ** 0.5
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    @classmethod
    def _hash_embedding(cls, text: str) -> List[float]:
        """Deterministic pseudo-embedding from SHA-256 hash.

        Not semantically meaningful, but provides consistent vectors
        for exact-match caching when no ML model is available.
        """
        # Generate enough hash bytes for 384 floats
        vectors = []
        for i in range(0, cls.EMBEDDING_DIM, 8):
            h = hashlib.sha256(f"{text}:{i}".encode()).digest()
            vals = struct.unpack("8f", h)
            vectors.extend(vals[:min(8, cls.EMBEDDING_DIM - i)])

        # Normalize
        norm = sum(v * v for v in vectors) ** 0.5
        if norm > 0:
            vectors = [v / norm for v in vectors]
        return vectors[:cls.EMBEDDING_DIM]

    @property
    def is_ml_available(self) -> bool:
        return _model_available

    def get_info(self) -> dict:
        return {
            "model": "all-MiniLM-L6-v2" if _model_available else "hash-fallback",
            "dimensions": self.EMBEDDING_DIM,
            "ml_available": _model_available,
        }
