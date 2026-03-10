"""
Ollama Client — Connects to local Ollama instance for LLM inference.
Supports chat, generate, model listing, and health checks.

Ollama API: http://localhost:11434
"""

import logging
import asyncio
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False
    logger.warning("httpx not installed — using urllib fallback for Ollama client")


class OllamaClient:
    """Client for local Ollama LLM instance."""

    def __init__(self, base_url: str = "http://localhost:11434"):
        self.base_url = base_url.rstrip("/")
        self._available = False
        self._models: List[str] = []

    async def check_health(self) -> dict:
        """Check if Ollama is running and reachable."""
        try:
            data = await self._get("/api/tags")
            models = [m["name"] for m in data.get("models", [])]
            self._models = models
            self._available = True
            return {"status": "connected", "models": models, "url": self.base_url}
        except Exception as e:
            self._available = False
            return {"status": "disconnected", "error": str(e), "url": self.base_url}

    async def list_models(self) -> List[str]:
        """List available Ollama models."""
        try:
            data = await self._get("/api/tags")
            self._models = [m["name"] for m in data.get("models", [])]
            return self._models
        except Exception:
            return self._models

    async def chat(self, model: str, messages: List[Dict[str, str]],
                   system: str = None, temperature: float = 0.7) -> dict:
        """Send chat completion request to Ollama."""
        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature},
        }
        if system:
            payload["messages"] = [{"role": "system", "content": system}] + messages

        try:
            data = await self._post("/api/chat", payload)
            return {
                "success": True,
                "message": data.get("message", {}).get("content", ""),
                "model": model,
                "total_duration_ms": data.get("total_duration", 0) / 1_000_000,
                "eval_count": data.get("eval_count", 0),
            }
        except Exception as e:
            return {"success": False, "error": str(e), "model": model}

    async def generate(self, model: str, prompt: str,
                       system: str = None, temperature: float = 0.7) -> dict:
        """Send generate request to Ollama."""
        payload: Dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": temperature},
        }
        if system:
            payload["system"] = system

        try:
            data = await self._post("/api/generate", payload)
            return {
                "success": True,
                "response": data.get("response", ""),
                "model": model,
                "total_duration_ms": data.get("total_duration", 0) / 1_000_000,
                "eval_count": data.get("eval_count", 0),
            }
        except Exception as e:
            return {"success": False, "error": str(e), "model": model}

    async def _get(self, path: str) -> dict:
        if HAS_HTTPX:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(f"{self.base_url}{path}")
                resp.raise_for_status()
                return resp.json()
        else:
            return await self._urllib_request("GET", path)

    async def _post(self, path: str, data: dict) -> dict:
        if HAS_HTTPX:
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(f"{self.base_url}{path}", json=data)
                resp.raise_for_status()
                return resp.json()
        else:
            return await self._urllib_request("POST", path, data)

    async def _urllib_request(self, method: str, path: str, data: dict = None) -> dict:
        """Fallback using urllib if httpx not available."""
        import urllib.request
        import json

        url = f"{self.base_url}{path}"
        req = urllib.request.Request(url, method=method)
        req.add_header("Content-Type", "application/json")
        if data:
            req.data = json.dumps(data).encode()

        def _do():
            with urllib.request.urlopen(req, timeout=120) as resp:
                return json.loads(resp.read())

        return await asyncio.get_event_loop().run_in_executor(None, _do)

    @property
    def is_available(self) -> bool:
        return self._available

    @property
    def models(self) -> List[str]:
        return self._models
