"""
Agent Templates & Cloning — Spawn agents from pre-configured templates.

Templates define:
  - Name pattern, title, department, skills
  - System prompt
  - LLM provider/model preferences
  - Default tool access

Cloning creates a new agent from an existing agent's configuration.
"""

import time
import uuid
import logging
from typing import Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from cortexdb.superadmin.agent_team import AgentTeamManager
    from cortexdb.superadmin.persistence import PersistenceStore

logger = logging.getLogger(__name__)

# Built-in templates
BUILTIN_TEMPLATES = [
    {
        "template_id": "tpl-code-reviewer",
        "name": "Code Reviewer",
        "title": "Code Quality Analyst",
        "department": "qa",
        "skills": ["code-review", "bug-detection", "best-practices"],
        "system_prompt": "You are an expert code reviewer. Analyze code for bugs, security issues, performance problems, and adherence to best practices. Provide specific, actionable feedback.",
        "llm_provider": "ollama",
        "category": "qa",
    },
    {
        "template_id": "tpl-technical-writer",
        "name": "Technical Writer",
        "title": "Documentation Specialist",
        "department": "documentation",
        "skills": ["documentation", "api-docs", "user-guides"],
        "system_prompt": "You are a technical writer specializing in clear, concise documentation. Write API docs, user guides, and architecture docs. Use examples and structured formatting.",
        "llm_provider": "ollama",
        "category": "docs",
    },
    {
        "template_id": "tpl-security-auditor",
        "name": "Security Auditor",
        "title": "Security Assessment Specialist",
        "department": "security",
        "skills": ["security-audit", "vulnerability-assessment", "owasp"],
        "system_prompt": "You are a security auditor. Analyze systems and code for vulnerabilities, review security configurations, and provide remediation guidance following OWASP and industry standards.",
        "llm_provider": "ollama",
        "category": "security",
    },
    {
        "template_id": "tpl-devops-engineer",
        "name": "DevOps Engineer",
        "title": "Infrastructure Automation Specialist",
        "department": "operations",
        "skills": ["docker", "kubernetes", "ci-cd", "monitoring"],
        "system_prompt": "You are a DevOps engineer. Design CI/CD pipelines, containerization strategies, monitoring setups, and infrastructure automation. Focus on reliability and observability.",
        "llm_provider": "ollama",
        "category": "ops",
    },
    {
        "template_id": "tpl-data-analyst",
        "name": "Data Analyst",
        "title": "Data Analysis Specialist",
        "department": "engineering",
        "skills": ["sql", "data-analysis", "visualization", "statistics"],
        "system_prompt": "You are a data analyst. Analyze datasets, write SQL queries, identify trends and anomalies, and present findings clearly with statistical rigor.",
        "llm_provider": "ollama",
        "category": "feature",
    },
]


class AgentTemplateManager:
    """Manages agent templates and cloning."""

    def __init__(self, team: "AgentTeamManager", persistence: "PersistenceStore"):
        self._team = team
        self._persistence = persistence
        self._templates: Dict[str, dict] = {}
        self._load_templates()

    def _load_templates(self):
        """Load built-in + custom templates."""
        for tpl in BUILTIN_TEMPLATES:
            self._templates[tpl["template_id"]] = {**tpl, "builtin": True}
        custom = self._persistence.kv_get("agent_templates", {})
        for tid, tpl in custom.items():
            self._templates[tid] = {**tpl, "builtin": False}

    def get_templates(self) -> List[dict]:
        """Get all available templates."""
        return list(self._templates.values())

    def get_template(self, template_id: str) -> Optional[dict]:
        return self._templates.get(template_id)

    def create_template(self, name: str, title: str, department: str,
                        skills: List[str], system_prompt: str,
                        llm_provider: str = "ollama", category: str = "general") -> dict:
        """Create a custom template."""
        tid = f"tpl-{uuid.uuid4().hex[:8]}"
        template = {
            "template_id": tid,
            "name": name,
            "title": title,
            "department": department,
            "skills": skills,
            "system_prompt": system_prompt,
            "llm_provider": llm_provider,
            "category": category,
            "created_at": time.time(),
        }
        self._templates[tid] = {**template, "builtin": False}
        self._save_custom()
        return template

    def spawn_from_template(self, template_id: str,
                            name_override: str = None) -> dict:
        """Spawn a new agent from a template."""
        template = self._templates.get(template_id)
        if not template:
            return {"error": "Template not found"}

        # Generate unique agent ID
        dept_prefix = template["department"][:3].upper()
        seq = str(uuid.uuid4().hex[:4]).upper()
        agent_id = f"CDB-{dept_prefix}-TPL-{seq}"

        agent_name = name_override or f"{template['name']} #{seq}"

        agent_data = {
            "agent_id": agent_id,
            "name": agent_name,
            "title": template["title"],
            "department": template["department"],
            "skills": template.get("skills", []),
            "system_prompt": template.get("system_prompt", ""),
            "llm_provider": template.get("llm_provider", "ollama"),
            "llm_model": template.get("llm_model", ""),
            "state": "active",
            "spawned_from": template_id,
            "created_at": time.time(),
        }

        self._team.add_agent(agent_data)
        logger.info("Spawned agent %s from template %s", agent_id, template_id)
        return agent_data

    def clone_agent(self, source_agent_id: str,
                    name_override: str = None) -> dict:
        """Clone an existing agent's configuration into a new agent."""
        source = self._team.get_agent(source_agent_id)
        if not source:
            return {"error": "Source agent not found"}

        dept = source.get("department", "eng")[:3].upper()
        seq = str(uuid.uuid4().hex[:4]).upper()
        new_id = f"CDB-{dept}-CLN-{seq}"

        clone_data = {
            "agent_id": new_id,
            "name": name_override or f"{source.get('name', 'Agent')} (clone)",
            "title": source.get("title", ""),
            "department": source.get("department", ""),
            "skills": source.get("skills", []),
            "system_prompt": source.get("system_prompt", ""),
            "llm_provider": source.get("llm_provider", "ollama"),
            "llm_model": source.get("llm_model", ""),
            "state": "active",
            "cloned_from": source_agent_id,
            "created_at": time.time(),
        }

        self._team.add_agent(clone_data)
        logger.info("Cloned agent %s -> %s", source_agent_id, new_id)
        return clone_data

    def _save_custom(self):
        """Save custom (non-builtin) templates."""
        custom = {tid: tpl for tid, tpl in self._templates.items()
                  if not tpl.get("builtin")}
        self._persistence.kv_set("agent_templates", custom)
