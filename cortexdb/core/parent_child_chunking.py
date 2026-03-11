"""Parent-Child (Hierarchical) Chunking for RAG

Creates a two-level hierarchy of chunks: large parent chunks for rich context
and small child chunks for precise retrieval.  After vector search returns
child-level matches, the parent chunk is fetched to provide the LLM with a
wider context window — giving the best of both granularity and coherence.

Each chunk carries a deterministic ID, character offsets, and approximate
token counts.  Children reference their parent via ``parent_id``.
"""

import hashlib
import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("cortexdb.core.parent_child_chunking")


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ParentChunk:
    chunk_id: str
    doc_id: str
    content: str
    chunk_index: int
    start_char: int
    end_char: int
    token_count: int
    metadata: Dict
    children: List[str] = field(default_factory=list)  # child chunk_ids


@dataclass
class ChildChunk:
    chunk_id: str
    doc_id: str
    parent_id: str  # parent chunk_id
    content: str
    chunk_index: int
    start_char: int  # relative to parent start
    end_char: int
    token_count: int
    metadata: Dict


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _estimate_tokens(text: str) -> int:
    """Approximate token count (~4 chars per token for English).

    CJK characters (Chinese, Japanese, Korean) are typically 1 token each,
    so they are counted separately from Latin text which averages ~4 chars/token.
    """
    cjk_count = sum(
        1 for ch in text
        if '\u4e00' <= ch <= '\u9fff'    # CJK Unified Ideographs
        or '\u3040' <= ch <= '\u309f'     # Hiragana
        or '\u30a0' <= ch <= '\u30ff'     # Katakana
    )
    non_cjk_len = len(text) - cjk_count
    return cjk_count + non_cjk_len // 4


def _generate_id(doc_id: str, level: str, index: int) -> str:
    """Deterministic hash from doc_id, hierarchy level, and index."""
    raw = f"{doc_id}:{level}:{index}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


# ---------------------------------------------------------------------------
# SmartBoundaryDetector
# ---------------------------------------------------------------------------

class SmartBoundaryDetector:
    """Identifies natural content boundaries for better chunk splitting.

    Detects paragraph breaks, section headers, code block fences, and
    list-to-prose transitions.
    """

    # Patterns compiled once at class level.
    _PARAGRAPH_BREAK = re.compile(r"\n\s*\n")
    _MARKDOWN_HEADER = re.compile(r"^#{1,6}\s", re.MULTILINE)
    _ALL_CAPS_LINE = re.compile(r"^[A-Z][A-Z0-9 ]{2,}$", re.MULTILINE)
    _SETEXT_HEADER = re.compile(r"^[^\n]+\n[=\-]{3,}\s*$", re.MULTILINE)
    _CODE_FENCE = re.compile(r"^```", re.MULTILINE)
    _LIST_ITEM = re.compile(r"^[ \t]*[-*+\d.]+[ \t]", re.MULTILINE)

    def detect_boundaries(self, text: str) -> List[int]:
        """Return a sorted, deduplicated list of character offsets where
        natural content boundaries occur.
        """
        boundaries: set = set()

        # Paragraph breaks (position right after the blank line).
        for m in self._PARAGRAPH_BREAK.finditer(text):
            boundaries.add(m.end())

        # Markdown-style headers.
        for m in self._MARKDOWN_HEADER.finditer(text):
            boundaries.add(m.start())

        # ALL CAPS heading lines.
        for m in self._ALL_CAPS_LINE.finditer(text):
            boundaries.add(m.start())

        # Setext-style headers (underlined with === or ---).
        for m in self._SETEXT_HEADER.finditer(text):
            boundaries.add(m.start())

        # Code block fences.
        for m in self._CODE_FENCE.finditer(text):
            boundaries.add(m.start())

        # List-to-prose transitions: find list items, then check if the next
        # non-blank line is *not* a list item.
        list_positions = [m.start() for m in self._LIST_ITEM.finditer(text)]
        for pos in list_positions:
            # Walk to the end of the current line.
            line_end = text.find("\n", pos)
            if line_end == -1:
                continue
            # Skip blank lines.
            next_pos = line_end + 1
            while next_pos < len(text) and text[next_pos] in " \t\n":
                if text[next_pos] == "\n":
                    next_pos += 1
                    break
                next_pos += 1
            if next_pos < len(text) and not self._LIST_ITEM.match(text[next_pos:]):
                boundaries.add(next_pos)

        # Remove boundary at position 0 (useless) and past end.
        boundaries.discard(0)
        result = sorted(b for b in boundaries if b < len(text))
        return result

    def split_at_boundaries(
        self,
        text: str,
        target_size: int,
        boundaries: List[int],
    ) -> List[Tuple[int, int, str]]:
        """Split *text* into segments of approximately *target_size* tokens,
        preferring detected *boundaries* over mid-sentence splits.

        Returns a list of ``(start_char, end_char, content)`` tuples.
        """
        if not text:
            return []

        target_chars = target_size * 4  # inverse of _estimate_tokens
        segments: List[Tuple[int, int, str]] = []
        pos = 0

        while pos < len(text):
            ideal_end = min(pos + target_chars, len(text))

            if ideal_end >= len(text):
                # Last segment — take everything remaining.
                segments.append((pos, len(text), text[pos:]))
                break

            # Look for the nearest boundary within a tolerance window around
            # the ideal split point (±25 % of target_chars).
            tolerance = target_chars // 4
            window_start = max(pos + 1, ideal_end - tolerance)
            window_end = min(len(text), ideal_end + tolerance)

            best = None
            best_dist = None
            for b in boundaries:
                if b < window_start:
                    continue
                if b > window_end:
                    break  # boundaries are sorted
                dist = abs(b - ideal_end)
                if best_dist is None or dist < best_dist:
                    best = b
                    best_dist = dist

            if best is not None:
                split_at = best
            else:
                # No boundary nearby — fall back to the nearest whitespace
                # before ideal_end to avoid splitting mid-word.
                split_at = ideal_end
                while split_at > pos and text[split_at] not in " \t\n":
                    split_at -= 1
                if split_at == pos:
                    # No whitespace found; hard-split at ideal_end.
                    split_at = ideal_end

            content = text[pos:split_at]
            segments.append((pos, split_at, content))
            pos = split_at

        return segments


