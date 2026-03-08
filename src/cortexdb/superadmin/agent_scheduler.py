"""
Agent Scheduler — Cron-like recurring tasks per agent.

Schedule agents to run tasks on regular intervals:
  - Hourly, daily, weekly schedules
  - Custom cron-like expressions (simplified)
  - Automatic task creation and enqueuing
  - Execution history tracking
"""

import time
import asyncio
import logging
from typing import Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from cortexdb.superadmin.agent_team import AgentTeamManager
    from cortexdb.superadmin.task_executor import TaskExecutor
    from cortexdb.superadmin.persistence import PersistenceStore

logger = logging.getLogger(__name__)

# Predefined intervals in seconds
INTERVALS = {
    "every_5min": 300,
    "every_15min": 900,
    "every_30min": 1800,
    "hourly": 3600,
    "every_4h": 14400,
    "every_8h": 28800,
    "daily": 86400,
    "weekly": 604800,
}


class ScheduledJob:
    """A recurring scheduled job for an agent."""
    def __init__(self, job_id: str, agent_id: str, title: str,
                 prompt: str, interval: str, category: str = "general",
                 enabled: bool = True):
        self.job_id = job_id
        self.agent_id = agent_id
        self.title = title
        self.prompt = prompt
        self.interval = interval
        self.interval_seconds = INTERVALS.get(interval, 86400)
        self.category = category
        self.enabled = enabled
        self.last_run: Optional[float] = None
        self.run_count = 0
        self.created_at = time.time()

    def is_due(self) -> bool:
        if not self.enabled:
            return False
        if self.last_run is None:
            return True
        return (time.time() - self.last_run) >= self.interval_seconds

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "agent_id": self.agent_id,
            "title": self.title,
            "prompt": self.prompt,
            "interval": self.interval,
            "interval_seconds": self.interval_seconds,
            "category": self.category,
            "enabled": self.enabled,
            "last_run": self.last_run,
            "run_count": self.run_count,
            "created_at": self.created_at,
            "next_run": (self.last_run + self.interval_seconds) if self.last_run else None,
        }


class AgentScheduler:
    """Manages scheduled recurring tasks for agents."""

    def __init__(self, team: "AgentTeamManager", executor: "TaskExecutor",
                 persistence: "PersistenceStore"):
        self._team = team
        self._executor = executor
        self._persistence = persistence
        self._jobs: Dict[str, ScheduledJob] = {}
        self._running = False
        self._load_jobs()

    def _load_jobs(self):
        """Load jobs from persistence."""
        saved = self._persistence.kv_get("scheduled_jobs", {})
        for jid, data in saved.items():
            job = ScheduledJob(
                job_id=jid,
                agent_id=data.get("agent_id", ""),
                title=data.get("title", ""),
                prompt=data.get("prompt", ""),
                interval=data.get("interval", "daily"),
                category=data.get("category", "general"),
                enabled=data.get("enabled", True),
            )
            job.last_run = data.get("last_run")
            job.run_count = data.get("run_count", 0)
            job.created_at = data.get("created_at", time.time())
            self._jobs[jid] = job

    def _save_jobs(self):
        self._persistence.kv_set("scheduled_jobs", {
            jid: job.to_dict() for jid, job in self._jobs.items()
        })

    def create_job(self, agent_id: str, title: str, prompt: str,
                   interval: str = "daily", category: str = "general") -> dict:
        """Create a new scheduled job."""
        if interval not in INTERVALS:
            return {"error": f"Invalid interval. Options: {list(INTERVALS.keys())}"}

        agent = self._team.get_agent(agent_id)
        if not agent:
            return {"error": "Agent not found"}

        import uuid
        job_id = f"sched-{uuid.uuid4().hex[:8]}"
        job = ScheduledJob(job_id, agent_id, title, prompt, interval, category)
        self._jobs[job_id] = job
        self._save_jobs()

        logger.info("Scheduled job %s for %s (%s)", job_id, agent_id, interval)
        return job.to_dict()

    def update_job(self, job_id: str, updates: dict) -> dict:
        """Update a scheduled job."""
        job = self._jobs.get(job_id)
        if not job:
            return {"error": "Job not found"}

        if "enabled" in updates:
            job.enabled = updates["enabled"]
        if "interval" in updates and updates["interval"] in INTERVALS:
            job.interval = updates["interval"]
            job.interval_seconds = INTERVALS[updates["interval"]]
        if "prompt" in updates:
            job.prompt = updates["prompt"]
        if "title" in updates:
            job.title = updates["title"]

        self._save_jobs()
        return job.to_dict()

    def delete_job(self, job_id: str) -> dict:
        if job_id in self._jobs:
            del self._jobs[job_id]
            self._save_jobs()
            return {"deleted": True}
        return {"error": "Job not found"}

    def get_jobs(self, agent_id: str = None) -> List[dict]:
        jobs = list(self._jobs.values())
        if agent_id:
            jobs = [j for j in jobs if j.agent_id == agent_id]
        return [j.to_dict() for j in jobs]

    def get_job(self, job_id: str) -> Optional[dict]:
        job = self._jobs.get(job_id)
        return job.to_dict() if job else None

    async def tick(self):
        """Check all jobs and execute any that are due."""
        for job in self._jobs.values():
            if not job.is_due():
                continue

            try:
                # Create a task for this scheduled job
                import uuid
                task_id = f"auto-{uuid.uuid4().hex[:8]}"
                self._team.create_task({
                    "task_id": task_id,
                    "title": f"[Scheduled] {job.title}",
                    "description": job.prompt,
                    "category": job.category,
                    "priority": "medium",
                    "assigned_to": job.agent_id,
                    "source": "scheduler",
                    "scheduled_job_id": job.job_id,
                })
                await self._executor.enqueue(task_id)
                job.last_run = time.time()
                job.run_count += 1
                logger.info("Scheduled job %s executed (task %s)", job.job_id, task_id)
            except Exception as e:
                logger.warning("Scheduled job %s failed: %s", job.job_id, e)

        self._save_jobs()

    async def start_scheduler(self, check_interval: int = 60):
        """Background loop that checks for due jobs."""
        self._running = True
        while self._running:
            await asyncio.sleep(check_interval)
            try:
                await self.tick()
            except Exception as e:
                logger.error("Scheduler tick failed: %s", e)

    def stop(self):
        self._running = False

    def get_status(self) -> dict:
        return {
            "running": self._running,
            "total_jobs": len(self._jobs),
            "enabled_jobs": sum(1 for j in self._jobs.values() if j.enabled),
            "available_intervals": list(INTERVALS.keys()),
        }
