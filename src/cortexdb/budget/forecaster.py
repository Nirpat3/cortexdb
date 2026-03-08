"""
AI Forecasting Agent — Predicts future costs and resource usage using
statistical analysis and pattern detection on historical data.

This agent runs as a background service that:
1. Analyzes usage trends per resource and per tenant
2. Detects anomalies (sudden spikes/drops)
3. Generates monthly/quarterly forecasts
4. Produces budget recommendations (over/under allocation)
5. Predicts when budget thresholds will be breached
"""

import time
import math
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field, asdict
from enum import Enum

logger = logging.getLogger(__name__)


class TrendDirection(str, Enum):
    UP = "up"
    DOWN = "down"
    STABLE = "stable"
    VOLATILE = "volatile"


class ForecastConfidence(str, Enum):
    HIGH = "high"        # R² > 0.8
    MEDIUM = "medium"    # R² 0.5-0.8
    LOW = "low"          # R² < 0.5


@dataclass
class Forecast:
    resource: str
    period: str  # "next_month", "next_quarter", "end_of_month"
    predicted_cost: float
    confidence: ForecastConfidence
    trend: TrendDirection
    trend_pct: float  # % change per month
    breach_date: Optional[str] = None  # ISO date when budget exceeded
    recommendation: Optional[str] = None
    details: Dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Anomaly:
    timestamp: float
    resource: str
    expected: float
    actual: float
    deviation_pct: float
    severity: str  # "info", "warning", "critical"
    description: str

    def to_dict(self) -> dict:
        return asdict(self)


