"""
Autonomy Loop — Enables agents to work autonomously.

Agents can:
  - Pick pending tasks from their queue
  - Execute tasks using LLM + tools
  - Delegate subtasks to other agents
  - Report results and update task status
  - Run continuously or on-demand
"""

import asyncio
import time
import logging
import json
from typing import Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from cortexdb.superadmin.agent_team import AgentTeamManager
    from cortexdb.superadmin.llm_router import LLMRouter
    from cortexdb.superadmin.agent_memory import AgentMemory
    from cortexdb.superadmin.agent_tools import AgentToolSystem
    from cortexdb.superadmin.persistence import PersistenceStore
    from cortexdb.superadmin.cost_tracker import CostTracker

logger = logging.getLogger(__name__)


class AutonomyConfig:
    """Per-agent autonomy configuration."""

    def __init__(
        self,
        enabled: bool = False,
        max_tasks_per_cycle: int = 3,
        cycle_interval_s: float = 60,
        allowed_tools: Optional[List[str]] = None,
        can_delegate: bool = True,
        auto_execute: bool = False,
        max_cost_per_cycle: float = 0.50,
    ):
        self.enabled = enabled
        self.max_tasks_per_cycle = max_tasks_per_cycle
        self.cycle_interval_s = cycle_interval_s
        self.allowed_tools = allowed_tools  # None = all tools
        self.can_delegate = can_delegate
        self.auto_execute = auto_execute
        self.max_cost_per_cycle = max_cost_per_cycle


