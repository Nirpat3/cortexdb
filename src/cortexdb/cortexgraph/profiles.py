"""Layer 4: Behavioral Profile (DOC-020 Section 3.4)

RFM (Recency, Frequency, Monetary) + Churn Probability + LTV +
Behavioral Embeddings + Customer Health Score + Auto-Segmentation.
"""

import time
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("cortexdb.cortexgraph.profiles")


@dataclass
class CustomerProfile:
    customer_id: str = ""
    recency_days: float = 0
    frequency_90d: int = 0
    monetary_90d: float = 0
    avg_basket: float = 0
    preferred_categories: List[str] = field(default_factory=list)
    preferred_channel: str = ""
    churn_probability: float = 0.0
    health_score: float = 100.0
    rfm_segment: str = "New"
    segments: List[str] = field(default_factory=list)
    ltv: float = 0
    next_purchase_predicted_days: Optional[int] = None
    tenant_id: Optional[str] = None
    computed_at: float = field(default_factory=time.time)


# Health score weights (DOC-020)
HEALTH_WEIGHTS = {
    "recency": 0.25,
    "frequency": 0.20,
    "monetary": 0.20,
    "engagement": 0.15,
    "sentiment": 0.10,
    "churn_inverse": 0.10,
}

# RFM segment rules
RFM_SEGMENTS = {
    "VIP": lambda r, f, m: r <= 7 and f >= 20 and m >= 500,
    "Loyal": lambda r, f, m: r <= 30 and f >= 10,
    "Regular": lambda r, f, m: r <= 30 and f >= 5,
    "Promising": lambda r, f, m: r <= 14 and f >= 2,
    "New": lambda r, f, m: r <= 30 and f <= 2,
    "At-Risk": lambda r, f, m: r > 30 and r <= 60 and f >= 5,
    "Dormant": lambda r, f, m: r > 60 and r <= 120,
    "Churned": lambda r, f, m: r > 120,
}


