"""
RAG Pipeline — Document ingestion into VectorCore for agent context retrieval.

Flow:
  1. Ingest: Accept text/markdown/URL content
  2. Chunk: Split into overlapping chunks (~500 tokens each)
  3. Embed: Generate vectors via VectorCore's embed_text
  4. Store: Upsert into Qdrant collection 'rag_documents'
  5. Retrieve: Similarity search for relevant chunks given a query
  6. Augment: Inject retrieved chunks into agent LLM context
"""

import time
import hashlib
import logging
import re
from typing import Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from cortexdb.superadmin.persistence import PersistenceStore

logger = logging.getLogger(__name__)

COLLECTION = "rag_documents"
CHUNK_SIZE = 500  # approximate characters per chunk
CHUNK_OVERLAP = 100  # overlap between chunks


class RAGPipeline:
    """Document ingestion and retrieval for agent context augmentation."""

    def __init__(self, engine_bridge, persistence: "PersistenceStore"):
        self._bridge = engine_bridge
        self._persistence = persistence
        self._documents: Dict[str, dict] = {}
        # Load index
        index = self._persistence.kv_get("rag_document_index", {})
        self._documents = index

    def _chunk_text(self, text: str) -> List[str]:
        """Split text into overlapping chunks."""
        chunks = []
        # Split on paragraphs first, then by size
        paragraphs = re.split(r'\n\n+', text)
        current_chunk = ""

        for para in paragraphs:
            if len(current_chunk) + len(para) > CHUNK_SIZE and current_chunk:
                chunks.append(current_chunk.strip())
                # Keep overlap
                current_chunk = current_chunk[-CHUNK_OVERLAP:] if len(current_chunk) > CHUNK_OVERLAP else ""
            current_chunk += para + "\n\n"

        if current_chunk.strip():
            chunks.append(current_chunk.strip())

        return chunks

    async def ingest(self, title: str, content: str, source: str = "manual",
                     metadata: dict = None) -> dict:
        """Ingest a document: chunk, embed, and store in VectorCore."""
        doc_id = hashlib.sha256(f"{title}:{time.time()}".encode()).hexdigest()[:16]
        chunks = self._chunk_text(content)

        if not chunks:
            return {"error": "No content to ingest"}

        stored = 0
        if self._bridge and self._bridge.has_vector:
            vector_engine = self._bridge._engines["vector"]
            try:
                await vector_engine._ensure_collection(COLLECTION)
                points = []
                for i, chunk in enumerate(chunks):
                    chunk_id = f"{doc_id}-{i}"
                    points.append({
                        "id": chunk_id,
                        "text": chunk,
                        "payload": {
                            "doc_id": doc_id,
                            "title": title,
                            "chunk_index": i,
                            "total_chunks": len(chunks),
                            "source": source,
                            "content": chunk,
                            **(metadata or {}),
                        },
                    })
                stored = await vector_engine.upsert_vectors(COLLECTION, points)
            except Exception as e:
                logger.warning("RAG ingest to VectorCore failed: %s", e)

        # Track document
        doc_entry = {
            "doc_id": doc_id,
            "title": title,
            "source": source,
            "chunks": len(chunks),
            "stored_vectors": stored,
            "char_count": len(content),
            "ingested_at": time.time(),
        }
        self._documents[doc_id] = doc_entry
        self._persistence.kv_set("rag_document_index", self._documents)

        logger.info("RAG ingested '%s': %d chunks, %d vectors stored", title, len(chunks), stored)
        return doc_entry

    async def retrieve(self, query: str, limit: int = 5,
                       threshold: float = 0.5) -> List[dict]:
        """Retrieve relevant document chunks for a query."""
        if not self._bridge or not self._bridge.has_vector:
            return []

        vector_engine = self._bridge._engines["vector"]
        try:
            results = await vector_engine.search_similar(
                collection=COLLECTION,
                query_text=query,
                threshold=threshold,
                limit=limit,
            )
            return [
                {
                    "content": r["payload"].get("content", ""),
                    "title": r["payload"].get("title", ""),
                    "score": r["score"],
                    "doc_id": r["payload"].get("doc_id", ""),
                    "chunk_index": r["payload"].get("chunk_index", 0),
                }
                for r in results
            ]
        except Exception as e:
            logger.warning("RAG retrieval failed: %s", e)
            return []

    def build_rag_context(self, chunks: List[dict], max_chars: int = 3000) -> str:
        """Build a context string from retrieved chunks for LLM injection."""
        if not chunks:
            return ""
        parts = ["## Retrieved Knowledge"]
        total = 0
        for chunk in chunks:
            text = f"\n[{chunk.get('title', 'doc')} (score: {chunk.get('score', 0):.2f})]:\n{chunk['content']}"
            total += len(text)
            if total > max_chars:
                break
            parts.append(text)
        return "\n".join(parts)

    def get_documents(self) -> List[dict]:
        """Get all ingested documents."""
        return list(self._documents.values())

    def delete_document(self, doc_id: str) -> dict:
        """Remove a document from the index."""
        if doc_id in self._documents:
            del self._documents[doc_id]
            self._persistence.kv_set("rag_document_index", self._documents)
            return {"deleted": True, "doc_id": doc_id}
        return {"error": "Document not found"}

    def get_stats(self) -> dict:
        return {
            "total_documents": len(self._documents),
            "total_chunks": sum(d.get("chunks", 0) for d in self._documents.values()),
            "vector_store": "connected" if (self._bridge and self._bridge.has_vector) else "unavailable",
        }
