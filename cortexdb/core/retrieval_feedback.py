"""
Retrieval Feedback Loop with Confidence Scoring

Evaluates RAG retrieval quality and triggers automatic query reformulation
when results are poor. Uses lightweight heuristics (term overlap, statistical
measures) — no ML models required.

Feedback loop: Search -> Score -> Reformulate (if needed) -> Re-search -> Best result
"""

import logging
import math
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("cortexdb.core.retrieval_feedback")


_STOP_WORDS = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "need", "to", "of", "in",
    "for", "on", "with", "at", "by", "from", "as", "into", "through",
    "during", "before", "after", "above", "below", "between", "out", "off",
    "over", "under", "again", "then", "once", "here", "there", "when",
    "where", "why", "how", "all", "both", "each", "few", "more", "most",
    "other", "some", "such", "no", "nor", "not", "only", "own", "same",
    "so", "than", "too", "very", "just", "about", "up", "and", "but",
    "or", "if", "while", "because", "until", "that", "this", "these",
    "those", "it", "its", "i", "me", "my", "we", "our", "you", "your",
    "he", "him", "his", "she", "her", "they", "them", "their", "what",
    "which", "who", "whom",
}


def _tokenize(text: str) -> List[str]:
    """Lowercase tokenization with basic punctuation removal."""
    return re.findall(r"[\w]+", text.lower())


def _content_tokens(text: str) -> set:
    """Extract content tokens (excluding stop words) for meaningful comparison."""
    return {t for t in _tokenize(text) if t not in _STOP_WORDS and len(t) > 1}


def _unique_tokens(text: str) -> set:
    return set(_tokenize(text))


# ---------------------------------------------------------------------------
# RetrievalConfidence
# ---------------------------------------------------------------------------

@dataclass
class RetrievalConfidence:
    """Quantified assessment of how well a set of results answers a query."""

    overall_score: float  # 0-1 composite score
    coverage_score: float  # fraction of query terms found in results
    coherence_score: float  # consistency of similarity scores (1 = tight cluster)
    relevance_distribution: List[float]  # per-result relevance scores
    verdict: str  # "high" | "medium" | "low" | "insufficient"
    suggestions: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# RetrievalFeedback
# ---------------------------------------------------------------------------

