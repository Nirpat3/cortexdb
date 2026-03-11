"""
Hybrid Search: Dense Vectors (Qdrant) + Sparse BM25 (PostgreSQL Full-Text) + Re-Ranking

Combines semantic similarity from vector search with keyword matching from BM25,
fused via Reciprocal Rank Fusion (RRF). Optionally applies cross-encoder re-ranking
on the fused top-k for maximum relevance.

Used by the /v1/rag/search endpoint for RAG retrieval.
"""

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger("cortexdb.core.hybrid_search")


@dataclass
class SearchResult:
    """Unified search result from hybrid search."""
    chunk_id: str
    content: str
    score: float              # Final combined score
    dense_score: float        # Vector similarity score
    sparse_score: float       # BM25/FTS score
    rerank_score: Optional[float] = None  # Cross-encoder score (if re-ranked)
    metadata: Dict = None

    def __post_init__(self):
        self.metadata = self.metadata or {}


class HybridSearch:
    """Hybrid search combining dense vectors (Qdrant) + sparse BM25 (PostgreSQL full-text).

    Fusion method: Reciprocal Rank Fusion (RRF) — robust, parameter-free:
        RRF(d) = sum 1/(k + rank_i(d))  where k=60 (standard)

    Optionally applies cross-encoder re-ranking on the fused top-k.
    """

    RRF_K = 60  # Standard RRF constant

    def __init__(self, engines: Dict[str, Any], embedding=None):
        self.engines = engines
        self.embedding = embedding
        self._reranker = None
        self._reranker_checked = False  # True after first attempt
        self._reranker_available = False
        self._search_count = 0

    def _ensure_reranker(self):
        """Lazy-load cross-encoder on first use (not at init, to avoid blocking startup).

        Sets _reranker_checked AFTER init completes to prevent concurrent callers
        from seeing checked=True but reranker=None.
        """
        if self._reranker_checked:
            return
        try:
            from sentence_transformers import CrossEncoder
            self._reranker = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
            self._reranker_available = True
            logger.info("Cross-encoder re-ranker loaded: ms-marco-MiniLM-L-6-v2")
        except ImportError:
            self._reranker_available = False
            logger.info("Cross-encoder not available — hybrid search will skip re-ranking. "
                        "Install: pip install sentence-transformers")
        except Exception as e:
            self._reranker_available = False
            logger.warning(f"Failed to load re-ranker: {e}")
        finally:
            self._reranker_checked = True  # set AFTER init to avoid race

    async def search(self, query: str, collection: str = "documents",
                     limit: int = 10, tenant_id: str = None,
                     dense_weight: float = 0.6, sparse_weight: float = 0.4,
                     rerank: bool = True, rerank_top_k: int = 20,
                     dense_threshold: float = 0.5) -> List[SearchResult]:
        """Hybrid search: dense + sparse with RRF fusion and optional re-ranking.

        Args:
            query: Search query text
            collection: Qdrant collection name
            limit: Final number of results to return
            tenant_id: Tenant ID for isolation
            dense_weight: Weight for dense vector results in RRF
            sparse_weight: Weight for sparse BM25 results in RRF
            rerank: Whether to apply cross-encoder re-ranking
            rerank_top_k: Number of candidates to re-rank (before final limit)
            dense_threshold: Minimum cosine similarity for dense results

        Returns: List of SearchResult sorted by final score
        """
        self._search_count += 1

        # Run dense and sparse searches in parallel
        dense_task = asyncio.create_task(
            self._dense_search(query, collection, rerank_top_k, tenant_id, dense_threshold))
        sparse_task = asyncio.create_task(
            self._sparse_search(query, collection, rerank_top_k, tenant_id))

        dense_results, sparse_results = await asyncio.gather(dense_task, sparse_task)

        # Fuse with Reciprocal Rank Fusion
        fused = self._rrf_fuse(dense_results, sparse_results, dense_weight, sparse_weight)

        # Optional cross-encoder re-ranking (lazy-loaded on first use)
        if rerank and fused:
            self._ensure_reranker()
        if rerank and self._reranker_available and fused:
            fused = self._rerank(query, fused[:rerank_top_k])

        return fused[:limit]

    async def _dense_search(self, query: str, collection: str,
                            limit: int, tenant_id: str = None,
                            threshold: float = 0.5) -> List[Dict]:
        """Vector similarity search via Qdrant."""
        if "vector" not in self.engines:
            return []

        target = f"tenant_{tenant_id}_{collection}" if tenant_id else collection
        try:
            results = await self.engines["vector"].search_similar(
                collection=target, query_text=query,
                threshold=threshold, limit=limit, tenant_id=tenant_id)
            return results
        except Exception as e:
            logger.warning(f"Dense search failed: {e}")
            return []

    async def _sparse_search(self, query: str, collection: str,
                             limit: int, tenant_id: str = None) -> List[Dict]:
        """BM25/full-text search via PostgreSQL ts_rank.

        Searches the rag_chunks table using tsvector/tsquery.
        """
        if "relational" not in self.engines:
            return []

        try:
            pool = self.engines["relational"].pool

            # Use plainto_tsquery for safe query parsing — handles special
            # characters, operators, and multi-word phrases without syntax errors.
            # Build query with optional tenant filter
            sql = """
                SELECT chunk_id, content, doc_id, chunk_index, metadata,
                       ts_rank_cd(to_tsvector('english', content),
                                  plainto_tsquery('english', $1)) AS rank
                FROM rag_chunks
                WHERE to_tsvector('english', content) @@ plainto_tsquery('english', $1)
            """
            params = [query[:500]]  # Cap raw query length for safety

            if tenant_id:
                sql += " AND tenant_id = $2"
                params.append(tenant_id)

            # Parameterized LIMIT to avoid SQL injection patterns
            param_idx = len(params) + 1
            sql += f" ORDER BY rank DESC LIMIT ${param_idx}"
            params.append(int(min(limit, 100)))

            async with pool.acquire() as conn:
                rows = await conn.fetch(sql, *params)

            results = []
            for row in rows:
                results.append({
                    "id": row["chunk_id"],
                    "score": float(row["rank"]),
                    "payload": {
                        "content": row["content"],
                        "doc_id": row["doc_id"],
                        "chunk_index": row["chunk_index"],
                        **(row["metadata"] if isinstance(row["metadata"], dict) else {}),
                    }
                })
            return results

        except Exception as e:
            logger.warning(f"Sparse search failed: {e}")
            return []

    def _rrf_fuse(self, dense: List[Dict], sparse: List[Dict],
                  dense_weight: float, sparse_weight: float) -> List[SearchResult]:
        """Reciprocal Rank Fusion of dense and sparse results.

        RRF(d) = w_dense/(k + rank_dense(d)) + w_sparse/(k + rank_sparse(d))
        """
        scores = {}  # chunk_id -> {rrf_score, dense_score, sparse_score, content, metadata}

        # Score dense results
        for rank, r in enumerate(dense):
            cid = r.get("id", "")
            content = r.get("payload", {}).get("content", "")
            dense_score = r.get("score", 0)

            if cid not in scores:
                scores[cid] = {"rrf": 0, "dense": 0, "sparse": 0,
                               "content": content, "metadata": r.get("payload", {})}
            scores[cid]["rrf"] += dense_weight / (self.RRF_K + rank + 1)
            scores[cid]["dense"] = dense_score

        # Score sparse results
        for rank, r in enumerate(sparse):
            cid = r.get("id", "")
            content = r.get("payload", {}).get("content", "")
            sparse_score = r.get("score", 0)

            if cid not in scores:
                scores[cid] = {"rrf": 0, "dense": 0, "sparse": 0,
                               "content": content, "metadata": r.get("payload", {})}
            scores[cid]["rrf"] += sparse_weight / (self.RRF_K + rank + 1)
            scores[cid]["sparse"] = sparse_score

        # Convert to SearchResult and sort
        results = []
        for cid, s in scores.items():
            results.append(SearchResult(
                chunk_id=cid,
                content=s["content"],
                score=s["rrf"],
                dense_score=s["dense"],
                sparse_score=s["sparse"],
                metadata=s["metadata"],
            ))

        results.sort(key=lambda r: r.score, reverse=True)
        return results

    def _rerank(self, query: str, candidates: List[SearchResult]) -> List[SearchResult]:
        """Re-rank candidates using cross-encoder model."""
        if not candidates or not self._reranker:
            return candidates

        pairs = [(query, c.content) for c in candidates]
        try:
            rerank_scores = self._reranker.predict(pairs)
            for candidate, score in zip(candidates, rerank_scores):
                candidate.rerank_score = float(score)

            candidates.sort(key=lambda r: r.rerank_score, reverse=True)
        except Exception as e:
            logger.warning(f"Re-ranking failed: {e}")

        return candidates

    def get_stats(self) -> Dict:
        return {
            "search_count": self._search_count,
            "reranker_available": self._reranker_available,
            "reranker_model": "ms-marco-MiniLM-L-6-v2" if self._reranker_available else None,
        }
