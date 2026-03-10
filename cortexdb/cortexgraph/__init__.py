"""CortexGraph — Customer Intelligence Layer

4 Layers:
  Layer 1: Identity Resolution (Deterministic + Probabilistic)
  Layer 2: Event Database (Real-Time Streaming + Time-Series Analytics)
  Layer 3: Relationship Graph (Customer <-> Product <-> Store <-> Campaign <-> Agent)
  Layer 4: Behavioral Profile (RFM + Churn + LTV + Embeddings + Health Score)
"""

from cortexdb.cortexgraph.identity import IdentityResolver
from cortexdb.cortexgraph.events import EventTracker
from cortexdb.cortexgraph.relationships import RelationshipGraph
from cortexdb.cortexgraph.profiles import BehavioralProfiler
from cortexdb.cortexgraph.insights import CortexGraphInsights

__all__ = ["IdentityResolver", "EventTracker", "RelationshipGraph",
           "BehavioralProfiler", "CortexGraphInsights"]
