"""
Agent Skill System — Structured skill profiles with levels, XP, and auto-enhancement.

Each skill has:
  - category: technical, domain, soft, operational
  - level: novice(1) -> beginner(2) -> intermediate(3) -> advanced(4) -> expert(5)
  - xp: experience points accumulated from task outcomes
  - confidence: rolling quality score (0-1) from outcome analyses
  - endorsements: count of high-grade task completions for this skill

Skills auto-enhance when:
  - XP crosses level thresholds (from completed tasks in matching categories)
  - Confidence rises above thresholds (from outcome analysis grades)
  - New skills are discovered from task patterns (LLM-identified)
"""

import time
import logging
from typing import Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from cortexdb.superadmin.agent_team import AgentTeamManager
    from cortexdb.superadmin.persistence import PersistenceStore

logger = logging.getLogger(__name__)

# XP thresholds per level
LEVEL_THRESHOLDS = {
    1: 0,       # novice
    2: 50,      # beginner
    3: 150,     # intermediate
    4: 400,     # advanced
    5: 1000,    # expert
}

LEVEL_NAMES = {
    1: "novice",
    2: "beginner",
    3: "intermediate",
    4: "advanced",
    5: "expert",
}

# XP awards per task grade
GRADE_XP = {
    1: 2, 2: 4, 3: 6, 4: 8, 5: 10,
    6: 14, 7: 20, 8: 28, 9: 38, 10: 50,
}

# Skill categories
SKILL_CATEGORIES = ["technical", "domain", "soft", "operational"]

# Map agent departments and known skill tags to categories
SKILL_CATEGORY_MAP = {
    # Technical
    "python": "technical", "typescript": "technical", "fastapi": "technical",
    "nextjs": "technical", "react": "technical", "postgresql": "technical",
    "redis": "technical", "sql": "technical", "docker": "technical",
    "kubernetes": "technical", "ci-cd": "technical", "github-actions": "technical",
    "async-programming": "technical", "tailwindcss": "technical", "zustand": "technical",
    "playwright": "technical", "pytest": "technical", "jest": "technical",
    "openapi": "technical", "swagger": "technical", "mcp": "technical",
    "a2a": "technical", "prometheus": "technical", "grafana": "technical",
    # Domain
    "system-design": "domain", "api-design": "domain", "database-design": "domain",
    "distributed-systems": "domain", "data-modeling": "domain", "query-optimization": "domain",
    "security-architecture": "domain", "threat-modeling": "domain",
    "test-strategy": "domain", "load-testing": "domain", "benchmarking": "domain",
    "security-testing": "domain", "owasp": "domain", "compliance-audit": "domain",
    "soc2": "domain", "hipaa": "domain", "pci-dss": "domain",
    # Soft
    "product-strategy": "soft", "decision-making": "soft", "coordination": "soft",
    "planning": "soft", "knowledge-management": "soft", "technical-writing": "soft",
    "documentation": "soft", "code-review": "soft",
    # Operational
    "devops": "operational", "deployment": "operational", "containerization": "operational",
    "monitoring": "operational", "alerting": "operational", "log-analysis": "operational",
    "incident-response": "operational", "infrastructure": "operational",
    "scaling": "operational", "networking": "operational", "backup": "operational",
    "disaster-recovery": "operational", "key-management": "operational",
    "encryption": "operational", "authentication": "operational", "secrets": "operational",
}

# Task category -> which skill tags are relevant
TASK_SKILL_MAP = {
    "bug": ["python", "typescript", "fastapi", "debugging", "code-review"],
    "feature": ["python", "typescript", "system-design", "api-design", "react", "fastapi"],
    "enhancement": ["python", "typescript", "code-review", "system-design"],
    "qa": ["test-strategy", "pytest", "jest", "e2e-testing", "automation", "quality-assurance"],
    "docs": ["technical-writing", "documentation", "api-docs", "user-guides"],
    "security": ["security-testing", "owasp", "compliance-audit", "threat-modeling", "encryption"],
    "ops": ["devops", "docker", "ci-cd", "monitoring", "deployment"],
    "general": [],
}


