"""
Expert Discovery — Find best-qualified agents for questions/domains.

Scores agents using a composite of skill matches, knowledge contributions,
and reputation trust to surface the right expert for any query or task.
"""

import logging
from typing import Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from cortexdb.superadmin.agent_team import AgentTeamManager
    from cortexdb.superadmin.agent_skills import AgentSkillManager
    from cortexdb.superadmin.knowledge_graph import KnowledgeGraphStore
    from cortexdb.superadmin.agent_reputation import AgentReputationManager
    from cortexdb.superadmin.persistence import PersistenceStore

logger = logging.getLogger(__name__)


class ExpertDiscovery:
    """Discovers the best-qualified agents for a given query or domain."""

    def __init__(
        self,
        team: "AgentTeamManager",
        skills: "AgentSkillManager",
        knowledge_graph: "KnowledgeGraphStore",
        reputation: "AgentReputationManager",
        persistence: "PersistenceStore",
    ):
        self._team = team
        self._skills = skills
        self._knowledge_graph = knowledge_graph
        self._reputation = reputation
        self._persistence = persistence

    def find_expert(self, query: str, domain: Optional[str] = None, top_k: int = 5) -> List[dict]:
        """Find top-k agents best qualified for a query string."""
        keywords = [w.lower() for w in query.split() if len(w) > 2]
        if not keywords:
            return []

        agents = self._team.get_all_agents()
        results: List[dict] = []

        for agent in agents:
            agent_id = agent["agent_id"]
            if domain and agent.get("department", "").lower() != domain.lower():
                continue

            # Skill score: matching skill levels / 5
            profile = self._skills.get_profile(agent_id)
            matched_skills: List[str] = []
            skill_total = 0.0
            for skill in profile.get("skills", []):
                if any(kw in skill["name"].lower() for kw in keywords):
                    matched_skills.append(skill["name"])
                    skill_total += skill["level"] / 5.0
            skill_score = min(skill_total, 1.0)

            # Knowledge score: nodes matching query keywords / 10
            nodes = self._knowledge_graph.get_nodes_for_agent(agent_id)
            knowledge_count = 0
            for node in nodes:
                text = (node.get("topic", "") + " " + node.get("content", "")).lower()
                if any(kw in text for kw in keywords):
                    knowledge_count += 1
            knowledge_score = min(knowledge_count / 10.0, 1.0)

            # Trust score from reputation
            trust_score = self._reputation.get_trust_score(agent_id)

            final_score = skill_score * 0.4 + knowledge_score * 0.3 + trust_score * 0.3

            if final_score > 0:
                results.append({
                    "agent_id": agent_id,
                    "name": agent.get("name", ""),
                    "department": agent.get("department", ""),
                    "score": round(final_score, 4),
                    "skills_matched": matched_skills,
                    "knowledge_count": knowledge_count,
                    "trust": round(trust_score, 3),
                })

        results.sort(key=lambda x: -x["score"])
        return results[:top_k]

    def get_domain_map(self) -> dict:
        """Build a map of topics to top agents. Cached in kv_store."""
        cached = self._persistence.kv_get("expert_discovery:domain_map", None)
        if cached:
            return cached

        nodes = self._knowledge_graph.get_all_nodes()
        topics = set(n.get("topic", "") for n in nodes if n.get("topic"))

        domains: Dict[str, List[dict]] = {}
        for topic in topics:
            experts = self.find_expert(topic, top_k=3)
            if experts:
                domains[topic] = [{"agent_id": e["agent_id"], "score": e["score"]} for e in experts]

        result = {"domains": domains}
        self._persistence.kv_set("expert_discovery:domain_map", result)
        return result

    def recommend_for_task(self, task_description: str) -> List[dict]:
        """Extract keywords from a task description and find experts."""
        keywords = [w for w in task_description.split() if len(w) > 3]
        if not keywords:
            return []
        query = " ".join(keywords)
        return self.find_expert(query, top_k=5)

    def get_expertise_matrix(self, department: Optional[str] = None) -> dict:
        """Grid of agents vs skill categories with proficiency levels."""
        agents = self._team.get_all_agents()
        if department:
            agents = [a for a in agents if a.get("department", "").lower() == department.lower()]

        categories: set = set()
        matrix: Dict[str, Dict[str, int]] = {}
        agent_list: List[dict] = []

        for agent in agents:
            agent_id = agent["agent_id"]
            profile = self._skills.get_profile(agent_id)
            agent_list.append({"agent_id": agent_id, "name": agent.get("name", ""),
                               "department": agent.get("department", "")})
            matrix[agent_id] = {}
            for skill in profile.get("skills", []):
                cat = skill.get("category", "technical")
                categories.add(cat)
                existing = matrix[agent_id].get(cat, 0)
                matrix[agent_id][cat] = max(existing, skill["level"])

        return {
            "agents": agent_list,
            "categories": sorted(categories),
            "matrix": matrix,
        }
