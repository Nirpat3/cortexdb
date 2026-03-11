"""
AI Copilot — In-dashboard conversational AI assistant.
Uses the existing LLM router to provide contextual help.

Provides multi-turn chat sessions with CortexDB context awareness,
CortexQL query generation, agent behavior explanation, and system
optimization suggestions.

Database: data/superadmin.db (shared with other superadmin modules)
Tables: copilot_sessions, copilot_suggestions
"""

import json
import os
import sqlite3
import time
import uuid
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from cortexdb.superadmin.llm_router import LLMRouter
    from cortexdb.superadmin.agent_team import AgentTeamManager
    from cortexdb.superadmin.persistence import PersistenceStore

logger = logging.getLogger("cortexdb.copilot")

DEFAULT_DB_PATH = os.path.join("data", "superadmin.db")

# ── System prompts ────────────────────────────────────────────────────

COPILOT_SYSTEM_PROMPT = """\
You are CortexDB Copilot, an AI assistant embedded in the CortexDB superadmin dashboard.
You help users understand their data, manage agents, write CortexQL queries, and optimize system performance.

Your capabilities:
- Answer questions about CortexDB architecture, agents, tasks, and data
- Generate CortexQL queries from natural language descriptions
- Explain agent behavior, performance metrics, and activity patterns
- Suggest system optimizations based on current workload and configuration
- Provide troubleshooting guidance for common issues

Always be concise, accurate, and actionable. When generating queries, include explanations.
When suggesting optimizations, prioritize by impact and effort.
"""

QUERY_GEN_PROMPT = """\
You are a CortexQL query generator. Given a natural language description, generate the
corresponding CortexQL query. CortexQL is similar to SQL but optimized for CortexDB's
multi-engine architecture.

Supported operations:
- SELECT, INSERT, UPDATE, DELETE for relational data
- SEARCH for vector/semantic queries
- STREAM for time-series data
- GRAPH TRAVERSE for knowledge graph queries

Return your response as JSON with keys:
- "query": the CortexQL query string
- "explanation": brief explanation of what the query does
- "engine": which CortexDB engine handles this query (relational, vector, stream, graph)
"""

OPTIMIZATION_PROMPT = """\
You are a CortexDB performance optimization advisor. Analyze the provided system metrics
and agent workload data to suggest improvements.

Focus areas:
- Agent workload balancing and task distribution
- LLM provider cost optimization and model selection
- Memory and resource utilization
- Task pipeline efficiency
- Knowledge graph connectivity

Return suggestions as a JSON array where each item has:
- "category": one of (performance, cost, reliability, scalability)
- "title": short title
- "description": detailed recommendation
- "impact": one of (high, medium, low)
- "effort": one of (high, medium, low)
"""


