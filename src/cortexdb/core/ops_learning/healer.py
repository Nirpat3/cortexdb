"""Healer — Rule-based anomaly detectors that revert to last known good config.

Each detector watches a specific signal type and triggers a rollback when
sustained anomalies are observed.  The Healer keeps a pointer to the
"last known good" snapshot version so rollback targets are stable.
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from cortexdb.core.ops_learning.config_store import ConfigStore
from cortexdb.core.ops_learning.signals import OpsSignalEmitter

logger = logging.getLogger("cortexdb.ops_learning.healer")


# ---------------------------------------------------------------------------
# Detector base
# ---------------------------------------------------------------------------

@dataclass
class DetectorResult:
    triggered: bool = False
    reason: str = ""
    severity: str = "warning"  # warning | critical


class BaseDetector(ABC):
    """Abstract anomaly detector."""

    name: str = "base"

    @abstractmethod
    def evaluate(self, signals: List[Dict[str, Any]]) -> DetectorResult:
        """Evaluate recent signals and decide whether to trigger."""
        ...


# ---------------------------------------------------------------------------
# Concrete detectors (v1 stubs)
# ---------------------------------------------------------------------------

class LatencySpikeDetector(BaseDetector):
    """Triggers when p99 latency exceeds 2× baseline for N consecutive windows."""

    name = "latency_spike"

    def __init__(self, baseline_ms: float = 500, multiplier: float = 2.0, consecutive: int = 3):
        self.baseline_ms = baseline_ms
        self.multiplier = multiplier
        self.consecutive = consecutive
        self._breach_count = 0

    def evaluate(self, signals: List[Dict[str, Any]]) -> DetectorResult:
        latency_signals = [
            s for s in signals if s.get("type") == "ops.latency"
        ]
        if not latency_signals:
            self._breach_count = 0
            return DetectorResult()

        threshold = self.baseline_ms * self.multiplier
        for sig in latency_signals:
            payload = sig.get("payload", {})
            if isinstance(payload, str):
                import json
                try:
                    payload = json.loads(payload)
                except Exception:
                    continue
            p99 = payload.get("p99", 0)
            if p99 > threshold:
                self._breach_count += 1
            else:
                self._breach_count = 0

        if self._breach_count >= self.consecutive:
            self._breach_count = 0
            return DetectorResult(
                triggered=True,
                reason=f"p99 latency exceeded {threshold}ms for {self.consecutive} consecutive windows",
                severity="critical",
            )
        return DetectorResult()


class ErrorFloodDetector(BaseDetector):
    """Triggers when error rate exceeds a sustained threshold."""

    name = "error_flood"

    def __init__(self, threshold: float = 0.1, consecutive: int = 3):
        self.threshold = threshold
        self.consecutive = consecutive
        self._breach_count = 0

    def evaluate(self, signals: List[Dict[str, Any]]) -> DetectorResult:
        error_signals = [
            s for s in signals if s.get("type") == "ops.error_rate"
        ]
        if not error_signals:
            self._breach_count = 0
            return DetectorResult()

        for sig in error_signals:
            payload = sig.get("payload", {})
            if isinstance(payload, str):
                import json
                try:
                    payload = json.loads(payload)
                except Exception:
                    continue
            rate = payload.get("rate", 0)
            if rate > self.threshold:
                self._breach_count += 1
            else:
                self._breach_count = 0

        if self._breach_count >= self.consecutive:
            self._breach_count = 0
            return DetectorResult(
                triggered=True,
                reason=f"Error rate > {self.threshold} for {self.consecutive} consecutive windows",
                severity="critical",
            )
        return DetectorResult()


class CacheCollapseDetector(BaseDetector):
    """Triggers when cache hit ratio drops below a floor."""

    name = "cache_collapse"

    def __init__(self, floor: float = 0.15, consecutive: int = 2):
        self.floor = floor
        self.consecutive = consecutive
        self._breach_count = 0

    def evaluate(self, signals: List[Dict[str, Any]]) -> DetectorResult:
        cache_signals = [
            s for s in signals if s.get("type") == "ops.cache_hit"
        ]
        if not cache_signals:
            self._breach_count = 0
            return DetectorResult()

        for sig in cache_signals:
            payload = sig.get("payload", {})
            if isinstance(payload, str):
                import json
                try:
                    payload = json.loads(payload)
                except Exception:
                    continue
            ratio = payload.get("ratio", 1.0)
            if ratio < self.floor:
                self._breach_count += 1
            else:
                self._breach_count = 0

        if self._breach_count >= self.consecutive:
            self._breach_count = 0
            return DetectorResult(
                triggered=True,
                reason=f"Cache hit ratio below {self.floor} for {self.consecutive} consecutive windows",
                severity="critical",
            )
        return DetectorResult()


# ---------------------------------------------------------------------------
# Healer orchestrator
# ---------------------------------------------------------------------------

class Healer:
    """Runs all detectors and triggers rollback when needed.

    Parameters
    ----------
    config_store : The active ``ConfigStore``.
    signal_emitter : ``OpsSignalEmitter`` for reading recent signals.
    detectors : List of detector instances (defaults to all built-in detectors).
    last_known_good : Snapshot version considered safe (updated after successful patches).
    """

    def __init__(
        self,
        config_store: ConfigStore,
        signal_emitter: OpsSignalEmitter,
        detectors: Optional[List[BaseDetector]] = None,
        last_known_good: int = 1,
    ):
        self.config_store = config_store
        self.signal_emitter = signal_emitter
        self.detectors = detectors or [
            LatencySpikeDetector(),
            ErrorFloodDetector(),
            CacheCollapseDetector(),
        ]
        self.last_known_good = last_known_good

    def set_last_known_good(self, version: int) -> None:
        self.last_known_good = version
        logger.info("Last known good updated to v%d", version)

    async def check(self) -> List[DetectorResult]:
        """Run all detectors against recent signals.

        If any detector triggers a critical result, initiate rollback.
        Returns all detector results.
        """
        signals = await self.signal_emitter.read_recent(count=200)
        results: List[DetectorResult] = []

        for detector in self.detectors:
            result = detector.evaluate(signals)
            results.append(result)
            if result.triggered and result.severity == "critical":
                logger.warning(
                    "Detector %s triggered: %s — rolling back to v%d",
                    detector.name,
                    result.reason,
                    self.last_known_good,
                )
                await self.config_store.rollback(
                    self.last_known_good, actor=f"healer:{detector.name}"
                )

        return results
