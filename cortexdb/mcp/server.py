"""CortexDB MCP Server

CortexDB exposed as a Model Context Protocol server.
AI agents (Claude, LangGraph, OpenAI Agents) discover and use CortexDB
for cross-engine queries, semantic search, and agent-to-agent discovery.

Tools:
  cortexdb.query      - Execute CortexQL query (cross-engine)
  cortexdb.write      - Write data with fan-out (multi-engine)
  cortexdb.health     - Check system health
  cortexdb.blocks     - List/search blocks
  cortexdb.agents     - List/search agents
  cortexdb.ledger     - Verify/read immutable ledger
  cortexdb.cache      - Cache statistics
  cortexdb.a2a        - Discover agents via A2A
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("cortexdb.mcp")


@dataclass
class MCPToolDefinition:
    name: str
    description: str
    input_schema: Dict
    handler: Optional[Callable] = None


@dataclass
class MCPToolResult:
    content: Any = None
    is_error: bool = False
    error_message: str = ""


class CortexMCPServer:
    """MCP Server that exposes CortexDB as tools for AI agents.

    Usage:
        mcp = CortexMCPServer(db)
        result = await mcp.call_tool("cortexdb.query", {"cortexql": "SELECT * FROM blocks"})
    """

    def __init__(self, db=None):
        self.db = db
        self._tools: Dict[str, MCPToolDefinition] = {}
        self._cortexgraph = None
        self._register_tools()

    def _register_tools(self):
        self._tools = {
            "cortexdb.query": MCPToolDefinition(
                name="cortexdb.query",
                description="Execute a CortexQL query against CortexDB. Supports SQL, vector search, graph traversal, and stream queries.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "cortexql": {"type": "string", "description": "The CortexQL query to execute"},
                        "params": {"type": "object", "description": "Query parameters (optional)"},
                        "hint": {"type": "string", "description": "Query hint: 'cache_first', 'skip_semantic', 'force_refresh'"},
                    },
                    "required": ["cortexql"],
                }),
            "cortexdb.write": MCPToolDefinition(
                name="cortexdb.write",
                description="Write data to CortexDB with automatic fan-out to appropriate engines (relational, cache, audit, stream).",
                input_schema={
                    "type": "object",
                    "properties": {
                        "data_type": {"type": "string", "description": "Data type: payment, agent, task, block, heartbeat, audit, experience"},
                        "payload": {"type": "object", "description": "Data payload"},
                        "actor": {"type": "string", "description": "Actor performing the write"},
                    },
                    "required": ["data_type", "payload"],
                }),
            "cortexdb.health": MCPToolDefinition(
                name="cortexdb.health",
                description="Get CortexDB system health including all engine statuses, cache stats, and performance metrics.",
                input_schema={"type": "object", "properties": {}},
            ),
            "cortexdb.blocks.list": MCPToolDefinition(
                name="cortexdb.blocks.list",
                description="List available blocks (functions, skills, workflows, agent templates, solutions) in the block registry.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "block_type": {"type": "string", "enum": ["L0_function", "L1_skill", "L2_workflow", "L3_agent_template", "L4_solution"]},
                        "limit": {"type": "integer", "default": 50},
                    },
                }),
            "cortexdb.agents.list": MCPToolDefinition(
                name="cortexdb.agents.list",
                description="List agents registered in CortexDB with their state, health, and capabilities.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "state": {"type": "string", "enum": ["SPAWNED", "RUNNING", "WAITING", "COMPLETE", "FAILED"]},
                        "limit": {"type": "integer", "default": 50},
                    },
                }),
            "cortexdb.ledger.verify": MCPToolDefinition(
                name="cortexdb.ledger.verify",
                description="Verify the integrity of CortexDB's immutable audit ledger (SHA-256 hash chain).",
                input_schema={"type": "object", "properties": {}},
            ),
            "cortexdb.cache.stats": MCPToolDefinition(
                name="cortexdb.cache.stats",
                description="Get read cascade cache statistics: hit rates per tier (R0 process, R1 Redis, R2 semantic, R3 persistent).",
                input_schema={"type": "object", "properties": {}},
            ),
            "cortexdb.a2a.discover": MCPToolDefinition(
                name="cortexdb.a2a.discover",
                description="Discover agents by skill via A2A protocol. Semantic search for agents matching a capability description.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "skill": {"type": "string", "description": "Skill or capability to search for"},
                        "limit": {"type": "integer", "default": 5},
                    },
                    "required": ["skill"],
                }),
        }

    def list_tools(self) -> List[Dict]:
        """List all available MCP tools (for agent discovery)."""
        return [{"name": t.name, "description": t.description,
                 "inputSchema": t.input_schema}
                for t in self._tools.values()]

    async def call_tool(self, tool_name: str, arguments: Dict = None) -> MCPToolResult:
        """Execute an MCP tool call."""
        if tool_name not in self._tools:
            return MCPToolResult(is_error=True,
                                error_message=f"Unknown tool: {tool_name}")

        if not self.db:
            return MCPToolResult(is_error=True,
                                error_message="CortexDB not initialized")

        args = arguments or {}

        # Route CortexGraph tools
        if tool_name.startswith("cortexgraph."):
            return await self._handle_cortexgraph_tool(tool_name, args)

        try:
            if tool_name == "cortexdb.query":
                result = await self.db.query(
                    args["cortexql"], args.get("params"), args.get("hint"))
                return MCPToolResult(content={
                    "data": result.data, "tier_served": result.tier_served.value,
                    "engines_hit": result.engines_hit,
                    "latency_ms": round(result.latency_ms, 3),
                    "cache_hit": result.cache_hit})

            elif tool_name == "cortexdb.write":
                result = await self.db.write(
                    args["data_type"], args["payload"],
                    args.get("actor", "mcp_agent"))
                return MCPToolResult(content={"status": "success", "fan_out": result})

            elif tool_name == "cortexdb.health":
                result = await self.db.health()
                return MCPToolResult(content=result)

            elif tool_name == "cortexdb.blocks.list":
                params = []
                query = "SELECT * FROM blocks WHERE status = 'active'"
                block_type = args.get("block_type")
                if block_type:
                    if not all(c.isalnum() or c in '-_' for c in str(block_type)):
                        return MCPToolResult(content={"error": "Invalid block_type"})
                    params.append(str(block_type))
                    query += f" AND block_type = ${len(params)}"
                limit = max(1, min(int(args.get("limit", 50)), 500))
                params.append(limit)
                query += f" LIMIT ${len(params)}"
                result = await self.db.query(query, params=params)
                return MCPToolResult(content={"blocks": result.data})

            elif tool_name == "cortexdb.agents.list":
                params = []
                query = "SELECT * FROM agents"
                state = args.get("state")
                if state:
                    valid = {"idle", "running", "paused", "stopped", "error", "active"}
                    if str(state) not in valid:
                        return MCPToolResult(content={"error": f"Invalid state: {valid}"})
                    params.append(str(state))
                    query += f" WHERE state = ${len(params)}"
                limit = max(1, min(int(args.get("limit", 50)), 500))
                params.append(limit)
                query += f" LIMIT ${len(params)}"
                result = await self.db.query(query, params=params)
                return MCPToolResult(content={"agents": result.data})

            elif tool_name == "cortexdb.ledger.verify":
                if "immutable" in self.db.engines:
                    intact = await self.db.engines["immutable"].verify_chain()
                    return MCPToolResult(content={
                        "chain_intact": intact,
                        "entries": len(self.db.engines["immutable"]._chain)})
                return MCPToolResult(content={"error": "ImmutableCore not connected"})

            elif tool_name == "cortexdb.cache.stats":
                stats = self.db.read_cascade.stats if self.db.read_cascade else {}
                return MCPToolResult(content=stats)

            elif tool_name == "cortexdb.a2a.discover":
                return MCPToolResult(content={
                    "agents": [], "query": args.get("skill"),
                    "note": "A2A discovery requires VectorCore with agent embeddings"})

        except Exception as e:
            logger.error(f"MCP tool error [{tool_name}]: {e}")
            return MCPToolResult(is_error=True, error_message=str(e))

    def register_cortexgraph_tools(self, insights):
        """Register CortexGraph MCP tools from the insights engine."""
        self._cortexgraph = insights
        for tool_def in insights.get_mcp_tools():
            self._tools[tool_def["name"]] = MCPToolDefinition(
                name=tool_def["name"],
                description=tool_def["description"],
                input_schema=tool_def["inputSchema"],
            )

    async def _handle_cortexgraph_tool(self, tool_name: str, args: Dict) -> MCPToolResult:
        """Handle CortexGraph MCP tool calls."""
        if not self._cortexgraph:
            return MCPToolResult(is_error=True, error_message="CortexGraph not initialized")

        try:
            if tool_name == "cortexgraph.customer_360":
                result = await self._cortexgraph.customer_360(
                    args["customer_id"], args.get("tenant_id"))
                return MCPToolResult(content=result)

            elif tool_name == "cortexgraph.similar_customers":
                result = await self._cortexgraph.find_similar_customers(
                    args["customer_id"], args.get("limit", 50))
                return MCPToolResult(content=result)

            elif tool_name == "cortexgraph.churn_risk":
                result = await self._cortexgraph.get_churn_risk_customers(
                    args.get("threshold", 0.7), limit=args.get("limit", 50))
                return MCPToolResult(content=result)

            elif tool_name == "cortexgraph.recommend_products":
                result = await self._cortexgraph.recommend_products(
                    args["customer_id"], args.get("limit", 5))
                return MCPToolResult(content=result)

            elif tool_name == "cortexgraph.attribution":
                result = await self._cortexgraph.campaign_attribution(args["campaign_id"])
                return MCPToolResult(content=result)

            return MCPToolResult(is_error=True, error_message=f"Unknown CortexGraph tool: {tool_name}")
        except Exception as e:
            logger.error(f"CortexGraph MCP tool error [{tool_name}]: {e}")
            return MCPToolResult(is_error=True, error_message=str(e))

    def get_server_info(self) -> Dict:
        return {
            "name": "cortexdb",
            "version": "3.0.0",
            "protocol": "MCP",
            "tools_count": len(self._tools),
            "capabilities": ["query", "write", "health", "blocks", "agents",
                             "ledger", "cache", "a2a", "cortexgraph"],
        }