class CopilotManager:
    """In-dashboard AI copilot with persistent chat sessions and context awareness.

    Integrates with the LLM router for AI responses, agent team for context,
    and persistence store for session history. All session data is stored in
    SQLite for durability across restarts.
    """

    def __init__(
        self,
        llm_router: "LLMRouter",
        agent_team: "AgentTeamManager",
        persistence_store: "PersistenceStore",
        db_path: str = DEFAULT_DB_PATH,
    ):
        self._router = llm_router
        self._team = agent_team
        self._store = persistence_store
        self.db_path = db_path
        self.db: Optional[sqlite3.Connection] = None
        self._init_db()

    # ── Database setup ────────────────────────────────────────────────

    def _get_connection(self) -> sqlite3.Connection:
        """Get or create a SQLite connection with row factory."""
        if self.db is None or not self._connection_alive():
            db_dir = os.path.dirname(self.db_path)
            if db_dir:
                os.makedirs(db_dir, exist_ok=True)
            self.db = sqlite3.connect(self.db_path, timeout=10.0)
            self.db.row_factory = sqlite3.Row
            self.db.execute("PRAGMA journal_mode=WAL")
            self.db.execute("PRAGMA foreign_keys=ON")
        return self.db

    def _connection_alive(self) -> bool:
        """Check if the current connection is still usable."""
        try:
            self.db.execute("SELECT 1")
            return True
        except Exception:
            return False

    def _init_db(self) -> None:
        """Ensure DB connection is ready. Tables are managed by migrations (v5)."""
        self._get_connection()
        logger.info("Copilot tables initialized (managed by migrations)")

    # ── Session management ────────────────────────────────────────────

    def create_session(self, user_id: str = "superadmin", title: str = None) -> dict:
        """Create a new chat session.

        Args:
            user_id: The user creating the session.
            title: Optional session title. Auto-generated if not provided.

        Returns:
            Dict with session id, user_id, title, and timestamps.
        """
        session_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        title = title or f"Session {now[:10]}"

        conn = self._get_connection()
        conn.execute(
            """
            INSERT INTO copilot_sessions (id, user_id, title, messages, created_at, updated_at)
            VALUES (?, ?, ?, '[]', ?, ?)
            """,
            (session_id, user_id, title, now, now),
        )
        conn.commit()
        logger.info("Created copilot session %s for user %s", session_id, user_id)

        return {
            "id": session_id,
            "user_id": user_id,
            "title": title,
            "messages": [],
            "created_at": now,
            "updated_at": now,
        }

    def list_sessions(self, user_id: str = "superadmin", limit: int = 20) -> list:
        """List recent chat sessions for a user.

        Args:
            user_id: Filter sessions by user.
            limit: Maximum number of sessions to return.

        Returns:
            List of session dicts (without full message history).
        """
        conn = self._get_connection()
        rows = conn.execute(
            """
            SELECT id, user_id, title, messages, created_at, updated_at
            FROM copilot_sessions
            WHERE user_id = ?
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()

        sessions = []
        for row in rows:
            messages = json.loads(row["messages"])
            sessions.append({
                "id": row["id"],
                "user_id": row["user_id"],
                "title": row["title"],
                "message_count": len(messages),
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            })
        return sessions

    def get_session(self, session_id: str) -> dict:
        """Get a session with its full message history.

        Args:
            session_id: The session to retrieve.

        Returns:
            Dict with session data and messages, or error dict if not found.
        """
        conn = self._get_connection()
        row = conn.execute(
            "SELECT * FROM copilot_sessions WHERE id = ?",
            (session_id,),
        ).fetchone()

        if row is None:
            return {"error": "Session not found", "session_id": session_id}

        return {
            "id": row["id"],
            "user_id": row["user_id"],
            "title": row["title"],
            "messages": json.loads(row["messages"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def delete_session(self, session_id: str) -> dict:
        """Delete a chat session and its suggestions.

        Args:
            session_id: The session to delete.

        Returns:
            Dict with success status.
        """
        conn = self._get_connection()
        row = conn.execute(
            "SELECT id FROM copilot_sessions WHERE id = ?", (session_id,)
        ).fetchone()
        if row is None:
            return {"error": "Session not found", "session_id": session_id}

        conn.execute("DELETE FROM copilot_suggestions WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM copilot_sessions WHERE id = ?", (session_id,))
        conn.commit()
        logger.info("Deleted copilot session %s", session_id)

        return {"success": True, "deleted": session_id}

    # ── Context building ──────────────────────────────────────────────

    def _build_system_context(self) -> str:
        """Build contextual information about the current CortexDB state."""
        parts = [COPILOT_SYSTEM_PROMPT]

        # Agent context
        try:
            agents = self._team.list_agents() if hasattr(self._team, "list_agents") else []
            if agents:
                agent_summary = []
                for a in agents[:20]:
                    if isinstance(a, dict):
                        agent_summary.append(
                            f"- {a.get('agent_id', '?')}: {a.get('name', '?')} "
                            f"({a.get('department', '?')}, {a.get('state', '?')})"
                        )
                    else:
                        agent_summary.append(
                            f"- {getattr(a, 'agent_id', '?')}: {getattr(a, 'name', '?')} "
                            f"({getattr(a, 'department', '?')}, {getattr(a, 'state', '?')})"
                        )
                parts.append(f"\n## Active Agents ({len(agents)} total)")
                parts.append("\n".join(agent_summary))
        except Exception as e:
            logger.debug("Could not load agent context: %s", e)

        # Task context
        try:
            tasks = self._store.load_tasks()
            if tasks:
                status_counts: Dict[str, int] = {}
                for t in tasks.values():
                    status = t.get("status", "unknown")
                    status_counts[status] = status_counts.get(status, 0) + 1
                parts.append(f"\n## Tasks ({len(tasks)} total)")
                for status, count in sorted(status_counts.items()):
                    parts.append(f"- {status}: {count}")
        except Exception as e:
            logger.debug("Could not load task context: %s", e)

        # Provider status
        try:
            provider_status = self._router.get_providers_status()
            parts.append("\n## LLM Providers")
            for provider, info in provider_status.items():
                if provider.startswith("_"):
                    continue
                if isinstance(info, dict):
                    configured = info.get("configured", False)
                    enabled = info.get("enabled", False)
                    model = info.get("model", "unknown")
                    parts.append(f"- {provider}: {'enabled' if enabled else 'disabled'} "
                                 f"(model: {model}, configured: {configured})")
        except Exception as e:
            logger.debug("Could not load provider context: %s", e)

        return "\n".join(parts)

    # ── Chat ──────────────────────────────────────────────────────────

    async def chat(self, session_id: str, message: str, context: dict = None) -> dict:
        """Send a message in a copilot session and get an AI response.

        This method:
        1. Builds a system prompt with CortexDB context
        2. Calls llm_router.chat() to get a response
        3. Stores message and response in the session
        4. Extracts any suggestions from the response

        Args:
            session_id: The session to chat in.
            message: The user's message.
            context: Optional additional context dict to include.

        Returns:
            Dict with response text and extracted suggestions.
        """
        # Validate session
        session = self.get_session(session_id)
        if "error" in session:
            return session

        # Build system prompt with context
        system_prompt = self._build_system_context()
        if context:
            system_prompt += f"\n\n## Additional Context\n{json.dumps(context, indent=2, default=str)}"

        # Build message history
        messages = []
        for msg in session["messages"][-20:]:  # Last 20 messages for context window
            messages.append({"role": msg["role"], "content": msg["content"]})
        messages.append({"role": "user", "content": message})

        # Call LLM
        start = time.time()
        try:
            result = await self._router.chat(
                provider="claude",
                messages=messages,
                system=system_prompt,
                temperature=0.5,
                failover=True,
            )
        except Exception as e:
            logger.error("Copilot LLM call failed: %s", e)
            return {"error": f"LLM call failed: {e}", "session_id": session_id}

        elapsed_ms = round((time.time() - start) * 1000, 1)
        response_text = result.get("message", "") or result.get("error", "No response")
        success = result.get("success", False)

        if not success:
            logger.warning("Copilot chat failed for session %s: %s", session_id, result.get("error"))
            return {
                "response": response_text,
                "suggestions": [],
                "success": False,
                "session_id": session_id,
                "elapsed_ms": elapsed_ms,
            }

        # Update session messages
        now = datetime.now(timezone.utc).isoformat()
        all_messages = session["messages"]
        all_messages.append({"role": "user", "content": message, "timestamp": now})
        all_messages.append({"role": "assistant", "content": response_text, "timestamp": now})

        conn = self._get_connection()
        conn.execute(
            "UPDATE copilot_sessions SET messages = ?, updated_at = ? WHERE id = ?",
            (json.dumps(all_messages, default=str), now, session_id),
        )
        conn.commit()

        # Extract suggestions from response
        suggestions = self._extract_suggestions(session_id, response_text)

        logger.info(
            "Copilot chat in session %s: %d chars response, %d suggestions, %.0fms",
            session_id, len(response_text), len(suggestions), elapsed_ms,
        )

        return {
            "response": response_text,
            "suggestions": suggestions,
            "success": True,
            "session_id": session_id,
            "model": result.get("model", "unknown"),
            "elapsed_ms": elapsed_ms,
        }

    def _extract_suggestions(self, session_id: str, response_text: str) -> list:
        """Extract actionable suggestions from a copilot response.

        Looks for patterns like query suggestions, optimization tips,
        and action items in the response text.
        """
        suggestions = []
        now = datetime.now(timezone.utc).isoformat()
        conn = self._get_connection()

        # Detect CortexQL query suggestions
        if any(kw in response_text.upper() for kw in ["SELECT ", "INSERT ", "UPDATE ", "DELETE ", "SEARCH ", "STREAM "]):
            suggestion_id = str(uuid.uuid4())
            suggestion = {
                "id": suggestion_id,
                "type": "query",
                "content": "Response contains a CortexQL query that can be executed.",
            }
            suggestions.append(suggestion)
            conn.execute(
                """
                INSERT INTO copilot_suggestions (id, session_id, suggestion_type, content, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (suggestion_id, session_id, "query", json.dumps(suggestion, default=str), now),
            )

        # Detect optimization suggestions
        if any(kw in response_text.lower() for kw in ["recommend", "optimize", "improve", "suggest"]):
            suggestion_id = str(uuid.uuid4())
            suggestion = {
                "id": suggestion_id,
                "type": "optimization",
                "content": "Response contains optimization recommendations.",
            }
            suggestions.append(suggestion)
            conn.execute(
                """
                INSERT INTO copilot_suggestions (id, session_id, suggestion_type, content, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (suggestion_id, session_id, "optimization", json.dumps(suggestion, default=str), now),
            )

        if suggestions:
            conn.commit()

        return suggestions

    # ── Specialized queries ───────────────────────────────────────────

    async def generate_query(self, description: str) -> dict:
        """Generate a CortexQL query from a natural language description.

        Args:
            description: Natural language description of the desired query.

        Returns:
            Dict with generated query, explanation, and target engine.
        """
        messages = [
            {"role": "user", "content": f"Generate a CortexQL query for: {description}"},
        ]

        try:
            result = await self._router.chat(
                provider="claude",
                messages=messages,
                system=QUERY_GEN_PROMPT,
                temperature=0.3,
                failover=True,
            )
        except Exception as e:
            logger.error("Query generation failed: %s", e)
            return {"error": f"Query generation failed: {e}"}

        if not result.get("success"):
            return {"error": result.get("error", "LLM call failed")}

        response_text = result.get("message", "")

        # Try to parse JSON response
        try:
            # Look for JSON block in the response
            json_start = response_text.find("{")
            json_end = response_text.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                parsed = json.loads(response_text[json_start:json_end])
                return {
                    "query": parsed.get("query", ""),
                    "explanation": parsed.get("explanation", ""),
                    "engine": parsed.get("engine", "relational"),
                    "raw_response": response_text,
                }
        except json.JSONDecodeError:
            pass

        # Fallback: return raw response
        return {
            "query": response_text,
            "explanation": "Could not parse structured response",
            "engine": "relational",
            "raw_response": response_text,
        }

    async def explain_agent(self, agent_id: str) -> dict:
        """Explain what an agent does, its performance, and recent activity.

        Args:
            agent_id: The agent to explain.

        Returns:
            Dict with agent explanation, performance summary, and recent activity.
        """
        # Gather agent data
        agent = self._team.get_agent(agent_id) if hasattr(self._team, "get_agent") else None
        if agent is None:
            return {"error": f"Agent '{agent_id}' not found"}

        agent_data = agent if isinstance(agent, dict) else (
            agent.to_dict() if hasattr(agent, "to_dict") else vars(agent)
        )

        # Gather recent tasks
        recent_tasks = []
        try:
            tasks = self._store.load_tasks()
            for tid, tdata in tasks.items():
                if tdata.get("assigned_to") == agent_id:
                    recent_tasks.append({
                        "task_id": tid,
                        "status": tdata.get("status"),
                        "priority": tdata.get("priority"),
                    })
            recent_tasks = recent_tasks[:10]
        except Exception as e:
            logger.debug("Could not load tasks for agent explanation: %s", e)

        # Build prompt
        context = {
            "agent": agent_data,
            "recent_tasks": recent_tasks,
        }

        messages = [
            {
                "role": "user",
                "content": (
                    f"Explain this CortexDB agent in detail:\n"
                    f"```json\n{json.dumps(context, indent=2, default=str)}\n```\n\n"
                    f"Include: role summary, key responsibilities, performance indicators, "
                    f"and any observations about task patterns."
                ),
            }
        ]

        try:
            result = await self._router.chat(
                provider="claude",
                messages=messages,
                system=COPILOT_SYSTEM_PROMPT,
                temperature=0.4,
                failover=True,
            )
        except Exception as e:
            logger.error("Agent explanation failed: %s", e)
            return {"error": f"Agent explanation failed: {e}", "agent_id": agent_id}

        return {
            "agent_id": agent_id,
            "explanation": result.get("message", ""),
            "agent_data": agent_data,
            "recent_tasks": recent_tasks,
            "success": result.get("success", False),
        }

    async def suggest_optimizations(self) -> dict:
        """Analyze the system and suggest performance and cost optimizations.

        Returns:
            Dict with list of optimization suggestions categorized by impact.
        """
        # Gather system metrics
        metrics: Dict[str, Any] = {}

        try:
            agents = self._team.list_agents() if hasattr(self._team, "list_agents") else []
            agent_count = len(agents)
            dept_counts: Dict[str, int] = {}
            state_counts: Dict[str, int] = {}
            for a in agents:
                dept = a.get("department", "?") if isinstance(a, dict) else getattr(a, "department", "?")
                state = a.get("state", "?") if isinstance(a, dict) else getattr(a, "state", "?")
                dept_counts[str(dept)] = dept_counts.get(str(dept), 0) + 1
                state_counts[str(state)] = state_counts.get(str(state), 0) + 1
            metrics["agents"] = {
                "total": agent_count,
                "by_department": dept_counts,
                "by_state": state_counts,
            }
        except Exception as e:
            logger.debug("Could not load agent metrics: %s", e)

        try:
            tasks = self._store.load_tasks()
            task_statuses: Dict[str, int] = {}
            for t in tasks.values():
                status = t.get("status", "unknown")
                task_statuses[status] = task_statuses.get(status, 0) + 1
            metrics["tasks"] = {
                "total": len(tasks),
                "by_status": task_statuses,
            }
        except Exception as e:
            logger.debug("Could not load task metrics: %s", e)

        try:
            metrics["llm"] = self._router.get_request_stats()
        except Exception as e:
            logger.debug("Could not load LLM stats: %s", e)

        messages = [
            {
                "role": "user",
                "content": (
                    f"Analyze these CortexDB system metrics and suggest optimizations:\n"
                    f"```json\n{json.dumps(metrics, indent=2, default=str)}\n```\n\n"
                    f"Return suggestions as a JSON array."
                ),
            }
        ]

        try:
            result = await self._router.chat(
                provider="claude",
                messages=messages,
                system=OPTIMIZATION_PROMPT,
                temperature=0.4,
                failover=True,
            )
        except Exception as e:
            logger.error("Optimization analysis failed: %s", e)
            return {"error": f"Optimization analysis failed: {e}"}

        response_text = result.get("message", "")
        suggestions = []

        # Try to parse JSON array from response
        try:
            json_start = response_text.find("[")
            json_end = response_text.rfind("]") + 1
            if json_start >= 0 and json_end > json_start:
                suggestions = json.loads(response_text[json_start:json_end])
        except json.JSONDecodeError:
            pass

        return {
            "suggestions": suggestions,
            "metrics": metrics,
            "raw_response": response_text,
            "success": result.get("success", False),
        }

    # ── Stats ─────────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        """Get copilot usage statistics.

        Returns:
            Dict with session count, message count, and suggestion count.
        """
        conn = self._get_connection()

        session_row = conn.execute(
            "SELECT COUNT(*) AS cnt FROM copilot_sessions"
        ).fetchone()
        session_count = session_row["cnt"] if session_row else 0

        # Count total messages across all sessions
        message_count = 0
        try:
            rows = conn.execute("SELECT messages FROM copilot_sessions").fetchall()
            for row in rows:
                msgs = json.loads(row["messages"])
                message_count += len(msgs)
        except Exception:
            pass

        suggestion_row = conn.execute(
            "SELECT COUNT(*) AS cnt FROM copilot_suggestions"
        ).fetchone()
        suggestion_count = suggestion_row["cnt"] if suggestion_row else 0

        applied_row = conn.execute(
            "SELECT COUNT(*) AS cnt FROM copilot_suggestions WHERE applied = 1"
        ).fetchone()
        applied_count = applied_row["cnt"] if applied_row else 0

        return {
            "sessions": session_count,
            "messages": message_count,
            "suggestions": suggestion_count,
            "applied_suggestions": applied_count,
        }

    # ── Cleanup ───────────────────────────────────────────────────────

    def close(self) -> None:
        """Close the database connection."""
        if self.db is not None:
            try:
                self.db.close()
            except Exception:
                pass
            self.db = None
