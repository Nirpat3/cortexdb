"""MCP tools and REST endpoint stubs for the Ops Learning Loop.

MCP tools:   ops.get_config, ops.set_config, ops.config_snapshot, ops.emit_signal
REST routes: GET /ops/config/{key}, PUT /ops/config/{key},
             POST /ops/config/snapshot, POST /ops/signals
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger("cortexdb.ops_learning.endpoints")


# ---------------------------------------------------------------------------
# MCP tool definitions (register via CortexMCPServer.register_ops_tools)
# ---------------------------------------------------------------------------

OPS_MCP_TOOLS = [
    {
        "name": "ops.get_config",
        "description": "Get the current value of an operational config key.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "Config key (e.g. cache.ttl_seconds)"},
            },
            "required": ["key"],
        },
    },
    {
        "name": "ops.set_config",
        "description": "Set an operational config key (validates against safe ranges).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "Config key"},
                "value": {"description": "New value (must be within safe range)"},
                "actor": {"type": "string", "description": "Who is making the change", "default": "mcp"},
            },
            "required": ["key", "value"],
        },
    },
    {
        "name": "ops.config_snapshot",
        "description": "Take a point-in-time snapshot of all operational config.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "note": {"type": "string", "description": "Optional note for the snapshot"},
                "actor": {"type": "string", "default": "mcp"},
            },
        },
    },
    {
        "name": "ops.emit_signal",
        "description": "Emit an operational signal (latency, error_rate, cache_hit, queue_depth).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "signal_type": {
                    "type": "string",
                    "description": "Signal type",
                    "enum": ["ops.latency", "ops.error_rate", "ops.cache_hit", "ops.queue_depth"],
                },
                "payload": {"type": "object", "description": "Signal payload"},
            },
            "required": ["signal_type", "payload"],
        },
    },
]


# ---------------------------------------------------------------------------
# MCP handler (wire into CortexMCPServer)
# ---------------------------------------------------------------------------

class OpsMCPHandler:
    """Handles MCP tool calls for ops learning tools."""

    def __init__(self, config_store, signal_emitter):
        self.config_store = config_store
        self.signal_emitter = signal_emitter

    async def handle(self, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """Dispatch an MCP tool call.  Returns ``{content, is_error}``."""
        try:
            if tool_name == "ops.get_config":
                value = await self.config_store.get(args["key"])
                return {"content": {"key": args["key"], "value": value}, "is_error": False}

            elif tool_name == "ops.set_config":
                await self.config_store.set(
                    args["key"], args["value"], actor=args.get("actor", "mcp")
                )
                return {"content": {"ok": True, "key": args["key"], "value": args["value"]}, "is_error": False}

            elif tool_name == "ops.config_snapshot":
                version = await self.config_store.snapshot(
                    actor=args.get("actor", "mcp"),
                    note=args.get("note", ""),
                )
                return {"content": {"version": version}, "is_error": False}

            elif tool_name == "ops.emit_signal":
                msg_id = await self.signal_emitter.emit(
                    args["signal_type"], args["payload"]
                )
                return {"content": {"stream_id": msg_id}, "is_error": False}

            return {"content": None, "is_error": True, "error_message": f"Unknown tool: {tool_name}"}

        except ValueError as exc:
            return {"content": None, "is_error": True, "error_message": str(exc)}
        except Exception as exc:
            logger.exception("Ops MCP handler error for %s", tool_name)
            return {"content": None, "is_error": True, "error_message": f"Internal error: {exc}"}


# ---------------------------------------------------------------------------
# FastAPI REST routes (mount on the main app)
# ---------------------------------------------------------------------------

def create_ops_router(config_store, signal_emitter):
    """Return a FastAPI APIRouter with ops learning endpoints.

    Usage::

        from cortexdb.core.ops_learning.endpoints import create_ops_router
        app.include_router(create_ops_router(config_store, emitter), prefix="/ops")
    """
    from fastapi import APIRouter, HTTPException
    from pydantic import BaseModel
    from typing import Any as TypAny, Optional as TypOpt

    router = APIRouter(tags=["ops-learning"])

    class SetConfigBody(BaseModel):
        value: TypAny
        actor: str = "api"

    class SnapshotBody(BaseModel):
        note: str = ""
        actor: str = "api"

    class EmitSignalBody(BaseModel):
        signal_type: str
        payload: dict

    @router.get("/config/{key}")
    async def get_config(key: str):
        value = await config_store.get(key)
        if value is None:
            raise HTTPException(404, f"Config key {key!r} not found")
        return {"key": key, "value": value}

    @router.put("/config/{key}")
    async def set_config(key: str, body: SetConfigBody):
        try:
            await config_store.set(key, body.value, actor=body.actor)
        except ValueError as exc:
            raise HTTPException(422, str(exc))
        return {"ok": True, "key": key, "value": body.value}

    @router.post("/config/snapshot")
    async def take_snapshot(body: SnapshotBody):
        version = await config_store.snapshot(actor=body.actor, note=body.note)
        return {"version": version}

    @router.post("/signals")
    async def emit_signal(body: EmitSignalBody):
        msg_id = await signal_emitter.emit(body.signal_type, body.payload)
        return {"stream_id": msg_id}

    return router
