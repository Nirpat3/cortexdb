"""RAG Pipeline — Ingest, Chunk, Embed, Store, Retrieve (with Intelligence Layers)

End-to-end Retrieval-Augmented Generation pipeline that orchestrates:
  ingest -> chunk -> embed -> store (PG + Qdrant)
  query understanding -> retrieve -> feedback loop -> ground -> format

Intelligence layers:
  - QueryUnderstanding: intent classification, entity extraction, multi-query reformulation
  - RetrievalFeedback: confidence scoring, adaptive re-search when results are poor
  - AnswerGrounding: citation mapping, hallucination prevention
  - HierarchicalChunker: parent-child chunking for precision + context

Integrates with:
  - ChunkingPipeline (cortexdb.core.chunking) for document splitting
  - HierarchicalChunker (cortexdb.core.parent_child_chunking) for parent-child chunking
  - EmbeddingPipeline (cortexdb.core.embedding) for vectorization
  - VectorEngine (cortexdb.engines.vector) for similarity search
  - RelationalEngine for metadata and chunk storage
"""

import asyncio
import hashlib
import json
import logging
from typing import Any, Dict, List, Optional

from cortexdb.core.chunking import ChunkingPipeline
from cortexdb.core.embedding import EmbeddingPipeline
from cortexdb.core.query_understanding import QueryUnderstanding
from cortexdb.core.retrieval_feedback import RetrievalFeedback, AnswerGrounding
from cortexdb.core.parent_child_chunking import HierarchicalChunker

logger = logging.getLogger("cortexdb.core.rag")


