"""AI Insights Engine (DOC-020 Section 4)

MCP tools for agents to query customer intelligence:
  cortexgraph.customer_360    - Complete customer view (all 4 layers)
  cortexgraph.identify        - Identity resolution
  cortexgraph.track           - Track customer event
  cortexgraph.similar         - Find similar customers
  cortexgraph.churn_risk      - Get churn risk customers
  cortexgraph.recommend       - Product recommendations
  cortexgraph.attribution     - Campaign attribution
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("cortexdb.cortexgraph.insights")


class CortexGraphInsights:
    """AI Insights Engine - agents query customer intelligence via MCP tools.

    Provides customer_360: identity + events + relationships + profile
    in a single call, enabling PRIME to reason about customers.
    """

    def __init__(self, identity_resolver=None, event_tracker=None,
                 relationship_graph=None, profiler=None):
        self.identity = identity_resolver
        self.events = event_tracker
        self.graph = relationship_graph
        self.profiler = profiler

    async def customer_360(self, customer_id: str,
                            tenant_id: Optional[str] = None) -> Dict:
        """Complete customer intelligence - all 4 layers in one call.

        Returns: identity + recent events + connections + behavioral profile.
        This is the primary MCP tool for agent customer reasoning.
        """
        result = {"customer_id": customer_id, "layers": {}}

        # Layer 1: Identity
        if self.identity:
            customer = self.identity._customers.get(customer_id)
            if customer:
                result["layers"]["identity"] = {
                    "name": customer.canonical_name,
                    "email": customer.canonical_email,
                    "phone": customer.canonical_phone,
                    "identifiers": len(customer.identifiers),
                    "merge_count": customer.merge_count,
                    "first_seen": customer.first_seen_at,
                }

        # Layer 2: Recent Events
        if self.events:
            recent = await self.events.query_events(
                customer_id, days=30, tenant_id=tenant_id, limit=20)
            event_counts = await self.events.get_event_counts(
                customer_id, days=90)
            result["layers"]["events"] = {
                "recent_30d": recent,
                "counts_90d": event_counts,
            }

        # Layer 3: Relationships
        if self.graph:
            connections = await self.graph.get_customer_connections(
                customer_id, tenant_id)
            result["layers"]["relationships"] = connections

        # Layer 4: Behavioral Profile
        if self.profiler:
            profile = await self.profiler.get_profile(customer_id, tenant_id)
            result["layers"]["profile"] = profile

        return result

    async def find_similar_customers(self, customer_id: str,
                                      limit: int = 50,
                                      tenant_id: Optional[str] = None) -> List[Dict]:
        """Find customers with similar behavioral patterns (lookalike)."""
        # TODO: Use VectorCore behavioral embeddings when available
        # For now: find customers in same segments
        if not self.profiler:
            return []

        target_profile = await self.profiler.get_profile(customer_id, tenant_id)
        if not target_profile:
            return []

        target_segments = set(target_profile.get("segments", []))
        results = []

        for cid, profile in self.profiler._profiles.items():
            if cid == customer_id:
                continue
            if tenant_id and profile.tenant_id != tenant_id:
                continue
            overlap = len(target_segments & set(profile.segments))
            if overlap > 0:
                results.append({
                    "customer_id": cid,
                    "similarity_score": overlap / max(len(target_segments), 1),
                    "shared_segments": list(target_segments & set(profile.segments)),
                    "health_score": profile.health_score,
                })

        results.sort(key=lambda x: x["similarity_score"], reverse=True)
        return results[:limit]

    async def get_churn_risk_customers(self, threshold: float = 0.7,
                                        tenant_id: Optional[str] = None,
                                        limit: int = 50) -> List[Dict]:
        """Get customers with high churn probability."""
        at_risk = []
        for cid, profile in self.profiler._profiles.items():
            if tenant_id and profile.tenant_id != tenant_id:
                continue
            if profile.churn_probability >= threshold:
                at_risk.append({
                    "customer_id": cid,
                    "churn_probability": profile.churn_probability,
                    "health_score": profile.health_score,
                    "recency_days": profile.recency_days,
                    "rfm_segment": profile.rfm_segment,
                })
        at_risk.sort(key=lambda x: x["churn_probability"], reverse=True)
        return at_risk[:limit]

    async def recommend_products(self, customer_id: str,
                                  limit: int = 5,
                                  tenant_id: Optional[str] = None) -> List[Dict]:
        """Product recommendations via collaborative filtering."""
        if not self.graph:
            return []
        return await self.graph.recommend_products(
            customer_id, limit, tenant_id)

    async def campaign_attribution(self, campaign_id: str,
                                    tenant_id: Optional[str] = None) -> Dict:
        """Campaign -> Customer -> Purchase attribution analysis."""
        if not self.graph:
            return {}
        return await self.graph.campaign_attribution(campaign_id, tenant_id)

    def get_mcp_tools(self) -> List[Dict]:
        """Return MCP tool definitions for CortexGraph."""
        return [
            {"name": "cortexgraph.customer_360",
             "description": "Get complete customer intelligence: identity, events, relationships, and behavioral profile in one call.",
             "inputSchema": {"type": "object", "properties": {
                 "customer_id": {"type": "string"}}, "required": ["customer_id"]}},
            {"name": "cortexgraph.similar_customers",
             "description": "Find customers with similar behavioral patterns (lookalike targeting).",
             "inputSchema": {"type": "object", "properties": {
                 "customer_id": {"type": "string"},
                 "limit": {"type": "integer", "default": 50}}, "required": ["customer_id"]}},
            {"name": "cortexgraph.churn_risk",
             "description": "Get customers at risk of churning (probability > threshold).",
             "inputSchema": {"type": "object", "properties": {
                 "threshold": {"type": "number", "default": 0.7},
                 "limit": {"type": "integer", "default": 50}}}},
            {"name": "cortexgraph.recommend_products",
             "description": "Product recommendations via collaborative filtering graph patterns.",
             "inputSchema": {"type": "object", "properties": {
                 "customer_id": {"type": "string"},
                 "limit": {"type": "integer", "default": 5}}, "required": ["customer_id"]}},
            {"name": "cortexgraph.attribution",
             "description": "Campaign attribution: trace Campaign -> Customer -> Purchase path.",
             "inputSchema": {"type": "object", "properties": {
                 "campaign_id": {"type": "string"}}, "required": ["campaign_id"]}},
        ]

    def get_stats(self) -> Dict:
        return {
            "identity": self.identity.get_stats() if self.identity else {},
            "events": self.events.get_stats() if self.events else {},
            "graph": self.graph.get_stats() if self.graph else {},
            "profiles": self.profiler.get_stats() if self.profiler else {},
        }