class SkillEntry:
    """A single skill with level, XP, and tracking data."""

    def __init__(self, name: str, category: str = "technical",
                 level: int = 1, xp: int = 0, confidence: float = 0.5,
                 endorsements: int = 0):
        self.name = name
        self.category = category
        self.level = level
        self.xp = xp
        self.confidence = confidence
        self.endorsements = endorsements
        self.task_count = 0
        self.last_used: Optional[float] = None
        self.created_at = time.time()
        self.history: List[dict] = []  # recent XP events (last 20)

    def add_xp(self, amount: int, source: str = "task"):
        """Add XP and check for level up."""
        old_level = self.level
        self.xp += amount
        self.task_count += 1
        self.last_used = time.time()

        # Check level up
        for lvl in sorted(LEVEL_THRESHOLDS.keys(), reverse=True):
            if self.xp >= LEVEL_THRESHOLDS[lvl]:
                self.level = lvl
                break

        leveled_up = self.level > old_level

        self.history.append({
            "xp": amount, "source": source,
            "level": self.level, "leveled_up": leveled_up,
            "timestamp": time.time(),
        })
        if len(self.history) > 20:
            self.history = self.history[-20:]

        return leveled_up

    def update_confidence(self, grade: int, weight: float = 0.3):
        """Update rolling confidence from task grade (1-10 -> 0-1)."""
        new_val = grade / 10.0
        self.confidence = self.confidence * (1 - weight) + new_val * weight
        if grade >= 8:
            self.endorsements += 1

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "category": self.category,
            "level": self.level,
            "level_name": LEVEL_NAMES.get(self.level, "novice"),
            "xp": self.xp,
            "xp_to_next": self._xp_to_next(),
            "confidence": round(self.confidence, 3),
            "endorsements": self.endorsements,
            "task_count": self.task_count,
            "last_used": self.last_used,
            "created_at": self.created_at,
        }

    def _xp_to_next(self) -> Optional[int]:
        next_lvl = self.level + 1
        if next_lvl > 5:
            return None
        return LEVEL_THRESHOLDS[next_lvl] - self.xp

    @staticmethod
    def from_dict(data: dict) -> "SkillEntry":
        s = SkillEntry(
            name=data["name"],
            category=data.get("category", "technical"),
            level=data.get("level", 1),
            xp=data.get("xp", 0),
            confidence=data.get("confidence", 0.5),
            endorsements=data.get("endorsements", 0),
        )
        s.task_count = data.get("task_count", 0)
        s.last_used = data.get("last_used")
        s.created_at = data.get("created_at", time.time())
        s.history = data.get("history", [])
        return s