class RAGPipeline:
    """End-to-end RAG pipeline with intelligence layers.

    Ingest: chunk -> embed -> store (PG + Qdrant)
    Retrieve: understand query -> multi-query search -> score confidence ->
              reformulate if needed -> ground answers -> cite sources -> format
    """

    def __init__(self, engines: Dict, embedding: EmbeddingPipeline,
                 chunking: ChunkingPipeline = None):
        self.engines = engines
        self.embedding = embedding
        self.chunking = chunking or ChunkingPipeline()
        self._ingest_count = 0

        # Intelligence layers
        self.query_understanding = QueryUnderstanding()
        self.retrieval_feedback = RetrievalFeedback()
        self.answer_grounding = AnswerGrounding()
        self.hierarchical_chunker = HierarchicalChunker()

    async def ingest(self, text: str, doc_id: str, collection: str = "documents",
                     metadata: Dict = None, tenant_id: str = None) -> Dict:
        """Ingest a document: chunk -> embed -> store in PG + Qdrant.

        Returns: {doc_id, chunks_created, collection}
        """
        # 1. Chunk the document
        chunks = self.chunking.chunk(text, doc_id, metadata)

        # 2. Embed all chunks in batch (run in thread to avoid blocking event loop)
        texts = [c.content for c in chunks]
        vectors = await asyncio.to_thread(self.embedding.embed_batch, texts)

        # 3. Upsert to Qdrant first (idempotent), before deleting old data
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

        # 4. Transactional PG: delete old + insert new in one transaction
        #    If this fails, Qdrant has the new data (idempotent upsert) but PG
        #    still has the old data — a retry will succeed cleanly.
        if "relational" in self.engines:
            pool = self.engines["relational"].pool
            new_chunk_ids = {c.chunk_id for c in chunks}
            async with pool.acquire() as conn:
                async with conn.transaction():
                    # Get old chunk IDs for Qdrant cleanup
                    if tenant_id:
                        old_rows = await conn.fetch(
                            "SELECT chunk_id FROM rag_chunks WHERE doc_id = $1 AND tenant_id = $2",
                            doc_id, tenant_id)
                    else:
                        old_rows = await conn.fetch(
                            "SELECT chunk_id FROM rag_chunks WHERE doc_id = $1", doc_id)
                    old_chunk_ids = {r["chunk_id"] for r in old_rows}

                    # Delete old PG rows
                    if tenant_id:
                        await conn.execute(
                            "DELETE FROM rag_chunks WHERE doc_id = $1 AND tenant_id = $2",
                            doc_id, tenant_id)
                    else:
                        await conn.execute("DELETE FROM rag_chunks WHERE doc_id = $1", doc_id)

                    # Insert document metadata
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

                    # Insert new chunks
                    await conn.executemany("""
                        INSERT INTO rag_chunks (chunk_id, doc_id, content,
                            chunk_index, start_char, end_char, token_count,
                            metadata, tenant_id)
                        VALUES ($1,$2,$3,$4,$5,$6,$7,$8::jsonb,$9)
                        ON CONFLICT (chunk_id) DO UPDATE SET
                            content=$3, token_count=$7, metadata=$8::jsonb
                    """, [(chunk.chunk_id, doc_id, chunk.content,
                           chunk.chunk_index, chunk.start_char, chunk.end_char,
                           chunk.token_count, json.dumps(chunk.metadata or {}),
                           tenant_id) for chunk in chunks])

            # Clean up orphan vectors from Qdrant (old IDs not in new set)
            orphan_ids = list(old_chunk_ids - new_chunk_ids)
            if orphan_ids and "vector" in self.engines:
                try:
                    await self.engines["vector"].delete_vectors(target_collection, orphan_ids)
                except Exception as e:
                    logger.warning(f"Failed to clean orphan vectors for doc {doc_id}: {e}")

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

    async def smart_retrieve(self, query: str, collection: str = "documents",
                              limit: int = 5, threshold: float = 0.75,
                              tenant_id: str = None,
                              use_feedback_loop: bool = True) -> Dict:
        """Intelligent retrieval with query understanding, feedback loop, and grounding.

        Flow:
          1. Analyze query intent (factual, procedural, comparative, etc.)
          2. Select retrieval strategy based on intent
          3. Reformulate into multiple query variants
          4. Search with each variant, merge results
          5. Score confidence — re-search if low (always scored against ORIGINAL query)
          6. Expand parent context for hierarchically-chunked docs
          7. Verify answer grounding, build citations
          8. Return enriched results

        Returns: {query, intent, strategy, results, confidence, citations, grounding, attempts}
        """
        # Guard: need vector engine
        if "vector" not in self.engines:
            return {"query": query, "intent": {}, "strategy": {}, "results": [],
                    "confidence": {"overall": 0, "verdict": "insufficient"},
                    "citations": [], "grounding": {}, "attempts": 0,
                    "reformulations_used": [], "query_variants": []}

        # 1. Understand the query
        intent = self.query_understanding.analyze(query)
        strategy = self.query_understanding.select_strategy(intent)
        query_variants = self.query_understanding.reformulate(query, intent)

        logger.info("Smart retrieve: intent=%s confidence=%.2f variants=%d",
                     intent.intent_type, intent.confidence, len(query_variants))

        # 2. Apply strategy-based search params
        search_threshold = min(threshold, strategy.get("score_threshold", threshold))
        search_limit = max(limit, strategy.get("limit", limit))

        target = f"tenant_{tenant_id}_{collection}" if tenant_id else collection

        # 3. Multi-query retrieval: search with each variant, merge + deduplicate
        all_results = []
        seen_ids = set()

        for variant in query_variants[:5]:  # cap at 5 variants
            try:
                results = await self.engines["vector"].search_similar(
                    collection=target, query_text=variant,
                    threshold=search_threshold, limit=search_limit,
                    tenant_id=tenant_id)
                for r in results:
                    rid = r.get("id", "")
                    if rid not in seen_ids:
                        seen_ids.add(rid)
                        payload = r.get("payload", {})
                        all_results.append({
                            "id": rid,
                            "content": payload.get("content", ""),
                            "score": r.get("score", 0.0),
                            "doc_id": payload.get("doc_id", ""),
                            "chunk_index": payload.get("chunk_index", 0),
                            "start_char": payload.get("start_char", 0),
                            "parent_id": payload.get("parent_id"),
                            "level": payload.get("level", "flat"),
                            "metadata": payload,
                        })
            except Exception as e:
                logger.warning("Variant search failed for %r: %s", variant[:50], e)

        # Sort by score descending
        all_results.sort(key=lambda r: r["score"], reverse=True)

        # 4. Feedback loop: score confidence, reformulate if needed
        #    IMPORTANT: Always score against the ORIGINAL query for fair comparison
        attempts = 1
        reformulations_used = []
        confidence = self.retrieval_feedback.score_results(query, all_results)

        if use_feedback_loop and self.retrieval_feedback.should_reformulate(confidence):
            logger.info("Low confidence (%.3f/%s), running feedback loop",
                         confidence.overall_score, confidence.verdict)

            original_query = query  # capture for scoring consistency

            async def _search_fn(q, **kwargs):
                t = kwargs.get("threshold", search_threshold)
                lim = kwargs.get("limit", search_limit)
                do_filter = kwargs.get("filter_low_scores", False)
                res = await self.engines["vector"].search_similar(
                    collection=target, query_text=q,
                    threshold=t, limit=lim, tenant_id=tenant_id)
                results = [{"id": r.get("id", ""), "content": r.get("payload", {}).get("content", ""),
                            "score": r.get("score", 0.0), "doc_id": r.get("payload", {}).get("doc_id", ""),
                            "chunk_index": r.get("payload", {}).get("chunk_index", 0),
                            "start_char": r.get("payload", {}).get("start_char", 0),
                            "parent_id": r.get("payload", {}).get("parent_id"),
                            "level": r.get("payload", {}).get("level", "flat"),
                            "metadata": r.get("payload", {})} for r in res]
                # Filter low-scoring results when narrow strategy requests it
                if do_filter and results:
                    median_score = sorted([r["score"] for r in results])[len(results) // 2]
                    results = [r for r in results if r["score"] >= median_score * 0.8]
                return results

            feedback_result = await self.retrieval_feedback.adaptive_search(
                query, _search_fn, threshold=search_threshold, limit=search_limit)

            # Re-score feedback results against the ORIGINAL query for fair comparison
            feedback_confidence = self.retrieval_feedback.score_results(
                original_query, feedback_result["results"])
            if feedback_confidence.overall_score > confidence.overall_score:
                all_results = feedback_result["results"]
                confidence = feedback_confidence
            attempts = feedback_result["attempts"]
            reformulations_used = feedback_result["reformulations_used"]

        # 5. Trim to requested limit
        final_results = all_results[:limit]

        # 6. Parent context expansion for hierarchically-chunked results
        #    If child chunks have parent_ids, fetch parent content from PG for richer context
        parent_expanded = False
        if any(r.get("parent_id") for r in final_results) and "relational" in self.engines:
            try:
                parent_ids = list(set(r["parent_id"] for r in final_results if r.get("parent_id")))
                pool = self.engines["relational"].pool
                async with pool.acquire() as conn:
                    rows = await conn.fetch(
                        "SELECT chunk_id, content, metadata FROM rag_chunks WHERE chunk_id = ANY($1::text[])",
                        parent_ids)
                    parent_map = {row["chunk_id"]: {"content": row["content"],
                                                     "metadata": json.loads(row["metadata"]) if row["metadata"] else {}}
                                  for row in rows}

                # Attach parent context to each result
                for r in final_results:
                    pid = r.get("parent_id")
                    if pid and pid in parent_map:
                        r["parent_content"] = parent_map[pid]["content"]
                        r["parent_token_count"] = len(parent_map[pid]["content"]) // 4
                        parent_expanded = True
            except Exception as e:
                logger.warning("Parent context expansion failed: %s", e)

        # 7. Grounding verification
        chunks_text = [r["content"] for r in final_results]
        grounding = self.answer_grounding.verify_grounding(chunks_text, query)

        # 8. Build citations
        citations = self.answer_grounding.build_citations(final_results)

        return {
            "query": query,
            "intent": {
                "type": intent.intent_type,
                "entities": intent.entities,
                "constraints": intent.constraints,
                "confidence": intent.confidence,
            },
            "strategy": strategy,
            "results": final_results,
            "confidence": {
                "overall": confidence.overall_score,
                "coverage": confidence.coverage_score,
                "coherence": confidence.coherence_score,
                "verdict": confidence.verdict,
                "suggestions": confidence.suggestions,
            },
            "citations": citations,
            "grounding": grounding,
            "attempts": attempts,
            "reformulations_used": reformulations_used,
            "query_variants": query_variants,
            "parent_expanded": parent_expanded,
        }

    async def retrieve_with_context(self, query: str, collection: str = "documents",
                                    limit: int = 5, threshold: float = 0.75,
                                    max_tokens: int = 4000,
                                    tenant_id: str = None,
                                    smart: bool = False) -> Dict:
        """Retrieve and format chunks for LLM context window.

        Args:
            smart: If True, uses intelligent retrieval with query understanding,
                   feedback loop, and grounding. If False, uses basic vector search.

        Returns: {query, context, chunks, total_tokens, truncated, ...intelligence_metadata}
        """
        intelligence_meta = {}

        if smart:
            smart_result = await self.smart_retrieve(
                query, collection, limit, threshold, tenant_id)
            results = smart_result["results"]
            intelligence_meta = {
                "intent": smart_result["intent"],
                "confidence": smart_result["confidence"],
                "citations": smart_result["citations"],
                "grounding": smart_result["grounding"],
                "attempts": smart_result["attempts"],
                "query_variants": smart_result["query_variants"],
            }
        else:
            results = await self.retrieve(query, collection, limit * 2, threshold, tenant_id)

        # Pack into context window respecting max_tokens
        context_parts = []
        total_tokens = 0
        used_chunks = []
        truncated = False

        for r in results:
            if smart:
                content = r.get("content", "")
            else:
                content = r.get("payload", {}).get("content", "")
            tokens = len(content) // 4  # approximate
            if total_tokens + tokens > max_tokens:
                truncated = True
                break
            context_parts.append(content)
            total_tokens += tokens
            used_chunks.append(r)

        context = "\n\n---\n\n".join(context_parts)

        result = {
            "query": query,
            "context": context,
            "chunks": used_chunks,
            "total_tokens": total_tokens,
            "truncated": truncated,
        }
        result.update(intelligence_meta)
        return result

    async def delete_document(self, doc_id: str, collection: str = "documents",
                              tenant_id: str = None) -> Dict:
        """Delete a document and all its chunks from PG + Qdrant."""
        deleted_chunks = 0

        # Get chunk IDs from PG (with tenant isolation)
        if "relational" in self.engines:
            pool = self.engines["relational"].pool
            async with pool.acquire() as conn:
                if tenant_id:
                    rows = await conn.fetch(
                        "SELECT chunk_id FROM rag_chunks WHERE doc_id = $1 AND tenant_id = $2",
                        doc_id, tenant_id)
                    chunk_ids = [r["chunk_id"] for r in rows]
                    await conn.execute(
                        "DELETE FROM rag_chunks WHERE doc_id = $1 AND tenant_id = $2",
                        doc_id, tenant_id)
                    await conn.execute(
                        "DELETE FROM rag_documents WHERE doc_id = $1 AND tenant_id = $2",
                        doc_id, tenant_id)
                else:
                    rows = await conn.fetch(
                        "SELECT chunk_id FROM rag_chunks WHERE doc_id = $1", doc_id)
                    chunk_ids = [r["chunk_id"] for r in rows]
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

    async def ingest_hierarchical(self, text: str, doc_id: str,
                                   collection: str = "documents",
                                   metadata: Dict = None,
                                   tenant_id: str = None) -> Dict:
        """Ingest with parent-child chunking for precision retrieval + rich context.

        Child chunks are stored in Qdrant for precise vector search.
        Parent chunks are stored in PG for context expansion after retrieval.
        """
        hierarchy = self.hierarchical_chunker.chunk(text, doc_id, metadata)
        parents = hierarchy["parents"]
        children = hierarchy["children"]

        # Embed child chunks (run in thread to avoid blocking event loop)
        child_texts = [c.content for c in children]
        child_vectors = await asyncio.to_thread(self.embedding.embed_batch, child_texts)

        # Upsert children to Qdrant first (idempotent), before deleting old data
        target = f"tenant_{tenant_id}_{collection}" if tenant_id else collection
        if "vector" in self.engines:
            points = []
            for child, vector in zip(children, child_vectors):
                points.append({
                    "id": child.chunk_id,
                    "vector": vector,
                    "payload": {
                        "doc_id": child.doc_id,
                        "parent_id": child.parent_id,
                        "content": child.content,
                        "chunk_index": child.chunk_index,
                        "start_char": child.start_char,
                        "end_char": child.end_char,
                        "token_count": child.token_count,
                        "level": "child",
                        "tenant_id": tenant_id,
                        **(metadata or {}),
                    }
                })
            await self.engines["vector"].upsert_vectors(target, points)

        # Transactional PG: delete old chunks + insert new in one transaction
        if "relational" in self.engines:
            pool = self.engines["relational"].pool
            new_chunk_ids = {c.chunk_id for c in children} | {p.chunk_id for p in parents}
            async with pool.acquire() as conn:
                async with conn.transaction():
                    # Get old chunk IDs for Qdrant cleanup
                    if tenant_id:
                        old_rows = await conn.fetch(
                            "SELECT chunk_id FROM rag_chunks WHERE doc_id = $1 AND tenant_id = $2",
                            doc_id, tenant_id)
                    else:
                        old_rows = await conn.fetch(
                            "SELECT chunk_id FROM rag_chunks WHERE doc_id = $1", doc_id)
                    old_chunk_ids = {r["chunk_id"] for r in old_rows}

                    # Delete old PG rows
                    if tenant_id:
                        await conn.execute(
                            "DELETE FROM rag_chunks WHERE doc_id = $1 AND tenant_id = $2",
                            doc_id, tenant_id)
                    else:
                        await conn.execute("DELETE FROM rag_chunks WHERE doc_id = $1", doc_id)

                    # Insert/update document metadata
                    await conn.execute("""
                        INSERT INTO rag_documents (doc_id, collection, chunk_count,
                            metadata, tenant_id, content_hash)
                        VALUES ($1, $2, $3, $4::jsonb, $5, $6)
                        ON CONFLICT (doc_id) DO UPDATE SET
                            chunk_count = $3, metadata = $4::jsonb,
                            content_hash = $6, updated_at = NOW()
                    """, doc_id, collection, len(children),
                        json.dumps({**(metadata or {}), "chunking": "hierarchical",
                                    "parent_count": len(parents)}),
                        tenant_id, hashlib.sha256(text.encode()).hexdigest())

                    # Batch insert all chunks (parents + children)
                    all_chunk_rows = []
                    for parent in parents:
                        all_chunk_rows.append((
                            parent.chunk_id, doc_id, parent.content,
                            parent.chunk_index, parent.start_char, parent.end_char,
                            parent.token_count,
                            json.dumps({**(parent.metadata or {}),
                                        "level": "parent", "children": parent.children}),
                            tenant_id))
                    for child in children:
                        all_chunk_rows.append((
                            child.chunk_id, doc_id, child.content,
                            child.chunk_index, child.start_char, child.end_char,
                            child.token_count,
                            json.dumps({**(child.metadata or {}),
                                        "level": "child", "parent_id": child.parent_id}),
                            tenant_id))
                    await conn.executemany("""
                        INSERT INTO rag_chunks (chunk_id, doc_id, content,
                            chunk_index, start_char, end_char, token_count,
                            metadata, tenant_id)
                        VALUES ($1,$2,$3,$4,$5,$6,$7,$8::jsonb,$9)
                        ON CONFLICT (chunk_id) DO UPDATE SET
                            content=$3, token_count=$7, metadata=$8::jsonb
                    """, all_chunk_rows)

            # Clean up orphan vectors from Qdrant (old IDs not in new set)
            orphan_ids = list(old_chunk_ids - new_chunk_ids)
            if orphan_ids and "vector" in self.engines:
                try:
                    await self.engines["vector"].delete_vectors(target, orphan_ids)
                except Exception as e:
                    logger.warning(f"Failed to clean orphan vectors for doc {doc_id}: {e}")

        self._ingest_count += 1
        return {
            "doc_id": doc_id,
            "parents_created": len(parents),
            "children_created": len(children),
            "collection": target,
            "chunking": "hierarchical",
        }

    def get_stats(self) -> Dict:
        return {
            "documents_ingested": self._ingest_count,
            "intelligence_layers": {
                "query_understanding": True,
                "retrieval_feedback": True,
                "answer_grounding": True,
                "hierarchical_chunking": True,
            },
        }