class RetrievalFeedback:
    """Scores retrieval quality and orchestrates query reformulation."""

    def __init__(
        self,
        threshold_high: float = 0.8,
        threshold_medium: float = 0.5,
        max_reformulations: int = 2,
    ):
        self.threshold_high = threshold_high
        self.threshold_medium = threshold_medium
        self.max_reformulations = max_reformulations

    # -- scoring -------------------------------------------------------------

    def score_results(
        self, query: str, results: List[Dict]
    ) -> RetrievalConfidence:
        """Evaluate retrieval quality using lightweight heuristics.

        Expected result dict keys:
            content (str)  — the text of the chunk
            score   (float) — similarity / relevance score from the search engine
        """
        if not results:
            return RetrievalConfidence(
                overall_score=0.0,
                coverage_score=0.0,
                coherence_score=0.0,
                relevance_distribution=[],
                verdict="insufficient",
                suggestions=["no results returned — broaden search or lower threshold"],
            )

        query_terms = _content_tokens(query)
        scores = [r.get("score", 0.0) for r in results]
        contents = [r.get("content", "") for r in results]

        coverage = self._coverage(query_terms, contents)
        coherence = self._coherence(scores)
        relevance_curve = self._relevance_curve_penalty(scores)
        count_factor = self._count_factor(len(results), scores)

        # Composite: weighted combination
        overall = (
            0.35 * coverage
            + 0.25 * coherence
            + 0.25 * relevance_curve
            + 0.15 * count_factor
        )
        overall = max(0.0, min(1.0, overall))

        verdict = self._verdict(overall)
        suggestions = self._build_suggestions(coverage, coherence, relevance_curve, count_factor, len(results))

        confidence = RetrievalConfidence(
            overall_score=round(overall, 4),
            coverage_score=round(coverage, 4),
            coherence_score=round(coherence, 4),
            relevance_distribution=[round(s, 4) for s in scores],
            verdict=verdict,
            suggestions=suggestions,
        )
        logger.debug(
            "scored query=%r  overall=%.3f  verdict=%s  (%d results)",
            query, overall, verdict, len(results),
        )
        return confidence

    # -- sub-scores ----------------------------------------------------------

    @staticmethod
    def _coverage(query_terms: set, contents: List[str]) -> float:
        """Fraction of query content terms that appear in at least one result.
        Uses content tokens (stop words excluded) for meaningful signal."""
        if not query_terms:
            return 1.0
        combined_tokens = set()
        for c in contents:
            combined_tokens.update(_content_tokens(c))
        matched = query_terms & combined_tokens
        return len(matched) / len(query_terms)

    @staticmethod
    def _coherence(scores: List[float]) -> float:
        """Top-k quality — do the top results have strong absolute scores?

        Rewards result sets where the top results score highly.
        A tight cluster of HIGH scores is good; a tight cluster of LOW scores is bad.
        """
        if not scores:
            return 0.0
        if len(scores) == 1:
            return min(1.0, scores[0])
        # Use the mean of the top-3 scores (or fewer if less available)
        sorted_desc = sorted(scores, reverse=True)
        top_k = sorted_desc[:min(3, len(sorted_desc))]
        top_mean = sum(top_k) / len(top_k)
        return max(0.0, min(1.0, top_mean))

    @staticmethod
    def _relevance_curve_penalty(scores: List[float]) -> float:
        """Sharp drop-off in scores is good (clear winners); gradual is bad.

        Measures the ratio between the top score and the median score.
        A large gap means clear separation -> high score.
        """
        if not scores:
            return 0.0
        sorted_desc = sorted(scores, reverse=True)
        top = sorted_desc[0]
        if top == 0:
            return 0.0
        median_idx = len(sorted_desc) // 2
        median = sorted_desc[median_idx]
        gap_ratio = (top - median) / top if top > 0 else 0.0
        # A gap_ratio near 1 means strong separation; near 0 means flat (no clear winners).
        # However a *single* result also yields gap_ratio 0 — handle that:
        if len(sorted_desc) == 1:
            return min(1.0, top)  # single result, just trust its raw score
        return max(0.0, min(1.0, 0.5 + gap_ratio))

    @staticmethod
    def _count_factor(n: int, scores: List[float]) -> float:
        """Penalise too few results or too many low-scoring results."""
        if n == 0:
            return 0.0
        # Penalty for very few results
        if n < 3:
            base = 0.3 * n  # 0.3 for 1, 0.6 for 2
        else:
            base = 1.0

        # Penalise if majority of results score below 0.3
        low_count = sum(1 for s in scores if s < 0.3)
        noise_ratio = low_count / n
        return base * (1.0 - 0.5 * noise_ratio)

    def _verdict(self, overall: float) -> str:
        if overall >= self.threshold_high:
            return "high"
        if overall >= self.threshold_medium:
            return "medium"
        if overall > 0.0:
            return "low"
        return "insufficient"

    @staticmethod
    def _build_suggestions(
        coverage: float,
        coherence: float,
        relevance_curve: float,
        count_factor: float,
        n_results: int,
    ) -> List[str]:
        suggestions: List[str] = []
        if coverage < 0.5:
            suggestions.append("low coverage — broaden search or add keyword terms")
        if coherence < 0.4:
            suggestions.append("low coherence — narrow query or add constraints to reduce noise")
        if relevance_curve < 0.4:
            suggestions.append("flat relevance curve — no clear top results, consider refining query")
        if n_results < 3:
            suggestions.append("few results — lower similarity threshold or broaden collection")
        if count_factor < 0.5 and n_results >= 3:
            suggestions.append("many low-scoring results — raise threshold to filter noise")
        return suggestions

    # -- reformulation -------------------------------------------------------

    def should_reformulate(self, confidence: RetrievalConfidence) -> bool:
        """Return True if confidence warrants a re-search attempt."""
        return confidence.verdict in ("low", "insufficient")

    def suggest_reformulation(
        self,
        query: str,
        confidence: RetrievalConfidence,
        attempt: int,
    ) -> Dict[str, Any]:
        """Suggest concrete reformulation strategy based on the confidence analysis.

        Returns:
            {"strategy": str, "params": dict} with adjusted search parameters.
        """
        strategy: str = "none"
        params: Dict[str, Any] = {}

        if confidence.verdict == "insufficient" or confidence.coverage_score < 0.3:
            strategy = "broaden"
            # Suggest lowering the threshold and increasing top-k
            params = {
                "score_threshold": max(0.1, 0.3 - 0.05 * attempt),
                "top_k_multiplier": 1.5 + 0.5 * attempt,
                "query_expansion": self._expand_query(query),
            }
        elif confidence.coherence_score < 0.4:
            strategy = "narrow"
            # Results are noisy — raise threshold and constrain
            query_terms = _tokenize(query)
            # Keep the most distinctive terms (longest, heuristic for specificity)
            distinctive = sorted(query_terms, key=len, reverse=True)[:3]
            params = {
                "score_threshold_increase": 0.1 * (attempt + 1),
                "refined_query": " ".join(distinctive),
                "filter_low_scores": True,
            }
        elif confidence.coverage_score < 0.6:
            strategy = "expand_terms"
            params = {
                "query_expansion": self._expand_query(query),
                "top_k_multiplier": 1.25,
            }
        else:
            strategy = "retry_relaxed"
            params = {
                "score_threshold": max(0.1, 0.4 - 0.1 * attempt),
                "top_k_multiplier": 1.5,
            }

        logger.info(
            "reformulation attempt=%d  strategy=%s  verdict=%s",
            attempt, strategy, confidence.verdict,
        )
        return {"strategy": strategy, "params": params}

    @staticmethod
    def _expand_query(query: str) -> str:
        """Simple query expansion: de-duplicate and keep original ordering."""
        tokens = _tokenize(query)
        seen: set = set()
        expanded: List[str] = []
        for t in tokens:
            if t not in seen:
                seen.add(t)
                expanded.append(t)
        return " ".join(expanded)

    # -- adaptive search loop ------------------------------------------------

    async def adaptive_search(
        self,
        query: str,
        search_fn: Callable[..., Any],
        **search_kwargs: Any,
    ) -> Dict[str, Any]:
        """Run a search with automatic reformulation when confidence is low.

        Args:
            query: The user query string.
            search_fn: An async callable ``search_fn(query, **kwargs) -> List[Dict]``.
            **search_kwargs: Forwarded to *search_fn*.

        Returns:
            {
                "results": List[Dict],
                "confidence": RetrievalConfidence,
                "attempts": int,
                "reformulations_used": List[str],
            }
        """
        best_results: List[Dict] = []
        best_confidence: Optional[RetrievalConfidence] = None
        reformulations_used: List[str] = []
        current_query = query
        current_kwargs = dict(search_kwargs)
        original_top_k = current_kwargs.get("top_k", current_kwargs.get("limit", 10))

        for attempt in range(1 + self.max_reformulations):
            results = await search_fn(current_query, **current_kwargs)
            confidence = self.score_results(current_query, results)

            # Track the best result set across attempts
            if best_confidence is None or confidence.overall_score > best_confidence.overall_score:
                best_results = results
                best_confidence = confidence

            logger.debug(
                "adaptive_search attempt=%d  score=%.3f  verdict=%s",
                attempt, confidence.overall_score, confidence.verdict,
            )

            # Good enough or no more attempts
            if not self.should_reformulate(confidence):
                break
            if attempt >= self.max_reformulations:
                break

            # Reformulate
            suggestion = self.suggest_reformulation(current_query, confidence, attempt)
            reformulations_used.append(suggestion["strategy"])
            params = suggestion["params"]

            # Apply reformulation to search kwargs
            if "refined_query" in params:
                current_query = params["refined_query"]
            elif "query_expansion" in params:
                current_query = params["query_expansion"]

            if "score_threshold" in params:
                current_kwargs["score_threshold"] = params["score_threshold"]
            elif "score_threshold_increase" in params:
                current_threshold = current_kwargs.get("score_threshold", 0.5)
                current_kwargs["score_threshold"] = min(0.95, current_threshold + params["score_threshold_increase"])

            if "top_k_multiplier" in params:
                # Multiply against the ORIGINAL top_k, not the already-multiplied value
                current_kwargs["top_k"] = int(original_top_k * params["top_k_multiplier"])

            if params.get("filter_low_scores"):
                current_kwargs["filter_low_scores"] = True

        return {
            "results": best_results,
            "confidence": best_confidence,
            "attempts": len(reformulations_used) + 1,
            "reformulations_used": reformulations_used,
        }


