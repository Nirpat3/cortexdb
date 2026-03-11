"""Document Chunking Pipeline for RAG

Splits documents into overlapping chunks with provenance tracking.
Supports token-based, sentence-based, and paragraph-based strategies.
Each chunk carries a deterministic ID (hash of doc_id + index), character
offsets into the original document, and approximate token counts.
"""

import hashlib
import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger("cortexdb.core.chunking")


@dataclass
class Chunk:
    chunk_id: str           # deterministic hash of doc_id + chunk_index
    doc_id: str             # parent document ID
    content: str            # chunk text
    chunk_index: int        # position in document (0-based)
    start_char: int         # character offset in original doc
    end_char: int           # character offset end
    metadata: Dict          # inherited from document + chunk-specific
    token_count: int        # approximate token count


@dataclass
class ChunkingConfig:
    strategy: str = "token"         # "token", "sentence", "paragraph"
    chunk_size: int = 512           # target tokens per chunk
    chunk_overlap: int = 50         # overlap tokens between chunks
    min_chunk_size: int = 50        # discard chunks smaller than this
    max_chunk_size: int = 1024      # hard limit
    separator: str = "\n\n"         # for paragraph strategy


class ChunkingPipeline:
    """Split documents into overlapping chunks with provenance metadata.

    Strategies:
      - token: whitespace-based splitting with ~4 chars/token heuristic
      - sentence: accumulate sentences until chunk_size, overlap by sentences
      - paragraph: split on double newlines, merge small / split large
    """

    def __init__(self, config: ChunkingConfig = None):
        self.config = config or ChunkingConfig()

    def chunk(self, text: str, doc_id: str, metadata: Dict = None) -> List[Chunk]:
        """Split text into overlapping chunks using the configured strategy."""
        strategy = self.config.strategy
        if strategy == "sentence":
            return self.chunk_by_sentences(text, doc_id, metadata)
        elif strategy == "paragraph":
            return self.chunk_by_paragraphs(text, doc_id, metadata)
        else:
            return self.chunk_by_tokens(text, doc_id, metadata)

    # ── Token-based chunking ─────────────────────────────────────────

    def chunk_by_tokens(self, text: str, doc_id: str, metadata: Dict = None) -> List[Chunk]:
        """Token-based chunking with overlap.

        Uses simple whitespace tokenizer.  Approximate token count via
        ``_estimate_tokens`` (~4 chars per token for English).
        """
        words = text.split()
        if not words:
            return []

        cfg = self.config
        # Convert token counts to approximate word counts (words ~= tokens for English)
        target_words = cfg.chunk_size
        overlap_words = cfg.chunk_overlap
        min_words = cfg.min_chunk_size
        max_words = cfg.max_chunk_size

        chunks: List[Chunk] = []
        idx = 0
        chunk_index = 0

        # Pre-compute word offsets once — O(n) instead of O(n²) per chunk
        self._word_offsets = self._build_word_offsets(text, words)

        while idx < len(words):
            end = min(idx + target_words, len(words))
            # Enforce max_chunk_size
            if end - idx > max_words:
                end = idx + max_words

            chunk_words = words[idx:end]
            content = " ".join(chunk_words)

            # Calculate character offsets in the original text
            start_char = self._find_word_offset(text, words, idx)
            end_char = self._find_word_offset(text, words, end - 1) + len(words[end - 1]) if end > 0 else 0

            token_count = self._estimate_tokens(content)

            # Skip chunks below minimum size (unless it's the only content)
            if token_count >= min_words or (chunk_index == 0 and idx + len(chunk_words) >= len(words)):
                chunk_meta = dict(metadata) if metadata else {}
                chunk_meta["strategy"] = "token"

                chunks.append(Chunk(
                    chunk_id=self._generate_chunk_id(doc_id, chunk_index),
                    doc_id=doc_id,
                    content=content,
                    chunk_index=chunk_index,
                    start_char=start_char,
                    end_char=end_char,
                    metadata=chunk_meta,
                    token_count=token_count,
                ))
                chunk_index += 1

            # Advance with overlap
            step = max(1, target_words - overlap_words)
            idx += step

            # If remaining words would be below minimum, include them in the last chunk
            if idx < len(words) and (len(words) - idx) < min_words:
                # Extend the last chunk if we already have one, otherwise loop will create a final one
                if chunks and chunk_index > 0:
                    remaining = " ".join(words[idx:])
                    last = chunks[-1]
                    extended_content = last.content + " " + remaining
                    extended_tokens = self._estimate_tokens(extended_content)
                    if extended_tokens <= max_words:
                        last_end_char = self._find_word_offset(text, words, len(words) - 1) + len(words[-1])
                        chunks[-1] = Chunk(
                            chunk_id=last.chunk_id,
                            doc_id=last.doc_id,
                            content=extended_content,
                            chunk_index=last.chunk_index,
                            start_char=last.start_char,
                            end_char=last_end_char,
                            metadata=last.metadata,
                            token_count=extended_tokens,
                        )
                        break
                # Otherwise just let the loop handle it
                continue

        return chunks

    # ── Sentence-based chunking ──────────────────────────────────────

    def chunk_by_sentences(self, text: str, doc_id: str, metadata: Dict = None) -> List[Chunk]:
        """Sentence-based chunking -- accumulate sentences until chunk_size reached.

        Splits on `.` `!` `?` followed by whitespace or end-of-string.
        Overlap is achieved by carrying the last N tokens worth of sentences.
        """
        # Split into sentences (keep the delimiter attached)
        sentences = re.split(r'(?<=[.!?])(?:\s+)', text)
        sentences = [s for s in sentences if s.strip()]

        if not sentences:
            return []

        cfg = self.config
        chunks: List[Chunk] = []
        chunk_index = 0
        _search_pos = 0  # track position for finding sentence offsets

        current_sentences: List[str] = []
        current_tokens = 0

        # Track which sentence index we started from (for overlap)
        overlap_start = 0

        for i, sentence in enumerate(sentences):
            sent_tokens = self._estimate_tokens(sentence)
            current_sentences.append(sentence)
            current_tokens += sent_tokens

            # Check if we've reached the target size or this is the last sentence
            if current_tokens >= cfg.chunk_size or i == len(sentences) - 1:
                content = " ".join(current_sentences)
                token_count = self._estimate_tokens(content)

                # Enforce max size by truncating words if needed
                if token_count > cfg.max_chunk_size:
                    words = content.split()[:cfg.max_chunk_size]
                    content = " ".join(words)
                    token_count = self._estimate_tokens(content)

                # Only emit if above minimum (or last chunk)
                if token_count >= cfg.min_chunk_size or i == len(sentences) - 1:
                    # Use _search_pos to resume from where we last left off,
                    # avoiding matching earlier duplicate sentences.
                    start_char = text.find(current_sentences[0], _search_pos)
                    if start_char == -1:
                        start_char = _search_pos
                    end_char = start_char + len(content)
                    if end_char > len(text):
                        end_char = len(text)
                    _search_pos = start_char + 1

                    chunk_meta = dict(metadata) if metadata else {}
                    chunk_meta["strategy"] = "sentence"
                    chunk_meta["sentence_count"] = len(current_sentences)

                    chunks.append(Chunk(
                        chunk_id=self._generate_chunk_id(doc_id, chunk_index),
                        doc_id=doc_id,
                        content=content,
                        chunk_index=chunk_index,
                        start_char=start_char,
                        end_char=end_char,
                        metadata=chunk_meta,
                        token_count=token_count,
                    ))
                    chunk_index += 1

                # Calculate overlap: carry last N tokens worth of sentences
                if i < len(sentences) - 1:
                    overlap_tokens = 0
                    overlap_sentences: List[str] = []
                    for s in reversed(current_sentences):
                        s_tokens = self._estimate_tokens(s)
                        if overlap_tokens + s_tokens > cfg.chunk_overlap:
                            break
                        overlap_sentences.insert(0, s)
                        overlap_tokens += s_tokens

                    current_sentences = overlap_sentences
                    current_tokens = overlap_tokens

        return chunks

    # ── Paragraph-based chunking ─────────────────────────────────────

    def chunk_by_paragraphs(self, text: str, doc_id: str, metadata: Dict = None) -> List[Chunk]:
        """Paragraph-based chunking -- split on double newlines.

        Merges small paragraphs together, splits large paragraphs into
        token-sized sub-chunks.
        """
        cfg = self.config
        paragraphs = text.split(cfg.separator)
        paragraphs = [p.strip() for p in paragraphs if p.strip()]

        if not paragraphs:
            return []

        chunks: List[Chunk] = []
        chunk_index = 0

        current_parts: List[str] = []
        current_tokens = 0

        for para in paragraphs:
            para_tokens = self._estimate_tokens(para)

            # If a single paragraph exceeds max_chunk_size, split it via token chunker
            if para_tokens > cfg.max_chunk_size:
                # Flush accumulated content first
                if current_parts:
                    content = (cfg.separator).join(current_parts)
                    chunks.extend(self._make_paragraph_chunks(
                        content, text, doc_id, chunk_index, metadata))
                    chunk_index = len(chunks)
                    current_parts = []
                    current_tokens = 0

                # Sub-chunk the large paragraph
                sub_pipeline = ChunkingPipeline(ChunkingConfig(
                    strategy="token",
                    chunk_size=cfg.chunk_size,
                    chunk_overlap=cfg.chunk_overlap,
                    min_chunk_size=cfg.min_chunk_size,
                    max_chunk_size=cfg.max_chunk_size,
                ))
                sub_chunks = sub_pipeline.chunk_by_tokens(para, doc_id, metadata)
                for sc in sub_chunks:
                    # Re-index and find correct offsets in original text
                    start_char = text.find(sc.content[:50])
                    if start_char == -1:
                        start_char = 0
                    chunk_meta = dict(metadata) if metadata else {}
                    chunk_meta["strategy"] = "paragraph"
                    chunk_meta["sub_chunked"] = True

                    chunks.append(Chunk(
                        chunk_id=self._generate_chunk_id(doc_id, chunk_index),
                        doc_id=doc_id,
                        content=sc.content,
                        chunk_index=chunk_index,
                        start_char=start_char,
                        end_char=start_char + len(sc.content),
                        metadata=chunk_meta,
                        token_count=sc.token_count,
                    ))
                    chunk_index += 1
                continue

            # Accumulate paragraphs until chunk_size
            if current_tokens + para_tokens > cfg.chunk_size and current_parts:
                content = (cfg.separator).join(current_parts)
                chunks.extend(self._make_paragraph_chunks(
                    content, text, doc_id, chunk_index, metadata))
                chunk_index = len(chunks)
                current_parts = []
                current_tokens = 0

            current_parts.append(para)
            current_tokens += para_tokens

        # Flush remaining
        if current_parts:
            content = (cfg.separator).join(current_parts)
            token_count = self._estimate_tokens(content)
            if token_count >= cfg.min_chunk_size or chunk_index == 0:
                chunks.extend(self._make_paragraph_chunks(
                    content, text, doc_id, chunk_index, metadata))

        return chunks

    # ── Helpers ───────────────────────────────────────────────────────

    def _make_paragraph_chunks(self, content: str, original_text: str,
                               doc_id: str, chunk_index: int,
                               metadata: Dict = None) -> List[Chunk]:
        """Create a single chunk from accumulated paragraph content."""
        token_count = self._estimate_tokens(content)
        start_char = original_text.find(content[:80]) if len(content) >= 80 else original_text.find(content)
        if start_char == -1:
            start_char = 0
        end_char = start_char + len(content)

        chunk_meta = dict(metadata) if metadata else {}
        chunk_meta["strategy"] = "paragraph"

        return [Chunk(
            chunk_id=self._generate_chunk_id(doc_id, chunk_index),
            doc_id=doc_id,
            content=content,
            chunk_index=chunk_index,
            start_char=start_char,
            end_char=end_char,
            metadata=chunk_meta,
            token_count=token_count,
        )]

    def _estimate_tokens(self, text: str) -> int:
        """Approximate token count (~4 chars per token for English)."""
        return len(text) // 4

    def _generate_chunk_id(self, doc_id: str, chunk_index: int) -> str:
        """Deterministic chunk ID from doc_id + index (128 bits / 32 hex chars)."""
        return hashlib.sha256(f"{doc_id}:{chunk_index}".encode()).hexdigest()[:32]

    def _build_word_offsets(self, text: str, words: List[str]) -> List[int]:
        """Pre-compute character offsets for all words in one pass — O(n)."""
        offsets = []
        pos = 0
        for word in words:
            idx = text.find(word, pos)
            if idx == -1:
                offsets.append(pos)
            else:
                offsets.append(idx)
                pos = idx + len(word)
        return offsets

    def _find_word_offset(self, text: str, words: List[str], word_index: int) -> int:
        """Find the character offset of the Nth word in the original text.

        Uses pre-computed offsets if available (set by callers via
        ``_word_offsets``), otherwise falls back to a single-pass build.
        """
        if word_index >= len(words):
            return len(text)
        if not hasattr(self, '_word_offsets') or self._word_offsets is None:
            self._word_offsets = self._build_word_offsets(text, words)
        if word_index < len(self._word_offsets):
            return self._word_offsets[word_index]
        return len(text)