class ForecastingAgent:
    """AI agent that analyzes usage patterns and generates cost forecasts."""

    def __init__(self, budget_tracker):
        self.tracker = budget_tracker
        self._forecasts: Dict[str, Forecast] = {}
        self._anomalies: List[Anomaly] = []
        self._last_run: float = 0
        self._run_count: int = 0

    async def run_analysis(self) -> Dict:
        """Run full forecasting analysis. Returns comprehensive report."""
        logger.info("Forecasting agent starting analysis run #%d", self._run_count + 1)
        start = time.time()

        budgets = self.tracker.get_budgets()
        history = self.tracker.get_usage_history(days=30)
        monthly = self.tracker.get_monthly_totals()

        results = {
            "forecasts": [],
            "anomalies": [],
            "recommendations": [],
            "overall_forecast": {},
            "run_metadata": {
                "run_number": self._run_count + 1,
                "timestamp": time.time(),
                "data_points_analyzed": len(history),
                "resources_analyzed": len(budgets),
            },
        }

        # Per-resource analysis
        for budget in budgets:
            resource = budget["resource"]
            resource_history = [h for h in history if h["resource"] == resource]

            # Generate forecast
            forecast = self._forecast_resource(budget, resource_history, monthly)
            self._forecasts[resource] = forecast
            results["forecasts"].append(forecast.to_dict())

            # Detect anomalies
            anomalies = self._detect_anomalies(resource, resource_history)
            self._anomalies.extend(anomalies)
            results["anomalies"].extend([a.to_dict() for a in anomalies])

            # Generate recommendation
            rec = self._generate_recommendation(budget, forecast)
            if rec:
                results["recommendations"].append(rec)

        # Overall forecast
        results["overall_forecast"] = self._compute_overall_forecast(budgets, monthly)

        # Tenant-level forecasts
        results["tenant_forecasts"] = self._forecast_tenants()

        elapsed = time.time() - start
        results["run_metadata"]["duration_ms"] = round(elapsed * 1000, 1)
        self._last_run = time.time()
        self._run_count += 1

        logger.info("Forecasting complete: %d forecasts, %d anomalies, %d recommendations in %.0fms",
                     len(results["forecasts"]), len(results["anomalies"]),
                     len(results["recommendations"]), elapsed * 1000)

        return results

    def _forecast_resource(self, budget: dict, history: List[dict], monthly: List[dict]) -> Forecast:
        """Forecast a single resource using linear regression + seasonality."""
        resource = budget["resource"]
        allocated = budget["allocated"]
        used = budget["used"]

        # Extract daily values
        values = [h["value"] for h in sorted(history, key=lambda x: x["timestamp"])]

        if len(values) < 3:
            return Forecast(
                resource=resource, period="next_month",
                predicted_cost=used * 1.1,
                confidence=ForecastConfidence.LOW,
                trend=TrendDirection.STABLE, trend_pct=0,
                recommendation="Insufficient data for reliable forecast"
            )

        # Linear regression
        n = len(values)
        x_vals = list(range(n))
        slope, intercept, r_squared = self._linear_regression(x_vals, values)

        # Trend detection
        if abs(slope) < 0.5:
            trend = TrendDirection.STABLE
        elif slope > 0:
            trend = TrendDirection.UP
        else:
            trend = TrendDirection.DOWN

        # Check volatility
        mean_val = sum(values) / n
        std_dev = math.sqrt(sum((v - mean_val) ** 2 for v in values) / n)
        cv = std_dev / mean_val if mean_val > 0 else 0
        if cv > 0.4:
            trend = TrendDirection.VOLATILE

        # Confidence based on R²
        if r_squared > 0.8:
            confidence = ForecastConfidence.HIGH
        elif r_squared > 0.5:
            confidence = ForecastConfidence.MEDIUM
        else:
            confidence = ForecastConfidence.LOW

        # Project next month cost
        # Current daily rate extrapolated
        days_remaining = 24  # assume ~24 days left in month
        daily_rate = used / max(1, 30 - days_remaining) if used > 0 else mean_val
        eom_projected = used + daily_rate * days_remaining

        # Next month: use trend
        monthly_costs = [m["cost"] for m in monthly if not m.get("partial")]
        if len(monthly_costs) >= 2:
            avg_growth = sum(
                (monthly_costs[i] - monthly_costs[i - 1]) / monthly_costs[i - 1]
                for i in range(1, len(monthly_costs))
            ) / (len(monthly_costs) - 1)
        else:
            avg_growth = slope / mean_val if mean_val > 0 else 0

        last_full_month = monthly_costs[-1] if monthly_costs else allocated * 0.75
        next_month_predicted = last_full_month * (1 + avg_growth)

        # Resource-specific share
        resource_share = used / sum(b["used"] for b in self.tracker.get_budgets()) if used > 0 else 1 / 6
        predicted_cost = round(next_month_predicted * resource_share, 2)

        trend_pct = round(avg_growth * 100, 1)

        # Breach detection
        breach_date = None
        if trend == TrendDirection.UP and used > 0:
            daily_increase = slope * budget.get("unit_cost", 1)
            remaining_budget = allocated - used
            if daily_increase > 0:
                days_to_breach = remaining_budget / daily_increase
                if days_to_breach < 60:
                    import datetime
                    breach = datetime.datetime.now() + datetime.timedelta(days=days_to_breach)
                    breach_date = breach.strftime("%Y-%m-%d")

        return Forecast(
            resource=resource,
            period="next_month",
            predicted_cost=predicted_cost,
            confidence=confidence,
            trend=trend,
            trend_pct=trend_pct,
            breach_date=breach_date,
            details={
                "eom_projected": round(eom_projected, 2),
                "daily_rate": round(daily_rate, 2),
                "r_squared": round(r_squared, 3),
                "volatility": round(cv, 3),
                "data_points": n,
            }
        )

    def _detect_anomalies(self, resource: str, history: List[dict]) -> List[Anomaly]:
        """Detect anomalies using z-score method."""
        anomalies = []
        values = [h["value"] for h in history]
        if len(values) < 5:
            return anomalies

        mean = sum(values) / len(values)
        std = math.sqrt(sum((v - mean) ** 2 for v in values) / len(values))
        if std == 0:
            return anomalies

        for h in history[-7:]:  # Check last 7 data points
            z_score = abs(h["value"] - mean) / std
            if z_score > 2:
                deviation = ((h["value"] - mean) / mean) * 100
                severity = "critical" if z_score > 3 else "warning" if z_score > 2.5 else "info"
                anomalies.append(Anomaly(
                    timestamp=h["timestamp"],
                    resource=resource,
                    expected=round(mean, 2),
                    actual=round(h["value"], 2),
                    deviation_pct=round(deviation, 1),
                    severity=severity,
                    description=f"{resource} usage {'spike' if h['value'] > mean else 'drop'}: "
                                f"{abs(deviation):.0f}% {'above' if h['value'] > mean else 'below'} average"
                ))

        return anomalies

    def _generate_recommendation(self, budget: dict, forecast: Forecast) -> Optional[dict]:
        """Generate budget recommendation based on forecast."""
        usage_pct = budget["usage_pct"]
        resource = budget["resource"]

        if forecast.trend == TrendDirection.UP and usage_pct > 80:
            increase = round(budget["allocated"] * 0.25, 2)
            return {
                "resource": resource,
                "type": "increase_budget",
                "severity": "high",
                "message": f"Increase {resource} budget by 25% (${increase:.0f}) — "
                           f"trending up {forecast.trend_pct:.1f}%/month, currently at {usage_pct:.0f}%",
                "suggested_budget": round(budget["allocated"] + increase, 2),
                "confidence": forecast.confidence.value,
            }
        elif forecast.trend == TrendDirection.DOWN and usage_pct < 40:
            decrease = round(budget["allocated"] * 0.15, 2)
            return {
                "resource": resource,
                "type": "decrease_budget",
                "severity": "low",
                "message": f"Consider reducing {resource} budget by 15% (${decrease:.0f}) — "
                           f"usage declining, only at {usage_pct:.0f}%",
                "suggested_budget": round(budget["allocated"] - decrease, 2),
                "confidence": forecast.confidence.value,
            }
        elif forecast.breach_date:
            return {
                "resource": resource,
                "type": "breach_warning",
                "severity": "critical",
                "message": f"{resource} will exceed budget by {forecast.breach_date} at current rate",
                "suggested_budget": round(budget["allocated"] * 1.3, 2),
                "confidence": forecast.confidence.value,
            }
        return None

    def _compute_overall_forecast(self, budgets: List[dict], monthly: List[dict]) -> dict:
        """Compute overall system cost forecast."""
        total_budget = sum(b["allocated"] for b in budgets)
        total_used = sum(b["used"] for b in budgets)

        monthly_costs = [m["cost"] for m in monthly if not m.get("partial")]
        if len(monthly_costs) >= 2:
            avg_monthly = sum(monthly_costs) / len(monthly_costs)
            growth_rate = sum(
                (monthly_costs[i] - monthly_costs[i - 1]) / monthly_costs[i - 1]
                for i in range(1, len(monthly_costs))
            ) / (len(monthly_costs) - 1)
        else:
            avg_monthly = total_budget * 0.75
            growth_rate = 0.03

        next_month = round(avg_monthly * (1 + growth_rate), 2)
        next_quarter = round(avg_monthly * 3 * (1 + growth_rate * 3), 2)
        annual = round(avg_monthly * 12 * (1 + growth_rate * 6), 2)

        return {
            "current_month_projected": round(total_used * (30 / max(1, 7)), 2),  # extrapolate
            "next_month": next_month,
            "next_quarter": next_quarter,
            "annual_projected": annual,
            "avg_monthly": round(avg_monthly, 2),
            "growth_rate_pct": round(growth_rate * 100, 2),
            "budget_health": "healthy" if total_used / total_budget < 0.8 else
                            "warning" if total_used / total_budget < 0.95 else "critical",
        }

    def _forecast_tenants(self) -> List[dict]:
        """Forecast per-tenant costs."""
        tenant_costs = self.tracker.get_tenant_costs()
        results = []
        for tc in tenant_costs:
            total = tc["total"]
            # Simple growth estimate based on plan type
            growth = {"Enterprise": 0.08, "Business": 0.05, "Starter": 0.12}.get(tc["plan"], 0.05)
            next_month = round(total * (1 + growth), 2)
            results.append({
                "tenant_id": tc["tenant_id"],
                "tenant_name": tc["tenant_name"],
                "plan": tc["plan"],
                "current_cost": total,
                "predicted_next_month": next_month,
                "growth_pct": round(growth * 100, 1),
                "trend": "up" if growth > 0 else "stable",
            })
        return results

    def get_last_forecast(self) -> Dict:
        """Get the most recent forecast results."""
        if not self._forecasts:
            return {"status": "no_data", "message": "Run analysis first"}
        return {
            "forecasts": [f.to_dict() for f in self._forecasts.values()],
            "anomalies": [a.to_dict() for a in self._anomalies[-20:]],
            "last_run": self._last_run,
            "run_count": self._run_count,
        }

    @staticmethod
    def _linear_regression(x: List[float], y: List[float]) -> Tuple[float, float, float]:
        """Simple linear regression returning (slope, intercept, r_squared)."""
        n = len(x)
        if n < 2:
            return 0, 0, 0

        sum_x = sum(x)
        sum_y = sum(y)
        sum_xy = sum(xi * yi for xi, yi in zip(x, y))
        sum_x2 = sum(xi ** 2 for xi in x)
        sum_y2 = sum(yi ** 2 for yi in y)

        denom = n * sum_x2 - sum_x ** 2
        if denom == 0:
            return 0, sum_y / n, 0

        slope = (n * sum_xy - sum_x * sum_y) / denom
        intercept = (sum_y - slope * sum_x) / n

        # R-squared
        ss_res = sum((yi - (slope * xi + intercept)) ** 2 for xi, yi in zip(x, y))
        mean_y = sum_y / n
        ss_tot = sum((yi - mean_y) ** 2 for yi in y)
        r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0

        return slope, intercept, max(0, r_squared)
