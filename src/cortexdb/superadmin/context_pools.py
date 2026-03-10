"""
Shared Context Pools — Per-department shared context for agent collaboration.

Each department has a pool of context entries contributed by its agents.
Entries are stored as a JSON array in the `context_pools` SQLite table.
Pools are capped at 100 entries and stale entries can be pruned by age.
"""

import json
import time
import uuid
import logging
from typing import List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from cortexdb.superadmin.agent_team import AgentTeamManager
    from cortexdb.superadmin.persistence import PersistenceStore

logger = logging.getLogger(__name__)

MAX_ENTRIES = 100


class SharedContextPools:
    """Manages per-department shared context pools."""

    def __init__(self, team: "AgentTeamManager", persistence: "PersistenceStore"):
        self._team = team
        self._persistence = persistence

    def contribute(self, department: str, agent_id: str, content: str,
                   category: str = "general") -> dict:
        """Add a context entry to a department pool."""
        entry = {
            "id": f"CP-{uuid.uuid4().hex[:8]}",
            "agent_id": agent_id,
            "content": content,
            "category": category,
            "created_at": time.time(),
        }
        row = self._persistence.conn.execute(
            "SELECT pool_id, data, contributors FROM context_pools WHERE department = ?",
            (department,),
        ).fetchone()

        if row:
            entries = json.loads(row["data"])
            contributors = json.loads(row["contributors"])
            entries.append(entry)
            if len(entries) > MAX_ENTRIES:
                entries = entries[-MAX_ENTRIES:]
            if agent_id not in contributors:
                contributors.append(agent_id)
            self._persistence.conn.execute(
                "UPDATE context_pools SET data = ?, contributors = ?, updated_at = ? WHERE pool_id = ?",
                (json.dumps(entries), json.dumps(contributors), time.time(), row["pool_id"]),
            )
        else:
            pool_id = f"pool-{uuid.uuid4().hex[:8]}"
            self._persistence.conn.execute(
                "INSERT INTO context_pools (pool_id, department, pool_type, data, contributors, updated_at) "
                "VALUES (?, ?, 'general', ?, ?, ?)",
                (pool_id, department, json.dumps([entry]), json.dumps([agent_id]), time.time()),
            )
        self._persistence.conn.commit()
        logger.info("Context contributed to %s pool by %s", department, agent_id)
        return entry

    def get_pool(self, department: str, category: Optional[str] = None,
                 limit: int = 50) -> dict:
        """Get pool entries, optionally filtered by category."""
        row = self._persistence.conn.execute(
            "SELECT data, contributors FROM context_pools WHERE department = ?",
            (department,),
        ).fetchone()
        if not row:
            return {"department": department, "entries": [], "total": 0, "contributors": []}
        entries = json.loads(row["data"])
        contributors = json.loads(row["contributors"])
        if category:
            entries = [e for e in entries if e.get("category") == category]
        total = len(entries)
        entries = entries[-limit:]
        return {"department": department, "entries": entries, "total": total,
                "contributors": contributors}

    def get_relevant_context(self, agent_id: str, task_description: str,
                             max_chars: int = 3000) -> str:
        """Get recent pool context for the agent's department."""
        agent = self._team.get_agent(agent_id)
        if not agent:
            return ""
        department = agent.get("department", "")
        if not department:
            return ""
        pool = self.get_pool(department)
        if not pool["entries"]:
            return ""
        parts: List[str] = []
        chars = 0
        for entry in reversed(pool["entries"]):
            line = f"[{entry['agent_id']}] {entry['content']}"
            if chars + len(line) > max_chars:
                break
            parts.append(line)
            chars += len(line)
        parts.reverse()
        return "\n".join(parts)

    def list_pools(self) -> List[dict]:
        """Summary of all context pools."""
        rows = self._persistence.conn.execute(
            "SELECT department, data, contributors, updated_at FROM context_pools"
        ).fetchall()
        result = []
        for r in rows:
            entries = json.loads(r["data"])
            contributors = json.loads(r["contributors"])
            result.append({
                "department": r["department"],
                "entry_count": len(entries),
                "last_updated": r["updated_at"],
                "contributor_count": len(contributors),
            })
        return result

    def prune_stale(self, max_age_days: int = 30) -> dict:
        """Remove entries older than threshold from all pools."""
        cutoff = time.time() - (max_age_days * 86400)
        pruned_count = 0
        pools_affected = 0
        rows = self._persistence.conn.execute(
            "SELECT pool_id, data FROM context_pools"
        ).fetchall()
        for r in rows:
            entries = json.loads(r["data"])
            filtered = [e for e in entries if e.get("created_at", 0) >= cutoff]
            removed = len(entries) - len(filtered)
            if removed > 0:
                pruned_count += removed
                pools_affected += 1
                self._persistence.conn.execute(
                    "UPDATE context_pools SET data = ?, updated_at = ? WHERE pool_id = ?",
                    (json.dumps(filtered), time.time(), r["pool_id"]),
                )
        if pools_affected:
            self._persistence.conn.commit()
        logger.info("Pruned %d stale entries from %d pools", pruned_count, pools_affected)
        return {"pruned_count": pruned_count, "pools_affected": pools_affected}
