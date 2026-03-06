"""Layer 3: Relationship Graph (DOC-020 Section 3.3)

Graph nodes: Customer, Product, Store, Campaign, Agent, Vendor, Household
Edges: PURCHASED, VISITED, REFERRED, TARGETED, SERVED, SUPPLIED_BY, etc.

Uses GraphCore (Apache AGE on PostgreSQL) for Cypher-style traversal.
Falls back to SQL JOIN queries when AGE is not available.
"""

import logging
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger("cortexdb.cortexgraph.relationships")

# Node types and their primary key fields
NODE_TYPES = {
    "Customer": "customer_id",
    "Product": "product_id",
    "Store": "store_id",
    "Campaign": "campaign_id",
    "Agent": "agent_id",
    "Vendor": "vendor_id",
    "Household": "household_id",
}

# Valid relationship types with (source_type, target_type)
EDGE_TYPES = {
    "PURCHASED": ("Customer", "Product"),
    "VISITED": ("Customer", "Store"),
    "REFERRED": ("Customer", "Customer"),
    "MEMBER_OF": ("Customer", "Household"),
    "TARGETED": ("Campaign", "Customer"),
    "PROMOTED": ("Campaign", "Product"),
    "SERVED": ("Agent", "Customer"),
    "SUPPLIED_BY": ("Product", "Vendor"),
    "STOCKED_AT": ("Product", "Store"),
    "RESPONDED_TO": ("Customer", "Campaign"),
    "SIMILAR_TO": ("Product", "Product"),
    "COMPLEMENTARY_TO": ("Product", "Product"),
    "EMPLOYS": ("Store", "Agent"),
    "INCLUDES": ("Household", "Customer"),
}


