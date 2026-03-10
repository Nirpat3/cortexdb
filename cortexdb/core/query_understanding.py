"""
CortexDB Query Understanding + Reformulation Layer

Sits between the user's raw query and the retrieval engine to maximize
retrieval accuracy. Classifies intent, extracts entities, reformulates
queries into multiple variants, and selects retrieval strategy parameters.

Uses lightweight NLP (regex, heuristics, word frequency) with no heavy ML deps.
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger("cortexdb.core.query_understanding")

# ---------------------------------------------------------------------------
# Intent keyword patterns
# ---------------------------------------------------------------------------

_INTENT_PATTERNS: Dict[str, List[re.Pattern]] = {
    "definitional": [
        re.compile(r"\b(what\s+is|what\s+are|define|definition\s+of|meaning\s+of|what\s+does\s+\w+\s+mean)\b", re.I),
        re.compile(r"\bwho\s+(is|was|are|were)\b", re.I),
    ],
    "procedural": [
        re.compile(r"\b(how\s+to|how\s+do|how\s+can|steps?\s+to|guide\s+to|tutorial|instructions?\s+for)\b", re.I),
        re.compile(r"\b(set\s*up|install|configure|create|build|implement|deploy|migrate)\b", re.I),
    ],
    "comparative": [
        re.compile(r"\b(compare|comparison|vs\.?|versus|difference\s+between|differ\s+from|better\s+than|worse\s+than)\b", re.I),
        re.compile(r"\b(pros?\s+and\s+cons?|advantages?\s+and\s+disadvantages?|trade\s*-?\s*offs?)\b", re.I),
    ],
    "exploratory": [
        re.compile(r"\b(explain|describe|overview|tell\s+me\s+about|explore|elaborate|discuss)\b", re.I),
        re.compile(r"\b(why|what\s+happens|what\s+if|implications?|impact)\b", re.I),
    ],
    "factual": [
        re.compile(r"\b(when|where|how\s+many|how\s+much|which|is\s+it\s+true)\b", re.I),
        re.compile(r"\b(list|name|count|number\s+of|amount)\b", re.I),
    ],
}

# Priority when multiple intents match (higher = takes precedence)
_INTENT_PRIORITY = {
    "comparative": 5,
    "procedural": 4,
    "definitional": 3,
    "exploratory": 2,
    "factual": 1,
}

# ---------------------------------------------------------------------------
# Stop words for keyword extraction
# ---------------------------------------------------------------------------

_STOP_WORDS: Set[str] = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "need", "dare", "ought",
    "used", "to", "of", "in", "for", "on", "with", "at", "by", "from",
    "as", "into", "through", "during", "before", "after", "above", "below",
    "between", "out", "off", "over", "under", "again", "further", "then",
    "once", "here", "there", "when", "where", "why", "how", "all", "both",
    "each", "few", "more", "most", "other", "some", "such", "no", "nor",
    "not", "only", "own", "same", "so", "than", "too", "very", "just",
    "don", "t", "s", "ll", "ve", "re", "d", "m", "o", "ain", "aren",
    "couldn", "didn", "doesn", "hadn", "hasn", "haven", "isn", "ma",
    "mightn", "mustn", "needn", "shan", "shouldn", "wasn", "weren",
    "won", "wouldn", "about", "up", "and", "but", "or", "if", "while",
    "because", "until", "that", "this", "these", "those", "it", "its",
    "i", "me", "my", "we", "our", "you", "your", "he", "him", "his",
    "she", "her", "they", "them", "their", "what", "which", "who", "whom",
}

# ---------------------------------------------------------------------------
# Synonym map (small built-in dict of common technical terms)
# ---------------------------------------------------------------------------

_SYNONYMS: Dict[str, List[str]] = {
    "database": ["db", "datastore", "data store"],
    "api": ["endpoint", "interface", "rest api"],
    "authentication": ["auth", "login", "sign-in"],
    "authorization": ["permissions", "access control", "rbac"],
    "cache": ["caching", "memoization", "in-memory store"],
    "query": ["request", "lookup", "search"],
    "index": ["indexing", "search index"],
    "vector": ["embedding", "dense vector"],
    "schema": ["data model", "table structure"],
    "deploy": ["deployment", "release", "ship"],
    "container": ["docker", "containerization"],
    "kubernetes": ["k8s", "orchestration"],
    "microservice": ["service", "micro-service"],
    "latency": ["response time", "delay"],
    "throughput": ["bandwidth", "requests per second"],
    "error": ["exception", "failure", "fault"],
    "log": ["logging", "log entry"],
    "monitor": ["monitoring", "observability", "metrics"],
    "config": ["configuration", "settings"],
    "encrypt": ["encryption", "cipher"],
    "test": ["testing", "unit test", "integration test"],
    "performance": ["perf", "speed", "efficiency"],
    "scale": ["scaling", "scalability", "horizontal scaling"],
    "replicate": ["replication", "replica"],
    "shard": ["sharding", "partition"],
    "migrate": ["migration", "data migration"],
    "backup": ["snapshot", "restore point"],
}

# Build a reverse lookup for quick expansion
_REVERSE_SYNONYMS: Dict[str, str] = {}
for _canonical, _syns in _SYNONYMS.items():
    for _syn in _syns:
        _REVERSE_SYNONYMS[_syn.lower()] = _canonical

# ---------------------------------------------------------------------------
# Constraint patterns (date ranges, categories, numeric filters)
# ---------------------------------------------------------------------------

_CONSTRAINT_PATTERNS = {
    "date_after": re.compile(
        r"\b(?:after|since|from)\s+(\d{4}[-/]\d{1,2}[-/]\d{1,2})\b", re.I
    ),
    "date_before": re.compile(
        r"\b(?:before|until|by)\s+(\d{4}[-/]\d{1,2}[-/]\d{1,2})\b", re.I
    ),
    "category": re.compile(
        r"\b(?:category|type|kind|in)\s*[:=]\s*[\"']?(\w[\w\s]*\w)[\"']?\b", re.I
    ),
    "limit": re.compile(
        r"\b(?:top|first|last|limit)\s+(\d+)\b", re.I
    ),
    "language": re.compile(
        r"\b(?:in|using|language)\s*[:=]?\s*(python|java|go|rust|javascript|typescript|c\+\+|ruby|php|swift|kotlin)\b", re.I
    ),
}

# Pattern for detecting multi-part / compound questions
_COMPOUND_SPLIT = re.compile(
    r"\b(?:and\s+also|also|additionally|moreover|furthermore)\b|[;]|\band\b(?=\s+(?:how|what|why|when|where|which|who|is|are|do|does|can|could))",
    re.I,
)


# ---------------------------------------------------------------------------
# QueryIntent dataclass
# ---------------------------------------------------------------------------

@dataclass
class QueryIntent:
    """Parsed intent, entities, and constraints from a raw query."""

    intent_type: str  # factual | procedural | comparative | exploratory | definitional
    entities: List[str] = field(default_factory=list)
    constraints: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0


# ---------------------------------------------------------------------------
# QueryUnderstanding
# ---------------------------------------------------------------------------

class QueryUnderstanding:
    """Lightweight query analysis and reformulation for retrieval pipelines."""

    def __init__(
        self,
        custom_synonyms: Optional[Dict[str, List[str]]] = None,
        custom_stop_words: Optional[Set[str]] = None,
    ) -> None:
        self._synonyms = dict(_SYNONYMS)
        self._reverse_synonyms = dict(_REVERSE_SYNONYMS)
        if custom_synonyms:
            for canonical, syns in custom_synonyms.items():
                self._synonyms[canonical.lower()] = [s.lower() for s in syns]
                for syn in syns:
                    self._reverse_synonyms[syn.lower()] = canonical.lower()

        self._stop_words = set(_STOP_WORDS)
        if custom_stop_words:
            self._stop_words |= {w.lower() for w in custom_stop_words}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze(self, query: str) -> QueryIntent:
        """Classify intent, extract entities and constraints from *query*."""
        if not query or not query.strip():
            logger.warning("Empty query received")
            return QueryIntent(intent_type="factual", confidence=0.0)

        query_clean = query.strip()

        intent_type, confidence = self._classify_intent(query_clean)
        entities = self._extract_entities(query_clean)
        constraints = self._extract_constraints(query_clean)

        intent = QueryIntent(
            intent_type=intent_type,
            entities=entities,
            constraints=constraints,
            confidence=confidence,
        )
        logger.debug("Analyzed query: %r -> %s", query_clean, intent)
        return intent

    def reformulate(self, query: str, intent: QueryIntent) -> List[str]:
        """Generate multiple reformulated queries for better recall.

        Always returns the original query first, followed by keyword-focused,
        synonym-expanded, and (for complex queries) decomposed sub-queries.
        """
        query_clean = query.strip()
        variants: List[str] = [query_clean]

        # Keyword-focused: strip stop words, keep content words
        keyword_version = self._keyword_reformulation(query_clean)
        if keyword_version and keyword_version != query_clean.lower():
            variants.append(keyword_version)

        # Synonym-expanded
        expanded = self._expand_synonyms(query_clean)
        if expanded and expanded != query_clean.lower():
            variants.append(expanded)

        # Decomposed sub-queries for complex / compound questions
        sub_queries = self._decompose(query_clean)
        for sq in sub_queries:
            sq_stripped = sq.strip()
            if sq_stripped and sq_stripped.lower() != query_clean.lower():
                variants.append(sq_stripped)

        # For comparative intents, generate per-entity queries
        if intent.intent_type == "comparative" and len(intent.entities) >= 2:
            for entity in intent.entities:
                per_entity = entity.strip()
                if per_entity and per_entity.lower() != query_clean.lower():
                    variants.append(per_entity)

        # Deduplicate while preserving order
        seen: Set[str] = set()
        unique: List[str] = []
        for v in variants:
            key = v.lower().strip()
            if key and key not in seen:
                seen.add(key)
                unique.append(v)

        logger.debug("Reformulated %r into %d variants", query_clean, len(unique))
        return unique

    def select_strategy(self, intent: QueryIntent) -> Dict[str, Any]:
        """Return retrieval parameters tuned for the given intent."""
        strategies: Dict[str, Dict[str, Any]] = {
            "factual": {
                "dense_weight": 0.7,
                "sparse_weight": 0.3,
                "score_threshold": 0.8,
                "limit": 10,
                "rerank": True,
            },
            "procedural": {
                "dense_weight": 0.5,
                "sparse_weight": 0.5,
                "score_threshold": 0.7,
                "limit": 10,
                "rerank": True,
            },
            "comparative": {
                "dense_weight": 0.6,
                "sparse_weight": 0.4,
                "score_threshold": 0.7,
                "limit": 15,
                "rerank": True,
                "per_entity_queries": True,
                "merge_results": True,
            },
            "exploratory": {
                "dense_weight": 0.5,
                "sparse_weight": 0.5,
                "score_threshold": 0.6,
                "limit": 20,
                "rerank": False,
                "diversity_bias": 0.3,
            },
            "definitional": {
                "dense_weight": 0.4,
                "sparse_weight": 0.6,
                "score_threshold": 0.75,
                "limit": 10,
                "rerank": True,
            },
        }

        strategy = dict(strategies.get(intent.intent_type, strategies["factual"]))
        strategy["intent_type"] = intent.intent_type
        strategy["confidence"] = intent.confidence

        logger.debug(
            "Selected strategy for intent=%s: %s", intent.intent_type, strategy
        )
        return strategy

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _classify_intent(self, query: str) -> tuple:
        """Return (intent_type, confidence) using keyword pattern matching."""
        scores: Dict[str, int] = {}

        for intent_type, patterns in _INTENT_PATTERNS.items():
            match_count = sum(
                1 for p in patterns if p.search(query)
            )
            if match_count > 0:
                scores[intent_type] = match_count

        if not scores:
            # Default to factual for simple queries, exploratory for longer ones
            word_count = len(query.split())
            if word_count > 8:
                return ("exploratory", 0.3)
            return ("factual", 0.3)

        # Pick the highest-scoring intent; break ties by priority
        best = max(
            scores.keys(),
            key=lambda k: (scores[k], _INTENT_PRIORITY.get(k, 0)),
        )
        total_patterns = sum(len(ps) for ps in _INTENT_PATTERNS.values())
        confidence = min(0.95, 0.5 + (scores[best] / total_patterns) * 2)

        return (best, round(confidence, 2))

    def _extract_entities(self, query: str) -> List[str]:
        """Extract key entities via quoted strings, capitalised words, and noun phrases."""
        entities: List[str] = []
        seen_lower: Set[str] = set()

        def _add(text: str) -> None:
            cleaned = text.strip().strip("\"'")
            if cleaned and cleaned.lower() not in seen_lower and cleaned.lower() not in self._stop_words:
                seen_lower.add(cleaned.lower())
                entities.append(cleaned)

        # 1. Quoted strings
        for match in re.finditer(r'["\']([^"\']{2,})["\']', query):
            _add(match.group(1))

        # 2. Capitalised words / multi-word proper nouns (skip sentence start)
        # Match sequences of capitalised words (e.g., "Google Cloud Platform")
        for match in re.finditer(r'(?<![.!?]\s)(?:^|\s)([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)', query):
            candidate = match.group(1).strip()
            # Skip if it's the very first word and looks like normal sentence start
            if match.start() == 0 and len(candidate.split()) == 1:
                continue
            _add(candidate)

        # 3. Technical terms: hyphenated compounds (e.g., "cache-invalidation")
        for match in re.finditer(r'\b(\w+-\w+(?:-\w+)*)\b', query):
            _add(match.group(1))

        # 4. Remaining content words (nouns/verbs heuristic: non-stop, 3+ chars)
        words = re.findall(r'\b[a-zA-Z]{3,}\b', query)
        for w in words:
            if w.lower() not in self._stop_words and w.lower() not in seen_lower:
                _add(w)

        return entities

    def _extract_constraints(self, query: str) -> Dict[str, Any]:
        """Pull structured constraints (dates, categories, limits) from the query."""
        constraints: Dict[str, Any] = {}
        for name, pattern in _CONSTRAINT_PATTERNS.items():
            match = pattern.search(query)
            if match:
                value = match.group(1).strip()
                # Convert numeric values
                if name == "limit":
                    constraints[name] = int(value)
                else:
                    constraints[name] = value
        return constraints

    def _keyword_reformulation(self, query: str) -> str:
        """Strip stop words, return space-joined content words."""
        words = re.findall(r'\b[a-zA-Z0-9]+\b', query.lower())
        keywords = [w for w in words if w not in self._stop_words and len(w) > 1]
        return " ".join(keywords)

    def _expand_synonyms(self, query: str) -> str:
        """Expand known terms with synonyms for broader recall."""
        words = query.lower().split()
        expanded_parts: List[str] = []

        i = 0
        while i < len(words):
            matched = False
            # Try multi-word synonym lookup (up to 3 words)
            for n in (3, 2):
                if i + n <= len(words):
                    phrase = " ".join(words[i:i + n])
                    if phrase in self._reverse_synonyms:
                        canonical = self._reverse_synonyms[phrase]
                        expanded_parts.append(f"{phrase} {canonical}")
                        i += n
                        matched = True
                        break
                    if phrase in self._synonyms:
                        extras = self._synonyms[phrase][:2]  # cap expansion
                        expanded_parts.append(f"{phrase} {' '.join(extras)}")
                        i += n
                        matched = True
                        break
            if not matched:
                word = words[i]
                if word in self._synonyms:
                    extras = self._synonyms[word][:2]
                    expanded_parts.append(f"{word} {' '.join(extras)}")
                elif word in self._reverse_synonyms:
                    canonical = self._reverse_synonyms[word]
                    expanded_parts.append(f"{word} {canonical}")
                else:
                    expanded_parts.append(word)
                i += 1

        return " ".join(expanded_parts)

    def _decompose(self, query: str) -> List[str]:
        """Split compound questions into independent sub-queries."""
        parts = _COMPOUND_SPLIT.split(query)
        # Only return sub-queries if we actually split into multiple pieces
        if len(parts) <= 1:
            return []
        return [p.strip() for p in parts if p and len(p.strip().split()) >= 3]
