"""
Skill-Based Auto-Hiring — Detect skill gaps and spawn agents from templates.

Analyzes:
  - Failed/low-grade tasks by category
  - Skill coverage across departments
  - Template availability
  - Department capacity
"""

import time
import uuid
import logging
from typing import List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from cortexdb.superadmin.agent_team import AgentTeamManager
    from cortexdb.superadmin.agent_skills import AgentSkillManager
    from cortexdb.superadmin.agent_templates import AgentTemplateManager
    from cortexdb.superadmin.persistence import PersistenceStore

logger = logging.getLogger(__name__)


class AutoHiringManager:
    """Detects skill gaps and recommends or auto-spawns agents."""

    def __init__(self, team: "AgentTeamManager", skills: "AgentSkillManager",
                 templates: "AgentTemplateManager", persistence: "PersistenceStore"):
        self._team = team
        self._skills = skills
        self._templates = templates
        self._persistence = persistence

    def detect_gaps(self) -> List[dict]:
        """Analyze skill coverage and find gaps."""
        catalog = self._skills.get_skill_catalog()
        profiles = self._skills.get_all_profiles_summary()
        agents = self._team.get_all_agents()

        gaps = []

        # Check for categories with low quality
        analyses = self._persistence.kv_get("outcome_analyses", [])
        cat_grades = {}
        for a in analyses[-200:]:
            cat = a.get("category", "general")
            grade = a.get("grade", 5)
            if cat not in cat_grades:
                cat_grades[cat] = []
            cat_grades[cat].append(grade)

        for cat, grades in cat_grades.items():
            avg = sum(grades) / len(grades) if grades else 5
            if avg < 5.0 and len(grades) >= 3:
                gaps.append({
                    "type": "low_quality",
                    "category": cat,
                    "avg_grade": round(avg, 2),
                    "task_count": len(grades),
                    "severity": "high" if avg < 3 else "medium",
                })

        # Check for departments with few agents
        dept_counts = {}
        for a in agents:
            dept = a.get("department", "")
            dept_counts[dept] = dept_counts.get(dept, 0) + 1

        for dept, count in dept_counts.items():
            if count <= 2:
                gaps.append({
                    "type": "understaffed",
                    "department": dept,
                    "agent_count": count,
                    "severity": "medium",
                })

        # Check for skills with low max level
        for skill in catalog.get("skills", []):
            if skill["agent_count"] <= 1 and skill["max_level"] <= 2:
                gaps.append({
                    "type": "skill_coverage",
                    "skill": skill["name"],
                    "agent_count": skill["agent_count"],
                    "max_level": skill["max_level"],
                    "severity": "low",
                })

        return gaps

    def recommend_hires(self) -> List[dict]:
        """Generate hiring recommendations based on gaps."""
        gaps = self.detect_gaps()
        templates = self._templates.get_templates()
        recommendations = []

        for gap in gaps:
            matched_templates = []
            for tpl in templates:
                tpl_skills = set(tpl.get("skills", []))
                if gap["type"] == "low_quality":
                    # Match templates by category
                    if gap["category"] in tpl.get("category", ""):
                        matched_templates.append(tpl)
                elif gap["type"] == "skill_coverage":
                    if gap["skill"] in tpl_skills:
                        matched_templates.append(tpl)

            if matched_templates:
                recommendations.append({
                    "gap": gap,
                    "recommended_templates": [t["template_id"] for t in matched_templates[:3]],
                    "template_names": [t["name"] for t in matched_templates[:3]],
                })

        return recommendations

    def auto_hire(self, template_id: str = None, name: str = None) -> dict:
        """Spawn a new agent from a template."""
        if not template_id:
            recs = self.recommend_hires()
            if not recs:
                return {"error": "No hiring recommendations"}
            template_id = recs[0]["recommended_templates"][0]

        result = self._templates.spawn_from_template(template_id, name)
        if "error" in result:
            return result

        # Log hire
        history = self._persistence.kv_get("hiring_history", [])
        history.append({
            "agent_id": result.get("agent_id"),
            "template_id": template_id,
            "name": result.get("name"),
            "hired_at": time.time(),
        })
        self._persistence.kv_set("hiring_history", history)

        logger.info("Auto-hired agent %s from template %s", result.get("agent_id"), template_id)
        return result

    def get_history(self) -> List[dict]:
        return self._persistence.kv_get("hiring_history", [])
