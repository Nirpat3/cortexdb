"""MemoryCore — Fast KV Cache Engine
Ultra-fast KV cache via Redis. Sessions, rate limiting, pub/sub."""

from typing import Any, Dict, Optional
from cortexdb.engines import BaseEngine

try:
    import redis.asyncio as aioredis
except ImportError:
    aioredis = None


class MemoryEngine(BaseEngine):
    def __init__(self, config: Dict):
        self.url = config.get("url", "redis://localhost:6379/0")
        self.password = config.get("password", "cortex_redis_secret")
        self.client = None

    async def connect(self):
        if aioredis is None:
            raise ImportError("redis required: pip install redis")
        self.client = aioredis.from_url(self.url, password=self.password, decode_responses=True)
        await self.client.ping()

    async def close(self):
        if self.client:
            await self.client.close()

    async def health(self) -> Dict:
        info = await self.client.info("memory")
        return {
            "engine": "Redis 7",
            "brain_region": "Working Memory",
            "used_memory_mb": round(info.get("used_memory", 0) / 1024 / 1024, 2),
            "max_memory_mb": round(info.get("maxmemory", 0) / 1024 / 1024, 2),
            "connected_clients": (await self.client.info("clients")).get("connected_clients", 0),
        }

    async def get(self, key: str) -> Optional[str]:
        return await self.client.get(key)

    async def set(self, key: str, value: str, ex: int = 3600) -> bool:
        return await self.client.set(key, value, ex=ex)

    async def delete(self, key: str) -> int:
        return await self.client.delete(key)

    async def write(self, data_type: str, payload: Dict, actor: str = "system") -> Any:
        import json
        key = f"{data_type}:{payload.get('id', 'default')}"
        await self.client.set(key, json.dumps(payload, default=str), ex=3600)
        return key

    async def touch(self, key: str, extend_seconds: int = 3600):
        """Extend TTL - like Synaptic Plasticity strengthening a pathway"""
        ttl = int(await self.client.ttl(key))
        if ttl > 0:
            await self.client.expire(key, ttl + extend_seconds)
