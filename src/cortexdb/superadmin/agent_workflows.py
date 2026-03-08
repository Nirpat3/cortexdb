"""
Agent Workflows — DAG-based multi-step agent pipelines.

A workflow defines a directed acyclic graph of steps where:
  - Each step is assigned to an agent
  - Steps can depend on other steps
  - Output from one step flows as context to dependent steps
  - The workflow engine executes steps respecting dependencies
  - Steps can have conditions (run only if previous step succeeded/failed)
"""

import time
import uuid
import logging
from typing import Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from cortexdb.superadmin.agent_team import AgentTeamManager
    from cortexdb.superadmin.llm_router import LLMRouter
    from cortexdb.superadmin.agent_memory import AgentMemory
    from cortexdb.superadmin.persistence import PersistenceStore

logger = logging.getLogger(__name__)


class WorkflowStep:
    """A single step in a workflow DAG."""
    def __init__(self, step_id: str, title: str, agent_id: str,
                 prompt: str, depends_on: List[str] = None,
                 condition: str = "always"):
        self.step_id = step_id
        self.title = title
        self.agent_id = agent_id
        self.prompt = prompt
        self.depends_on = depends_on or []
        self.condition = condition  # always, on_success, on_failure
        self.status = "pending"
        self.result: Optional[str] = None
        self.started_at: Optional[float] = None
        self.completed_at: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "step_id": self.step_id,
            "title": self.title,
            "agent_id": self.agent_id,
            "prompt": self.prompt,
            "depends_on": self.depends_on,
            "condition": self.condition,
            "status": self.status,
            "result": self.result,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }


class Workflow:
    """A complete workflow definition with steps."""
    def __init__(self, workflow_id: str, name: str, description: str = ""):
        self.workflow_id = workflow_id
        self.name = name
        self.description = description
        self.steps: Dict[str, WorkflowStep] = {}
        self.status = "draft"  # draft, running, completed, failed
        self.created_at = time.time()
        self.completed_at: Optional[float] = None

    def add_step(self, step: WorkflowStep):
        self.steps[step.step_id] = step

    def get_ready_steps(self) -> List[WorkflowStep]:
        """Get steps whose dependencies are all completed."""
        ready = []
        for step in self.steps.values():
            if step.status != "pending":
                continue
            deps_met = all(
                self.steps[dep].status == "completed"
                for dep in step.depends_on
                if dep in self.steps
            )
            if not deps_met:
                continue
            # Check condition
            if step.condition == "on_success":
                if any(self.steps[d].status == "failed" for d in step.depends_on if d in self.steps):
                    step.status = "skipped"
                    continue
            elif step.condition == "on_failure":
                if all(self.steps[d].status == "completed" for d in step.depends_on if d in self.steps):
                    step.status = "skipped"
                    continue
            ready.append(step)
        return ready

    def to_dict(self) -> dict:
        return {
            "workflow_id": self.workflow_id,
            "name": self.name,
            "description": self.description,
            "status": self.status,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "steps": {k: v.to_dict() for k, v in self.steps.items()},
            "step_count": len(self.steps),
            "completed_steps": sum(1 for s in self.steps.values() if s.status in ("completed", "skipped")),
        }


class WorkflowEngine:
    """Executes workflow DAGs."""

    def __init__(self, team: "AgentTeamManager", router: "LLMRouter",
                 memory: "AgentMemory", persistence: "PersistenceStore"):
        self._team = team
        self._router = router
        self._memory = memory
        self._persistence = persistence
        self._workflows: Dict[str, Workflow] = {}

    def create_workflow(self, name: str, description: str = "",
                        steps: List[dict] = None) -> dict:
        """Create a new workflow from a step definition list."""
        wf_id = f"wf-{uuid.uuid4().hex[:8]}"
        workflow = Workflow(wf_id, name, description)

        for i, step_def in enumerate(steps or []):
            step = WorkflowStep(
                step_id=step_def.get("step_id", f"step-{i+1}"),
                title=step_def.get("title", f"Step {i+1}"),
                agent_id=step_def.get("agent_id", ""),
                prompt=step_def.get("prompt", ""),
                depends_on=step_def.get("depends_on", []),
                condition=step_def.get("condition", "always"),
            )
            workflow.add_step(step)

        self._workflows[wf_id] = workflow
        self._save_workflow(workflow)
        return workflow.to_dict()

    async def execute(self, workflow_id: str) -> dict:
        """Execute a workflow by running steps in dependency order."""
        workflow = self._workflows.get(workflow_id)
        if not workflow:
            return {"error": "Workflow not found"}

        workflow.status = "running"
        max_iterations = len(workflow.steps) + 1  # safety limit

        for _ in range(max_iterations):
            ready = workflow.get_ready_steps()
            if not ready:
                break

            for step in ready:
                await self._execute_step(workflow, step)

        # Check completion
        all_done = all(s.status in ("completed", "failed", "skipped")
                       for s in workflow.steps.values())
        any_failed = any(s.status == "failed" for s in workflow.steps.values())

        workflow.status = "failed" if any_failed else "completed" if all_done else "stalled"
        workflow.completed_at = time.time()
        self._save_workflow(workflow)

        return workflow.to_dict()

    async def _execute_step(self, workflow: Workflow, step: WorkflowStep):
        """Execute a single workflow step."""
        step.status = "running"
        step.started_at = time.time()

        agent = self._team.get_agent(step.agent_id)
        if not agent:
            step.status = "failed"
            step.result = f"Agent {step.agent_id} not found"
            return

        # Build context from dependency results
        context_parts = [step.prompt]
        for dep_id in step.depends_on:
            dep = workflow.steps.get(dep_id)
            if dep and dep.result:
                context_parts.append(f"\n## Result from '{dep.title}' ({dep.agent_id}):\n{dep.result[:2000]}")

        system = agent.get("system_prompt", "You are a helpful AI agent.")
        provider = agent.get("llm_provider", "ollama")
        model = agent.get("llm_model", "")

        try:
            result = await self._router.chat(
                provider,
                [{"role": "user", "content": "\n".join(context_parts)}],
                model=model or None,
                system=system,
                temperature=0.5,
            )
            step.result = result.get("message", "") or result.get("error", "No response")
            step.status = "completed" if result.get("success") else "failed"
        except Exception as e:
            step.result = str(e)
            step.status = "failed"

        step.completed_at = time.time()

    def get_workflow(self, workflow_id: str) -> Optional[dict]:
        wf = self._workflows.get(workflow_id)
        return wf.to_dict() if wf else None

    def get_all_workflows(self) -> List[dict]:
        return [wf.to_dict() for wf in self._workflows.values()]

    def _save_workflow(self, workflow: Workflow):
        self._persistence.kv_set(f"workflow:{workflow.workflow_id}", workflow.to_dict())