# ---------------------------------------------------------------------------
# AnswerGrounding
# ---------------------------------------------------------------------------

class AnswerGrounding:
    """Verifies that retrieved chunks are actually grounded in the query
    and builds citation provenance for each result."""

    def verify_grounding(
        self, answer_chunks: List[str], query: str
    ) -> Dict[str, Any]:
        """Check which chunks are grounded in the query.

        A chunk is considered *grounded* when it contains at least one
        query term (case-insensitive token overlap).

        Returns:
            {
                "grounded_chunks": List[int],   — indices of supporting chunks
                "ungrounded_chunks": List[int],  — indices of noise chunks
                "grounding_score": float,        — fraction grounded
                "warnings": List[str],
            }
        """
        query_terms = _content_tokens(query)
        if not query_terms:
            return {
                "grounded_chunks": list(range(len(answer_chunks))),
                "ungrounded_chunks": [],
                "grounding_score": 1.0,
                "warnings": ["empty query — all chunks treated as grounded"],
            }

        # Require at least 2 content-word overlaps (or 1 if query has <=2 terms)
        min_overlap = min(2, len(query_terms))

        grounded: List[int] = []
        ungrounded: List[int] = []

        for idx, chunk in enumerate(answer_chunks):
            chunk_tokens = _content_tokens(chunk)
            overlap = query_terms & chunk_tokens
            if len(overlap) >= min_overlap:
                grounded.append(idx)
            else:
                ungrounded.append(idx)

        total = len(answer_chunks) if answer_chunks else 1
        grounding_score = len(grounded) / total

        warnings: List[str] = []
        if grounding_score < 0.5:
            warnings.append(
                f"only {len(grounded)}/{len(answer_chunks)} chunks are grounded in the query"
            )
        if not answer_chunks:
            warnings.append("no chunks provided for grounding verification")

        logger.debug(
            "grounding check: %d/%d grounded (%.2f)",
            len(grounded), len(answer_chunks), grounding_score,
        )

        return {
            "grounded_chunks": grounded,
            "ungrounded_chunks": ungrounded,
            "grounding_score": round(grounding_score, 4),
            "warnings": warnings,
        }

    @staticmethod
    def build_citations(results: List[Dict]) -> List[Dict[str, Any]]:
        """Map each result back to its source document with provenance.

        Expected result dict keys (all optional except *content*):
            content    (str)  — chunk text
            score      (float)
            chunk_id   (str)
            doc_id     (str)
            chunk_index (int)
            start_char  (int)

        Returns:
            List of citation dicts with normalised structure.
        """
        citations: List[Dict[str, Any]] = []

        for idx, r in enumerate(results):
            content = r.get("content", "")
            preview = content[:120] + ("..." if len(content) > 120 else "")

            citation: Dict[str, Any] = {
                "chunk_id": r.get("chunk_id", f"chunk_{idx}"),
                "doc_id": r.get("doc_id", "unknown"),
                "content_preview": preview,
                "score": r.get("score", 0.0),
                "position": {
                    "chunk_index": r.get("chunk_index", idx),
                    "start_char": r.get("start_char", 0),
                },
            }
            citations.append(citation)

        return citations