# ---------------------------------------------------------------------------
# HierarchicalChunker
# ---------------------------------------------------------------------------

class HierarchicalChunker:
    """Two-pass chunker: large parent chunks for context, small child chunks
    for precise retrieval.

    Parameters
    ----------
    parent_size : int
        Target token count for parent chunks (default 1024).
    child_size : int
        Target token count for child chunks (default 256).
    child_overlap : int
        Overlap tokens between consecutive child chunks (default 32).
    min_child_size : int
        Minimum token count for a child chunk to be emitted (default 64).
    """

    def __init__(
        self,
        parent_size: int = 1024,
        child_size: int = 256,
        child_overlap: int = 32,
        min_child_size: int = 64,
    ):
        self.parent_size = parent_size
        self.child_size = child_size
        # Ensure overlap is strictly less than child_size to prevent zero/negative step
        self.child_overlap = min(child_overlap, child_size - 1)
        self.min_child_size = min_child_size
        self._boundary_detector = SmartBoundaryDetector()

    # -- public API ---------------------------------------------------------

    def chunk(
        self,
        text: str,
        doc_id: str,
        metadata: Dict = None,
    ) -> Dict[str, list]:
        """Create hierarchical chunks from *text*.

        1. First pass — split text into large, paragraph-aware parent chunks.
        2. Second pass — split each parent into overlapping child chunks.
        3. Link children to parents via ``parent_id``.

        Returns ``{"parents": List[ParentChunk], "children": List[ChildChunk]}``.
        """
        if not text or not text.strip():
            return {"parents": [], "children": []}

        base_meta = dict(metadata) if metadata else {}
        boundaries = self._boundary_detector.detect_boundaries(text)

        # -- First pass: parent chunks ------------------------------------
        parent_segments = self._boundary_detector.split_at_boundaries(
            text, self.parent_size, boundaries,
        )

        parents: List[ParentChunk] = []
        children: List[ChildChunk] = []
        child_global_index = 0

        for p_idx, (p_start, p_end, p_content) in enumerate(parent_segments):
            parent_id = _generate_id(doc_id, "parent", p_idx)
            parent_meta = dict(base_meta)
            parent_meta["level"] = "parent"

            parent = ParentChunk(
                chunk_id=parent_id,
                doc_id=doc_id,
                content=p_content,
                chunk_index=p_idx,
                start_char=p_start,
                end_char=p_end,
                token_count=_estimate_tokens(p_content),
                metadata=parent_meta,
                children=[],
            )

            # -- Second pass: child chunks inside this parent -------------
            child_segments = self._split_children(p_content)

            for c_local_idx, (c_start, c_end, c_content) in enumerate(child_segments):
                child_id = _generate_id(doc_id, "child", child_global_index)
                child_meta = dict(base_meta)
                child_meta["level"] = "child"
                child_meta["parent_chunk_index"] = p_idx

                child = ChildChunk(
                    chunk_id=child_id,
                    doc_id=doc_id,
                    parent_id=parent_id,
                    content=c_content,
                    chunk_index=child_global_index,
                    start_char=p_start + c_start,   # absolute offset in document
                    end_char=p_start + c_end,
                    token_count=_estimate_tokens(c_content),
                    metadata=child_meta,
                )
                parent.children.append(child_id)
                children.append(child)
                child_global_index += 1

            parents.append(parent)

        logger.info(
            "Hierarchical chunking complete for doc_id=%s: %d parents, %d children",
            doc_id, len(parents), len(children),
        )
        return {"parents": parents, "children": children}

    def get_parent_for_child(
        self,
        child_id: str,
        parents: List[ParentChunk],
    ) -> Optional[ParentChunk]:
        """Look up the parent chunk that owns *child_id*."""
        for parent in parents:
            if child_id in parent.children:
                return parent
        return None

    def expand_context(
        self,
        child_results: List[Dict],
        parents: List[ParentChunk],
        max_tokens: int = 4000,
    ) -> List[Dict]:
        """Expand child-level search results to parent-level context.

        Each entry in *child_results* must contain at minimum
        ``{"child_id": str, "score": float}``.  Additional keys are preserved.

        Deduplicates parents (multiple children may share one) and respects
        the *max_tokens* budget.  Returns parent-level dicts ordered by the
        best child score within each parent.
        """
        # Build child_id -> parent index (O(P+C) instead of O(P*C) per lookup)
        child_to_parent: Dict[str, ParentChunk] = {}
        for parent in parents:
            for cid in parent.children:
                child_to_parent[cid] = parent

        # Map parent_id -> (parent, best_score, matching child ids).
        parent_map: Dict[str, dict] = {}

        for result in child_results:
            child_id = result.get("child_id")
            if child_id is None:
                continue
            score = result.get("score", 0.0)

            parent = child_to_parent.get(child_id)
            if parent is None:
                logger.warning("No parent found for child_id=%s", child_id)
                continue

            pid = parent.chunk_id
            if pid not in parent_map:
                parent_map[pid] = {
                    "parent": parent,
                    "best_score": score,
                    "matched_children": [child_id],
                }
            else:
                entry = parent_map[pid]
                entry["best_score"] = max(entry["best_score"], score)
                if child_id not in entry["matched_children"]:
                    entry["matched_children"].append(child_id)

        # Sort by best child score descending.
        ordered = sorted(parent_map.values(), key=lambda e: e["best_score"], reverse=True)

        expanded: List[Dict] = []
        tokens_used = 0

        for entry in ordered:
            parent: ParentChunk = entry["parent"]
            if tokens_used + parent.token_count > max_tokens:
                logger.debug(
                    "Token budget exhausted (%d/%d), stopping expansion",
                    tokens_used, max_tokens,
                )
                break

            expanded.append({
                "parent_id": parent.chunk_id,
                "doc_id": parent.doc_id,
                "content": parent.content,
                "token_count": parent.token_count,
                "score": entry["best_score"],
                "matched_children": entry["matched_children"],
                "metadata": parent.metadata,
            })
            tokens_used += parent.token_count

        logger.info(
            "Context expansion: %d child results -> %d unique parents (%d tokens)",
            len(child_results), len(expanded), tokens_used,
        )
        return expanded

    # -- internal helpers ---------------------------------------------------

    def _split_children(self, parent_content: str) -> List[Tuple[int, int, str]]:
        """Split *parent_content* into overlapping child segments.

        Offsets are relative to the start of the parent.
        """
        target_chars = self.child_size * 4
        overlap_chars = self.child_overlap * 4
        min_chars = self.min_child_size * 4
        step = max(1, target_chars - overlap_chars)

        segments: List[Tuple[int, int, str]] = []
        pos = 0
        text_len = len(parent_content)

        while pos < text_len:
            end = min(pos + target_chars, text_len)

            # Try to avoid splitting mid-word by snapping to whitespace.
            if end < text_len:
                snap = end
                while snap > pos and parent_content[snap] not in " \t\n":
                    snap -= 1
                if snap > pos:
                    end = snap

            content = parent_content[pos:end]
            token_count = _estimate_tokens(content)

            # If this is the last segment, merge it into the previous one
            # when it's below the minimum size.
            remaining = text_len - end
            if remaining > 0 and _estimate_tokens(parent_content[end:]) < self.min_child_size:
                # Extend this segment to the end of the parent.
                content = parent_content[pos:]
                end = text_len
                token_count = _estimate_tokens(content)
                segments.append((pos, end, content))
                break

            if token_count >= self.min_child_size or not segments:
                segments.append((pos, end, content))

            # Advance based on actual end position minus overlap, not fixed step
            new_pos = end - overlap_chars
            # Ensure pos always advances by at least 1 to avoid infinite loops
            pos = max(pos + 1, new_pos)

        return segments
