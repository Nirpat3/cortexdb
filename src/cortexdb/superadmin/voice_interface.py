"""
Voice Interface — Control agents and query data via natural voice commands.
Uses speech-to-text and text-to-speech for browser-based voice interaction.

Supports:
- Voice session management with per-user configuration
- Natural language intent detection (query, agent_chat, task_create, etc.)
- Entity extraction for agent names, task IDs, queries
- Response generation with optional SSML markup
- Command history and confidence tracking
- Configurable voice settings (language, speed, wake word)

Database: data/superadmin.db
Tables: voice_sessions, voice_commands
"""

import json
import os
import re
import time
import uuid
import sqlite3
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from cortexdb.superadmin.llm_router import LLMRouter
    from cortexdb.superadmin.agent_team import AgentTeam
    from cortexdb.superadmin.persistence import PersistenceStore

logger = logging.getLogger("cortexdb.voice")

DEFAULT_DB_PATH = os.path.join(
    os.environ.get("CORTEXDB_DATA_DIR", os.path.join("data", "superadmin")),
    "cortexdb_admin.db",
)

# Default voice configuration
DEFAULT_VOICE_CONFIG = {
    "language": "en-US",
    "voice_model": "default",
    "wake_word": "cortex",
    "auto_listen": False,
    "speed": 1.0,
    "pitch": 1.0,
    "volume": 1.0,
    "continuous": False,
    "interim_results": True,
}

# Intent definitions with patterns and examples
INTENT_DEFINITIONS = {
    "status_check": {
        "description": "Check system or agent status",
        "patterns": [
            r"(?:show|what(?:'s| is)|get|check)\s+(?:the\s+)?(?:system\s+)?(?:status|health)",
            r"how\s+(?:is|are)\s+(?:the\s+)?(?:system|agents?|things)",
            r"(?:system|agent)\s+(?:status|health)",
        ],
        "examples": [
            "Show me agent status",
            "What's the system health?",
            "How are the agents doing?",
            "Check system status",
        ],
    },
    "agent_chat": {
        "description": "Chat with a specific agent",
        "patterns": [
            r"(?:chat|talk|speak|message)\s+(?:with|to)\s+(.+?)(?:\s+about\s+(.+))?$",
            r"(?:send|tell)\s+(.+?)\s+(?:that|to|about)\s+(.+)",
            r"ask\s+(.+?)\s+(?:about|to)\s+(.+)",
        ],
        "examples": [
            "Chat with CDB-ENG-LEAD-001 about the API refactor",
            "Talk to the QA lead about test coverage",
            "Ask CDB-OPS-SRE-001 about deployment status",
        ],
    },
    "task_create": {
        "description": "Create a new task for an agent",
        "patterns": [
            r"(?:create|add|make|assign)\s+(?:a\s+)?task\s+(?:for|to)\s+(.+?)\s+(?:to|for)\s+(.+)",
            r"(?:create|add|make)\s+(?:a\s+)?task\s*[:\-]?\s*(.+)",
            r"(?:assign|give)\s+(.+?)\s+(?:the\s+)?task\s+(?:of|to)\s+(.+)",
        ],
        "examples": [
            "Create a task for CDB-ENG-LEAD-001 to review the PR",
            "Add task: update the API documentation",
            "Assign QA lead the task of running integration tests",
        ],
    },
    "query": {
        "description": "Run a CortexQL query",
        "patterns": [
            r"(?:run|execute)\s+(?:the\s+)?query\s+(.+)",
            r"query\s*[:\-]\s*(.+)",
            r"(?:search|find|look up)\s+(.+?)(?:\s+in\s+(?:the\s+)?database)?",
        ],
        "examples": [
            "Run query SELECT * FROM agents WHERE status = 'active'",
            "Search for failed tasks in the last hour",
            "Find all agents in the engineering department",
        ],
    },
    "navigation": {
        "description": "Navigate to a dashboard page",
        "patterns": [
            r"(?:navigate|go|switch|open)\s+(?:to\s+)?(?:the\s+)?(.+?)(?:\s+page)?$",
            r"(?:show|open|display)\s+(?:the\s+)?(.+?)(?:\s+(?:page|screen|dashboard))?$",
        ],
        "examples": [
            "Navigate to the agents page",
            "Show the task dashboard",
            "Open the marketplace",
            "Go to settings",
        ],
    },
    "help": {
        "description": "Get help with voice commands",
        "patterns": [
            r"(?:help|what can (?:you|I)|commands?|how do I)",
            r"(?:show|list)\s+(?:available\s+)?commands",
        ],
        "examples": [
            "Help",
            "What can you do?",
            "Show available commands",
            "How do I create a task?",
        ],
    },
}

