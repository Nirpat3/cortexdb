"""
LLM Router — Routes agent requests to the configured LLM provider.
Supports: Ollama (local), Claude API, OpenAI API.
"""

import json
import os
import time
import logging
from typing import AsyncIterator, Callable, Dict, List, Optional
from enum import Enum

from cortexdb.observability.tracing import trace_span

logger = logging.getLogger(__name__)


class LLMProvider(str, Enum):
    OLLAMA = "ollama"
    CLAUDE = "claude"
    OPENAI = "openai"


# Default models per provider
DEFAULT_MODELS = {
    LLMProvider.OLLAMA: "llama3.1:8b",
    LLMProvider.CLAUDE: "claude-sonnet-4-20250514",
    LLMProvider.OPENAI: "gpt-4o",
}


DEFAULT_FAILOVER_CHAIN = [LLMProvider.OLLAMA, LLMProvider.CLAUDE, LLMProvider.OPENAI]
MAX_RETRIES = 2
RETRY_DELAY_S = 1.0


class LLMRouter:
    """Routes LLM requests to the configured provider with failover support."""

    def __init__(self, ollama_client=None, model_tracker=None):
        self.ollama = ollama_client
        self._provider_config: Dict[str, dict] = {}
        self._request_log: List[dict] = []
        self._failover_chain: List[LLMProvider] = list(DEFAULT_FAILOVER_CHAIN)
        self._circuit_state: Dict[str, dict] = {}  # provider -> {failures, open_until}
        self._model_tracker = model_tracker

    def configure_provider(self, provider: str, config: dict):
        """Configure a provider with API key and default model."""
        self._provider_config[provider] = {
            "api_key": config.get("api_key", ""),
            "model": config.get("model", DEFAULT_MODELS.get(LLMProvider(provider), "")),
            "base_url": config.get("base_url", ""),
            "enabled": config.get("enabled", True),
        }

    def set_failover_chain(self, chain: List[str]):
        """Set the failover order. E.g. ['ollama', 'claude', 'openai']."""
        self._failover_chain = [LLMProvider(p) for p in chain]

    def _is_circuit_open(self, provider: str) -> bool:
        state = self._circuit_state.get(provider)
        if not state:
            return False
        if state.get("open_until", 0) > time.time():
            return True
        # Circuit half-open: allow retry
        return False

    def _record_failure(self, provider: str):
        state = self._circuit_state.setdefault(provider, {"failures": 0, "open_until": 0})
        state["failures"] = state.get("failures", 0) + 1
        if state["failures"] >= 3:
            state["open_until"] = time.time() + 60  # Open for 60s
            logger.warning("Circuit breaker OPEN for %s (3 consecutive failures)", provider)

    def _record_success(self, provider: str):
        self._circuit_state[provider] = {"failures": 0, "open_until": 0}

    async def chat(self, provider: str, messages: List[Dict[str, str]],
                   model: str = None, system: str = None,
                   temperature: float = 0.7, failover: bool = True,
                   tools: Optional[List[dict]] = None) -> dict:
        """Route chat request to provider with optional failover chain."""
        result = await self._chat_single(provider, messages, model, system, temperature, tools=tools)

        if result.get("success") or not failover:
            return result

        # Failover: try other providers in chain
        for fallback in self._failover_chain:
            if fallback.value == provider:
                continue
            if self._is_circuit_open(fallback.value):
                continue
            config = self._provider_config.get(fallback.value, {})
            if not config.get("enabled", fallback == LLMProvider.OLLAMA):
                continue
            logger.info("Failing over from %s to %s", provider, fallback.value)
            result = await self._chat_single(fallback.value, messages, None, system, temperature, tools=tools)
            if result.get("success"):
                result["failover_from"] = provider
                return result

        return result

    async def _chat_single(self, provider: str, messages: List[Dict[str, str]],
                           model: str = None, system: str = None,
                           temperature: float = 0.7,
                           tools: Optional[List[dict]] = None) -> dict:
        """Execute a single chat request with retry."""
        import asyncio as _asyncio

        for attempt in range(MAX_RETRIES + 1):
            if self._is_circuit_open(provider):
                return {"success": False, "error": f"{provider} circuit breaker open", "provider": provider}

            start = time.time()
            result = {"success": False, "provider": provider}

            try:
                if provider == LLMProvider.OLLAMA:
                    if not self.ollama or not self.ollama.is_available:
                        return {"success": False, "error": "Ollama not connected", "provider": provider}
                    model = model or self._get_model(provider)
                    result = await self.ollama.chat(model, messages, system, temperature)
                elif provider == LLMProvider.CLAUDE:
                    result = await self._claude_chat(messages, model, system, temperature, tools=tools)
                elif provider == LLMProvider.OPENAI:
                    result = await self._openai_chat(messages, model, system, temperature, tools=tools)
                else:
                    return {"success": False, "error": f"Unknown provider: {provider}"}
            except Exception as e:
                result = {"success": False, "error": str(e), "provider": provider}

            elapsed = round((time.time() - start) * 1000, 1)
            result["elapsed_ms"] = elapsed
            self._log_request(provider, model, elapsed, result.get("success", False))

            if result.get("success"):
                self._record_success(provider)
                return result

            self._record_failure(provider)
            if attempt < MAX_RETRIES:
                await _asyncio.sleep(RETRY_DELAY_S * (attempt + 1))

        return result

    async def _claude_chat(self, messages: List[Dict], model: str = None,
                           system: str = None, temperature: float = 0.7,
                           tools: Optional[List[dict]] = None) -> dict:
        """Call Claude API (Anthropic)."""
        config = self._provider_config.get(LLMProvider.CLAUDE, {})
        api_key = config.get("api_key") or os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            return {"success": False, "error": "Claude API key not configured"}

        model = model or config.get("model", DEFAULT_MODELS[LLMProvider.CLAUDE])

        try:
            import httpx
            headers = {
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            }
            payload = {
                "model": model,
                "max_tokens": 4096,
                "messages": messages,
                "temperature": temperature,
            }
            if system:
                payload["system"] = system

            if tools:
                claude_tools = []
                for t in tools:
                    claude_tools.append({
                        "name": t["name"],
                        "description": t.get("description", ""),
                        "input_schema": {
                            "type": "object",
                            "properties": {
                                p["name"]: {"type": p.get("type", "string"), "description": p.get("description", "")}
                                for p in t.get("parameters", [])
                            },
                            "required": [p["name"] for p in t.get("parameters", []) if p.get("required", True)],
                        },
                    })
                payload["tools"] = claude_tools

            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post("https://api.anthropic.com/v1/messages", json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()

                content_blocks = data.get("content", [])
                text_parts = []
                tool_calls = []
                for block in content_blocks:
                    if block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
                    elif block.get("type") == "tool_use":
                        tool_calls.append({
                            "id": block.get("id"),
                            "name": block.get("name"),
                            "arguments": block.get("input", {}),
                        })

                result = {
                    "success": True,
                    "message": "\n".join(text_parts),
                    "model": model,
                    "provider": "claude",
                    "usage": data.get("usage", {}),
                    "stop_reason": data.get("stop_reason"),
                }
                if tool_calls:
                    result["tool_calls"] = tool_calls
                return result
        except Exception as e:
            return {"success": False, "error": str(e), "provider": "claude"}

    async def _openai_chat(self, messages: List[Dict], model: str = None,
                           system: str = None, temperature: float = 0.7,
                           tools: Optional[List[dict]] = None) -> dict:
        """Call OpenAI API."""
        config = self._provider_config.get(LLMProvider.OPENAI, {})
        api_key = config.get("api_key") or os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            return {"success": False, "error": "OpenAI API key not configured"}

        model = model or config.get("model", DEFAULT_MODELS[LLMProvider.OPENAI])

        try:
            import httpx
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            msgs = []
            if system:
                msgs.append({"role": "system", "content": system})
            msgs.extend(messages)

            payload = {"model": model, "messages": msgs, "temperature": temperature}

            if tools:
                openai_tools = []
                for t in tools:
                    openai_tools.append({
                        "type": "function",
                        "function": {
                            "name": t["name"],
                            "description": t.get("description", ""),
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    p["name"]: {"type": p.get("type", "string"), "description": p.get("description", "")}
                                    for p in t.get("parameters", [])
                                },
                                "required": [p["name"] for p in t.get("parameters", []) if p.get("required", True)],
                            },
                        },
                    })
                payload["tools"] = openai_tools

            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post("https://api.openai.com/v1/chat/completions", json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                choice = data["choices"][0]
                message = choice["message"]
                content = message.get("content", "") or ""
                result = {
                    "success": True,
                    "message": content,
                    "model": model,
                    "provider": "openai",
                    "usage": data.get("usage", {}),
                    "stop_reason": choice.get("finish_reason"),
                }
                if message.get("tool_calls"):
                    result["tool_calls"] = [
                        {
                            "id": tc["id"],
                            "name": tc["function"]["name"],
                            "arguments": json.loads(tc["function"].get("arguments", "{}")),
                        }
                        for tc in message["tool_calls"]
                    ]
                return result
        except Exception as e:
            return {"success": False, "error": str(e), "provider": "openai"}

    async def chat_with_tools(self, provider: str, messages: List[Dict[str, str]],
                              tools: List[dict], tool_executor: Callable,
                              agent_id: str = "", model: str = None,
                              system: str = None, temperature: float = 0.7,
                              max_rounds: int = 5) -> dict:
        """Chat with automatic native tool execution loop."""
        current_messages = list(messages)

        for round_num in range(max_rounds):
            result = await self.chat(
                provider, current_messages, model=model,
                system=system, temperature=temperature,
                failover=True, tools=tools,
            )

            if not result.get("success") or not result.get("tool_calls"):
                return result

            # Execute tool calls
            tool_results = []
            for tc in result["tool_calls"]:
                try:
                    args = tc.get("arguments", {})
                    arg_list = list(args.values())
                    tool_result = await tool_executor(agent_id, tc["name"], arg_list)
                    tool_results.append({"id": tc.get("id"), "name": tc["name"], "result": str(tool_result)})
                except Exception as e:
                    tool_results.append({"id": tc.get("id"), "name": tc["name"], "result": f"Error: {e}"})

            # Append assistant message + tool results for next round
            if provider in ("claude", LLMProvider.CLAUDE):
                # Claude: assistant content blocks + tool_result messages
                assistant_content = []
                if result.get("message"):
                    assistant_content.append({"type": "text", "text": result["message"]})
                for tc in result["tool_calls"]:
                    assistant_content.append({"type": "tool_use", "id": tc["id"], "name": tc["name"], "input": tc.get("arguments", {})})
                current_messages.append({"role": "assistant", "content": assistant_content})

                tool_result_content = []
                for tr in tool_results:
                    tool_result_content.append({"type": "tool_result", "tool_use_id": tr["id"], "content": tr["result"]})
                current_messages.append({"role": "user", "content": tool_result_content})
            else:
                # OpenAI format
                current_messages.append({
                    "role": "assistant",
                    "content": result.get("message", ""),
                    "tool_calls": [
                        {"id": tc["id"], "type": "function", "function": {"name": tc["name"], "arguments": json.dumps(tc.get("arguments", {}))}}
                        for tc in result["tool_calls"]
                    ]
                })
                for tr in tool_results:
                    current_messages.append({"role": "tool", "tool_call_id": tr["id"], "content": tr["result"]})

            result["_tool_round"] = round_num + 1

        return result

    async def chat_stream(self, provider: str, messages: List[Dict[str, str]],
                          model: str = None, system: str = None,
                          temperature: float = 0.7) -> AsyncIterator[str]:
        """Stream chat response as SSE-compatible text chunks."""
        start = time.time()
        model = model or self._get_model(provider)

        try:
            if provider == LLMProvider.OLLAMA:
                async for chunk in self._ollama_stream(messages, model, system, temperature):
                    yield chunk
            elif provider == LLMProvider.CLAUDE:
                async for chunk in self._claude_stream(messages, model, system, temperature):
                    yield chunk
            elif provider == LLMProvider.OPENAI:
                async for chunk in self._openai_stream(messages, model, system, temperature):
                    yield chunk
            else:
                yield f"Error: Unknown provider {provider}"
        except Exception as e:
            yield f"Error: {e}"

        elapsed = round((time.time() - start) * 1000, 1)
        self._log_request(provider, model, elapsed, True)

    async def _ollama_stream(self, messages, model, system, temperature) -> AsyncIterator[str]:
        if not self.ollama or not self.ollama.is_available:
            yield "Error: Ollama not connected"
            return
        import httpx
        base = self.ollama.base_url.rstrip("/")
        payload = {"model": model, "messages": messages, "stream": True}
        if system:
            payload["messages"] = [{"role": "system", "content": system}] + list(messages)
        async with httpx.AsyncClient(timeout=120) as client:
            async with client.stream("POST", f"{base}/api/chat", json=payload) as resp:
                import json as _json
                async for line in resp.aiter_lines():
                    if line.strip():
                        try:
                            data = _json.loads(line)
                            token = data.get("message", {}).get("content", "")
                            if token:
                                yield token
                        except Exception:
                            pass

    async def _claude_stream(self, messages, model, system, temperature) -> AsyncIterator[str]:
        config = self._provider_config.get(LLMProvider.CLAUDE, {})
        api_key = config.get("api_key") or os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            yield "Error: Claude API key not configured"
            return
        import httpx
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        payload = {
            "model": model, "max_tokens": 4096, "messages": messages,
            "temperature": temperature, "stream": True,
        }
        if system:
            payload["system"] = system
        async with httpx.AsyncClient(timeout=120) as client:
            async with client.stream("POST", "https://api.anthropic.com/v1/messages",
                                     json=payload, headers=headers) as resp:
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        import json as _json
                        try:
                            data = _json.loads(line[6:])
                            if data.get("type") == "content_block_delta":
                                text = data.get("delta", {}).get("text", "")
                                if text:
                                    yield text
                        except Exception:
                            pass

    async def _openai_stream(self, messages, model, system, temperature) -> AsyncIterator[str]:
        config = self._provider_config.get(LLMProvider.OPENAI, {})
        api_key = config.get("api_key") or os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            yield "Error: OpenAI API key not configured"
            return
        import httpx
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.extend(messages)
        payload = {"model": model, "messages": msgs, "temperature": temperature, "stream": True}
        async with httpx.AsyncClient(timeout=120) as client:
            async with client.stream("POST", "https://api.openai.com/v1/chat/completions",
                                     json=payload, headers=headers) as resp:
                async for line in resp.aiter_lines():
                    if line.startswith("data: ") and line.strip() != "data: [DONE]":
                        import json as _json
                        try:
                            data = _json.loads(line[6:])
                            token = data["choices"][0].get("delta", {}).get("content", "")
                            if token:
                                yield token
                        except Exception:
                            pass

    def _get_model(self, provider: str) -> str:
        config = self._provider_config.get(provider, {})
        return config.get("model", DEFAULT_MODELS.get(LLMProvider(provider), ""))

    def _log_request(self, provider: str, model: str, elapsed_ms: float, success: bool,
                     category: str = None, grade: int = None):
        # Emit OTel span for each LLM call
        with trace_span("llm.request", {
            "llm.provider": provider, "llm.model": model or "default",
            "llm.elapsed_ms": elapsed_ms, "llm.success": success,
            "llm.category": category or "", "llm.grade": grade or 0,
        }):
            pass

        self._request_log.append({
            "timestamp": time.time(),
            "provider": provider,
            "model": model,
            "elapsed_ms": elapsed_ms,
            "success": success,
            "category": category,
        })
        if len(self._request_log) > 500:
            self._request_log = self._request_log[-500:]

        # Feed into model tracker if available
        if self._model_tracker and category:
            self._model_tracker.record(provider, model or "default", category,
                                       success, elapsed_ms, grade)

    def get_providers_status(self) -> dict:
        statuses = {}
        for p in LLMProvider:
            config = self._provider_config.get(p.value, {})
            circuit = self._circuit_state.get(p.value, {})
            statuses[p.value] = {
                "configured": bool(config.get("api_key") or (p == LLMProvider.OLLAMA and self.ollama)),
                "enabled": config.get("enabled", p == LLMProvider.OLLAMA),
                "model": config.get("model", DEFAULT_MODELS[p]),
                "connected": self.ollama.is_available if p == LLMProvider.OLLAMA and self.ollama else None,
                "circuit_breaker": "open" if self._is_circuit_open(p.value) else "closed",
                "consecutive_failures": circuit.get("failures", 0),
            }
        return {
            **statuses,
            "_failover_chain": [p.value for p in self._failover_chain],
        }

    def get_request_stats(self) -> dict:
        total = len(self._request_log)
        if total == 0:
            return {"total_requests": 0}
        success = sum(1 for r in self._request_log if r["success"])
        avg_ms = sum(r["elapsed_ms"] for r in self._request_log) / total
        by_provider = {}
        for r in self._request_log:
            p = r["provider"]
            by_provider[p] = by_provider.get(p, 0) + 1
        return {
            "total_requests": total,
            "success_rate": round(success / total * 100, 1),
            "avg_latency_ms": round(avg_ms, 1),
            "by_provider": by_provider,
        }