class AutonomyLoop:
    """Manages autonomous agent execution cycles."""

    def __init__(self, team, router, memory, tool_system, persistence, cost_tracker=None):
        self._team = team
        self._router = router
        self._memory = memory
        self._tools = tool_system
        self._persistence = persistence
        self._cost_tracker = cost_tracker
        self._configs: Dict[str, AutonomyConfig] = {}
        self._running: Dict[str, bool] = {}  # agent_id -> is_running
        self._cycle_history: List[dict] = []  # recent cycle results
        self._tasks: Dict[str, asyncio.Task] = {}  # background tasks

    def configure_agent(self, agent_id: str, config: dict) -> dict:
        """Set autonomy configuration for an agent."""
        self._configs[agent_id] = AutonomyConfig(
            enabled=config.get("enabled", False),
            max_tasks_per_cycle=config.get("max_tasks_per_cycle", 3),
            cycle_interval_s=config.get("cycle_interval_s", 60),
            allowed_tools=config.get("allowed_tools"),
            can_delegate=config.get("can_delegate", True),
            auto_execute=config.get("auto_execute", False),
            max_cost_per_cycle=config.get("max_cost_per_cycle", 0.50),
        )
        # Persist config in kv_store
        self._persistence.kv_set(f"autonomy_config:{agent_id}", config)
        return {"agent_id": agent_id, "config": config}

    def get_config(self, agent_id: str) -> dict:
        """Get autonomy config for an agent."""
        # Try memory first, then kv_store
        cfg = self._configs.get(agent_id)
        if not cfg:
            stored = self._persistence.kv_get(f"autonomy_config:{agent_id}", None)
            if stored:
                self._configs[agent_id] = AutonomyConfig(**stored)
                cfg = self._configs[agent_id]
        if not cfg:
            return {"agent_id": agent_id, "enabled": False}
        return {
            "agent_id": agent_id,
            "enabled": cfg.enabled,
            "max_tasks_per_cycle": cfg.max_tasks_per_cycle,
            "cycle_interval_s": cfg.cycle_interval_s,
            "allowed_tools": cfg.allowed_tools,
            "can_delegate": cfg.can_delegate,
            "auto_execute": cfg.auto_execute,
            "max_cost_per_cycle": cfg.max_cost_per_cycle,
        }

    async def start_agent(self, agent_id: str) -> dict:
        """Start autonomous loop for an agent."""
        cfg = self._configs.get(agent_id)
        if not cfg or not cfg.enabled:
            return {"error": "Autonomy not enabled for this agent"}
        if self._running.get(agent_id):
            return {"error": "Agent already running autonomously"}

        self._running[agent_id] = True
        task = asyncio.create_task(self._run_loop(agent_id))
        self._tasks[agent_id] = task
        logger.info("Started autonomy loop for %s", agent_id)
        return {"agent_id": agent_id, "status": "started"}

    async def stop_agent(self, agent_id: str) -> dict:
        """Stop autonomous loop for an agent."""
        self._running[agent_id] = False
        task = self._tasks.pop(agent_id, None)
        if task and not task.done():
            task.cancel()
        logger.info("Stopped autonomy loop for %s", agent_id)
        return {"agent_id": agent_id, "status": "stopped"}

    async def run_single_cycle(self, agent_id: str) -> dict:
        """Run one autonomy cycle for an agent (on-demand)."""
        return await self._execute_cycle(agent_id)

    async def _run_loop(self, agent_id: str):
        """Background loop that runs cycles at the configured interval."""
        cfg = self._configs.get(agent_id)
        if not cfg:
            return

        while self._running.get(agent_id):
            try:
                result = await self._execute_cycle(agent_id)
                self._cycle_history.append(result)
                if len(self._cycle_history) > 200:
                    self._cycle_history = self._cycle_history[-200:]
            except Exception as e:
                logger.error("Autonomy cycle failed for %s: %s", agent_id, e)

            await asyncio.sleep(cfg.cycle_interval_s)

    async def _execute_cycle(self, agent_id: str) -> dict:
        """Execute one autonomy cycle: pick tasks, execute, report."""
        cfg = self._configs.get(agent_id, AutonomyConfig())
        agent = self._team.get_agent(agent_id)
        if not agent:
            return {"agent_id": agent_id, "error": "Agent not found"}

        start = time.time()

        # 1. Get pending tasks for this agent
        pending = self._get_pending_tasks(agent_id, cfg.max_tasks_per_cycle)
        if not pending:
            return {
                "agent_id": agent_id,
                "cycle_at": start,
                "tasks_found": 0,
                "tasks_completed": 0,
                "elapsed_ms": 0,
            }

        completed = 0
        failed = 0
        delegated = 0
        results = []

        for task in pending:
            task_id = task.get("task_id", "")

            # 2. Build prompt for the task
            system_prompt = self._build_agent_prompt(agent, cfg)
            task_prompt = self._build_task_prompt(task)

            messages = [{"role": "user", "content": task_prompt}]

            # Add memory context
            if self._memory:
                context = self._memory.build_context(agent_id, include_history=True)
                if context:
                    system_prompt += f"\n\n## Your Memory\n{context}"

            # 3. Call LLM with tool support
            provider = agent.get("llm_provider", "ollama")
            model = agent.get("llm_model", "")

            try:
                result = await self._router.chat(
                    provider,
                    messages,
                    model=model or None,
                    system=system_prompt,
                    temperature=0.4,
                )
                response = result.get("message", "")
                success = result.get("success", False)

                # 4. Execute any tool calls in the response
                if success and self._tools and self._tools.has_tool_calls(response):
                    tool_results = await self._tools.execute_tool_calls(agent_id, response)

                    # Feed tool results back for a follow-up
                    feedback = "\n".join(
                        f"[[{tr['tool']}]] "
                        + (
                            "Result: " + str(tr.get("result", ""))
                            if "result" in tr
                            else "Error: " + tr.get("error", "")
                        )
                        for tr in tool_results
                    )
                    messages.append({"role": "assistant", "content": response})
                    messages.append(
                        {
                            "role": "user",
                            "content": f"Tool results:\n{feedback}\n\nSummarize the outcome.",
                        }
                    )

                    follow_up = await self._router.chat(
                        provider,
                        messages,
                        model=model or None,
                        system=system_prompt,
                        temperature=0.4,
                    )
                    response = follow_up.get("message", response)

                # 5. Check if agent wants to delegate
                if success and cfg.can_delegate and "[[delegate" in response.lower():
                    delegated += 1
                    self._update_task(task_id, "delegated", response)
                elif success:
                    completed += 1
                    self._update_task(task_id, "completed", response)
                else:
                    failed += 1
                    self._update_task(task_id, "failed", result.get("error", "LLM call failed"))

                results.append(
                    {
                        "task_id": task_id,
                        "status": "completed" if success else "failed",
                        "response_preview": response[:200],
                    }
                )

                # Store in memory
                if self._memory and success:
                    self._memory.remember(
                        agent_id,
                        f"Completed task {task_id}: {response[:100]}",
                        "task_completion",
                    )

            except Exception as e:
                failed += 1
                self._update_task(task_id, "failed", str(e))
                results.append({"task_id": task_id, "status": "failed", "error": str(e)})

        elapsed = round((time.time() - start) * 1000, 1)
        cycle_result = {
            "agent_id": agent_id,
            "cycle_at": start,
            "tasks_found": len(pending),
            "tasks_completed": completed,
            "tasks_failed": failed,
            "tasks_delegated": delegated,
            "elapsed_ms": elapsed,
            "results": results,
        }

        logger.info(
            "Autonomy cycle for %s: %d found, %d completed, %d failed, %d delegated (%.1fms)",
            agent_id,
            len(pending),
            completed,
            failed,
            delegated,
            elapsed,
        )
        return cycle_result

    def _get_pending_tasks(self, agent_id: str, limit: int) -> List[dict]:
        """Get pending tasks assigned to this agent."""
        try:
            rows = self._persistence.conn.execute(
                "SELECT task_id, data, priority, created_at FROM tasks "
                "WHERE assigned_to = ? AND status = 'pending' "
                "ORDER BY CASE priority WHEN 'critical' THEN 0 WHEN 'high' THEN 1 "
                "WHEN 'medium' THEN 2 ELSE 3 END, created_at ASC LIMIT ?",
                (agent_id, limit),
            ).fetchall()
            results = []
            for row in rows:
                task = {"task_id": row[0], "priority": row[2], "created_at": row[3]}
                try:
                    data = json.loads(row[1])
                    task.update(data)
                except (json.JSONDecodeError, TypeError):
                    task["raw_data"] = row[1]
                results.append(task)
            return results
        except Exception as e:
            logger.warning("Failed to get pending tasks for %s: %s", agent_id, e)
            return []

    def _update_task(self, task_id: str, status: str, result: str):
        """Update task status and result."""
        try:
            data_row = self._persistence.conn.execute(
                "SELECT data FROM tasks WHERE task_id = ?", (task_id,)
            ).fetchone()
            if data_row:
                data = json.loads(data_row[0]) if data_row[0] else {}
                data["result"] = result[:2000]
                data["completed_at"] = time.time()
                self._persistence.conn.execute(
                    "UPDATE tasks SET status = ?, data = ?, updated_at = ? WHERE task_id = ?",
                    (status, json.dumps(data), time.time(), task_id),
                )
                self._persistence.conn.commit()
        except Exception as e:
            logger.warning("Failed to update task %s: %s", task_id, e)

    def _build_agent_prompt(self, agent: dict, cfg: AutonomyConfig) -> str:
        """Build system prompt for autonomous execution."""
        parts = [
            agent.get("system_prompt", ""),
            f"\nYou are {agent.get('name', 'an AI agent')} ({agent.get('title', '')}).",
            f"Department: {agent.get('department', 'unknown')}",
            "\nYou are working AUTONOMOUSLY. Complete the assigned task thoroughly.",
            "Use available tools when needed. Be precise and actionable.",
        ]
        if cfg.can_delegate:
            parts.append(
                "You may delegate subtasks by including "
                "[[delegate(agent_id, task_description)]] in your response."
            )
        if self._tools:
            parts.append("")
            parts.append(self._tools.get_tool_descriptions(agent.get("agent_id")))
        return "\n".join(parts)

    def _build_task_prompt(self, task: dict) -> str:
        """Build the user prompt from a task."""
        parts = [f"## Task: {task.get('title', 'Untitled')}"]
        if task.get("description"):
            parts.append(task["description"])
        if task.get("prompt"):
            parts.append(task["prompt"])
        parts.append(f"\nPriority: {task.get('priority', 'medium')}")
        if task.get("context"):
            parts.append(f"Context: {task['context']}")
        return "\n".join(parts)

    # ── Status & History ──

    def get_status(self) -> dict:
        """Get overall autonomy status."""
        active = [aid for aid, running in self._running.items() if running]
        configured = list(self._configs.keys())
        return {
            "active_agents": active,
            "configured_agents": configured,
            "total_active": len(active),
            "total_configured": len(configured),
            "recent_cycles": len(self._cycle_history),
        }

    def get_agent_status(self, agent_id: str) -> dict:
        """Get autonomy status for a specific agent."""
        cfg = self.get_config(agent_id)
        is_running = self._running.get(agent_id, False)
        recent = [c for c in self._cycle_history if c.get("agent_id") == agent_id][-10:]
        return {
            **cfg,
            "is_running": is_running,
            "recent_cycles": recent,
        }

    def get_cycle_history(self, agent_id: str = None, limit: int = 50) -> List[dict]:
        """Get recent cycle history."""
        history = self._cycle_history
        if agent_id:
            history = [c for c in history if c.get("agent_id") == agent_id]
        return history[-limit:]

    def get_all_configs(self) -> List[dict]:
        """Get all configured agents with their autonomy settings."""
        results = []
        for agent_id, cfg in self._configs.items():
            results.append(
                {
                    "agent_id": agent_id,
                    "enabled": cfg.enabled,
                    "is_running": self._running.get(agent_id, False),
                    "max_tasks_per_cycle": cfg.max_tasks_per_cycle,
                    "cycle_interval_s": cfg.cycle_interval_s,
                    "can_delegate": cfg.can_delegate,
                }
            )
        return results