class BehavioralProfiler:
    """Computes and caches customer behavioral profiles.

    Profiles are computed from TemporalCore event data and cached in MemoryCore.
    Sleep Cycle refreshes all profiles nightly.
    """

    def __init__(self, engines: Dict[str, Any] = None, embedding=None):
        self.engines = engines or {}
        self.embedding = embedding
        self._profiles: Dict[str, CustomerProfile] = {}
        self._profile_count = 0

    async def compute_profile(self, customer_id: str,
                               tenant_id: Optional[str] = None) -> CustomerProfile:
        """Compute full behavioral profile for a customer."""
        self._profile_count += 1
        profile = CustomerProfile(customer_id=customer_id, tenant_id=tenant_id)

        # RFM from TemporalCore
        if "temporal" in self.engines:
            try:
                rfm = await self._compute_rfm(customer_id)
                profile.recency_days = rfm.get("recency_days", 999)
                profile.frequency_90d = rfm.get("frequency", 0)
                profile.monetary_90d = rfm.get("monetary", 0)
                profile.avg_basket = rfm.get("avg_basket", 0)
            except Exception as e:
                logger.warning(f"RFM computation error: {e}")

        # Segment assignment
        profile.rfm_segment = self._assign_rfm_segment(
            profile.recency_days, profile.frequency_90d, profile.monetary_90d)
        profile.segments = self._auto_segment(profile)

        # Churn probability (simple heuristic; upgrade to ML model)
        profile.churn_probability = self._compute_churn_probability(profile)

        # Health score
        profile.health_score = self._compute_health_score(profile)

        # Cache
        self._profiles[customer_id] = profile

        # Store in MemoryCore for instant retrieval
        if "memory" in self.engines:
            try:
                import json
                cache_key = f"profile:{customer_id}"
                if tenant_id:
                    cache_key = f"tenant:{tenant_id}:{cache_key}"
                await self.engines["memory"].set(cache_key,
                    json.dumps(self._profile_to_dict(profile), default=str),
                    ex=86400)  # 24hr TTL
            except Exception:
                pass

        return profile

    async def _compute_rfm(self, customer_id: str) -> Dict:
        """Compute Recency, Frequency, Monetary from event data."""
        try:
            rows = await self.engines["temporal"].execute(
                "SELECT "
                "  EXTRACT(DAY FROM NOW() - MAX(time)) as recency_days, "
                "  COUNT(*) as frequency, "
                "  COALESCE(SUM((properties->>'amount')::NUMERIC), 0) as monetary, "
                "  COALESCE(AVG((properties->>'amount')::NUMERIC), 0) as avg_basket "
                "FROM events "
                "WHERE customer_id = $1 AND event_type = 'purchase_completed' "
                "AND time > NOW() - INTERVAL '90 days'",
                [customer_id])
            if rows and rows[0]:
                return {
                    "recency_days": float(rows[0].get("recency_days") or 999),
                    "frequency": int(rows[0].get("frequency") or 0),
                    "monetary": float(rows[0].get("monetary") or 0),
                    "avg_basket": float(rows[0].get("avg_basket") or 0),
                }
        except Exception as e:
            logger.warning(f"RFM query error: {e}")
        return {}

    @staticmethod
    def _assign_rfm_segment(recency: float, frequency: int, monetary: float) -> str:
        """Assign RFM segment based on rules."""
        for segment, rule in RFM_SEGMENTS.items():
            if rule(recency, frequency, monetary):
                return segment
        return "Unknown"

    @staticmethod
    def _auto_segment(profile: CustomerProfile) -> List[str]:
        """Auto-assign behavioral segments."""
        segments = [profile.rfm_segment]
        if profile.monetary_90d >= 500:
            segments.append("High-Value")
        if profile.frequency_90d >= 15:
            segments.append("Frequent-Buyer")
        if profile.churn_probability > 0.7:
            segments.append("At-Risk")
        if profile.recency_days <= 7 and profile.frequency_90d <= 2:
            segments.append("New-Customer")
        return segments

    @staticmethod
    def _compute_churn_probability(profile: CustomerProfile) -> float:
        """Simple churn probability heuristic.

        Upgrade to XGBoost model in production (DOC-020 Section 3.4).
        """
        score = 0.0
        # Recency: more days = higher churn risk
        if profile.recency_days > 90:
            score += 0.4
        elif profile.recency_days > 60:
            score += 0.25
        elif profile.recency_days > 30:
            score += 0.1

        # Frequency: fewer purchases = higher churn
        if profile.frequency_90d == 0:
            score += 0.3
        elif profile.frequency_90d < 3:
            score += 0.15
        elif profile.frequency_90d < 5:
            score += 0.05

        # Monetary: lower spend = less engaged
        if profile.monetary_90d < 50:
            score += 0.2
        elif profile.monetary_90d < 100:
            score += 0.1

        return min(1.0, score)

    @staticmethod
    def _compute_health_score(profile: CustomerProfile) -> float:
        """Composite health score 0-100 (DOC-020 Section 3.4)."""
        # Recency score (25%): 0-30 days = 100, 90+ = 0
        recency_score = max(0, 100 - (profile.recency_days / 90 * 100))

        # Frequency score (20%): 20+ = 100, 0 = 0
        frequency_score = min(100, profile.frequency_90d / 20 * 100)

        # Monetary score (20%): $500+ = 100, $0 = 0
        monetary_score = min(100, profile.monetary_90d / 500 * 100)

        # Engagement (15%): placeholder (from event counts)
        engagement_score = min(100, profile.frequency_90d * 10)

        # Sentiment (10%): placeholder
        sentiment_score = 70

        # Churn inverse (10%)
        churn_inverse = (1 - profile.churn_probability) * 100

        health = (
            recency_score * HEALTH_WEIGHTS["recency"] +
            frequency_score * HEALTH_WEIGHTS["frequency"] +
            monetary_score * HEALTH_WEIGHTS["monetary"] +
            engagement_score * HEALTH_WEIGHTS["engagement"] +
            sentiment_score * HEALTH_WEIGHTS["sentiment"] +
            churn_inverse * HEALTH_WEIGHTS["churn_inverse"]
        )
        return round(max(0, min(100, health)), 1)

    async def get_profile(self, customer_id: str,
                           tenant_id: Optional[str] = None) -> Optional[Dict]:
        """Get cached profile or compute fresh."""
        # Check MemoryCore cache
        if "memory" in self.engines:
            try:
                import json
                cache_key = f"profile:{customer_id}"
                if tenant_id:
                    cache_key = f"tenant:{tenant_id}:{cache_key}"
                cached = await self.engines["memory"].get(cache_key)
                if cached:
                    return json.loads(cached)
            except Exception:
                pass

        # Check in-memory
        if customer_id in self._profiles:
            return self._profile_to_dict(self._profiles[customer_id])

        # Compute fresh
        profile = await self.compute_profile(customer_id, tenant_id)
        return self._profile_to_dict(profile)

    async def compute_all(self, tenant_id: Optional[str] = None,
                           limit: int = 1000) -> Dict:
        """Batch compute profiles (called during Sleep Cycle)."""
        computed = 0
        if "relational" not in self.engines:
            return {"computed": 0, "error": "no_relational_engine"}

        try:
            query = "SELECT customer_id FROM customers"
            params = []
            if tenant_id:
                query += " WHERE tenant_id = $1"
                params = [tenant_id]
            query += f" ORDER BY last_seen_at DESC LIMIT {limit}"

            rows = await self.engines["relational"].execute(query, params)
            for row in (rows or []):
                try:
                    await self.compute_profile(
                        str(row["customer_id"]), tenant_id)
                    computed += 1
                except Exception:
                    pass
        except Exception as e:
            return {"computed": computed, "error": str(e)}

        return {"computed": computed}

    @staticmethod
    def _profile_to_dict(p: CustomerProfile) -> Dict:
        return {
            "customer_id": p.customer_id,
            "recency_days": p.recency_days,
            "frequency_90d": p.frequency_90d,
            "monetary_90d": p.monetary_90d,
            "avg_basket": p.avg_basket,
            "churn_probability": p.churn_probability,
            "health_score": p.health_score,
            "rfm_segment": p.rfm_segment,
            "segments": p.segments,
            "ltv": p.ltv,
            "computed_at": p.computed_at,
        }

    def get_stats(self) -> Dict:
        return {
            "profiles_computed": self._profile_count,
            "profiles_cached": len(self._profiles),
        }
