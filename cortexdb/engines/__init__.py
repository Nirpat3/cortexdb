"""CortexDB Engine Base Class - all engines implement this interface"""

from abc import ABC, abstractmethod
from typing import Any, Dict


class BaseEngine(ABC):
    """Every CortexDB engine must implement these methods"""

    @abstractmethod
    async def connect(self): ...

    @abstractmethod
    async def close(self): ...

    @abstractmethod
    async def health(self) -> Dict: ...

    @abstractmethod
    async def write(self, data_type: str, payload: Dict, actor: str) -> Any: ...
