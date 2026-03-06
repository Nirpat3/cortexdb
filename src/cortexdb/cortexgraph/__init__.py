"""CortexGraph™ - Next-Gen Customer Intelligence (DOC-020)

4 Layers:
  Layer 1: Identity Resolution (Deterministic + Probabilistic + AI)
  Layer 2: Event Database (Real-Time Streaming + Time-Series Analytics)
  Layer 3: Relationship Graph (Customer <-> Product <-> Store <-> Campaign <-> Agent)
  Layer 4: Behavioral Profile (RFM + Churn + LTV + Embeddings + Health Score)

Replaces: Segment ($120K/yr) + mParticle ($200K/yr) + Amperity ($500K/yr)
"""

from cortexdb.cortexgraph.identity import IdentityResolver
from cortexdb.cortexgraph.events import EventTracker
from cortexdb.cortexgraph.relationships import RelationshipGraph
from cortexdb.cortexgraph.profiles import BehavioralProfiler
from cortexdb.cortexgraph.insights import CortexGraphInsights

__all__ = ["IdentityResolver", "EventTracker", "RelationshipGraph",
           "BehavioralProfiler", "CortexGraphInsights"]
