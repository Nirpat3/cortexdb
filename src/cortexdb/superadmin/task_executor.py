"""
Task Execution Engine — Background worker that routes tasks to LLM providers.
When a task is assigned, builds a prompt from the task + agent's system prompt,
sends to the LLM, and stores the result.

Supports: auto-execute on assignment, manual trigger, batch execution.
"""

import time
import asyncio
import logging
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from cortexdb.superadmin.agent_team import AgentTeamManager
    from cortexdb.superadmin.llm_router import LLMRouter
    from cortexdb.superadmin.agent_memory import AgentMemory
    from cortexdb.superadmin.outcome_analyzer import OutcomeAnalyzer

logger = logging.getLogger(__name__)


class TaskExecutor:
    """Executes tasks by routing to the assigned agent's LLM provider."""

    def __init__(self, agent_team: "AgentTeamManager", llm_router: "LLMRouter",
                 memory: "AgentMemory" = None, on_complete=None,
                 outcome_analyzer: "OutcomeAnalyzer" = None,
                 cost_tracker=None, engine_bridge=None):
        self._team = agent_team
        self._router = llm_router
        self._memory = memory
        self._on_complete = on_complete  # async callback(task_id, status)
        self._analyzer = outcome_analyzer
        self._cost_tracker = cost_tracker
        self._engine_bridge = engine_bridge
        self._running = False
        self._queue: asyncio.Queue = asyncio.Queue()
        self._active_tasks: set = set()
        self._max_concurrent = 3

    # ── Queue management ──

    async def enqueue(self, task_id: str):
        """Add a task to the execution queue."""
        await self._queue.put(task_id)
        logger.info("Task %s enqueued for execution", task_id)

    async def start(self):
        """Start the background execution loop."""
        self._running = True
        logger.info("TaskExecutor started (max_concurrent=%d)", self._max_concurrent)
        workers = [asyncio.create_task(self._worker(i)) for i in range(self._max_concurrent)]
        try:
            await asyncio.gather(*workers)
        except asyncio.CancelledError:
            pass

    def stop(self):
        """Signal the executor to stop."""
        self._running = False

    async def _worker(self, worker_id: int):
        """Worker loop that pulls tasks from the queue."""
        while self._running:
            try:
                task_id = await asyncio.wait_for(self._queue.get(), timeout=2.0)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

            if task_id in self._active_tasks:
                continue

            self._active_tasks.add(task_id)
            try:
                await self._execute_task(task_id)
            except Exception as e:
                logger.error("Worker %d: task %s failed: %s", worker_id, task_id, e)
            finally:
                self._active_tasks.discard(task_id)
                self._queue.task_done()

    # ── Core execution ──

    async def _execute_task(self, task_id: str):
        """Execute a single task via LLM."""
        task = self._team.get_task(task_id)
        if not task:
            logger.warning("Task %s not found, skipping", task_id)
            return

        if task["status"] not in ("pending", "in_progress", "approved"):
            return

        agent_id = task.get("assigned_to")
        agent = self._team.get_agent(agent_id) if agent_id else None

        # Start execution trace
        trace = None
        if hasattr(self, '_execution_replay') and self._execution_replay:
            trace = self._execution_replay.start_trace(task_id, agent_id or "system")

        t0 = time.time()

        # Determine provider and model
        provider = "ollama"
        model = ""
        system_prompt = self._build_system_prompt(task, agent)
        if trace:
            trace.add_step("prompt_built", (time.time() - t0) * 1000,
                           inputs={"task_id": task_id, "category": task.get("category")},
                           outputs={"prompt_length": len(system_prompt)})

        # Inject agent memory context
        if self._memory and agent_id:
            context = self._memory.build_context(agent_id)
            if context:
                system_prompt += f"\n\n{context}"
                if trace:
                    trace.add_step("context_injected", (time.time() - t0) * 1000,
                                   metadata={"context_length": len(context)})

        if agent:
            provider = agent.get("llm_provider", "ollama")
            model = agent.get("llm_model", "")

        # Check model tracker for learned recommendation
        category = task.get("category", "general")
        if hasattr(self._router, '_model_tracker') and self._router._model_tracker:
            rec = self._router._model_tracker.recommend(category)
            if rec and rec.get("score", 0) > 0.6:
                provider = rec["provider"]
                model = rec.get("model", model)
                logger.info("Using learned model recommendation for %s: %s/%s (score=%.2f)",
                           category, provider, model, rec["score"])

        if trace:
            trace.add_step("model_selected", (time.time() - t0) * 1000,
                           outputs={"provider": provider, "model": model or "default"})

        # Update task status
        self._team.update_task(task_id, {
            "status": "in_progress",
            "started_at": time.time(),
        })
        if agent_id:
            self._team.update_agent(agent_id, {"state": "working", "current_task": task_id})

        logger.info("Executing task %s via %s:%s (agent: %s)", task_id, provider, model or "default", agent_id or "none")

        # Build the user prompt
        user_prompt = self._build_task_prompt(task)

        # Call LLM
        llm_start = time.time()
        messages = [{"role": "user", "content": user_prompt}]
        if trace:
            trace.add_step("llm_called", (time.time() - t0) * 1000,
                           inputs={"provider": provider, "model": model or "default"},
                           metadata={"prompt_tokens_est": len(user_prompt) // 4})
        result = await self._router.chat(
            provider, messages,
            model=model or None,
            system=system_prompt,
            temperature=0.4,  # Lower temp for task work
        )
        llm_ms = (time.time() - llm_start) * 1000

        # Store result
        response = result.get("message") or result.get("response") or result.get("error", "No response")
        success = result.get("success", False)

        if trace:
            trace.add_step("result_received", llm_ms,
                           outputs={"success": success, "response_length": len(str(response))},
                           metadata={"elapsed_ms": result.get("elapsed_ms", 0)})

        new_status = "review" if success else "failed"
        self._team.update_task(task_id, {
            "status": new_status,
            "result": response,
            "completed_at": time.time(),
            "metadata": {
                "llm_provider": provider,
                "llm_model": model or result.get("model", ""),
                "elapsed_ms": result.get("elapsed_ms", 0),
                "success": success,
            },
        })

        # Update agent state
        if agent_id:
            if success:
                self._team.update_agent(agent_id, {"state": "active", "current_task": None})
                # Increment completed counter
                agent_data = self._team.get_agent(agent_id)
                if agent_data:
                    self._team.update_agent(agent_id, {
                        "tasks_completed": agent_data.get("tasks_completed", 0) + 1,
                    })
            else:
                self._team.update_agent(agent_id, {"state": "error", "current_task": None})
                agent_data = self._team.get_agent(agent_id)
                if agent_data:
                    self._team.update_agent(agent_id, {
                        "tasks_failed": agent_data.get("tasks_failed", 0) + 1,
                    })

        # Audit
        if hasattr(self._team, '_persistence') and self._team._persistence:
            self._team._persistence.audit(
                "task_executed", "task", task_id,
                {"status": new_status, "provider": provider, "agent": agent_id},
            )

        # Token-precise cost tracking
        if self._cost_tracker and result.get("usage"):
            agent_data = self._team.get_agent(agent_id) if agent_id else None
            self._cost_tracker.record(
                provider=provider,
                model=model or result.get("model", "default"),
                agent_id=agent_id or "",
                category=task.get("category", "general"),
                usage=result["usage"],
                department=agent_data.get("department") if agent_data else None,
            )

        # Engine bridge: publish event + immutable audit
        if self._engine_bridge:
            try:
                await self._engine_bridge.publish_event("task_completed", {
                    "task_id": task_id, "agent_id": agent_id or "",
                    "status": new_status, "provider": provider,
                })
                await self._engine_bridge.log_execution(
                    task_id, agent_id or "", new_status,
                    {"provider": provider, "model": model, "elapsed_ms": result.get("elapsed_ms", 0)},
                )
            except Exception as e:
                logger.debug("Engine bridge logging failed: %s", e)

        # Store in agent memory
        if self._memory and agent_id:
            self._memory.add_task_summary(
                agent_id, task_id, task["title"],
                response[:500] if isinstance(response, str) else str(response)[:500],
                success,
            )
            self._memory.add_turn(agent_id, "user", f"Task: {task['title']}")
            self._memory.add_turn(agent_id, "assistant", response[:300] if isinstance(response, str) else "")

        # Outcome analysis — the learning feedback loop
        if self._analyzer and success:
            try:
                analysis = await self._analyzer.analyze(task, response, agent_id)
                grade = analysis.get("grade")
                if grade:
                    self._team.update_task(task_id, {
                        "analysis": {
                            "grade": grade,
                            "quality": analysis.get("quality"),
                            "learnings_count": len(analysis.get("learnings", [])),
                        },
                    })
                    # Feed grade back to model tracker via router
                    category = task.get("category", "general")
                    self._router._log_request(
                        provider, model or "default",
                        result.get("elapsed_ms", 0), True,
                        category=category, grade=grade,
                    )
                if trace:
                    trace.add_step("outcome_analyzed", (time.time() - t0) * 1000,
                                   outputs={"grade": analysis.get("grade"), "quality": analysis.get("quality")})
            except Exception as e:
                logger.warning("Outcome analysis failed for %s: %s", task_id, e)

        # Finish execution trace
        if trace:
            trace.add_step("completed", (time.time() - t0) * 1000,
                           outputs={"status": new_status, "success": success})
            if hasattr(self, '_execution_replay') and self._execution_replay:
                self._execution_replay.finish_trace(task_id)

        logger.info("Task %s completed: %s (%s)", task_id, new_status, f"{result.get('elapsed_ms', 0):.0f}ms")

        # Notify via callback (used for WebSocket push)
        if self._on_complete:
            try:
                await self._on_complete(task_id, new_status)
            except Exception:
                pass

        # Pipeline chaining: auto-enqueue next tasks
        if success and task.get("next_tasks"):
            for next_task_id in task["next_tasks"]:
                next_task = self._team.get_task(next_task_id)
                if next_task and next_task["status"] == "pending":
                    # Pass previous result as context
                    self._team.update_task(next_task_id, {
                        "pipeline_context": {
                            "previous_task": task_id,
                            "previous_result": response[:2000],
                        },
                    })
                    await self.enqueue(next_task_id)
                    logger.info("Pipeline: auto-enqueued %s after %s", next_task_id, task_id)

    def _build_system_prompt(self, task: dict, agent: Optional[dict]) -> str:
        """Build system prompt combining agent identity + task context."""
        parts = []

        if agent:
            parts.append(agent.get("system_prompt", ""))
            parts.append(f"\nYou are working on a {task.get('category', 'general')} task "
                         f"with {task.get('priority', 'medium')} priority.")
            if task.get("microservice"):
                parts.append(f"This task targets the '{task['microservice']}' microservice.")
        else:
            parts.append("You are a CortexDB AI assistant helping with development tasks.")
            parts.append(f"Task category: {task.get('category', 'general')}, "
                         f"priority: {task.get('priority', 'medium')}.")

        parts.append("\nProvide a clear, actionable response. If the task involves code, "
                     "include code snippets. If it involves analysis, provide structured findings.")
        return "\n".join(parts)

    def _build_task_prompt(self, task: dict) -> str:
        """Build the user message from task details."""
        parts = [f"## Task: {task['title']}"]
        if task.get("description"):
            parts.append(f"\n{task['description']}")
        if task.get("microservice"):
            parts.append(f"\nMicroservice: {task['microservice']}")
        parts.append(f"\nPriority: {task.get('priority', 'medium')}")
        parts.append(f"Category: {task.get('category', 'general')}")

        # Pipeline context from previous task
        ctx = task.get("pipeline_context")
        if ctx:
            parts.append(f"\n## Context from previous task ({ctx.get('previous_task', 'unknown')})")
            parts.append(ctx.get("previous_result", ""))

        parts.append("\nPlease complete this task and provide your detailed response.")
        return "\n".join(parts)

    # ── Manual triggers ──

    async def execute_now(self, task_id: str) -> dict:
        """Execute a task immediately (bypasses queue)."""
        await self._execute_task(task_id)
        return self._team.get_task(task_id) or {"error": "Task not found"}

    async def execute_pending(self) -> int:
        """Queue all pending tasks for execution."""
        tasks = self._team.get_all_tasks("pending")
        count = 0
        for t in tasks:
            if t.get("assigned_to"):
                await self.enqueue(t["task_id"])
                count += 1
        return count

    def get_status(self) -> dict:
        return {
            "running": self._running,
            "queue_size": self._queue.qsize(),
            "active_tasks": list(self._active_tasks),
            "max_concurrent": self._max_concurrent,
        }
