"""CortexDB Engine Base Class - all engines implement this interface.

v2: Added _with_reconnect() for automatic retry with exponential backoff.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict

logger = logging.getLogger("cortexdb.engines")


class BaseEngine(ABC):
    """Every CortexDB engine must implement these methods."""

    # Reconnect config
    RECONNECT_MAX_ATTEMPTS = 3
    RECONNECT_BASE_DELAY = 1.0    # seconds
    RECONNECT_MAX_DELAY = 30.0    # seconds

    def __init__(self):
        self._reconnect_count = 0
        self._last_reconnect_error = None

    @abstractmethod
    async def connect(self): ...

    @abstractmethod
    async def close(self): ...

    @abstractmethod
    async def health(self) -> Dict: ...

    @abstractmethod
    async def write(self, data_type: str, payload: Dict, actor: str) -> Any: ...

    async def _with_reconnect(self, op_name: str, coro_factory: Callable,
                               reconnect_errors: tuple = (Exception,)):
        """Execute an async operation with automatic reconnect on failure.

        Args:
            op_name: Human-readable operation name for logging
            coro_factory: Callable that returns a new coroutine each call
            reconnect_errors: Tuple of exception types that trigger reconnect

        Returns:
            The result of the operation

        Raises:
            The last exception if all attempts fail
        """
        last_error = None
        for attempt in range(self.RECONNECT_MAX_ATTEMPTS):
            try:
                return await coro_factory()
            except reconnect_errors as e:
                last_error = e
                self._last_reconnect_error = str(e)
                delay = min(
                    self.RECONNECT_BASE_DELAY * (2 ** attempt),
                    self.RECONNECT_MAX_DELAY
                )
                logger.warning(
                    "%s: %s failed (attempt %d/%d): %s. Reconnecting in %.1fs...",
                    self.__class__.__name__, op_name,
                    attempt + 1, self.RECONNECT_MAX_ATTEMPTS,
                    e, delay
                )
                await asyncio.sleep(delay)
                try:
                    await self.connect()
                    self._reconnect_count += 1
                    logger.info("%s: reconnected successfully", self.__class__.__name__)
                except Exception as reconnect_err:
                    logger.error("%s: reconnect failed: %s",
                                 self.__class__.__name__, reconnect_err)
        raise last_error

    @property
    def reconnect_stats(self) -> Dict:
        return {
            "reconnect_count": self._reconnect_count,
            "last_error": self._last_reconnect_error,
        }
