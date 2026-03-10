"""Layer 1: Identity Resolution (DOC-020 Section 3.1)

Deterministic: exact match on email, phone, loyalty_id, device_id
Probabilistic: VectorCore cosine similarity > 0.92 = likely same person
Merge: unify two customer records, audit in ImmutableCore
Anonymous-to-Known: retroactively attribute anonymous events
"""

import time
import uuid
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger("cortexdb.cortexgraph.identity")


class IdentifierType(Enum):
    EMAIL = "email"
    PHONE = "phone"
    DEVICE_ID = "device_id"
    LOYALTY_ID = "loyalty_id"
    COOKIE = "cookie"
    IP = "ip"
    SOCIAL_HANDLE = "social_handle"
    POS_CUSTOMER_ID = "pos_customer_id"
    PAYMENT_TOKEN = "payment_token"


@dataclass
class CustomerIdentity:
    customer_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    canonical_name: str = ""
    canonical_email: str = ""
    canonical_phone: str = ""
    identifiers: List[Dict] = field(default_factory=list)
    merge_count: int = 0
    confidence_score: float = 1.0
    status: str = "active"
    tenant_id: Optional[str] = None
    first_seen_at: float = field(default_factory=time.time)
    last_seen_at: float = field(default_factory=time.time)


@dataclass
class IdentityMatch:
    customer_id: str
    match_type: str  # "deterministic" or "probabilistic"
    confidence: float
    matched_on: str  # which identifier matched
    matched_value: str


