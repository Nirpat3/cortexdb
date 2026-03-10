"""Prometheus Metrics (DOC-019 Section 2.1)

Counters, gauges, histograms for all CortexDB operations.
Exposed at /health/metrics in Prometheus text format.
"""

import time
import logging
from collections import defaultdict, deque
from typing import Dict, List, Optional

logger = logging.getLogger("cortexdb.observability.metrics")

# Fixed-size ring buffer for histogram observations
HISTOGRAM_MAX_SIZE = 5000


class MetricsCollector:
    """Lightweight Prometheus-compatible metrics collector.

    Stores counters, gauges, and histogram ring buffers in memory.
    Exports as Prometheus text format via /health/metrics.
    """

    def __init__(self):
        self._counters: Dict[str, float] = defaultdict(float)
        self._gauges: Dict[str, float] = {}
        self._histograms: Dict[str, deque] = defaultdict(lambda: deque(maxlen=HISTOGRAM_MAX_SIZE))
        self._start_time = time.time()

    # -- Counters --

    def inc(self, name: str, value: float = 1, labels: Dict = None):
        key = self._key(name, labels)
        self._counters[key] += value

    # -- Gauges --

    def set_gauge(self, name: str, value: float, labels: Dict = None):
        key = self._key(name, labels)
        self._gauges[key] = value

    # -- Histograms --

    def observe(self, name: str, value: float, labels: Dict = None):
        key = self._key(name, labels)
        self._histograms[key].append(value)  # deque(maxlen) auto-evicts oldest

    # -- Pre-defined CortexDB metrics --

    def record_query(self, tier: str, latency_ms: float, cache_hit: bool,
                     tenant_id: Optional[str] = None):
        self.inc("cortexdb_queries_total", labels={"tier": tier, "cache_hit": str(cache_hit)})
        self.observe("cortexdb_query_latency_ms", latency_ms, labels={"tier": tier})
        if tenant_id:
            self.inc("cortexdb_tenant_queries_total", labels={"tenant_id": tenant_id})

    def record_write(self, data_type: str, latency_ms: float,
                     sync_engines: int, async_engines: int):
        self.inc("cortexdb_writes_total", labels={"data_type": data_type})
        self.observe("cortexdb_write_latency_ms", latency_ms, labels={"data_type": data_type})
        self.inc("cortexdb_write_fanout_sync", value=sync_engines)
        self.inc("cortexdb_write_fanout_async", value=async_engines)

    def record_amygdala(self, allowed: bool, latency_us: float):
        self.inc("cortexdb_amygdala_checks_total", labels={"allowed": str(allowed)})
        self.observe("cortexdb_amygdala_latency_us", latency_us)

    def record_rate_limit(self, tier: str, tenant_id: str):
        self.inc("cortexdb_rate_limit_exceeded_total", labels={"tier": tier, "tenant_id": tenant_id})

    def record_engine_health(self, engine: str, healthy: bool):
        self.set_gauge(f"cortexdb_engine_healthy", 1.0 if healthy else 0.0,
                       labels={"engine": engine})

    def record_cache_stats(self, r0_hit_rate: float, r0_size: int):
        self.set_gauge("cortexdb_cache_r0_hit_rate", r0_hit_rate)
        self.set_gauge("cortexdb_cache_r0_size", r0_size)

    def record_active_tenants(self, count: int):
        self.set_gauge("cortexdb_active_tenants", count)

    def record_active_agents(self, count: int):
        self.set_gauge("cortexdb_active_agents", count)

    # -- Export --

    def export_prometheus(self) -> str:
        """Export all metrics in Prometheus text exposition format."""
        lines = [
            "# CortexDB Metrics",
            f"# Uptime: {time.time() - self._start_time:.0f}s",
            "",
        ]

        # Counters
        for key, val in sorted(self._counters.items()):
            lines.append(f"# TYPE {key.split('{')[0]} counter")
            lines.append(f"{key} {val}")

        # Gauges
        for key, val in sorted(self._gauges.items()):
            lines.append(f"# TYPE {key.split('{')[0]} gauge")
            lines.append(f"{key} {val}")

        # Histograms (summary with percentiles)
        for key, values in sorted(self._histograms.items()):
            if not values:
                continue
            sorted_vals = sorted(values)
            n = len(sorted_vals)
            base = key.split("{")[0]
            labels = key[len(base):]
            lines.append(f"# TYPE {base} summary")
            lines.append(f"{base}_count{labels} {n}")
            lines.append(f"{base}_sum{labels} {sum(sorted_vals):.3f}")
            for q in [0.5, 0.95, 0.99]:
                idx = min(int(n * q), n - 1)
                lines.append(f'{base}{{quantile="{q}",{labels[1:] if labels else "}"} {sorted_vals[idx]:.3f}')

        return "\n".join(lines) + "\n"

    def get_summary(self) -> Dict:
        """Get metrics summary as dict for JSON endpoints."""
        return {
            "counters": dict(self._counters),
            "gauges": dict(self._gauges),
            "uptime_seconds": round(time.time() - self._start_time, 1),
        }

    @staticmethod
    def _key(name: str, labels: Dict = None) -> str:
        if not labels:
            return name
        label_str = ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))
        return f"{name}{{{label_str}}}"