class AgentSkillManager:
    """Manages structured skill profiles for all agents."""

    def __init__(self, team: "AgentTeamManager", persistence: "PersistenceStore"):
        self._team = team
        self._persistence = persistence
        self._profiles: Dict[str, Dict[str, SkillEntry]] = {}
        self._load_profiles()

    def _load_profiles(self):
        """Load skill profiles from persistence, bootstrapping from agent skill lists."""
        saved = self._persistence.kv_get("agent_skill_profiles", {})

        # Load saved profiles
        for agent_id, skills_data in saved.items():
            self._profiles[agent_id] = {}
            for skill_name, sdata in skills_data.items():
                self._profiles[agent_id][skill_name] = SkillEntry.from_dict(sdata)

        # Bootstrap: ensure every agent has a profile from their static skills
        for agent in self._team.get_all_agents():
            agent_id = agent["agent_id"]
            if agent_id not in self._profiles:
                self._profiles[agent_id] = {}
            for skill_name in agent.get("skills", []):
                if skill_name not in self._profiles[agent_id]:
                    category = SKILL_CATEGORY_MAP.get(skill_name, "technical")
                    self._profiles[agent_id][skill_name] = SkillEntry(
                        name=skill_name, category=category,
                    )

        self._save_profiles()

    def _save_profiles(self):
        data = {}
        for agent_id, skills in self._profiles.items():
            data[agent_id] = {
                name: entry.to_dict() for name, entry in skills.items()
            }
        self._persistence.kv_set("agent_skill_profiles", data)

    # ── Query ──

    def get_profile(self, agent_id: str) -> dict:
        """Get full skill profile for an agent."""
        skills = self._profiles.get(agent_id, {})
        entries = [e.to_dict() for e in skills.values()]
        entries.sort(key=lambda x: (-x["level"], -x["xp"]))

        by_category = {}
        for e in entries:
            cat = e["category"]
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(e)

        total_xp = sum(e["xp"] for e in entries)
        avg_level = sum(e["level"] for e in entries) / len(entries) if entries else 0
        avg_confidence = sum(e["confidence"] for e in entries) / len(entries) if entries else 0

        return {
            "agent_id": agent_id,
            "skills": entries,
            "by_category": by_category,
            "summary": {
                "total_skills": len(entries),
                "total_xp": total_xp,
                "avg_level": round(avg_level, 2),
                "avg_confidence": round(avg_confidence, 3),
                "total_endorsements": sum(e["endorsements"] for e in entries),
                "expert_skills": sum(1 for e in entries if e["level"] >= 5),
                "advanced_skills": sum(1 for e in entries if e["level"] >= 4),
            },
        }

    def get_all_profiles_summary(self) -> List[dict]:
        """Get summary of skill profiles for all agents."""
        summaries = []
        for agent_id in self._profiles:
            agent = self._team.get_agent(agent_id)
            profile = self.get_profile(agent_id)
            summaries.append({
                "agent_id": agent_id,
                "agent_name": agent.get("name", "") if agent else "",
                "department": agent.get("department", "") if agent else "",
                **profile["summary"],
            })
        summaries.sort(key=lambda x: -x["total_xp"])
        return summaries

    def get_skill_leaderboard(self, skill_name: str = None) -> List[dict]:
        """Get agents ranked by a specific skill or overall XP."""
        board = []
        for agent_id, skills in self._profiles.items():
            agent = self._team.get_agent(agent_id)
            if skill_name:
                entry = skills.get(skill_name)
                if entry:
                    board.append({
                        "agent_id": agent_id,
                        "agent_name": agent.get("name", "") if agent else "",
                        "skill": skill_name,
                        "level": entry.level,
                        "level_name": LEVEL_NAMES.get(entry.level, "novice"),
                        "xp": entry.xp,
                        "confidence": round(entry.confidence, 3),
                    })
            else:
                total_xp = sum(e.xp for e in skills.values())
                board.append({
                    "agent_id": agent_id,
                    "agent_name": agent.get("name", "") if agent else "",
                    "total_xp": total_xp,
                    "skill_count": len(skills),
                    "avg_level": round(sum(e.level for e in skills.values()) / max(len(skills), 1), 1),
                })
        board.sort(key=lambda x: -(x.get("xp", 0) or x.get("total_xp", 0)))
        return board

    # ── Skill Enhancement (called after task outcomes) ──

    def enhance_from_outcome(self, agent_id: str, task_category: str,
                             grade: int, task_keywords: List[str] = None) -> dict:
        """Enhance agent skills based on a task outcome.

        Called by outcome_analyzer after grading. Awards XP to matching skills
        and updates confidence scores.

        Returns dict of changes (level ups, new skills, xp awarded).
        """
        if agent_id not in self._profiles:
            self._profiles[agent_id] = {}

        skills = self._profiles[agent_id]
        xp_amount = GRADE_XP.get(grade, 10)
        changes = {"xp_awarded": {}, "level_ups": [], "new_skills": [], "confidence_updates": []}

        # Find matching skills for this task category
        relevant_tags = set(TASK_SKILL_MAP.get(task_category, []))
        if task_keywords:
            relevant_tags.update(k.lower() for k in task_keywords)

        # Award XP to skills that overlap with the task
        awarded_any = False
        for skill_name, entry in skills.items():
            if skill_name.lower() in relevant_tags or task_category.lower() in skill_name.lower():
                leveled_up = entry.add_xp(xp_amount, source=f"task:{task_category}")
                entry.update_confidence(grade)
                changes["xp_awarded"][skill_name] = xp_amount
                changes["confidence_updates"].append({
                    "skill": skill_name,
                    "confidence": round(entry.confidence, 3),
                })
                if leveled_up:
                    changes["level_ups"].append({
                        "skill": skill_name,
                        "new_level": entry.level,
                        "level_name": LEVEL_NAMES.get(entry.level, ""),
                    })
                awarded_any = True

        # If no skills matched, award smaller XP to all skills in the agent's profile
        if not awarded_any:
            base_xp = max(xp_amount // 3, 1)
            for skill_name, entry in skills.items():
                entry.add_xp(base_xp, source=f"task:{task_category}:ambient")
                entry.update_confidence(grade, weight=0.1)

        # Discover new skills from task keywords if grade is high
        if grade >= 7 and task_keywords:
            for keyword in task_keywords:
                kw = keyword.lower().strip()
                if kw and kw not in skills and len(kw) > 2:
                    category = SKILL_CATEGORY_MAP.get(kw, "technical")
                    new_entry = SkillEntry(name=kw, category=category)
                    new_entry.add_xp(xp_amount, source="discovered")
                    new_entry.update_confidence(grade)
                    skills[kw] = new_entry
                    changes["new_skills"].append({
                        "skill": kw, "category": category,
                        "source": "task_outcome",
                    })

        self._save_profiles()

        logger.info("Skills enhanced for %s: %d XP awards, %d level-ups, %d new skills",
                     agent_id, len(changes["xp_awarded"]),
                     len(changes["level_ups"]), len(changes["new_skills"]))
        return changes

    # ── Manual Skill Management ──

    def add_skill(self, agent_id: str, skill_name: str,
                  category: str = None, level: int = 1) -> dict:
        """Manually add a skill to an agent."""
        if agent_id not in self._profiles:
            self._profiles[agent_id] = {}

        if skill_name in self._profiles[agent_id]:
            return {"error": "Skill already exists", "skill": skill_name}

        cat = category or SKILL_CATEGORY_MAP.get(skill_name, "technical")
        entry = SkillEntry(name=skill_name, category=cat, level=level)
        # Set initial XP to match the level
        entry.xp = LEVEL_THRESHOLDS.get(level, 0)
        self._profiles[agent_id][skill_name] = entry

        # Also add to the agent's static skill list
        agent = self._team.get_agent(agent_id)
        if agent:
            agent_skills = agent.get("skills", [])
            if skill_name not in agent_skills:
                agent_skills.append(skill_name)
                self._team.update_agent(agent_id, {"skills": agent_skills})

        self._save_profiles()
        return entry.to_dict()

    def remove_skill(self, agent_id: str, skill_name: str) -> dict:
        """Remove a skill from an agent."""
        skills = self._profiles.get(agent_id, {})
        if skill_name not in skills:
            return {"error": "Skill not found"}

        del skills[skill_name]

        # Also remove from static list
        agent = self._team.get_agent(agent_id)
        if agent:
            agent_skills = [s for s in agent.get("skills", []) if s != skill_name]
            self._team.update_agent(agent_id, {"skills": agent_skills})

        self._save_profiles()
        return {"removed": skill_name}

    def get_skill_catalog(self) -> dict:
        """Get all known skills across all agents with usage stats."""
        catalog: Dict[str, dict] = {}
        for agent_id, skills in self._profiles.items():
            for name, entry in skills.items():
                if name not in catalog:
                    catalog[name] = {
                        "name": name,
                        "category": entry.category,
                        "agent_count": 0,
                        "max_level": 0,
                        "total_xp": 0,
                    }
                catalog[name]["agent_count"] += 1
                catalog[name]["max_level"] = max(catalog[name]["max_level"], entry.level)
                catalog[name]["total_xp"] += entry.xp

        items = sorted(catalog.values(), key=lambda x: -x["agent_count"])
        by_category: Dict[str, list] = {}
        for item in items:
            cat = item["category"]
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(item)

        return {
            "total_unique_skills": len(catalog),
            "skills": items,
            "by_category": by_category,
            "categories": SKILL_CATEGORIES,
        }

    def get_enhancement_history(self, agent_id: str) -> List[dict]:
        """Get recent skill enhancement events for an agent."""
        history = self._persistence.kv_get(f"skill_history:{agent_id}", [])
        return history[-50:]

    def record_enhancement(self, agent_id: str, changes: dict):
        """Record an enhancement event in history."""
        key = f"skill_history:{agent_id}"
        history = self._persistence.kv_get(key, [])
        history.append({
            "timestamp": time.time(),
            "xp_awarded": changes.get("xp_awarded", {}),
            "level_ups": changes.get("level_ups", []),
            "new_skills": changes.get("new_skills", []),
        })
        if len(history) > 100:
            history = history[-100:]
        self._persistence.kv_set(key, history)
