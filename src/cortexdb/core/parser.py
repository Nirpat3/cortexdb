"""CortexQL Parser (DOC-018 Gap G16)

Extends SQL with CortexDB-specific operations:
  FIND SIMILAR TO <text> IN <collection>    -> VectorCore
  TRAVERSE <start> -> <end> VIA <edges>     -> GraphCore
  SUBSCRIBE TO <event>                      -> StreamCore
  COMMIT TO LEDGER <entry>                  -> ImmutableCore
  HINT(cache_first | skip_semantic | force_refresh)

v2.0: Pattern-based routing (regex).
v3.0: ANTLR4-based full parser (future).
"""

import re
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("cortexdb.core.parser")


class QueryType(Enum):
    SQL = "sql"                  # Standard SQL -> RelationalCore
    VECTOR_SEARCH = "vector"     # FIND SIMILAR -> VectorCore
    GRAPH_TRAVERSE = "graph"     # TRAVERSE -> GraphCore
    STREAM_SUBSCRIBE = "stream"  # SUBSCRIBE TO -> StreamCore
    LEDGER_COMMIT = "ledger"     # COMMIT TO LEDGER -> ImmutableCore
    TEMPORAL = "temporal"        # Time-bucketed -> TemporalCore
    MULTI_ENGINE = "multi"       # Cross-engine -> Bridge
    CACHE_ONLY = "cache"         # HINT(cache_first) -> ReadCascade only


@dataclass
class ParsedQuery:
    original: str
    query_type: QueryType = QueryType.SQL
    engine: str = "relational"
    sub_queries: List[Dict] = field(default_factory=list)
    hints: List[str] = field(default_factory=list)
    collection: str = ""
    parameters: Dict = field(default_factory=dict)

    @property
    def is_multi_engine(self) -> bool:
        return self.query_type == QueryType.MULTI_ENGINE or len(self.sub_queries) > 1


# CortexQL extension patterns
PATTERNS = {
    "FIND_SIMILAR": re.compile(
        r"FIND\s+SIMILAR\s+TO\s+['\"](.+?)['\"]\s+IN\s+(\w+)",
        re.IGNORECASE),
    "TRAVERSE": re.compile(
        r"TRAVERSE\s+['\"]?(\w+)['\"]?\s*->\s*['\"]?(\w+)['\"]?\s+VIA\s+(\w+)",
        re.IGNORECASE),
    "SUBSCRIBE": re.compile(
        r"SUBSCRIBE\s+TO\s+['\"]?(\w+)['\"]?",
        re.IGNORECASE),
    "COMMIT_LEDGER": re.compile(
        r"COMMIT\s+TO\s+LEDGER\s+(.+)",
        re.IGNORECASE),
    "HINT": re.compile(
        r"HINT\s*\(\s*(\w+)\s*\)",
        re.IGNORECASE),
    "TIME_BUCKET": re.compile(
        r"time_bucket\s*\(", re.IGNORECASE),
    "HYPERTABLE": re.compile(
        r"FROM\s+(heartbeats|agent_metrics|query_metrics)",
        re.IGNORECASE),
}


class CortexQLParser:
    """Pattern-based CortexQL parser (v2.0).

    Analyzes query text, identifies CortexQL extensions,
    and routes sub-queries to appropriate engines.
    """

    def parse(self, query: str) -> ParsedQuery:
        """Parse a CortexQL query and determine routing."""
        parsed = ParsedQuery(original=query)

        # Extract hints
        hints = PATTERNS["HINT"].findall(query)
        parsed.hints = [h.lower() for h in hints]
        if "cache_first" in parsed.hints:
            parsed.query_type = QueryType.CACHE_ONLY
            return parsed

        # Check for CortexQL extensions
        sim_match = PATTERNS["FIND_SIMILAR"].search(query)
        if sim_match:
            parsed.query_type = QueryType.VECTOR_SEARCH
            parsed.engine = "vector"
            parsed.parameters["search_text"] = sim_match.group(1)
            parsed.collection = sim_match.group(2)
            return parsed

        trav_match = PATTERNS["TRAVERSE"].search(query)
        if trav_match:
            parsed.query_type = QueryType.GRAPH_TRAVERSE
            parsed.engine = "graph"
            parsed.parameters["start"] = trav_match.group(1)
            parsed.parameters["end"] = trav_match.group(2)
            parsed.parameters["edge_type"] = trav_match.group(3)
            return parsed

        sub_match = PATTERNS["SUBSCRIBE"].search(query)
        if sub_match:
            parsed.query_type = QueryType.STREAM_SUBSCRIBE
            parsed.engine = "stream"
            parsed.parameters["event_type"] = sub_match.group(1)
            return parsed

        ledger_match = PATTERNS["COMMIT_LEDGER"].search(query)
        if ledger_match:
            parsed.query_type = QueryType.LEDGER_COMMIT
            parsed.engine = "immutable"
            parsed.parameters["entry"] = ledger_match.group(1).strip()
            return parsed

        # Check for temporal queries
        if (PATTERNS["TIME_BUCKET"].search(query) or
                PATTERNS["HYPERTABLE"].search(query)):
            parsed.query_type = QueryType.TEMPORAL
            parsed.engine = "temporal"
            return parsed

        # Default: standard SQL -> RelationalCore
        parsed.query_type = QueryType.SQL
        parsed.engine = "relational"
        return parsed

    def route(self, query: str) -> Tuple[str, str, Dict]:
        """Parse and return (engine_name, clean_query, parameters).

        Convenience method for the Router.
        """
        parsed = self.parse(query)

        # Strip HINT() from query before sending to engine
        clean = PATTERNS["HINT"].sub("", query).strip()

        return parsed.engine, clean, parsed.parameters
