"""StreamCore - Brain Region: Thalamic Relay (Event Streaming)
Real-time event bus. Agent events, heartbeats, notifications.
REPLACES: Kafka (for MVP/Growth). Uses Redis Streams."""

import json
import time
from typing import Any, Dict, Optional
from cortexdb.engines import BaseEngine

try:
    import redis.asyncio as aioredis
except ImportError:
    aioredis = None


class StreamEngine(BaseEngine):
    def __init__(self, config: Dict):
        self.url = config.get("url", "redis://localhost:6380/0")
        self.password = config.get("password", "cortex_stream_secret")
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
            "engine": "Redis Streams",
            "brain_region": "Thalamic Relay",
            "used_memory_mb": round(info.get("used_memory", 0) / 1024 / 1024, 2),
        }

    async def publish(self, stream: str, event: Dict) -> str:
        """Publish event to stream (like thalamus routing sensory signal)"""
        event["_timestamp"] = time.time()
        return await self.client.xadd(
            stream,
            {k: json.dumps(v) if not isinstance(v, str) else v for k, v in event.items()}
        )

    async def subscribe(self, stream: str, last_id: str = "$", count: int = 10):
        """Read from stream"""
        return await self.client.xread({stream: last_id}, count=count, block=1000)

    async def write(self, data_type: str, payload: Dict, actor: str = "system") -> Any:
        return await self.publish(
            f"cortex:{data_type}",
            {"payload": json.dumps(payload, default=str), "actor": actor}
        )