class IdentityResolver:
    """Customer Identity Resolution across all touchpoints.

    Flow:
    1. Receive identifier (email, phone, device_id, etc.)
    2. Deterministic check: exact match in customer_identifiers
    3. If no match: probabilistic check via VectorCore similarity
    4. If match found: link identifier to existing customer
    5. If no match: create new customer record
    6. If multiple matches: merge candidates
    """

    SIMILARITY_THRESHOLD = 0.92
    REVIEW_THRESHOLD = 0.85

    def __init__(self, engines: Dict[str, Any] = None, embedding=None):
        self.engines = engines or {}
        self.embedding = embedding
        self._customers: Dict[str, CustomerIdentity] = {}
        self._identifier_index: Dict[str, str] = {}  # "type:value" -> customer_id
        self._resolve_count = 0
        self._merge_count = 0

    async def identify(self, identifiers: Dict[str, str],
                       tenant_id: Optional[str] = None,
                       attributes: Optional[Dict] = None) -> Dict:
        """Resolve one or more identifiers to a customer_id.

        Args:
            identifiers: {type: value} e.g. {"email": "john@acme.com", "phone": "+1555..."}
            tenant_id: Tenant scope
            attributes: Optional {name, city, etc.} for probabilistic matching

        Returns:
            {customer_id, is_new, match_type, confidence, identifiers_linked}
        """
        self._resolve_count += 1

        # Step 1: Deterministic resolution - exact match
        for id_type, id_value in identifiers.items():
            match = await self._deterministic_match(id_type, id_value, tenant_id)
            if match:
                # Link any new identifiers to existing customer
                linked = await self._link_identifiers(
                    match.customer_id, identifiers, tenant_id)
                return {
                    "customer_id": match.customer_id,
                    "is_new": False,
                    "match_type": "deterministic",
                    "confidence": match.confidence,
                    "matched_on": match.matched_on,
                    "identifiers_linked": linked,
                }

        # Step 2: Probabilistic resolution - vector similarity
        if self.embedding and attributes:
            prob_match = await self._probabilistic_match(attributes, tenant_id)
            if prob_match and prob_match.confidence >= self.SIMILARITY_THRESHOLD:
                linked = await self._link_identifiers(
                    prob_match.customer_id, identifiers, tenant_id)
                return {
                    "customer_id": prob_match.customer_id,
                    "is_new": False,
                    "match_type": "probabilistic",
                    "confidence": prob_match.confidence,
                    "identifiers_linked": linked,
                }
            elif prob_match and prob_match.confidence >= self.REVIEW_THRESHOLD:
                # Needs human review
                logger.info(f"Identity match needs review: {prob_match.confidence:.2f}")

        # Step 3: No match - create new customer
        customer = await self._create_customer(identifiers, attributes, tenant_id)
        return {
            "customer_id": customer.customer_id,
            "is_new": True,
            "match_type": "new",
            "confidence": 1.0,
            "identifiers_linked": len(identifiers),
        }

    async def _deterministic_match(self, id_type: str, id_value: str,
                                   tenant_id: Optional[str]) -> Optional[IdentityMatch]:
        """Exact match on identifier type + value."""
        key = f"{tenant_id or ''}:{id_type}:{id_value}"

        # In-memory index
        customer_id = self._identifier_index.get(key)
        if customer_id:
            return IdentityMatch(
                customer_id=customer_id, match_type="deterministic",
                confidence=1.0, matched_on=id_type, matched_value=id_value)

        # RelationalCore lookup
        if "relational" in self.engines:
            try:
                rows = await self.engines["relational"].execute(
                    "SELECT customer_id FROM customer_identifiers "
                    "WHERE identifier_type = $1 AND identifier_value = $2 "
                    "AND (tenant_id = $3 OR $3 IS NULL) LIMIT 1",
                    [id_type, id_value, tenant_id])
                if rows:
                    cid = str(rows[0]["customer_id"])
                    self._identifier_index[key] = cid
                    return IdentityMatch(
                        customer_id=cid, match_type="deterministic",
                        confidence=1.0, matched_on=id_type, matched_value=id_value)
            except Exception as e:
                logger.warning(f"Deterministic match DB error: {e}")

        return None

    async def _probabilistic_match(self, attributes: Dict,
                                   tenant_id: Optional[str]) -> Optional[IdentityMatch]:
        """Vector similarity match on customer attributes."""
        if not self.embedding or "vector" not in self.engines:
            return None

        # Build attribute text for embedding
        attr_text = " ".join(f"{k}:{v}" for k, v in sorted(attributes.items()) if v)
        query_vec = self.embedding.embed(attr_text)

        try:
            collection = f"tenant_{tenant_id}_customers" if tenant_id else "customer_identities"
            results = await self.engines["vector"].search_similar(
                collection=collection, query_vector=query_vec,
                threshold=self.REVIEW_THRESHOLD, limit=1)
            if results:
                return IdentityMatch(
                    customer_id=results[0]["payload"]["customer_id"],
                    match_type="probabilistic",
                    confidence=results[0]["score"],
                    matched_on="vector_similarity",
                    matched_value=attr_text[:100])
        except Exception as e:
            logger.warning(f"Probabilistic match error: {e}")

        return None

    async def _create_customer(self, identifiers: Dict[str, str],
                               attributes: Optional[Dict],
                               tenant_id: Optional[str]) -> CustomerIdentity:
        """Create a new customer record with initial identifiers."""
        customer = CustomerIdentity(
            canonical_email=identifiers.get("email", ""),
            canonical_phone=identifiers.get("phone", ""),
            canonical_name=(attributes or {}).get("name", ""),
            tenant_id=tenant_id,
        )

        # Store in memory
        self._customers[customer.customer_id] = customer

        # Index identifiers
        for id_type, id_value in identifiers.items():
            key = f"{tenant_id or ''}:{id_type}:{id_value}"
            self._identifier_index[key] = customer.customer_id
            customer.identifiers.append({
                "type": id_type, "value": id_value,
                "source": "identity_resolver", "confidence": 1.0,
            })

        # Persist to RelationalCore
        if "relational" in self.engines:
            try:
                await self.engines["relational"].execute(
                    "INSERT INTO customers (customer_id, canonical_name, canonical_email, "
                    "canonical_phone, tenant_id) VALUES ($1, $2, $3, $4, $5)",
                    [customer.customer_id, customer.canonical_name,
                     customer.canonical_email, customer.canonical_phone, tenant_id])

                for id_type, id_value in identifiers.items():
                    await self.engines["relational"].execute(
                        "INSERT INTO customer_identifiers "
                        "(customer_id, identifier_type, identifier_value, source, "
                        "confidence, tenant_id) VALUES ($1, $2, $3, $4, $5, $6)",
                        [customer.customer_id, id_type, id_value,
                         "identity_resolver", 1.0, tenant_id])
            except Exception as e:
                logger.warning(f"Customer persist error: {e}")

        logger.info(f"New customer created: {customer.customer_id}")
        return customer

    async def _link_identifiers(self, customer_id: str,
                                identifiers: Dict[str, str],
                                tenant_id: Optional[str]) -> int:
        """Link new identifiers to an existing customer."""
        linked = 0
        for id_type, id_value in identifiers.items():
            key = f"{tenant_id or ''}:{id_type}:{id_value}"
            if key not in self._identifier_index:
                self._identifier_index[key] = customer_id
                linked += 1
        return linked

    async def merge(self, canonical_id: str, duplicate_id: str,
                    reason: str = "manual") -> Dict:
        """Merge two customer records into one."""
        self._merge_count += 1

        # Move all identifiers from duplicate to canonical
        keys_to_update = []
        for key, cid in self._identifier_index.items():
            if cid == duplicate_id:
                keys_to_update.append(key)
        for key in keys_to_update:
            self._identifier_index[key] = canonical_id

        # Audit in ImmutableCore
        if "immutable" in self.engines:
            try:
                await self.engines["immutable"].write("audit", {
                    "entry_type": "CUSTOMER_MERGE",
                    "canonical_id": canonical_id,
                    "duplicate_id": duplicate_id,
                    "reason": reason,
                    "identifiers_moved": len(keys_to_update),
                }, actor="identity_resolver")
            except Exception:
                pass

        logger.info(f"Customer merged: {duplicate_id} -> {canonical_id}")
        return {"canonical_id": canonical_id, "merged_id": duplicate_id,
                "identifiers_moved": len(keys_to_update)}

    def get_stats(self) -> Dict:
        return {
            "total_customers": len(self._customers),
            "total_identifiers": len(self._identifier_index),
            "resolves": self._resolve_count,
            "merges": self._merge_count,
        }
