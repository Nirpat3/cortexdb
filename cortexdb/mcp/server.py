"""CortexDB MCP Server

CortexDB exposed as a Model Context Protocol server.
AI agents (Claude, LangGraph, OpenAI Agents) discover and use CortexDB
for cross-engine queries, semantic search, and agent-to-agent discovery.

Tools:
  cortexdb.query        - Execute CortexQL query (cross-engine)
  cortexdb.write        - Write data with fan-out (multi-engine)
  cortexdb.health       - Check system health
  cortexdb.blocks       - List/search blocks
  cortexdb.agents       - List/search agents
  cortexdb.ledger       - Verify/read immutable ledger
  cortexdb.cache        - Cache statistics
  cortexdb.a2a          - Discover agents via A2A
  cortexdb.memory.store - Store an agent memory
  cortexdb.memory.recall - Recall relevant agent memories
  cortexdb.memory.forget - GDPR-compliant memory deletion
  cortexdb.memory.share  - Share a memory with other agents
  cortexdb.rag.ingest    - Ingest a document for RAG
  cortexdb.rag.retrieve  - Retrieve relevant context for a query
  cortexdb.rag.smart_retrieve - Intelligent retrieval with query understanding + feedback loop
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
                        "tenant_id": {"type": "string", "description": "Tenant ID for isolation (required in multi-tenant mode)"},
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
                        "tenant_id": {"type": "string", "description": "Tenant ID for isolation (required in multi-tenant mode)"},
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
                        "state": {"type": "string", "enum": ["idle", "running", "paused", "stopped", "error", "active"]},
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
            # ── Agent Memory Protocol tools ───────────────────────────
            "cortexdb.memory.store": MCPToolDefinition(
                name="cortexdb.memory.store",
                description="Store a memory for an AI agent. Auto-embeds content for semantic recall, indexes across PostgreSQL and Qdrant, and caches working memory in Redis.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "agent_id": {"type": "string", "description": "The agent storing the memory"},
                        "content": {"type": "string", "description": "Text content of the memory"},
                        "memory_type": {"type": "string", "enum": ["episodic", "semantic", "working"], "default": "episodic",
                                        "description": "Memory type: episodic (events, auto-decays), semantic (facts, stable), working (short-term, Redis-backed)"},
                        "metadata": {"type": "object", "description": "Optional metadata (JSON object)"},
                        "tenant_id": {"type": "string", "description": "Tenant ID for isolation"},
                        "ttl_seconds": {"type": "integer", "description": "Time-to-live in seconds (auto-set for working memory)"},
                        "importance": {"type": "number", "description": "Relevance weight 0.0-1.0 (default 0.5)"},
                    },
                    "required": ["agent_id", "content"],
                }),
            "cortexdb.memory.recall": MCPToolDefinition(
                name="cortexdb.memory.recall",
                description="Recall relevant memories for an AI agent via semantic search with time decay. Searches owned and shared memories across Qdrant and Redis.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "agent_id": {"type": "string", "description": "The agent recalling memories"},
                        "query": {"type": "string", "description": "Natural-language query to match against memories"},
                        "memory_type": {"type": "string", "enum": ["episodic", "semantic", "working"],
                                        "description": "Filter by memory type (optional)"},
                        "limit": {"type": "integer", "default": 10, "description": "Max memories to return (1-100)"},
                        "time_decay": {"type": "boolean", "default": True, "description": "Apply time decay (newer memories score higher)"},
                        "include_shared": {"type": "boolean", "default": True, "description": "Include memories shared with this agent"},
                        "tenant_id": {"type": "string", "description": "Tenant ID for isolation"},
                    },
                    "required": ["agent_id", "query"],
                }),
            "cortexdb.memory.forget": MCPToolDefinition(
                name="cortexdb.memory.forget",
                description="GDPR-compliant memory deletion. Removes agent memories from PostgreSQL, Qdrant, and Redis. Specify at least one of memory_id, before, or memory_type.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "agent_id": {"type": "string", "description": "The agent whose memories to delete"},
                        "memory_id": {"type": "string", "description": "Delete a specific memory by UUID"},
                        "before": {"type": "number", "description": "Delete all memories created before this Unix timestamp"},
                        "memory_type": {"type": "string", "enum": ["episodic", "semantic", "working"],
                                        "description": "Delete all memories of this type"},
                        "tenant_id": {"type": "string", "description": "Tenant ID for isolation"},
                    },
                    "required": ["agent_id"],
                }),
            "cortexdb.memory.share": MCPToolDefinition(
                name="cortexdb.memory.share",
                description="Share an agent memory with other agents. Only the owning agent can share. Updates ACL in PostgreSQL and Qdrant.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "agent_id": {"type": "string", "description": "The owning agent's ID"},
                        "memory_id": {"type": "string", "description": "The memory UUID to share"},
                        "target_agent_ids": {"type": "array", "items": {"type": "string"},
                                             "description": "List of agent IDs to grant access"},
                        "tenant_id": {"type": "string", "description": "Tenant ID for isolation"},
                    },
                    "required": ["agent_id", "memory_id", "target_agent_ids"],
                }),
            # ── RAG Pipeline tools ────────────────────────────────────
            "cortexdb.rag.ingest": MCPToolDefinition(
                name="cortexdb.rag.ingest",
                description="Ingest a document for RAG. Chunks the text, embeds each chunk, and stores in PostgreSQL + Qdrant for semantic retrieval.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "The document text to ingest"},
                        "doc_id": {"type": "string", "description": "Unique document identifier"},
                        "collection": {"type": "string", "default": "documents",
                                       "description": "Collection name for organizing documents"},
                        "metadata": {"type": "object", "description": "Optional metadata (JSON object)"},
                        "tenant_id": {"type": "string", "description": "Tenant ID for isolation"},
                    },
                    "required": ["text", "doc_id"],
                }),
            "cortexdb.rag.retrieve": MCPToolDefinition(
                name="cortexdb.rag.retrieve",
                description="Retrieve relevant document chunks for a query via semantic search. Returns ranked context formatted for LLM consumption with token budget control.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Natural-language query to match against document chunks"},
                        "collection": {"type": "string", "default": "documents",
                                       "description": "Collection to search in"},
                        "limit": {"type": "integer", "default": 5,
                                  "description": "Max chunks to return (1-50)"},
                        "threshold": {"type": "number", "default": 0.75,
                                      "description": "Minimum similarity threshold (0.0-1.0)"},
                        "max_tokens": {"type": "integer", "default": 4000,
                                       "description": "Maximum tokens in the context window"},
                        "smart": {"type": "boolean", "default": False,
                                  "description": "Enable intelligent retrieval with query understanding and feedback loop"},
                        "tenant_id": {"type": "string", "description": "Tenant ID for isolation"},
                    },
                    "required": ["query"],
                }),
            "cortexdb.rag.smart_retrieve": MCPToolDefinition(
                name="cortexdb.rag.smart_retrieve",
                description="Intelligent RAG retrieval. Analyzes query intent, generates multi-query variants, scores retrieval confidence, auto-reformulates on low confidence, verifies answer grounding, and returns citations.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Natural-language query"},
                        "collection": {"type": "string", "default": "documents"},
                        "limit": {"type": "integer", "default": 5},
                        "threshold": {"type": "number", "default": 0.75,
                                      "description": "Minimum similarity threshold"},
                        "feedback_loop": {"type": "boolean", "default": True,
                                          "description": "Auto-reformulate when confidence is low"},
                        "tenant_id": {"type": "string"},
                    },
                    "required": ["query"],
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
                    args["cortexql"], args.get("params"), args.get("hint"),
                    tenant_id=args.get("tenant_id"))
                return MCPToolResult(content={
                    "data": result.data, "tier_served": result.tier_served.value,
                    "engines_hit": result.engines_hit,
                    "latency_ms": round(result.latency_ms, 3),
                    "cache_hit": result.cache_hit})

            elif tool_name == "cortexdb.write":
                result = await self.db.write(
                    args["data_type"], args["payload"],
                    args.get("actor", "mcp_agent"),
                    tenant_id=args.get("tenant_id"))
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

            # ── Agent Memory Protocol handlers ────────────────────
            elif tool_name == "cortexdb.memory.store":
                if not self.db.agent_memory:
                    return MCPToolResult(is_error=True,
                                        error_message="Agent Memory not initialized")
                result = await self.db.agent_memory.store(
                    agent_id=args["agent_id"],
                    content=args["content"],
                    memory_type=args.get("memory_type", "episodic"),
                    metadata=args.get("metadata"),
                    tenant_id=args.get("tenant_id"),
                    ttl_seconds=args.get("ttl_seconds"),
                    importance=float(args.get("importance", 0.5)),
                )
                return MCPToolResult(content=result)

            elif tool_name == "cortexdb.memory.recall":
                if not self.db.agent_memory:
                    return MCPToolResult(is_error=True,
                                        error_message="Agent Memory not initialized")
                result = await self.db.agent_memory.recall(
                    agent_id=args["agent_id"],
                    query=args["query"],
                    memory_type=args.get("memory_type"),
                    limit=int(args.get("limit", 10)),
                    time_decay=args.get("time_decay", True),
                    include_shared=args.get("include_shared", True),
                    tenant_id=args.get("tenant_id"),
                )
                return MCPToolResult(content={"memories": result, "count": len(result)})

            elif tool_name == "cortexdb.memory.forget":
                if not self.db.agent_memory:
                    return MCPToolResult(is_error=True,
                                        error_message="Agent Memory not initialized")
                result = await self.db.agent_memory.forget(
                    agent_id=args["agent_id"],
                    memory_id=args.get("memory_id"),
                    before=args.get("before"),
                    memory_type=args.get("memory_type"),
                    tenant_id=args.get("tenant_id"),
                )
                return MCPToolResult(content=result)

            elif tool_name == "cortexdb.memory.share":
                if not self.db.agent_memory:
                    return MCPToolResult(is_error=True,
                                        error_message="Agent Memory not initialized")
                result = await self.db.agent_memory.share(
                    agent_id=args["agent_id"],
                    memory_id=args["memory_id"],
                    target_agent_ids=args["target_agent_ids"],
                    tenant_id=args.get("tenant_id"),
                )
                return MCPToolResult(content=result)

            # ── RAG Pipeline handlers ─────────────────────────────
            elif tool_name == "cortexdb.rag.ingest":
                if not self.db.rag:
                    return MCPToolResult(is_error=True,
                                        error_message="RAG pipeline not initialized")
                result = await self.db.rag.ingest(
                    text=args["text"],
                    doc_id=args["doc_id"],
                    collection=args.get("collection", "documents"),
                    metadata=args.get("metadata"),
                    tenant_id=args.get("tenant_id"),
                )
                return MCPToolResult(content=result)

            elif tool_name == "cortexdb.rag.retrieve":
                if not self.db.rag:
                    return MCPToolResult(is_error=True,
                                        error_message="RAG pipeline not initialized")
                result = await self.db.rag.retrieve_with_context(
                    query=args["query"],
                    collection=args.get("collection", "documents"),
                    limit=int(args.get("limit", 5)),
                    threshold=float(args.get("threshold", 0.75)),
                    max_tokens=int(args.get("max_tokens", 4000)),
                    tenant_id=args.get("tenant_id"),
                    smart=bool(args.get("smart", False)),
                )
                return MCPToolResult(content=result)

            elif tool_name == "cortexdb.rag.smart_retrieve":
                if not self.db.rag:
                    return MCPToolResult(is_error=True,
                                        error_message="RAG pipeline not initialized")
                result = await self.db.rag.smart_retrieve(
                    query=args["query"],
                    collection=args.get("collection", "documents"),
                    limit=int(args.get("limit", 5)),
                    threshold=float(args.get("threshold", 0.75)),
                    tenant_id=args.get("tenant_id"),
                    use_feedback_loop=bool(args.get("feedback_loop", True)),
                )
                return MCPToolResult(content=result)

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
                             "ledger", "cache", "a2a", "cortexgraph", "memory", "rag"],
        }
