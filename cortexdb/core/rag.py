"""RAG Pipeline — Ingest, Chunk, Embed, Store, Retrieve

End-to-end Retrieval-Augmented Generation pipeline that orchestrates:
  ingest -> chunk -> embed -> store (PG + Qdrant)
  retrieve -> rank -> format for LLM context window

Integrates with:
  - ChunkingPipeline (cortexdb.core.chunking) for document splitting
  - EmbeddingPipeline (cortexdb.core.embedding) for vectorization
  - VectorEngine (cortexdb.engines.vector) for similarity search
  - RelationalEngine for metadata and chunk storage
"""

import hashlib
import json
import logging
from typing import Any, Dict, List, Optional

from cortexdb.core.chunking import ChunkingPipeline
from cortexdb.core.embedding import EmbeddingPipeline

logger = logging.getLogger("cortexdb.core.rag")


class RAGPipeline:
    """End-to-end RAG pipeline: ingest -> chunk -> embed -> store -> search -> format."""

    def __init__(self, engines: Dict, embedding: EmbeddingPipeline,
                 chunking: ChunkingPipeline = None):
        self.engines = engines
        self.embedding = embedding
        self.chunking = chunking or ChunkingPipeline()
        self._ingest_count = 0

    async def ingest(self, text: str, doc_id: str, collection: str = "documents",
                     metadata: Dict = None, tenant_id: str = None) -> Dict:
        """Ingest a document: chunk -> embed -> store in PG + Qdrant.

        Returns: {doc_id, chunks_created, collection}
        """
        # 1. Chunk the document
        chunks = self.chunking.chunk(text, doc_id, metadata)

        # 2. Store document metadata in PG
        if "relational" in self.engines:
            pool = self.engines["relational"].pool
            async with pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO rag_documents (doc_id, collection, chunk_count,
                        metadata, tenant_id, content_hash)
                    VALUES ($1, $2, $3, $4::jsonb, $5, $6)
                    ON CONFLICT (doc_id) DO UPDATE SET
                        chunk_count = $3, metadata = $4::jsonb,
                        content_hash = $6, updated_at = NOW()
                """, doc_id, collection, len(chunks),
                    json.dumps(metadata or {}), tenant_id,
                    hashlib.sha256(text.encode()).hexdigest())

        # 3. Embed all chunks in batch
        texts = [c.content for c in chunks]
        vectors = self.embedding.embed_batch(texts)

        # 4. Upsert to Qdrant
        target_collection = f"tenant_{tenant_id}_{collection}" if tenant_id else collection
        if "vector" in self.engines:
            points = []
            for chunk, vector in zip(chunks, vectors):
                points.append({
                    "id": chunk.chunk_id,
                    "vector": vector,
                    "payload": {
                        "doc_id": chunk.doc_id,
                        "content": chunk.content,
                        "chunk_index": chunk.chunk_index,
                        "start_char": chunk.start_char,
                        "end_char": chunk.end_char,
                        "token_count": chunk.token_count,
                        "tenant_id": tenant_id,
                        **(metadata or {}),
                    }
                })
            await self.engines["vector"].upsert_vectors(target_collection, points)

        # 5. Store chunks in PG for retrieval by ID
        if "relational" in self.engines:
            pool = self.engines["relational"].pool
            async with pool.acquire() as conn:
                for chunk in chunks:
                    await conn.execute("""
                        INSERT INTO rag_chunks (chunk_id, doc_id, content,
                            chunk_index, start_char, end_char, token_count,
                            metadata, tenant_id)
                        VALUES ($1,$2,$3,$4,$5,$6,$7,$8::jsonb,$9)
                        ON CONFLICT (chunk_id) DO UPDATE SET
                            content=$3, token_count=$7, metadata=$8::jsonb
                    """, chunk.chunk_id, doc_id, chunk.content,
                        chunk.chunk_index, chunk.start_char, chunk.end_char,
                        chunk.token_count, json.dumps(chunk.metadata or {}),
                        tenant_id)

        self._ingest_count += 1
        return {"doc_id": doc_id, "chunks_created": len(chunks),
                "collection": target_collection}

    async def retrieve(self, query: str, collection: str = "documents",
                       limit: int = 5, threshold: float = 0.75,
                       tenant_id: str = None) -> List[Dict]:
        """Semantic search over chunked documents.

        Returns ranked chunks with provenance (doc_id, position, score).
        """
        target = f"tenant_{tenant_id}_{collection}" if tenant_id else collection
        if "vector" not in self.engines:
            return []

        results = await self.engines["vector"].search_similar(
            collection=target, query_text=query,
            threshold=threshold, limit=limit, tenant_id=tenant_id)

        return results

    async def retrieve_with_context(self, query: str, collection: str = "documents",
                                    limit: int = 5, threshold: float = 0.75,
                                    max_tokens: int = 4000,
                                    tenant_id: str = None) -> Dict:
        """Retrieve and format chunks for LLM context window.

        Returns: {query, context, chunks, total_tokens, truncated}
        """
        results = await self.retrieve(query, collection, limit * 2, threshold, tenant_id)

        # Pack into context window respecting max_tokens
        context_parts = []
        total_tokens = 0
        used_chunks = []
        truncated = False

        for r in results:
            content = r.get("payload", {}).get("content", "")
            tokens = len(content) // 4  # approximate
            if total_tokens + tokens > max_tokens:
                truncated = True
                break
            context_parts.append(content)
            total_tokens += tokens
            used_chunks.append(r)

        context = "\n\n---\n\n".join(context_parts)

        return {
            "query": query,
            "context": context,
            "chunks": used_chunks,
            "total_tokens": total_tokens,
            "truncated": truncated,
        }

    async def delete_document(self, doc_id: str, collection: str = "documents",
                              tenant_id: str = None) -> Dict:
        """Delete a document and all its chunks from PG + Qdrant."""
        deleted_chunks = 0

        # Get chunk IDs from PG
        if "relational" in self.engines:
            pool = self.engines["relational"].pool
            async with pool.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT chunk_id FROM rag_chunks WHERE doc_id = $1", doc_id)
                chunk_ids = [r["chunk_id"] for r in rows]

                # Delete from PG
                await conn.execute("DELETE FROM rag_chunks WHERE doc_id = $1", doc_id)
                await conn.execute("DELETE FROM rag_documents WHERE doc_id = $1", doc_id)
                deleted_chunks = len(chunk_ids)

                # Delete from Qdrant
                if chunk_ids and "vector" in self.engines:
                    target = f"tenant_{tenant_id}_{collection}" if tenant_id else collection
                    try:
                        await self.engines["vector"].delete_vectors(target, chunk_ids)
                    except Exception as e:
                        logger.warning(f"Failed to delete vectors for doc {doc_id}: {e}")

        return {"doc_id": doc_id, "chunks_deleted": deleted_chunks}

    def get_stats(self) -> Dict:
        return {"documents_ingested": self._ingest_count}
