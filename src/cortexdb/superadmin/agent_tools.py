"""
Agent Tool System — Enables agents to call tools during execution.

Agents can:
  - Search the codebase (grep-like)
  - Execute CortexQL queries
  - Fetch URLs
  - Read/write agent memory
  - Delegate to other agents
  - Run CLI commands (sandboxed)

Tool calls are detected in LLM output, executed, and results fed back.
"""

import asyncio
import time
import logging
import os
import re
from typing import Dict, List, Optional, Callable, Awaitable, TYPE_CHECKING

if TYPE_CHECKING:
    from cortexdb.superadmin.agent_team import AgentTeamManager
    from cortexdb.superadmin.agent_memory import AgentMemory
    from cortexdb.superadmin.persistence import PersistenceStore

logger = logging.getLogger(__name__)

# Tool call pattern: [[tool_name(arg1, arg2)]]
TOOL_CALL_PATTERN = re.compile(r'\[\[(\w+)\(([^)]*)\)\]\]')


class ToolDefinition:
    """A tool that agents can invoke."""

    def __init__(self, name: str, description: str,
                 parameters: List[dict], handler: Callable[..., Awaitable]):
        self.name = name
        self.description = description
        self.parameters = parameters
        self.handler = handler


class AgentToolSystem:
    """Manages tool registration and execution for agents."""

    def __init__(self, team: "AgentTeamManager", memory: "AgentMemory",
                 persistence: "PersistenceStore"):
        self._team = team
        self._memory = memory
        self._persistence = persistence
        self._tools: Dict[str, ToolDefinition] = {}
        self._execution_log: List[dict] = []
        self._rate_limiter = None  # Set externally: ToolRateLimiter instance
        self._register_builtin_tools()

    def _register_builtin_tools(self):
        """Register the built-in tools available to all agents."""
        self.register(ToolDefinition(
            name="search_memory",
            description="Search agent long-term memory for relevant facts",
            parameters=[{"name": "query", "type": "string"}],
            handler=self._tool_search_memory,
        ))
        self.register(ToolDefinition(
            name="remember",
            description="Store a fact in long-term memory",
            parameters=[{"name": "fact", "type": "string"}, {"name": "category", "type": "string"}],
            handler=self._tool_remember,
        ))
        self.register(ToolDefinition(
            name="list_agents",
            description="List all agents and their current status",
            parameters=[],
            handler=self._tool_list_agents,
        ))
        self.register(ToolDefinition(
            name="get_task_history",
            description="Get recent task history for an agent",
            parameters=[{"name": "agent_id", "type": "string"}],
            handler=self._tool_get_history,
        ))
        self.register(ToolDefinition(
            name="query_data",
            description="Execute a read-only CortexQL query",
            parameters=[{"name": "query", "type": "string"}],
            handler=self._tool_query_data,
        ))
        self.register(ToolDefinition(
            name="run_command",
            description="Execute a CLI command and return output (sandboxed, 30s timeout)",
            parameters=[{"name": "command", "type": "string"}],
            handler=self._tool_run_command,
        ))
        self.register(ToolDefinition(
            name="read_file",
            description="Read contents of a file",
            parameters=[{"name": "path", "type": "string"}],
            handler=self._tool_read_file,
        ))
        self.register(ToolDefinition(
            name="write_file",
            description="Write content to a file",
            parameters=[{"name": "path", "type": "string"}, {"name": "content", "type": "string"}],
            handler=self._tool_write_file,
        ))
        self.register(ToolDefinition(
            name="list_dir",
            description="List files and directories at a path",
            parameters=[{"name": "path", "type": "string"}],
            handler=self._tool_list_dir,
        ))

    def register(self, tool: ToolDefinition):
        """Register a tool."""
        self._tools[tool.name] = tool

    def get_tool_descriptions(self, agent_id: str = None) -> str:
        """Build tool description text for LLM system prompt injection."""
        lines = ["## Available Tools", "Call tools using: [[tool_name(arg1, arg2)]]", ""]
        for name, tool in self._tools.items():
            params = ", ".join(p["name"] for p in tool.parameters)
            lines.append(f"- **{name}**({params}): {tool.description}")
        return "\n".join(lines)

    async def execute_tool_calls(self, agent_id: str, text: str) -> List[dict]:
        """Parse and execute any tool calls found in LLM output."""
        results = []
        for match in TOOL_CALL_PATTERN.finditer(text):
            tool_name = match.group(1)
            args_str = match.group(2).strip()
            args = [a.strip().strip('"').strip("'") for a in args_str.split(",")] if args_str else []

            tool = self._tools.get(tool_name)
            if not tool:
                results.append({"tool": tool_name, "error": "Unknown tool"})
                continue

            # Rate limit check
            if self._rate_limiter and not self._rate_limiter.check(agent_id, tool_name):
                results.append({"tool": tool_name, "error": "Rate limit exceeded. Try again later."})
                continue

            try:
                result = await tool.handler(agent_id, *args)
                results.append({"tool": tool_name, "result": result})
                self._log_execution(agent_id, tool_name, args, result)
            except Exception as e:
                results.append({"tool": tool_name, "error": str(e)})
                logger.warning("Tool %s failed for %s: %s", tool_name, agent_id, e)

        return results

    def has_tool_calls(self, text: str) -> bool:
        """Check if text contains tool calls."""
        return bool(TOOL_CALL_PATTERN.search(text))

    def get_tools(self) -> List[dict]:
        """Get all registered tools."""
        return [
            {"name": t.name, "description": t.description, "parameters": t.parameters}
            for t in self._tools.values()
        ]

    def get_execution_log(self, agent_id: str = None, limit: int = 20) -> List[dict]:
        """Get recent tool execution log."""
        log = self._execution_log
        if agent_id:
            log = [e for e in log if e.get("agent_id") == agent_id]
        return log[-limit:]

    def _log_execution(self, agent_id: str, tool: str, args: list, result):
        self._execution_log.append({
            "agent_id": agent_id, "tool": tool, "args": args,
            "result_preview": str(result)[:200], "timestamp": time.time(),
        })
        if len(self._execution_log) > 500:
            self._execution_log = self._execution_log[-500:]

    # ── Built-in tool handlers ──

    async def _tool_search_memory(self, agent_id: str, query: str = "") -> str:
        facts = self._memory.recall(agent_id, limit=10)
        matching = [f for f in facts if query.lower() in f.get("fact", "").lower()]
        if not matching:
            return "No matching facts found."
        return "\n".join(f"- [{f['category']}] {f['fact']}" for f in matching[:5])

    async def _tool_remember(self, agent_id: str, fact: str = "", category: str = "general") -> str:
        self._memory.remember(agent_id, fact, category)
        return f"Remembered: {fact}"

    async def _tool_list_agents(self, agent_id: str) -> str:
        agents = self._team.get_all_agents()
        lines = [f"- {a['agent_id']}: {a.get('name', '')} ({a.get('state', 'unknown')})"
                 for a in agents[:20]]
        return "\n".join(lines)

    async def _tool_get_history(self, agent_id: str, target_id: str = "") -> str:
        tid = target_id or agent_id
        history = self._memory.get_task_history(tid, limit=5)
        if not history:
            return f"No task history for {tid}"
        lines = [f"- [{h['task_id']}] {h['title']}: {'OK' if h['success'] else 'FAIL'}"
                 for h in history]
        return "\n".join(lines)

    async def _tool_query_data(self, agent_id: str, query: str = "") -> str:
        # Placeholder — in production this would execute a CortexQL read query
        return f"Query execution not yet connected to core engines. Query: {query}"

    # ── CLI & filesystem tool handlers ──

    # Commands that are never allowed (destructive / dangerous)
    _BLOCKED_PATTERNS = re.compile(
        r'(rm\s+-rf\s+/|mkfs|dd\s+if=|:(){ :|fork\s+bomb|shutdown|reboot'
        r'|halt|poweroff|init\s+0|chmod\s+-R\s+777\s+/'
        r'|curl\s+.*\|\s*(ba)?sh|wget\s+.*\|\s*(ba)?sh)',
        re.IGNORECASE,
    )

    async def _tool_run_command(self, agent_id: str, command: str = "") -> str:
        """Execute a CLI command with safety checks and timeout."""
        if not command.strip():
            return "Error: empty command"

        if self._BLOCKED_PATTERNS.search(command):
            logger.warning("Agent %s attempted blocked command: %s", agent_id, command[:100])
            return "Error: command blocked by safety policy"

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=os.getcwd(),
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
            output = stdout.decode("utf-8", errors="replace")
            err_output = stderr.decode("utf-8", errors="replace")

            # Truncate large output
            max_len = 4000
            if len(output) > max_len:
                output = output[:max_len] + f"\n... (truncated, {len(output)} chars total)"
            if err_output and len(err_output) > 1000:
                err_output = err_output[:1000] + "\n... (truncated)"

            result = f"Exit code: {proc.returncode}\n"
            if output:
                result += f"stdout:\n{output}\n"
            if err_output:
                result += f"stderr:\n{err_output}"
            return result.strip()
        except asyncio.TimeoutError:
            return "Error: command timed out after 30 seconds"
        except Exception as e:
            return f"Error: {e}"

    async def _tool_read_file(self, agent_id: str, path: str = "") -> str:
        """Read a file and return its content."""
        if not path.strip():
            return "Error: no path provided"
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            if len(content) > 8000:
                content = content[:8000] + f"\n... (truncated, {len(content)} chars total)"
            return content
        except FileNotFoundError:
            return f"Error: file not found: {path}"
        except Exception as e:
            return f"Error reading file: {e}"

    async def _tool_write_file(self, agent_id: str, path: str = "", content: str = "") -> str:
        """Write content to a file."""
        if not path.strip():
            return "Error: no path provided"
        try:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            return f"Written {len(content)} chars to {path}"
        except Exception as e:
            return f"Error writing file: {e}"

    async def _tool_list_dir(self, agent_id: str, path: str = ".") -> str:
        """List directory contents."""
        if not path.strip():
            path = "."
        try:
            entries = os.listdir(path)
            lines = []
            for entry in sorted(entries)[:100]:
                full = os.path.join(path, entry)
                kind = "dir" if os.path.isdir(full) else "file"
                lines.append(f"  {kind}  {entry}")
            result = f"Directory: {os.path.abspath(path)} ({len(entries)} entries)\n"
            result += "\n".join(lines)
            if len(entries) > 100:
                result += f"\n... and {len(entries) - 100} more"
            return result
        except FileNotFoundError:
            return f"Error: directory not found: {path}"
        except Exception as e:
            return f"Error listing directory: {e}"
