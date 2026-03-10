"""
Model Performance Tracker — Learns which LLM provider+model works best for each task category.

Tracks per-(provider, model, category):
  - Success rate
  - Average latency
  - Average quality grade (from outcome analyzer)
  - Cost estimate

Exposes a recommend() method that returns the best provider for a given category
based on historical performance, not static rules.
"""

import time
import logging
from typing import Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from cortexdb.superadmin.persistence import PersistenceStore

logger = logging.getLogger(__name__)

TRACKER_KEY = "model_performance_tracker"


class ModelPerformanceTracker:
    """Tracks and learns LLM model performance per task category."""

    def __init__(self, persistence: "PersistenceStore"):
        self._persistence = persistence

    def _get_data(self) -> dict:
        return self._persistence.kv_get(TRACKER_KEY, {"entries": {}, "recommendations": {}})

    def _save_data(self, data: dict):
        self._persistence.kv_set(TRACKER_KEY, data)

    def record(self, provider: str, model: str, category: str,
               success: bool, elapsed_ms: float, grade: int = None):
        """Record a model execution result."""
        data = self._get_data()
        entries = data.get("entries", {})

        key = f"{provider}:{model}:{category}"
        entry = entries.get(key, {
            "provider": provider, "model": model, "category": category,
            "total": 0, "successes": 0, "failures": 0,
            "total_ms": 0, "grade_sum": 0, "grade_count": 0,
            "first_seen": time.time(),
        })

        entry["total"] = entry.get("total", 0) + 1
        if success:
            entry["successes"] = entry.get("successes", 0) + 1
        else:
            entry["failures"] = entry.get("failures", 0) + 1
        entry["total_ms"] = entry.get("total_ms", 0) + elapsed_ms
        entry["avg_ms"] = round(entry["total_ms"] / entry["total"], 1)
        entry["success_rate"] = round(entry["successes"] / entry["total"] * 100, 1)

        if grade is not None:
            entry["grade_sum"] = entry.get("grade_sum", 0) + grade
            entry["grade_count"] = entry.get("grade_count", 0) + 1
            entry["avg_grade"] = round(entry["grade_sum"] / entry["grade_count"], 2)

        entry["last_used"] = time.time()
        entries[key] = entry
        data["entries"] = entries

        # Recompute recommendations
        data["recommendations"] = self._compute_recommendations(entries)

        self._save_data(data)

    def recommend(self, category: str) -> Optional[dict]:
        """Recommend the best provider+model for a task category based on learned data.

        Returns:
            dict with provider, model, score, reason — or None if no data
        """
        data = self._get_data()
        recs = data.get("recommendations", {})
        return recs.get(category)

    def get_all_recommendations(self) -> dict:
        """Get recommendations for all categories."""
        data = self._get_data()
        return data.get("recommendations", {})

    def get_performance_data(self) -> dict:
        """Get full performance tracking data."""
        data = self._get_data()
        entries = data.get("entries", {})

        # Group by provider
        by_provider = {}
        for entry in entries.values():
            p = entry.get("provider", "unknown")
            if p not in by_provider:
                by_provider[p] = {"total": 0, "successes": 0, "categories": set()}
            by_provider[p]["total"] += entry.get("total", 0)
            by_provider[p]["successes"] += entry.get("successes", 0)
            by_provider[p]["categories"].add(entry.get("category", ""))

        # Convert sets to lists for JSON
        for p in by_provider:
            by_provider[p]["categories"] = list(by_provider[p]["categories"])
            total = by_provider[p]["total"]
            by_provider[p]["success_rate"] = round(
                by_provider[p]["successes"] / total * 100, 1) if total else 0

        return {
            "entries": list(entries.values()),
            "by_provider": by_provider,
            "recommendations": data.get("recommendations", {}),
            "total_tracked": sum(e.get("total", 0) for e in entries.values()),
        }

    def _compute_recommendations(self, entries: dict) -> dict:
        """Compute best provider+model per category from all tracked data."""
        # Group entries by category
        by_category: Dict[str, list] = {}
        for entry in entries.values():
            cat = entry.get("category", "general")
            by_category.setdefault(cat, []).append(entry)

        recommendations = {}
        for category, cat_entries in by_category.items():
            best = None
            best_score = -1

            for entry in cat_entries:
                if entry.get("total", 0) < 2:
                    continue  # Need at least 2 data points

                # Composite score: weighted combination of success rate, grade, and speed
                success_rate = entry.get("success_rate", 0) / 100  # 0-1
                avg_grade = entry.get("avg_grade", 5) / 10  # 0-1
                # Speed bonus: faster is better, normalize to 0-1 (cap at 30s)
                avg_ms = entry.get("avg_ms", 15000)
                speed_score = max(0, 1 - (avg_ms / 30000))

                # Weights: quality matters most, then reliability, then speed
                score = (avg_grade * 0.5) + (success_rate * 0.35) + (speed_score * 0.15)

                if score > best_score:
                    best_score = score
                    best = entry

            if best:
                reasons = []
                if best.get("avg_grade", 0) >= 7:
                    reasons.append(f"high quality ({best['avg_grade']}/10)")
                if best.get("success_rate", 0) >= 90:
                    reasons.append(f"reliable ({best['success_rate']}%)")
                if best.get("avg_ms", 99999) < 5000:
                    reasons.append(f"fast ({best['avg_ms']}ms avg)")

                recommendations[category] = {
                    "provider": best["provider"],
                    "model": best["model"],
                    "score": round(best_score, 3),
                    "based_on": best.get("total", 0),
                    "avg_grade": best.get("avg_grade"),
                    "success_rate": best.get("success_rate"),
                    "reason": ", ".join(reasons) if reasons else "best available",
                }

        return recommendations
