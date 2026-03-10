"""
Agent Sleep Cycle — Nightly maintenance for the agent intelligence layer.

Runs periodically (default: every 6 hours, deep cycle at 2 AM) to:
  1. Consolidate: Compress short-term memory into long-term learnings
  2. Decay: Remove stale/low-value facts from long-term memory
  3. Strengthen: Reinforce frequently-validated patterns
  4. Pre-compute: Update delegation scores and model recommendations
  5. Evolve: Auto-evolve prompts for underperforming agents
  6. Report: Generate a sleep cycle summary

This is the "dreaming" phase where agents digest their experiences.
"""

import time
import logging
import asyncio
from typing import Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from cortexdb.superadmin.agent_memory import AgentMemory
    from cortexdb.superadmin.agent_team import AgentTeamManager
    from cortexdb.superadmin.outcome_analyzer import OutcomeAnalyzer
    from cortexdb.superadmin.prompt_evolution import PromptEvolution
    from cortexdb.superadmin.model_tracker import ModelPerformanceTracker
    from cortexdb.superadmin.persistence import PersistenceStore

logger = logging.getLogger(__name__)


class AgentSleepCycle:
    """Nightly maintenance cycle for agent intelligence."""

    def __init__(self, memory: "AgentMemory", team: "AgentTeamManager",
                 analyzer: "OutcomeAnalyzer", prompt_evo: "PromptEvolution",
                 model_tracker: "ModelPerformanceTracker",
                 persistence: "PersistenceStore"):
        self._memory = memory
        self._team = team
        self._analyzer = analyzer
        self._prompt_evo = prompt_evo
        self._model_tracker = model_tracker
        self._persistence = persistence
        self._running = False
        self._last_result: Optional[dict] = None
        self._cycle_count = 0

    async def run(self) -> dict:
        """Execute the full agent sleep cycle."""
        if self._running:
            return {"status": "already_running"}

        self._running = True
        start = time.time()
        result = {
            "started_at": start,
            "tasks": {},
        }

        agents = self._team.get_all_agents()
        logger.info("Agent sleep cycle STARTED for %d agents", len(agents))

        # Phase 1: Consolidate short-term → long-term
        try:
            result["tasks"]["consolidate"] = await self._consolidate(agents)
        except Exception as e:
            result["tasks"]["consolidate"] = {"error": str(e)}
            logger.error("Sleep consolidate failed: %s", e)

        # Phase 2: Decay stale facts
        try:
            result["tasks"]["decay"] = self._decay(agents)
        except Exception as e:
            result["tasks"]["decay"] = {"error": str(e)}

        # Phase 3: Strengthen validated patterns
        try:
            result["tasks"]["strengthen"] = self._strengthen(agents)
        except Exception as e:
            result["tasks"]["strengthen"] = {"error": str(e)}

        # Phase 4: Pre-compute (update caches)
        try:
            result["tasks"]["precompute"] = self._precompute()
        except Exception as e:
            result["tasks"]["precompute"] = {"error": str(e)}

        # Phase 5: Auto-evolve worst-performing agent prompts
        try:
            result["tasks"]["evolve"] = await self._auto_evolve(agents)
        except Exception as e:
            result["tasks"]["evolve"] = {"error": str(e)}

        result["completed_at"] = time.time()
        result["duration_s"] = round(result["completed_at"] - start, 1)
        self._running = False
        self._last_result = result
        self._cycle_count += 1

        # Store in persistence
        history = self._persistence.kv_get("sleep_cycle_history", [])
        history.append({
            "cycle": self._cycle_count,
            "duration_s": result["duration_s"],
            "timestamp": start,
            "tasks": {k: "ok" if "error" not in v else "error" for k, v in result["tasks"].items()},
        })
        if len(history) > 50:
            history = history[-50:]
        self._persistence.kv_set("sleep_cycle_history", history)

        logger.info("Agent sleep cycle COMPLETED in %.1fs", result["duration_s"])
        return result

    async def _consolidate(self, agents: List[dict]) -> dict:
        """Phase 1: Analyze short-term conversations to extract durable learnings."""
        consolidated = 0
        for agent in agents:
            aid = agent["agent_id"]
            turns = self._memory.get_recent_turns(aid, limit=20)
            if len(turns) < 4:
                continue

            # Extract assistant responses that contain substantive content
            assistant_turns = [t for t in turns if t["role"] == "assistant" and len(t.get("content", "")) > 50]
            for turn in assistant_turns:
                content = turn["content"]
                # Look for patterns worth remembering
                if any(kw in content.lower() for kw in
                       ["important:", "note:", "key finding", "recommendation:", "pattern:", "learned"]):
                    # Extract the key sentence
                    for sentence in content.split(". "):
                        sentence = sentence.strip()
                        if len(sentence) > 20 and any(kw in sentence.lower() for kw in
                                                       ["should", "must", "always", "never", "best", "important", "key"]):
                            self._memory.remember(aid, sentence[:200], category="consolidated")
                            consolidated += 1
                            break

            # Clear old short-term after consolidation
            if len(turns) >= 15:
                key = self._memory._key(aid, "short_term")
                self._memory._persistence.kv_set(key, turns[-10:])

        return {"consolidated_facts": consolidated}

    def _decay(self, agents: List[dict]) -> dict:
        """Phase 2: Remove old, low-value facts from long-term memory."""
        decayed = 0
        now = time.time()
        max_age = 30 * 24 * 3600  # 30 days

        for agent in agents:
            aid = agent["agent_id"]
            key = self._memory._key(aid, "long_term")
            facts = self._memory._persistence.kv_get(key, [])
            if not facts:
                continue

            # Remove facts older than max_age that aren't patterns or consolidated
            original_count = len(facts)
            facts = [f for f in facts if
                     (now - f.get("timestamp", now)) < max_age or
                     f.get("category") in ("patterns", "consolidated", "prompt_insights")]

            if len(facts) < original_count:
                decayed += original_count - len(facts)
                self._memory._persistence.kv_set(key, facts)

        return {"facts_decayed": decayed}

    def _strengthen(self, agents: List[dict]) -> dict:
        """Phase 3: Reinforce patterns that correlate with high-grade outcomes."""
        strengthened = 0

        for agent in agents:
            aid = agent["agent_id"]
            # Get agent quality scores
            scores = self._analyzer.get_agent_scores(aid)
            by_cat = scores.get("by_category", {})

            # For high-performing categories, reinforce the pattern
            for cat, cat_score in by_cat.items():
                if cat_score.get("avg", 0) >= 8 and cat_score.get("total", 0) >= 3:
                    self._memory.remember(
                        aid,
                        f"[strength] Consistently excellent at {cat} tasks (avg grade {cat_score['avg']})",
                        category="strengths",
                    )
                    strengthened += 1

        return {"patterns_strengthened": strengthened}

    def _precompute(self) -> dict:
        """Phase 4: Pre-compute delegation scores and refresh recommendations."""
        # Trigger model tracker to recompute
        perf = self._model_tracker.get_performance_data()
        return {
            "models_tracked": perf.get("total_tracked", 0),
            "recommendations": len(perf.get("recommendations", {})),
        }

    async def _auto_evolve(self, agents: List[dict]) -> dict:
        """Phase 5: Auto-evolve prompts for underperforming agents."""
        evolved = 0
        skipped = 0

        for agent in agents:
            aid = agent["agent_id"]
            weak = self._prompt_evo.get_weak_categories(aid, threshold=5.0)
            if not weak:
                skipped += 1
                continue

            # Only evolve if enough data
            scores = self._analyzer.get_agent_scores(aid)
            if scores.get("total", 0) < 5:
                skipped += 1
                continue

            try:
                evolution = await self._prompt_evo.evolve_prompt(aid, agent)
                if evolution and evolution.get("new_prompt"):
                    # Auto-apply if the agent's current avg is below 5
                    if scores.get("avg", 10) < 5.0:
                        self._prompt_evo.apply_evolution(
                            aid, evolution["new_prompt"], self._team)
                        evolved += 1
                        logger.info("Auto-evolved prompt for %s (avg grade %.1f)",
                                   aid, scores.get("avg", 0))
                    else:
                        evolved += 1  # Generated but not auto-applied
            except Exception as e:
                logger.warning("Auto-evolve failed for %s: %s", aid, e)

        return {"evolved": evolved, "skipped": skipped}

    # ── Background scheduler ──

    async def start_scheduler(self, interval_hours: float = 6):
        """Run sleep cycle periodically in the background."""
        interval_s = interval_hours * 3600
        while True:
            await asyncio.sleep(interval_s)
            try:
                await self.run()
            except Exception as e:
                logger.error("Scheduled sleep cycle failed: %s", e)

    # ── Status ──

    def get_status(self) -> dict:
        return {
            "running": self._running,
            "cycle_count": self._cycle_count,
            "last_result": self._last_result,
            "history": self._persistence.kv_get("sleep_cycle_history", [])[-10:],
        }
