"""Layer 2: Event Database (DOC-020 Section 3.2)

Real-time event tracking via StreamCore + TemporalCore.
Event types: Transaction, Behavioral, Communication, Agent, External, Lifecycle.
"""

import time
import uuid
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("cortexdb.cortexgraph.events")


@dataclass
class CustomerEvent:
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    customer_id: str = ""
    event_type: str = ""
    properties: Dict = field(default_factory=dict)
    source: str = ""
    session_id: str = ""
    channel: str = ""
    tenant_id: Optional[str] = None
    timestamp: float = field(default_factory=time.time)


# Auto-create graph edges from these event types
EVENT_TO_EDGE = {
    "purchase_completed": ("Customer", "PURCHASED", "Product", "product_id"),
    "store_visited": ("Customer", "VISITED", "Store", "store_id"),
    "campaign_responded": ("Customer", "RESPONDED_TO", "Campaign", "campaign_id"),
    "agent_interaction": ("Agent", "SERVED", "Customer", "agent_id"),
    "referral_made": ("Customer", "REFERRED", "Customer", "referred_customer_id"),
}


class EventTracker:
    """Real-time event ingestion and analytics.

    Events flow: SDK/API -> StreamCore (real-time) -> TemporalCore (time-series)
    Auto-creates graph edges for purchase, visit, campaign events.
    """

    def __init__(self, engines: Dict[str, Any] = None,
                 identity_resolver=None, relationship_graph=None):
        self.engines = engines or {}
        self.identity_resolver = identity_resolver
        self.relationship_graph = relationship_graph
        self._event_count = 0
        self._events_buffer: List[CustomerEvent] = []

    async def track(self, customer_id: str, event_type: str,
                    properties: Dict = None, source: str = "api",
                    session_id: str = "", channel: str = "",
                    tenant_id: Optional[str] = None) -> Dict:
        """Track a customer event.

        Writes to:
          - StreamCore: real-time event stream
          - TemporalCore: time-series storage
          - GraphCore: auto-creates edges for purchase/visit events
          - ImmutableCore: financial events (purchase, refund) get audit trail
        """
        self._event_count += 1
        event = CustomerEvent(
            customer_id=customer_id, event_type=event_type,
            properties=properties or {}, source=source,
            session_id=session_id, channel=channel,
            tenant_id=tenant_id)

        results = {"event_id": event.event_id, "engines": {}}

        # StreamCore: real-time event
        if "stream" in self.engines:
            try:
                stream_key = f"events:{event_type}"
                if tenant_id:
                    stream_key = f"tenant:{tenant_id}:{stream_key}"
                await self.engines["stream"].publish(stream_key, {
                    "event_id": event.event_id,
                    "customer_id": customer_id,
                    "event_type": event_type,
                    "properties": properties or {},
                    "timestamp": event.timestamp,
                })
                results["engines"]["stream"] = "published"
            except Exception as e:
                results["engines"]["stream"] = f"error: {e}"

        # TemporalCore: time-series
        if "temporal" in self.engines:
            try:
                await self.engines["temporal"].write("event", {
                    "time": event.timestamp,
                    "customer_id": customer_id,
                    "event_type": event_type,
                    "properties": properties or {},
                    "source": source,
                    "session_id": session_id,
                    "channel": channel,
                    "tenant_id": tenant_id,
                }, actor="event_tracker")
                results["engines"]["temporal"] = "stored"
            except Exception as e:
                results["engines"]["temporal"] = f"error: {e}"

        # ImmutableCore: financial events
        if event_type in ("purchase_completed", "refund_issued", "payment_failed"):
            if "immutable" in self.engines:
                try:
                    await self.engines["immutable"].write("audit", {
                        "entry_type": f"FINANCIAL_{event_type.upper()}",
                        "customer_id": customer_id,
                        "amount": (properties or {}).get("amount", 0),
                        "tenant_id": tenant_id,
                    }, actor="event_tracker")
                    results["engines"]["immutable"] = "audited"
                except Exception:
                    pass

        # GraphCore: auto-create edges
        if event_type in EVENT_TO_EDGE and self.relationship_graph:
            try:
                src_type, rel, tgt_type, tgt_key = EVENT_TO_EDGE[event_type]
                target_id = (properties or {}).get(tgt_key)
                if target_id:
                    await self.relationship_graph.add_edge(
                        src_type, customer_id, rel, tgt_type, str(target_id),
                        properties={"timestamp": event.timestamp,
                                    "amount": (properties or {}).get("amount")},
                        tenant_id=tenant_id)
                    results["engines"]["graph"] = f"edge:{rel}"
            except Exception as e:
                results["engines"]["graph"] = f"error: {e}"

        # Update customer last_seen
        if "relational" in self.engines:
            try:
                await self.engines["relational"].execute(
                    "UPDATE customers SET last_seen_at = NOW() "
                    "WHERE customer_id = $1", [customer_id])
            except Exception:
                pass

        return results

    async def track_batch(self, events: List[Dict],
                          tenant_id: Optional[str] = None) -> Dict:
        """Track multiple events in batch."""
        results = {"tracked": 0, "errors": 0}
        for evt in events:
            try:
                await self.track(
                    customer_id=evt["customer_id"],
                    event_type=evt["event_type"],
                    properties=evt.get("properties"),
                    source=evt.get("source", "batch"),
                    tenant_id=tenant_id)
                results["tracked"] += 1
            except Exception:
                results["errors"] += 1
        return results

    async def query_events(self, customer_id: str,
                           event_type: Optional[str] = None,
                           days: int = 90,
                           tenant_id: Optional[str] = None,
                           limit: int = 100) -> List[Dict]:
        """Query events for a customer."""
        if "temporal" not in self.engines:
            return []

        query = (
            "SELECT time, event_type, properties, source, channel "
            "FROM events WHERE customer_id = $1 "
            f"AND time > NOW() - INTERVAL '{days} days'")
        params = [customer_id]

        if event_type:
            query += " AND event_type = $2"
            params.append(event_type)

        limit = max(1, min(int(limit), 1000))
        params.append(limit)
        query += f" ORDER BY time DESC LIMIT ${len(params)}"

        try:
            return await self.engines["temporal"].execute(query, params) or []
        except Exception as e:
            logger.warning(f"Event query error: {e}")
            return []

    async def get_event_counts(self, customer_id: str,
                               days: int = 90) -> Dict:
        """Get event type counts for a customer."""
        if "temporal" not in self.engines:
            return {}
        try:
            rows = await self.engines["temporal"].execute(
                "SELECT event_type, COUNT(*) as count "
                "FROM events WHERE customer_id = $1 "
                f"AND time > NOW() - INTERVAL '{days} days' "
                "GROUP BY event_type ORDER BY count DESC",
                [customer_id])
            return {r["event_type"]: r["count"] for r in (rows or [])}
        except Exception:
            return {}

    def get_stats(self) -> Dict:
        return {"total_events_tracked": self._event_count}
