"""A2A Agent Card Registry (DOC-017 Section 10, DOC-018 G19)

Agents register capabilities. Other agents discover via semantic search.
CortexDB is the A2A registry: agents find each other through CortexDB.
"""

import time
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("cortexdb.a2a.registry")


@dataclass
class AgentCard:
    """A2A Agent Card - agent capability advertisement."""
    agent_id: str
    name: str
    description: str
    skills: List[str] = field(default_factory=list)
    tools: List[str] = field(default_factory=list)
    auth: Dict = field(default_factory=dict)
    endpoint_url: str = ""
    protocol: str = "mcp"  # mcp | rest | grpc
    model: str = ""
    max_concurrent_tasks: int = 5
    tenant_id: Optional[str] = None
    metadata: Dict = field(default_factory=dict)
    registered_at: float = field(default_factory=time.time)
    last_heartbeat: float = field(default_factory=time.time)

    @property
    def is_alive(self) -> bool:
        return (time.time() - self.last_heartbeat) < 300  # 5 min timeout

    @property
    def skills_text(self) -> str:
        """Concatenated skills for embedding/search."""
        return f"{self.name}: {self.description}. Skills: {', '.join(self.skills)}"


class A2ARegistry:
    """Agent-to-Agent registry. Store, discover, and manage agent cards.

    Storage:
      - In-memory for fast lookup
      - RelationalCore for persistence (a2a_agent_cards table)
      - VectorCore for semantic discovery (embed skills description)
    """

    def __init__(self, engines: Dict[str, Any] = None):
        self.engines = engines or {}
        self._cards: Dict[str, AgentCard] = {}

    async def register(self, card: AgentCard) -> Dict:
        """Register or update an agent card."""
        self._cards[card.agent_id] = card

        # Persist to RelationalCore
        if "relational" in self.engines:
            try:
                import json
                await self.engines["relational"].execute(
                    "INSERT INTO a2a_agent_cards "
                    "(agent_id, name, description, skills, tools, auth_config, "
                    "endpoint_url, protocol, model, tenant_id, metadata) "
                    "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11) "
                    "ON CONFLICT (agent_id) DO UPDATE SET "
                    "name=$2, description=$3, skills=$4, tools=$5, "
                    "endpoint_url=$7, last_heartbeat=NOW()",
                    [card.agent_id, card.name, card.description,
                     card.skills, card.tools, json.dumps(card.auth),
                     card.endpoint_url, card.protocol, card.model,
                     card.tenant_id, json.dumps(card.metadata)])
            except Exception as e:
                logger.warning(f"Failed to persist agent card: {e}")

        logger.info(f"A2A agent registered: {card.agent_id} ({card.name})")
        return {"agent_id": card.agent_id, "status": "registered",
                "skills": card.skills}

    async def deregister(self, agent_id: str):
        self._cards.pop(agent_id, None)

    async def discover(self, skill: str, tenant_id: Optional[str] = None,
                       limit: int = 5) -> List[Dict]:
        """Discover agents by skill (keyword match, upgradeable to semantic)."""
        results = []
        skill_lower = skill.lower()

        for card in self._cards.values():
            if tenant_id and card.tenant_id and card.tenant_id != tenant_id:
                continue
            if not card.is_alive:
                continue

            # Keyword match on skills and description
            score = 0
            for s in card.skills:
                if skill_lower in s.lower():
                    score += 1.0
            if skill_lower in card.description.lower():
                score += 0.5
            if skill_lower in card.name.lower():
                score += 0.3

            if score > 0:
                results.append({
                    "agent_id": card.agent_id, "name": card.name,
                    "description": card.description, "skills": card.skills,
                    "endpoint_url": card.endpoint_url, "protocol": card.protocol,
                    "relevance_score": score,
                })

        results.sort(key=lambda x: x["relevance_score"], reverse=True)
        return results[:limit]

    async def heartbeat(self, agent_id: str) -> bool:
        card = self._cards.get(agent_id)
        if card:
            card.last_heartbeat = time.time()
            return True
        return False

    def get_card(self, agent_id: str) -> Optional[AgentCard]:
        return self._cards.get(agent_id)

    def list_cards(self, tenant_id: Optional[str] = None,
                   alive_only: bool = True) -> List[Dict]:
        cards = list(self._cards.values())
        if tenant_id:
            cards = [c for c in cards if c.tenant_id == tenant_id]
        if alive_only:
            cards = [c for c in cards if c.is_alive]
        return [{"agent_id": c.agent_id, "name": c.name,
                 "skills": c.skills, "protocol": c.protocol,
                 "is_alive": c.is_alive, "tenant_id": c.tenant_id}
                for c in cards]

    def get_stats(self) -> Dict:
        alive = sum(1 for c in self._cards.values() if c.is_alive)
        return {"total_agents": len(self._cards), "alive": alive,
                "dead": len(self._cards) - alive}
