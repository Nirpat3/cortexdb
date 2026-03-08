"""
Outcome Analyzer — The core learning feedback loop.

After every task execution:
  1. Uses a lightweight LLM call to grade the result (1-10)
  2. Extracts key learnings (what worked, what didn't)
  3. Identifies reusable patterns (prompt strategies, approach types)
  4. Auto-stores learnings in agent long-term memory
  5. Updates per-agent + per-category quality scores

This is what makes the system actually learn from experience.
"""

import time
import logging
from typing import Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from cortexdb.superadmin.llm_router import LLMRouter
    from cortexdb.superadmin.agent_memory import AgentMemory
    from cortexdb.superadmin.persistence import PersistenceStore

logger = logging.getLogger(__name__)

GRADING_PROMPT = """You are a quality analyst for an AI agent workforce. Grade this task result.

TASK: {title}
CATEGORY: {category}
DESCRIPTION: {description}
AGENT RESULT:
{result}

Respond in EXACTLY this format (no other text):
GRADE: <1-10>
QUALITY: <poor|fair|good|excellent>
LEARNINGS:
- <learning 1>
- <learning 2>
PROMPT_INSIGHT: <what about the task prompt led to this quality of output>
REUSABLE_PATTERN: <a generalizable approach that could help with similar tasks>
"""


