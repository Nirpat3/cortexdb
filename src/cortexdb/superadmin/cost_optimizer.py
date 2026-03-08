"""
Cost Optimization Engine — Auto-route tasks to cheapest capable model.

Combines model quality scores with pricing data to find the cheapest
provider/model that meets a quality threshold for each task category.
"""

import logging
from typing import Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from cortexdb.superadmin.llm_router import LLMRouter
    from cortexdb.superadmin.model_tracker import ModelPerformanceTracker
    from cortexdb.superadmin.cost_tracker import CostTracker
    from cortexdb.superadmin.persistence import PersistenceStore

logger = logging.getLogger(__name__)

# Cost per 1M tokens (input) — simplified pricing
PROVIDER_COSTS = {
    "ollama": 0.0,
    "claude": 3.0,
    "openai": 2.5,
}


class CostOptimizer:
    """Recommends cheapest capable model per task category."""

    def __init__(self, router: "LLMRouter", model_tracker: "ModelPerformanceTracker",
                 cost_tracker: "CostTracker", persistence: "PersistenceStore"):
        self._router = router
        self._tracker = model_tracker
        self._cost_tracker = cost_tracker
        self._persistence = persistence

    def recommend(self, category: str, quality_threshold: float = 6.0) -> Optional[dict]:
        """Find cheapest provider that achieves avg grade >= threshold for this category."""
        performances = self._tracker.get_all_performance()
        candidates = []

        for provider, models in performances.items():
            for model, data in models.items():
                cat_data = data.get("by_category", {}).get(category, {})
                avg_grade = cat_data.get("avg_grade", 0)
                total = cat_data.get("total", 0)

                if total < 2:
                    # Not enough data — use overall
                    avg_grade = data.get("avg_grade", 0)
                    total = data.get("total", 0)

                if total >= 2 and avg_grade >= quality_threshold:
                    cost = PROVIDER_COSTS.get(provider, 5.0)
                    candidates.append({
                        "provider": provider,
                        "model": model,
                        "avg_grade": round(avg_grade, 2),
                        "task_count": total,
                        "cost_per_1m": cost,
                    })

        if not candidates:
            return None

        # Sort by cost (cheapest first), then by quality (highest first)
        candidates.sort(key=lambda x: (x["cost_per_1m"], -x["avg_grade"]))
        return candidates[0]

    def get_report(self) -> dict:
        """Generate optimization report: current spend vs optimal."""
        totals = self._cost_tracker.get_totals()
        current_cost = totals.get("total_cost", 0)

        # Find optimal for each category
        categories = ["bug", "feature", "enhancement", "qa", "docs", "security", "ops", "general"]
        recommendations = {}
        potential_savings = 0

        for cat in categories:
            rec = self.recommend(cat)
            if rec:
                recommendations[cat] = rec
                # Estimate savings if using cheapest model
                by_cat = totals.get("by_category", {}).get(cat, {})
                cat_cost = by_cat.get("cost", 0) if isinstance(by_cat, dict) else 0
                if rec["cost_per_1m"] == 0 and cat_cost > 0:
                    potential_savings += cat_cost

        return {
            "current_total_cost": round(current_cost, 4),
            "potential_savings": round(potential_savings, 4),
            "recommendations": recommendations,
            "recommendation_count": len(recommendations),
        }

    def apply_optimizations(self, dry_run: bool = True) -> dict:
        """Apply recommended models to agents. If dry_run, just show changes."""
        report = self.get_report()
        changes = []

        # This is simplified — in practice would update agent LLM config
        for cat, rec in report.get("recommendations", {}).items():
            changes.append({
                "category": cat,
                "recommended_provider": rec["provider"],
                "recommended_model": rec["model"],
                "expected_quality": rec["avg_grade"],
                "cost_per_1m": rec["cost_per_1m"],
                "applied": not dry_run,
            })

        return {
            "dry_run": dry_run,
            "changes": changes,
            "total_changes": len(changes),
        }