class RelationshipGraph:
    """Customer Relationship Graph built on GraphCore.

    Provides:
      - Node/edge CRUD
      - Multi-hop traversal (collaborative filtering, influence mapping)
      - Cross-sell recommendations via graph patterns
      - Attribution analysis (Campaign -> Customer -> Purchase)
    """

    def __init__(self, engines: Dict[str, Any] = None):
        self.engines = engines or {}
        self._nodes: Dict[str, Dict[str, Dict]] = {t: {} for t in NODE_TYPES}
        self._edges: List[Dict] = []
        self._edge_count = 0

    async def add_node(self, node_type: str, node_id: str,
                       properties: Dict = None,
                       tenant_id: Optional[str] = None) -> Dict:
        """Add or update a graph node."""
        if node_type not in NODE_TYPES:
            raise ValueError(f"Unknown node type: {node_type}. Valid: {list(NODE_TYPES.keys())}")

        node = {"id": node_id, "type": node_type,
                "properties": properties or {},
                "tenant_id": tenant_id,
                "created_at": time.time()}
        self._nodes[node_type][node_id] = node

        # Persist to GraphCore
        if "graph" in self.engines:
            try:
                pk = NODE_TYPES[node_type]
                props = {pk: node_id, **(properties or {})}
                if tenant_id:
                    props["tenant_id"] = tenant_id
                await self.engines["graph"].add_vertex(node_type, props)
            except Exception as e:
                logger.warning(f"GraphCore add_node error: {e}")

        return node

    async def add_edge(self, src_type: str, src_id: str,
                       relationship: str,
                       tgt_type: str, tgt_id: str,
                       properties: Dict = None,
                       tenant_id: Optional[str] = None) -> Dict:
        """Add a relationship edge between two nodes."""
        self._edge_count += 1

        edge = {
            "source": {"type": src_type, "id": src_id},
            "target": {"type": tgt_type, "id": tgt_id},
            "relationship": relationship,
            "properties": properties or {},
            "tenant_id": tenant_id,
            "created_at": time.time(),
        }
        self._edges.append(edge)

        # Ensure nodes exist
        if src_id not in self._nodes.get(src_type, {}):
            await self.add_node(src_type, src_id, tenant_id=tenant_id)
        if tgt_id not in self._nodes.get(tgt_type, {}):
            await self.add_node(tgt_type, tgt_id, tenant_id=tenant_id)

        # Persist to GraphCore
        if "graph" in self.engines:
            try:
                await self.engines["graph"].add_edge(
                    src_type, src_id, relationship, tgt_type, tgt_id,
                    properties or {})
            except Exception as e:
                logger.warning(f"GraphCore add_edge error: {e}")

        return edge

    async def traverse(self, start_type: str, start_id: str,
                       relationship: str,
                       depth: int = 1,
                       tenant_id: Optional[str] = None) -> List[Dict]:
        """Traverse graph from a starting node along a relationship type."""
        # GraphCore Cypher query
        if "graph" in self.engines:
            try:
                cypher = (
                    f"MATCH (s:{start_type})-[:{relationship}*1..{depth}]->(t) "
                    f"WHERE s.{NODE_TYPES.get(start_type, 'id')} = '{start_id}' "
                    f"RETURN t")
                return await self.engines["graph"].execute(cypher) or []
            except Exception as e:
                logger.warning(f"GraphCore traverse error: {e}")

        # Fallback: in-memory traversal
        results = []
        for edge in self._edges:
            if (edge["source"]["type"] == start_type and
                    edge["source"]["id"] == start_id and
                    edge["relationship"] == relationship):
                if tenant_id and edge.get("tenant_id") != tenant_id:
                    continue
                results.append({
                    "node_type": edge["target"]["type"],
                    "node_id": edge["target"]["id"],
                    "relationship": relationship,
                    "properties": edge["properties"],
                })
        return results

    async def get_customer_connections(self, customer_id: str,
                                       tenant_id: Optional[str] = None) -> Dict:
        """Get all connections for a customer (products, stores, campaigns, agents)."""
        connections = {}
        for rel in ["PURCHASED", "VISITED", "RESPONDED_TO", "MEMBER_OF"]:
            results = await self.traverse("Customer", customer_id, rel,
                                          tenant_id=tenant_id)
            if results:
                connections[rel.lower()] = results

        # Agents that served this customer (reverse edge)
        agents = []
        for edge in self._edges:
            if (edge["relationship"] == "SERVED" and
                    edge["target"]["id"] == customer_id):
                agents.append({
                    "agent_id": edge["source"]["id"],
                    "properties": edge["properties"],
                })
        if agents:
            connections["served_by"] = agents

        return connections

    async def recommend_products(self, customer_id: str,
                                  limit: int = 5,
                                  tenant_id: Optional[str] = None) -> List[Dict]:
        """Collaborative filtering: products bought by similar customers.

        Pattern: (Customer)-[:PURCHASED]->(Product)<-[:PURCHASED]-(Similar)-[:PURCHASED]->(Rec)
        WHERE NOT (Customer)-[:PURCHASED]->(Rec)
        """
        # Get products this customer purchased
        purchased = await self.traverse("Customer", customer_id, "PURCHASED",
                                        tenant_id=tenant_id)
        purchased_ids = {p["node_id"] for p in purchased}

        if not purchased_ids:
            return []

        # Find other customers who purchased the same products
        similar_customers = set()
        recommendations: Dict[str, int] = {}

        for edge in self._edges:
            if (edge["relationship"] == "PURCHASED" and
                    edge["target"]["id"] in purchased_ids and
                    edge["source"]["id"] != customer_id):
                similar_customers.add(edge["source"]["id"])

        # Get products those customers bought (that this customer hasn't)
        for edge in self._edges:
            if (edge["relationship"] == "PURCHASED" and
                    edge["source"]["id"] in similar_customers and
                    edge["target"]["id"] not in purchased_ids):
                pid = edge["target"]["id"]
                recommendations[pid] = recommendations.get(pid, 0) + 1

        # Sort by frequency (more similar customers bought it = stronger signal)
        sorted_recs = sorted(recommendations.items(), key=lambda x: x[1], reverse=True)
        return [{"product_id": pid, "score": count,
                 "similar_buyers": count}
                for pid, count in sorted_recs[:limit]]

    async def campaign_attribution(self, campaign_id: str,
                                    tenant_id: Optional[str] = None) -> Dict:
        """Attribution: Campaign -> Targeted Customers -> Purchases."""
        targeted = 0
        purchased = 0
        revenue = 0.0

        for edge in self._edges:
            if (edge["relationship"] == "TARGETED" and
                    edge["source"]["id"] == campaign_id):
                targeted += 1
                cust_id = edge["target"]["id"]
                # Check if this customer purchased after being targeted
                for e2 in self._edges:
                    if (e2["relationship"] == "PURCHASED" and
                            e2["source"]["id"] == cust_id and
                            e2.get("created_at", 0) >= edge.get("created_at", 0)):
                        purchased += 1
                        revenue += (e2["properties"] or {}).get("amount", 0)

        return {
            "campaign_id": campaign_id,
            "customers_targeted": targeted,
            "customers_purchased": purchased,
            "conversion_rate": round(purchased / max(targeted, 1) * 100, 1),
            "revenue": round(revenue, 2),
        }

    def get_stats(self) -> Dict:
        node_counts = {t: len(nodes) for t, nodes in self._nodes.items() if nodes}
        return {
            "total_nodes": sum(node_counts.values()),
            "total_edges": self._edge_count,
            "nodes_by_type": node_counts,
        }