class OutcomeAnalyzer:
    """Analyzes task outcomes and feeds learnings back into agent memory."""

    def __init__(self, llm_router: "LLMRouter", memory: "AgentMemory",
                 persistence: "PersistenceStore", prompt_evolution=None):
        self._router = llm_router
        self._memory = memory
        self._persistence = persistence
        self._prompt_evolution = prompt_evolution
        self._analysis_provider = "ollama"  # Use cheapest provider for grading
        self._enabled = True

    def set_provider(self, provider: str):
        """Set which LLM provider to use for analysis (defaults to ollama for cost)."""
        self._analysis_provider = provider

    async def analyze(self, task: dict, result: str, agent_id: str = None) -> dict:
        """Analyze a completed task result and extract learnings.

        Returns:
            dict with grade, quality, learnings, patterns
        """
        if not self._enabled:
            return {"skipped": True}

        title = task.get("title", "Unknown")
        category = task.get("category", "general")
        description = task.get("description", "")

        # Build the grading prompt
        prompt = GRADING_PROMPT.format(
            title=title,
            category=category,
            description=description[:500],
            result=result[:2000],
        )

        # Call LLM for analysis (use low temperature for consistency)
        try:
            llm_result = await self._router.chat(
                self._analysis_provider,
                [{"role": "user", "content": prompt}],
                temperature=0.2,
                failover=True,
            )
        except Exception as e:
            logger.warning("Outcome analysis failed for task %s: %s", task.get("task_id"), e)
            return {"error": str(e)}

        if not llm_result.get("success"):
            return {"error": llm_result.get("error", "LLM call failed")}

        response = llm_result.get("message", "")

        # Parse the structured response
        analysis = self._parse_analysis(response)
        analysis["task_id"] = task.get("task_id", "")
        analysis["agent_id"] = agent_id or ""
        analysis["category"] = category
        analysis["timestamp"] = time.time()
        analysis["analysis_provider"] = self._analysis_provider
        analysis["analysis_elapsed_ms"] = llm_result.get("elapsed_ms", 0)

        # Store learnings in agent memory
        if agent_id and self._memory:
            self._store_learnings(agent_id, analysis, category)

        # Store analysis in persistence for historical tracking
        self._store_analysis(analysis)

        # Update quality scores
        self._update_scores(agent_id, category, analysis.get("grade", 5))

        # Auto-enhance agent skills from outcome
        if agent_id and hasattr(self, '_skill_manager') and self._skill_manager:
            try:
                keywords = analysis.get("learnings", [])
                changes = self._skill_manager.enhance_from_outcome(
                    agent_id, category, analysis.get("grade", 5),
                    task_keywords=keywords[:5],
                )
                self._skill_manager.record_enhancement(agent_id, changes)
                analysis["skill_changes"] = changes
            except Exception as e:
                logger.warning("Skill enhancement failed for %s: %s", agent_id, e)

        # Alert on low quality outcomes
        if hasattr(self, '_alert_system') and self._alert_system:
            try:
                grade = analysis.get("grade", 5)
                if grade <= 3:
                    self._alert_system.on_low_grade(
                        agent_id or "unknown", task.get("task_id", ""), grade, category)
            except Exception as e:
                logger.debug("Alert system notification failed: %s", e)

        # Update agent reputation
        if hasattr(self, '_reputation') and self._reputation and agent_id:
            try:
                self._reputation.update_from_outcome(agent_id, analysis.get("grade", 5))
            except Exception as e:
                logger.debug("Reputation update failed: %s", e)

        # Feed into prompt evolution tracker
        if self._prompt_evolution and agent_id:
            import hashlib
            prompt_hash = hashlib.md5(
                task.get("_system_prompt", "default").encode()
            ).hexdigest()[:8]
            self._prompt_evolution.record_prompt_result(
                agent_id, category, prompt_hash, analysis.get("grade", 5)
            )

        logger.info("Outcome analyzed: task=%s grade=%s quality=%s learnings=%d",
                     task.get("task_id"), analysis.get("grade"), analysis.get("quality"),
                     len(analysis.get("learnings", [])))

        return analysis

    def _parse_analysis(self, response: str) -> dict:
        """Parse the structured LLM response into a dict."""
        analysis = {
            "grade": 5,
            "quality": "fair",
            "learnings": [],
            "prompt_insight": "",
            "reusable_pattern": "",
            "raw_response": response[:1000],
        }

        for line in response.split("\n"):
            line = line.strip()
            if line.startswith("GRADE:"):
                try:
                    analysis["grade"] = max(1, min(10, int(line.split(":", 1)[1].strip())))
                except (ValueError, IndexError):
                    pass
            elif line.startswith("QUALITY:"):
                q = line.split(":", 1)[1].strip().lower()
                if q in ("poor", "fair", "good", "excellent"):
                    analysis["quality"] = q
            elif line.startswith("- ") and analysis.get("_in_learnings"):
                analysis["learnings"].append(line[2:].strip())
            elif line.startswith("LEARNINGS:"):
                analysis["_in_learnings"] = True
            elif line.startswith("PROMPT_INSIGHT:"):
                analysis["prompt_insight"] = line.split(":", 1)[1].strip()
                analysis.pop("_in_learnings", None)
            elif line.startswith("REUSABLE_PATTERN:"):
                analysis["reusable_pattern"] = line.split(":", 1)[1].strip()
                analysis.pop("_in_learnings", None)

        analysis.pop("_in_learnings", None)
        return analysis

    def _store_learnings(self, agent_id: str, analysis: dict, category: str):
        """Auto-store extracted learnings into agent long-term memory."""
        for learning in analysis.get("learnings", []):
            if learning and len(learning) > 10:
                self._memory.remember(agent_id, learning, category=category)

        pattern = analysis.get("reusable_pattern", "")
        if pattern and len(pattern) > 10:
            self._memory.remember(agent_id, f"[pattern] {pattern}", category="patterns")

        insight = analysis.get("prompt_insight", "")
        if insight and len(insight) > 10:
            self._memory.remember(agent_id, f"[prompt] {insight}", category="prompt_insights")

    def _store_analysis(self, analysis: dict):
        """Store analysis in persistence for historical tracking."""
        key = "outcome_analyses"
        analyses = self._persistence.kv_get(key, [])
        analyses.append({
            "task_id": analysis.get("task_id"),
            "agent_id": analysis.get("agent_id"),
            "category": analysis.get("category"),
            "grade": analysis.get("grade"),
            "quality": analysis.get("quality"),
            "learnings_count": len(analysis.get("learnings", [])),
            "timestamp": analysis.get("timestamp"),
        })
        # Keep last 500 analyses
        if len(analyses) > 500:
            analyses = analyses[-500:]
        self._persistence.kv_set(key, analyses)

    def _update_scores(self, agent_id: str, category: str, grade: int):
        """Update rolling quality scores per agent and per category."""
        # Per-agent scores
        if agent_id:
            key = f"quality_scores:agent:{agent_id}"
            scores = self._persistence.kv_get(key, {"total": 0, "sum": 0, "by_category": {}})
            scores["total"] = scores.get("total", 0) + 1
            scores["sum"] = scores.get("sum", 0) + grade
            scores["avg"] = round(scores["sum"] / scores["total"], 2)
            scores["last_grade"] = grade
            scores["last_updated"] = time.time()

            # Per-category within agent
            cat_scores = scores.get("by_category", {})
            cat = cat_scores.get(category, {"total": 0, "sum": 0})
            cat["total"] = cat.get("total", 0) + 1
            cat["sum"] = cat.get("sum", 0) + grade
            cat["avg"] = round(cat["sum"] / cat["total"], 2)
            cat_scores[category] = cat
            scores["by_category"] = cat_scores
            self._persistence.kv_set(key, scores)

        # Global per-category scores
        key = f"quality_scores:category:{category}"
        scores = self._persistence.kv_get(key, {"total": 0, "sum": 0})
        scores["total"] = scores.get("total", 0) + 1
        scores["sum"] = scores.get("sum", 0) + grade
        scores["avg"] = round(scores["sum"] / scores["total"], 2)
        self._persistence.kv_set(key, scores)

    # ── Query methods ──

    def get_agent_scores(self, agent_id: str) -> dict:
        """Get quality scores for an agent."""
        return self._persistence.kv_get(f"quality_scores:agent:{agent_id}",
                                        {"total": 0, "avg": 0, "by_category": {}})

    def get_category_scores(self, category: str) -> dict:
        """Get quality scores for a task category."""
        return self._persistence.kv_get(f"quality_scores:category:{category}",
                                        {"total": 0, "avg": 0})

    def get_all_scores(self) -> dict:
        """Get quality scores summary across all agents and categories."""
        agents_scores = {}
        category_scores = {}

        # Scan kv_store for score keys
        for cat in ["bug", "feature", "enhancement", "qa", "docs", "security", "ops", "general"]:
            s = self.get_category_scores(cat)
            if s.get("total", 0) > 0:
                category_scores[cat] = s

        return {"categories": category_scores}

    def get_recent_analyses(self, limit: int = 20) -> List[dict]:
        """Get recent outcome analyses."""
        analyses = self._persistence.kv_get("outcome_analyses", [])
        return analyses[-limit:]

    def get_insights(self) -> dict:
        """Generate aggregate insights from all analyses."""
        analyses = self._persistence.kv_get("outcome_analyses", [])
        if not analyses:
            return {"total_analyzed": 0}

        grades = [a.get("grade", 5) for a in analyses]
        by_quality = {}
        for a in analyses:
            q = a.get("quality", "fair")
            by_quality[q] = by_quality.get(q, 0) + 1

        return {
            "total_analyzed": len(analyses),
            "avg_grade": round(sum(grades) / len(grades), 2),
            "grade_distribution": {
                "1-3 (poor)": sum(1 for g in grades if g <= 3),
                "4-6 (fair)": sum(1 for g in grades if 4 <= g <= 6),
                "7-8 (good)": sum(1 for g in grades if 7 <= g <= 8),
                "9-10 (excellent)": sum(1 for g in grades if g >= 9),
            },
            "quality_distribution": by_quality,
        }
