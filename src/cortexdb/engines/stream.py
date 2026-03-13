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
    RECONNECT_ERRORS = (ConnectionError, TimeoutError, OSError)

    def __init__(self, config: Dict):
        super().__init__()
        import os
        self._use_uds = os.getenv("CORTEX_USE_UNIX_SOCKETS", "").lower() in ("true", "1")
        if self._use_uds:
            self.url = config.get("uds_path", "unix:///var/run/redis/redis-stream.sock")
        else:
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
            **self.reconnect_stats,
        }

    async def publish(self, stream: str, event: Dict) -> str:
        event["_timestamp"] = time.time()
        return await self._with_reconnect(
            "publish",
            lambda: self.client.xadd(
                stream,
                {k: json.dumps(v) if not isinstance(v, str) else v for k, v in event.items()}
            ),
            reconnect_errors=self.RECONNECT_ERRORS)

    async def subscribe(self, stream: str, last_id: str = "$", count: int = 10):
        return await self._with_reconnect(
            "subscribe",
            lambda: self.client.xread({stream: last_id}, count=count, block=1000),
            reconnect_errors=self.RECONNECT_ERRORS)

    async def write(self, data_type: str, payload: Dict, actor: str = "system") -> Any:
        return await self.publish(
            f"cortex:{data_type}",
            {"payload": json.dumps(payload, default=str), "actor": actor}
        )