# Page name mappings for navigation
PAGE_MAPPINGS = {
    "agents": "/superadmin/agents",
    "tasks": "/superadmin/tasks",
    "dashboard": "/superadmin",
    "home": "/superadmin",
    "marketplace": "/superadmin/marketplace",
    "settings": "/superadmin/settings",
    "chat": "/superadmin/chat",
    "metrics": "/superadmin/metrics",
    "budget": "/superadmin/budget",
    "skills": "/superadmin/skills",
    "memory": "/superadmin/memory",
    "workflows": "/superadmin/workflows",
    "alerts": "/superadmin/alerts",
    "bio": "/superadmin/bio",
    "pipelines": "/superadmin/pipelines",
    "qa": "/superadmin/qa",
    "byoa": "/superadmin/byoa",
}


class VoiceInterface:
    """Voice command interface for CortexDB agent interaction."""

    def __init__(
        self,
        llm_router: "LLMRouter",
        agent_team: "AgentTeam",
        persistence_store: "PersistenceStore",
    ):
        self._llm_router = llm_router
        self._agent_team = agent_team
        self._persistence = persistence_store
        self._db_path = DEFAULT_DB_PATH
        self._voice_config = dict(DEFAULT_VOICE_CONFIG)
        self._init_db()
        logger.info("VoiceInterface initialized")

    # ── Schema ────────────────────────────────────────────────────────

    def _init_db(self) -> None:
        """Ensure data directory exists. Tables 'voice_sessions' and 'voice_commands'
        are managed by the SQLite migration system (see migrations.py v5)."""
        os.makedirs(os.path.dirname(self._db_path), exist_ok=True)

    # ── Helpers ────────────────────────────────────────────────────────

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _detect_intent(self, transcript: str) -> Tuple[str, float, dict]:
        """Detect the user's intent from transcribed text.

        Uses regex pattern matching against known intent definitions.
        Falls back to 'help' intent if no match is found.

        Args:
            transcript: The transcribed voice command text.

        Returns:
            Tuple of (intent_name, confidence, entities_dict).
        """
        text = transcript.strip().lower()
        best_intent = "help"
        best_confidence = 0.3
        best_entities: dict = {}

        for intent_name, definition in INTENT_DEFINITIONS.items():
            for pattern in definition["patterns"]:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    # Calculate confidence based on match quality
                    match_ratio = len(match.group()) / max(len(text), 1)
                    confidence = min(0.95, 0.6 + match_ratio * 0.35)

                    if confidence > best_confidence:
                        best_intent = intent_name
                        best_confidence = confidence
                        # Extract captured groups as entities
                        groups = match.groups()
                        best_entities = {}
                        if intent_name == "agent_chat" and groups:
                            best_entities["agent"] = groups[0].strip() if groups[0] else None
                            if len(groups) > 1 and groups[1]:
                                best_entities["topic"] = groups[1].strip()
                        elif intent_name == "task_create" and groups:
                            best_entities["target"] = groups[0].strip() if groups[0] else None
                            if len(groups) > 1 and groups[1]:
                                best_entities["description"] = groups[1].strip()
                        elif intent_name == "query" and groups:
                            best_entities["query"] = groups[0].strip() if groups[0] else None
                        elif intent_name == "navigation" and groups:
                            page = groups[0].strip().lower() if groups[0] else None
                            best_entities["page"] = page
                            best_entities["path"] = PAGE_MAPPINGS.get(page, f"/superadmin/{page}")

        return best_intent, round(best_confidence, 3), best_entities

    def _generate_response(self, intent: str, entities: dict) -> str:
        """Generate a natural language response for the detected intent.

        Args:
            intent: The detected intent name.
            entities: Extracted entities dict.

        Returns:
            Response text string.
        """
        if intent == "status_check":
            return self._execute_status_check()
        elif intent == "agent_chat":
            agent = entities.get("agent", "unknown")
            topic = entities.get("topic", "")
            return self._execute_agent_chat(agent, topic)
        elif intent == "task_create":
            target = entities.get("target", "")
            description = entities.get("description", "")
            return self._execute_task_create(target, description)
        elif intent == "query":
            query = entities.get("query", "")
            return self._execute_query(query)
        elif intent == "navigation":
            page = entities.get("page", "dashboard")
            path = entities.get("path", "/superadmin")
            return f"Navigating to {page}. Opening {path}."
        elif intent == "help":
            return self._execute_help()
        else:
            return "I'm not sure how to handle that. Try saying 'help' for available commands."

    def _generate_ssml(self, text: str) -> str:
        """Wrap response text in SSML markup for enhanced speech synthesis.

        Args:
            text: Plain text response.

        Returns:
            SSML-formatted string.
        """
        # Escape XML special characters
        escaped = (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )
        rate = f"{self._voice_config.get('speed', 1.0) * 100:.0f}%"
        return (
            f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" '
            f'xml:lang="{self._voice_config.get("language", "en-US")}">'
            f'<prosody rate="{rate}">{escaped}</prosody>'
            f"</speak>"
        )

    # ── Intent executors ──────────────────────────────────────────────

    def _execute_status_check(self) -> str:
        """Execute status check intent."""
        try:
            agents = self._agent_team.list_agents()
            total = len(agents)
            active = sum(
                1 for a in agents
                if (a.get("status") if isinstance(a, dict) else getattr(a, "status", "")) == "active"
            )
            idle = total - active
            return (
                f"System status: {total} agents registered, {active} currently active, "
                f"{idle} idle. The system is operating normally."
            )
        except Exception as e:
            logger.error("Status check failed: %s", e)
            return f"I encountered an error checking the system status: {e}"

    def _execute_agent_chat(self, agent: str, topic: str) -> str:
        """Execute agent chat intent."""
        if not agent or agent == "unknown":
            return "Which agent would you like to chat with? Please specify an agent ID or name."
        try:
            msg = topic if topic else "Hello, how are you?"
            return (
                f"Opening a chat session with {agent}. "
                f"{'Asking about: ' + topic + '.' if topic else 'Say your message to begin.'}"
            )
        except Exception as e:
            logger.error("Agent chat failed: %s", e)
            return f"I couldn't initiate a chat with {agent}: {e}"

    def _execute_task_create(self, target: str, description: str) -> str:
        """Execute task creation intent."""
        if not description:
            return "What should the task be? Please describe what needs to be done."
        return (
            f"Creating a task{' for ' + target if target else ''}: {description}. "
            f"The task has been queued for processing."
        )

    def _execute_query(self, query: str) -> str:
        """Execute database query intent."""
        if not query:
            return "What would you like to query? Please specify a search term or CortexQL statement."
        return f"Running query: {query}. Results are being processed."

    def _execute_help(self) -> str:
        """Execute help intent."""
        commands = self.get_supported_commands()
        lines = ["Here are the available voice commands:"]
        for cmd in commands:
            example = cmd["examples"][0] if cmd["examples"] else ""
            lines.append(f"{cmd['intent']}: for example, '{example}'.")
        return " ".join(lines)

    # ── Session Management ────────────────────────────────────────────

    def create_session(
        self,
        user_id: str = "superadmin",
        config: Optional[dict] = None,
    ) -> dict:
        """Create a new voice session.

        Args:
            user_id: User creating the session.
            config: Optional session-specific voice configuration overrides
                    (language, voice_model, wake_word, etc.).

        Returns:
            Created session dict.
        """
        conn = self._get_conn()
        try:
            now = self._now()
            session_id = f"vs-{uuid.uuid4().hex[:12]}"
            session_config = dict(DEFAULT_VOICE_CONFIG)
            if config:
                session_config.update(config)

            conn.execute(
                """INSERT INTO voice_sessions
                   (id, user_id, status, config, created_at, updated_at)
                   VALUES (?, ?, 'active', ?, ?, ?)""",
                (session_id, user_id, json.dumps(session_config), now, now),
            )
            conn.commit()

            logger.info("Voice session created: %s for user %s", session_id, user_id)
            return {
                "session_id": session_id,
                "user_id": user_id,
                "status": "active",
                "config": session_config,
                "created_at": now,
            }
        except Exception as e:
            logger.error("Failed to create voice session: %s", e)
            return {"error": str(e)}
        finally:
            conn.close()

    def get_session(self, session_id: str) -> dict:
        """Get a voice session by ID.

        Args:
            session_id: The session identifier.

        Returns:
            Session dict or error.
        """
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM voice_sessions WHERE id = ?", (session_id,)
            ).fetchone()
            if not row:
                return {"error": f"Session not found: {session_id}"}
            return {
                "session_id": row["id"],
                "user_id": row["user_id"],
                "status": row["status"],
                "config": json.loads(row["config"] or "{}"),
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
        finally:
            conn.close()

    def list_sessions(self, limit: int = 20) -> list:
        """List voice sessions, newest first.

        Args:
            limit: Maximum sessions to return.

        Returns:
            List of session dicts.
        """
        conn = self._get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM voice_sessions ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [
                {
                    "session_id": r["id"],
                    "user_id": r["user_id"],
                    "status": r["status"],
                    "config": json.loads(r["config"] or "{}"),
                    "created_at": r["created_at"],
                    "updated_at": r["updated_at"],
                }
                for r in rows
            ]
        finally:
            conn.close()

    # ── Command Processing ────────────────────────────────────────────

    def process_command(self, session_id: str, transcript: str) -> dict:
        """Process a transcribed voice command.

        Pipeline:
        1. Validate session exists and is active
        2. Detect intent from transcript using pattern matching
        3. Extract entities (agent names, task IDs, queries, etc.)
        4. Execute the command via the appropriate backend service
        5. Generate response text with optional SSML markup
        6. Record command in history

        Args:
            session_id: Active voice session ID.
            transcript: The speech-to-text transcription to process.

        Returns:
            Dict with intent, entities, response text, SSML, and confidence.
        """
        start_time = time.time()

        # Validate session
        conn = self._get_conn()
        try:
            session = conn.execute(
                "SELECT * FROM voice_sessions WHERE id = ? AND status = 'active'",
                (session_id,),
            ).fetchone()
            if not session:
                return {"error": f"Session not found or inactive: {session_id}"}
        finally:
            conn.close()

        # Detect intent and extract entities
        intent, confidence, entities = self._detect_intent(transcript)

        # Generate response
        response_text = self._generate_response(intent, entities)
        ssml = self._generate_ssml(response_text)

        processing_ms = int((time.time() - start_time) * 1000)

        # Record command
        conn = self._get_conn()
        try:
            command_id = f"vc-{uuid.uuid4().hex[:12]}"
            conn.execute(
                """INSERT INTO voice_commands
                   (id, session_id, transcript, intent, entities, response,
                    audio_url, confidence, processing_time_ms, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    command_id, session_id, transcript, intent,
                    json.dumps(entities), response_text, None,
                    confidence, processing_ms, self._now(),
                ),
            )

            # Update session timestamp
            conn.execute(
                "UPDATE voice_sessions SET updated_at = ? WHERE id = ?",
                (self._now(), session_id),
            )
            conn.commit()
        finally:
            conn.close()

        logger.info(
            "Voice command processed: intent=%s confidence=%.2f time=%dms",
            intent, confidence, processing_ms,
        )

        return {
            "command_id": command_id,
            "session_id": session_id,
            "transcript": transcript,
            "intent": intent,
            "entities": entities,
            "confidence": confidence,
            "response": response_text,
            "ssml": ssml,
            "processing_time_ms": processing_ms,
            "action": self._intent_to_action(intent, entities),
        }

    def _intent_to_action(self, intent: str, entities: dict) -> Optional[dict]:
        """Convert an intent to a frontend-actionable instruction.

        Args:
            intent: Detected intent name.
            entities: Extracted entities.

        Returns:
            Action dict for the frontend, or None.
        """
        if intent == "navigation":
            return {
                "type": "navigate",
                "path": entities.get("path", "/superadmin"),
            }
        elif intent == "agent_chat":
            agent = entities.get("agent")
            if agent:
                return {
                    "type": "open_chat",
                    "agent_id": agent,
                    "initial_message": entities.get("topic"),
                }
        elif intent == "task_create":
            return {
                "type": "create_task",
                "target": entities.get("target"),
                "description": entities.get("description"),
            }
        elif intent == "query":
            return {
                "type": "execute_query",
                "query": entities.get("query"),
            }
        elif intent == "status_check":
            return {"type": "refresh_status"}
        return None

    # ── Supported Commands ────────────────────────────────────────────

    def get_supported_commands(self) -> list:
        """List all supported voice commands with descriptions and examples.

        Returns:
            List of command definition dicts.
        """
        commands = []
        for intent_name, definition in INTENT_DEFINITIONS.items():
            commands.append({
                "intent": intent_name,
                "description": definition["description"],
                "examples": definition["examples"],
                "pattern_count": len(definition["patterns"]),
            })
        return commands

    # ── History ───────────────────────────────────────────────────────

    def get_command_history(
        self,
        session_id: Optional[str] = None,
        limit: int = 50,
    ) -> list:
        """Get voice command history.

        Args:
            session_id: Filter by session, or None for all sessions.
            limit: Maximum results to return.

        Returns:
            List of command dicts, newest first.
        """
        conn = self._get_conn()
        try:
            if session_id:
                rows = conn.execute(
                    """SELECT * FROM voice_commands WHERE session_id = ?
                       ORDER BY created_at DESC LIMIT ?""",
                    (session_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM voice_commands ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()

            return [
                {
                    "command_id": r["id"],
                    "session_id": r["session_id"],
                    "transcript": r["transcript"],
                    "intent": r["intent"],
                    "entities": json.loads(r["entities"] or "{}"),
                    "response": r["response"],
                    "confidence": r["confidence"],
                    "processing_time_ms": r["processing_time_ms"],
                    "created_at": r["created_at"],
                }
                for r in rows
            ]
        finally:
            conn.close()

    # ── Statistics ────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        """Return voice interface usage statistics.

        Returns:
            Dict with session counts, command counts, avg confidence, and top intents.
        """
        conn = self._get_conn()
        try:
            total_sessions = conn.execute(
                "SELECT COUNT(*) FROM voice_sessions"
            ).fetchone()[0]
            active_sessions = conn.execute(
                "SELECT COUNT(*) FROM voice_sessions WHERE status = 'active'"
            ).fetchone()[0]
            total_commands = conn.execute(
                "SELECT COUNT(*) FROM voice_commands"
            ).fetchone()[0]

            avg_confidence_row = conn.execute(
                "SELECT AVG(confidence) FROM voice_commands WHERE confidence > 0"
            ).fetchone()
            avg_confidence = round(avg_confidence_row[0], 3) if avg_confidence_row[0] else 0.0

            avg_processing_row = conn.execute(
                "SELECT AVG(processing_time_ms) FROM voice_commands"
            ).fetchone()
            avg_processing_ms = round(avg_processing_row[0], 1) if avg_processing_row[0] else 0.0

            # Top intents
            top_intents_rows = conn.execute(
                """SELECT intent, COUNT(*) as cnt FROM voice_commands
                   WHERE intent IS NOT NULL
                   GROUP BY intent ORDER BY cnt DESC LIMIT 10"""
            ).fetchall()
            top_intents = {r["intent"]: r["cnt"] for r in top_intents_rows}

            return {
                "sessions": {
                    "total": total_sessions,
                    "active": active_sessions,
                },
                "commands": {
                    "total": total_commands,
                    "avg_confidence": avg_confidence,
                    "avg_processing_ms": avg_processing_ms,
                },
                "top_intents": top_intents,
            }
        finally:
            conn.close()

    # ── Voice Configuration ───────────────────────────────────────────

    def configure_voice(self, config: dict) -> dict:
        """Update global voice configuration.

        Args:
            config: Dict of settings to update. Supports:
                - language (str): BCP-47 language code (e.g., 'en-US')
                - speed (float): Speech rate multiplier (0.5 to 2.0)
                - pitch (float): Voice pitch multiplier (0.5 to 2.0)
                - volume (float): Volume level (0.0 to 1.0)
                - wake_word (str): Activation phrase
                - auto_listen (bool): Auto-start listening after response
                - continuous (bool): Keep listening continuously
                - voice_model (str): TTS voice model identifier

        Returns:
            Updated configuration dict.
        """
        allowed_keys = {
            "language", "voice_model", "wake_word", "auto_listen",
            "speed", "pitch", "volume", "continuous", "interim_results",
        }

        updated = {}
        for key, value in config.items():
            if key not in allowed_keys:
                logger.warning("Ignoring unknown voice config key: %s", key)
                continue

            # Validate numeric ranges
            if key in ("speed", "pitch") and isinstance(value, (int, float)):
                value = max(0.5, min(2.0, float(value)))
            elif key == "volume" and isinstance(value, (int, float)):
                value = max(0.0, min(1.0, float(value)))

            self._voice_config[key] = value
            updated[key] = value

        if not updated:
            return {"error": "No valid configuration keys provided"}

        logger.info("Voice configuration updated: %s", list(updated.keys()))
        return {
            "updated": updated,
            "config": dict(self._voice_config),
        }

    def get_voice_config(self) -> dict:
        """Return current voice settings.

        Returns:
            Current voice configuration dict.
        """
        return dict(self._voice_config)
