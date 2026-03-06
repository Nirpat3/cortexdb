"""Circuit Breaker - Cascading Failure Prevention (DOC-014 Section 5)

States: CLOSED (normal) -> OPEN (tripped) -> HALF_OPEN (testing)
"""

import asyncio
import time
import logging
from enum import Enum
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("cortexdb.heartbeat.circuit_breaker")


class CircuitState(Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


@dataclass
class CircuitBreakerConfig:
    name: str
    failure_threshold: int = 5
    failure_window: float = 60.0
    cooldown: float = 30.0
    timeout: float = 5.0
    half_open_max: int = 1


PRESET_CONFIGS = {
    "cybersource": CircuitBreakerConfig("cybersource", 3, 30, 30, 5),
    "authorize_net": CircuitBreakerConfig("authorize_net", 3, 30, 30, 5),
    "claude_api": CircuitBreakerConfig("claude_api", 5, 60, 15, 30),
    "openai_api": CircuitBreakerConfig("openai_api", 5, 60, 15, 30),
    "instagram": CircuitBreakerConfig("instagram", 5, 60, 60, 10),
    "rapidrms": CircuitBreakerConfig("rapidrms", 3, 30, 30, 5),
    "postgresql": CircuitBreakerConfig("postgresql", 2, 10, 5, 3),
    "redis": CircuitBreakerConfig("redis", 3, 15, 10, 1),
    "plaid": CircuitBreakerConfig("plaid", 3, 30, 60, 10),
    "vault": CircuitBreakerConfig("vault", 1, 5, 5, 2),
    "hyperledger": CircuitBreakerConfig("hyperledger", 3, 30, 30, 5),
}


class CircuitOpenError(Exception):
    pass


class CircuitBreaker:
    def __init__(self, config: CircuitBreakerConfig):
        self.config = config
        self.state = CircuitState.CLOSED
        self._failures: List[float] = []
        self._last_failure_time: float = 0
        self._opened_at: float = 0
        self._half_open_calls: int = 0
        self._total_calls: int = 0
        self._total_failures: int = 0
        self._total_successes: int = 0
        self._fallback: Optional[Callable] = None

    def set_fallback(self, fallback: Callable) -> None:
        self._fallback = fallback

    async def call(self, func: Callable, *args, **kwargs) -> Any:
        self._total_calls += 1

        if self.state == CircuitState.OPEN:
            if self._should_attempt_reset():
                self.state = CircuitState.HALF_OPEN
                self._half_open_calls = 0
            else:
                if self._fallback:
                    return await self._fallback(*args, **kwargs) if asyncio.iscoroutinefunction(self._fallback) else self._fallback(*args, **kwargs)
                raise CircuitOpenError(f"Circuit {self.config.name} is OPEN")

        if self.state == CircuitState.HALF_OPEN:
            self._half_open_calls += 1
            if self._half_open_calls > self.config.half_open_max:
                raise CircuitOpenError(f"Circuit {self.config.name} HALF_OPEN: max probes reached")

        try:
            if asyncio.iscoroutinefunction(func):
                result = await asyncio.wait_for(func(*args, **kwargs), timeout=self.config.timeout)
            else:
                result = func(*args, **kwargs)
            self._on_success()
            return result
        except (asyncio.TimeoutError, Exception):
            self._on_failure()
            raise

    def _on_success(self) -> None:
        self._total_successes += 1
        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.CLOSED
            self._failures.clear()
            logger.info(f"Circuit {self.config.name}: HALF_OPEN -> CLOSED")

    def _on_failure(self) -> None:
        now = time.time()
        self._failures.append(now)
        self._last_failure_time = now
        self._total_failures += 1

        cutoff = now - self.config.failure_window
        self._failures = [t for t in self._failures if t > cutoff]

        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.OPEN
            self._opened_at = now
        elif len(self._failures) >= self.config.failure_threshold:
            self.state = CircuitState.OPEN
            self._opened_at = now
            logger.warning(f"Circuit {self.config.name}: CLOSED -> OPEN ({len(self._failures)} failures)")

    def _should_attempt_reset(self) -> bool:
        return time.time() - self._opened_at >= self.config.cooldown

    @property
    def _cooldown_remaining(self) -> float:
        return max(0, self.config.cooldown - (time.time() - self._opened_at))

    def get_status(self) -> Dict:
        return {
            "name": self.config.name, "state": self.state.value,
            "failures_in_window": len(self._failures),
            "failure_threshold": self.config.failure_threshold,
            "cooldown_remaining": round(self._cooldown_remaining, 1) if self.state == CircuitState.OPEN else 0,
            "total_calls": self._total_calls,
            "total_failures": self._total_failures,
            "total_successes": self._total_successes,
        }

    @classmethod
    def from_preset(cls, name: str) -> "CircuitBreaker":
        config = PRESET_CONFIGS.get(name)
        if not config:
            raise ValueError(f"Unknown preset: {name}. Available: {list(PRESET_CONFIGS.keys())}")
        return cls(config)


class CircuitBreakerRegistry:
    def __init__(self):
        self._breakers: Dict[str, CircuitBreaker] = {}

    def register(self, breaker: CircuitBreaker) -> None:
        self._breakers[breaker.config.name] = breaker

    def get(self, name: str) -> Optional[CircuitBreaker]:
        return self._breakers.get(name)

    def get_or_create(self, name: str) -> CircuitBreaker:
        if name not in self._breakers:
            if name in PRESET_CONFIGS:
                self._breakers[name] = CircuitBreaker.from_preset(name)
            else:
                self._breakers[name] = CircuitBreaker(CircuitBreakerConfig(name))
        return self._breakers[name]

    def get_all_status(self) -> List[Dict]:
        return [b.get_status() for b in self._breakers.values()]

    def get_open_circuits(self) -> List[str]:
        return [n for n, b in self._breakers.items() if b.state == CircuitState.OPEN]
