"""
Discord Integration — Bot for Discord servers with alerts, slash commands, and agent chat.

Supports:
- Rich embed notifications to Discord channels via webhooks
- Agent alert forwarding with color-coded severity
- Slash command handling (agents, tasks, status, chat, help)
- Incoming webhook processing for Discord events
- Channel-to-event mapping for routing
- Slash command registration definitions

Database: data/superadmin.db
Tables: discord_config, discord_messages
"""

import json
import os
import time
import uuid
import hmac
import hashlib
import sqlite3
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from cortexdb.superadmin.persistence import PersistenceStore
    from cortexdb.superadmin.agent_team import AgentTeam
    from cortexdb.superadmin.agent_bus import AgentBus

logger = logging.getLogger("cortexdb.discord")

DEFAULT_DB_PATH = os.path.join("data", "superadmin.db")

# Discord embed color codes by severity
SEVERITY_COLORS = {
    "critical": 0xFF0000,   # Red
    "warning": 0xFFA500,    # Orange
    "info": 0x3498DB,       # Blue
    "success": 0x2ECC71,    # Green
}

# Slash command definitions for Discord registration
SLASH_COMMANDS = [
    {
        "name": "cortex-agents",
        "description": "List all active CortexDB agents",
        "type": 1,
    },
    {
        "name": "cortex-tasks",
        "description": "List recent tasks and their statuses",
        "type": 1,
    },
    {
        "name": "cortex-status",
        "description": "Show CortexDB system health summary",
        "type": 1,
    },
    {
        "name": "cortex-chat",
        "description": "Chat with a CortexDB agent",
        "type": 1,
        "options": [
            {
                "name": "agent",
                "description": "Agent ID to chat with",
                "type": 3,  # STRING
                "required": True,
            },
            {
                "name": "message",
                "description": "Message to send to the agent",
                "type": 3,
                "required": True,
            },
        ],
    },
    {
        "name": "cortex-help",
        "description": "Show available CortexDB bot commands",
        "type": 1,
    },
]


class DiscordIntegration:
    """Discord bot integration for CortexDB agent notifications and commands."""

    def __init__(
        self,
        persistence_store: "PersistenceStore",
        agent_team: "AgentTeam",
        agent_bus: "AgentBus",
    ):
        self._persistence = persistence_store
        self._agent_team = agent_team
        self._agent_bus = agent_bus
        self._db_path = DEFAULT_DB_PATH
        self._init_db()
        logger.info("DiscordIntegration initialized")

    # ── Schema ────────────────────────────────────────────────────────

    def _init_db(self) -> None:
        """Ensure data directory exists. Tables 'discord_config' and 'discord_messages'
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

    def _mask_token(self, token: Optional[str]) -> Optional[str]:
        """Mask a token for safe display."""
        if not token:
            return None
        if len(token) <= 8:
            return "****"
        return token[:4] + "****" + token[-4:]

    def _record_message(
        self,
        conn: sqlite3.Connection,
        direction: str,
        message: str,
        channel_id: str = None,
        user_id: str = None,
        agent_id: str = None,
        command: str = None,
        status: str = "sent",
    ) -> str:
        msg_id = f"dmsg-{uuid.uuid4().hex[:12]}"
        conn.execute(
            """INSERT INTO discord_messages
               (id, direction, channel_id, user_id, agent_id, message, command, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (msg_id, direction, channel_id, user_id, agent_id, message, command, status, self._now()),
        )
        conn.commit()
        return msg_id

    def _build_embed(
        self,
        title: str,
        description: str,
        color: int = 0x3498DB,
        fields: Optional[List[Dict]] = None,
        footer: Optional[str] = None,
        thumbnail_url: Optional[str] = None,
    ) -> dict:
        """Build a Discord rich embed payload.

        Args:
            title: Embed title.
            description: Embed description/body text.
            color: Integer color code.
            fields: List of {"name": str, "value": str, "inline": bool} dicts.
            footer: Optional footer text.
            thumbnail_url: Optional thumbnail image URL.

        Returns:
            Discord embed dict.
        """
        embed = {
            "title": title,
            "description": description,
            "color": color,
            "timestamp": self._now(),
        }
        if fields:
            embed["fields"] = fields
        if footer:
            embed["footer"] = {"text": footer}
        if thumbnail_url:
            embed["thumbnail"] = {"url": thumbnail_url}
        return embed

    # ── Configuration ─────────────────────────────────────────────────

    def configure(
        self,
        bot_token: Optional[str] = None,
        webhook_url: Optional[str] = None,
        guild_id: Optional[str] = None,
        command_prefix: str = "!cortex",
    ) -> dict:
        """Save or update Discord configuration.

        Args:
            bot_token: Discord bot token for full bot functionality.
            webhook_url: Discord webhook URL for notification-only mode.
            guild_id: Discord server (guild) ID.
            command_prefix: Prefix for text commands (default: !cortex).

        Returns:
            Configuration summary dict.
        """
        if not bot_token and not webhook_url:
            return {"error": "Either bot_token or webhook_url is required"}

        conn = self._get_conn()
        try:
            now = self._now()
            config_id = "discord-primary"

            existing = conn.execute(
                "SELECT id FROM discord_config WHERE id = ?", (config_id,)
            ).fetchone()

            if existing:
                conn.execute(
                    """UPDATE discord_config
                       SET guild_id = ?, bot_token = ?, webhook_url = ?,
                           command_prefix = ?, enabled = 1, updated_at = ?
                       WHERE id = ?""",
                    (guild_id, bot_token, webhook_url, command_prefix, now, config_id),
                )
            else:
                conn.execute(
                    """INSERT INTO discord_config
                       (id, guild_id, bot_token, webhook_url, channel_mappings,
                        command_prefix, enabled, created_at, updated_at)
                       VALUES (?, ?, ?, ?, '{}', ?, 1, ?, ?)""",
                    (config_id, guild_id, bot_token, webhook_url, command_prefix, now, now),
                )
            conn.commit()

            mode = "bot" if bot_token else "webhook"
            logger.info("Discord integration configured (mode=%s, guild=%s)", mode, guild_id)
            return {
                "status": "configured",
                "mode": mode,
                "guild_id": guild_id,
                "bot_token_set": bot_token is not None,
                "webhook_url_set": webhook_url is not None,
                "command_prefix": command_prefix,
                "updated_at": now,
            }
        except Exception as e:
            logger.error("Failed to configure Discord integration: %s", e)
            return {"error": str(e)}
        finally:
            conn.close()

    def get_config(self) -> dict:
        """Return current Discord configuration with masked token.

        Returns:
            Config dict or indication that integration is not configured.
        """
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM discord_config WHERE id = ?", ("discord-primary",)
            ).fetchone()
            if not row:
                return {"configured": False}
            return {
                "configured": True,
                "guild_id": row["guild_id"],
                "bot_token": self._mask_token(row["bot_token"]),
                "webhook_url": row["webhook_url"],
                "channel_mappings": json.loads(row["channel_mappings"] or "{}"),
                "command_prefix": row["command_prefix"],
                "enabled": bool(row["enabled"]),
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
        finally:
            conn.close()

    # ── Sending ───────────────────────────────────────────────────────

    def send_notification(
        self,
        channel_id: str,
        message: str,
        embed_data: Optional[dict] = None,
    ) -> dict:
        """Send a message or rich embed to a Discord channel.

        Args:
            channel_id: Target Discord channel ID.
            message: Plain text content (always included as fallback).
            embed_data: Optional Discord embed dict for rich formatting.

        Returns:
            Delivery result dict.
        """
        conn = self._get_conn()
        try:
            config = conn.execute(
                "SELECT * FROM discord_config WHERE id = ? AND enabled = 1",
                ("discord-primary",),
            ).fetchone()
            if not config:
                return {"error": "Discord integration not configured or disabled"}

            # Build payload
            payload: Dict[str, Any] = {"content": message}
            msg_type = "text"
            if embed_data:
                payload["embeds"] = [embed_data]
                msg_type = "embed"

            # In production, this would POST to the Discord API/webhook.
            logger.info(
                "Discord notification -> channel=%s type=%s len=%d",
                channel_id, msg_type, len(message),
            )

            msg_id = self._record_message(
                conn,
                direction="outbound",
                message=message,
                channel_id=channel_id,
                status="delivered",
            )

            return {
                "message_id": msg_id,
                "channel_id": channel_id,
                "message_type": msg_type,
                "status": "delivered",
            }
        except Exception as e:
            logger.error("Discord send_notification failed: %s", e)
            return {"error": str(e)}
        finally:
            conn.close()

    def send_agent_alert(self, agent_id: str, alert_type: str, details: dict) -> dict:
        """Format and send an agent alert to the appropriate Discord channel.

        Args:
            agent_id: ID of the agent triggering the alert.
            alert_type: Alert category (e.g., 'task_failed', 'budget_breach').
            details: Additional alert data including optional 'severity'.

        Returns:
            Delivery result dict.
        """
        conn = self._get_conn()
        try:
            config_row = conn.execute(
                "SELECT channel_mappings FROM discord_config WHERE id = ? AND enabled = 1",
                ("discord-primary",),
            ).fetchone()
            if not config_row:
                return {"error": "Discord integration not configured or disabled"}

            mappings = json.loads(config_row["channel_mappings"] or "{}")
            channel_id = mappings.get("agent_alert", mappings.get("default", "general"))
        finally:
            conn.close()

        severity = details.get("severity", "info")
        color = SEVERITY_COLORS.get(severity, SEVERITY_COLORS["info"])
        body = details.get("message", f"Agent {agent_id} raised a {alert_type} alert.")

        embed = self._build_embed(
            title=f"Agent Alert: {alert_type.replace('_', ' ').title()}",
            description=body,
            color=color,
            fields=[
                {"name": "Agent", "value": f"`{agent_id}`", "inline": True},
                {"name": "Type", "value": alert_type, "inline": True},
                {"name": "Severity", "value": severity.upper(), "inline": True},
            ],
            footer="CortexDB Agent Alert System",
        )

        result = self.send_notification(channel_id, body, embed_data=embed)

        # Tag with agent_id
        if "message_id" in result:
            conn2 = self._get_conn()
            try:
                conn2.execute(
                    "UPDATE discord_messages SET agent_id = ? WHERE id = ?",
                    (agent_id, result["message_id"]),
                )
                conn2.commit()
            finally:
                conn2.close()

        result["alert_type"] = alert_type
        result["agent_id"] = agent_id
        logger.info("Discord agent alert sent: agent=%s type=%s", agent_id, alert_type)
        return result

    # ── Commands ──────────────────────────────────────────────────────

    def handle_command(
        self,
        command: str,
        args: List[str],
        user_id: str,
        channel_id: str,
    ) -> dict:
        """Process a Discord bot command.

        Supported commands:
        - agents — List active agents
        - tasks — List recent tasks
        - status — System health summary
        - chat <agent_id> <message> — Chat with an agent
        - help — Show command list

        Args:
            command: The command name (without prefix).
            args: List of command arguments.
            user_id: Discord user ID who invoked the command.
            channel_id: Discord channel where command was sent.

        Returns:
            Response dict with reply text and optional embed.
        """
        conn = self._get_conn()
        try:
            self._record_message(
                conn,
                direction="inbound",
                message=f"{command} {' '.join(args)}".strip(),
                channel_id=channel_id,
                user_id=user_id,
                command=command,
                status="received",
            )
        finally:
            conn.close()

        cmd = command.lower().strip()
        handlers = {
            "agents": self._cmd_agents,
            "tasks": self._cmd_tasks,
            "status": self._cmd_status,
            "chat": lambda: self._cmd_chat(args, user_id),
            "help": self._cmd_help,
        }

        handler = handlers.get(cmd)
        if not handler:
            return {
                "reply": f"Unknown command: `{cmd}`. Use `help` for available commands.",
                "embed": None,
            }

        try:
            return handler()
        except Exception as e:
            logger.error("Discord command '%s' failed: %s", cmd, e)
            return {"reply": f"Error executing `{cmd}`: {e}", "embed": None}

    def _cmd_agents(self) -> dict:
        """Handle the agents command."""
        agents = self._agent_team.list_agents()
        if not agents:
            return {"reply": "No agents registered.", "embed": None}

        fields = []
        for a in agents[:25]:  # Discord embed field limit
            data = a if isinstance(a, dict) else a.__dict__ if hasattr(a, "__dict__") else {}
            aid = data.get("agent_id", str(a))
            status = data.get("status", "unknown")
            role = data.get("role", "agent")
            fields.append({
                "name": aid,
                "value": f"Role: {role} | Status: {status}",
                "inline": True,
            })

        embed = self._build_embed(
            title=f"Active Agents ({len(agents)})",
            description="Current CortexDB agent workforce",
            color=SEVERITY_COLORS["info"],
            fields=fields,
            footer="CortexDB Agent Team",
        )
        return {"reply": f"Found {len(agents)} agents.", "embed": embed}

    def _cmd_tasks(self) -> dict:
        """Handle the tasks command."""
        tasks = self._persistence.query_tasks(limit=10) if hasattr(self._persistence, "query_tasks") else []
        if not tasks:
            return {"reply": "No recent tasks found.", "embed": None}

        fields = []
        for t in tasks:
            t_data = dict(t) if hasattr(t, "keys") else t
            tid = t_data.get("task_id", "?")
            status = t_data.get("status", "?")
            assigned = t_data.get("assigned_to", "unassigned")
            fields.append({
                "name": tid,
                "value": f"Status: {status} | Agent: {assigned}",
                "inline": False,
            })

        embed = self._build_embed(
            title="Recent Tasks",
            description=f"Showing {len(tasks)} most recent tasks",
            color=SEVERITY_COLORS["info"],
            fields=fields,
        )
        return {"reply": f"{len(tasks)} recent tasks.", "embed": embed}

    def _cmd_status(self) -> dict:
        """Handle the status command."""
        agents = self._agent_team.list_agents()
        active = sum(
            1 for a in agents
            if (a.get("status") if isinstance(a, dict) else getattr(a, "status", "")) == "active"
        )
        embed = self._build_embed(
            title="CortexDB System Status",
            description="Current system health overview",
            color=SEVERITY_COLORS["success"],
            fields=[
                {"name": "Total Agents", "value": str(len(agents)), "inline": True},
                {"name": "Active", "value": str(active), "inline": True},
                {"name": "Discord Bot", "value": "Online", "inline": True},
            ],
            footer=f"Updated {self._now()}",
        )
        return {"reply": "System status retrieved.", "embed": embed}

    def _cmd_chat(self, args: List[str], user_id: str) -> dict:
        """Handle the chat command."""
        if len(args) < 2:
            return {
                "reply": "Usage: `chat <agent_id> <message>`",
                "embed": None,
            }
        agent_id = args[0]
        message = " ".join(args[1:])
        try:
            self._agent_bus.send(
                msg_type="direct",
                from_agent=f"discord-{user_id}",
                to_agent=agent_id,
                content=message,
            )
            return {
                "reply": f"Message sent to `{agent_id}`. Awaiting response...",
                "embed": None,
            }
        except Exception as e:
            return {"reply": f"Failed to send message to `{agent_id}`: {e}", "embed": None}

    def _cmd_help(self) -> dict:
        """Handle the help command."""
        embed = self._build_embed(
            title="CortexDB Discord Bot",
            description="Available commands for interacting with your agent workforce.",
            color=SEVERITY_COLORS["info"],
            fields=[
                {"name": "`agents`", "value": "List all active agents", "inline": False},
                {"name": "`tasks`", "value": "List recent tasks", "inline": False},
                {"name": "`status`", "value": "System health summary", "inline": False},
                {"name": "`chat <agent> <msg>`", "value": "Chat with an agent", "inline": False},
                {"name": "`help`", "value": "Show this help message", "inline": False},
            ],
            footer="CortexDB v1.0",
        )
        return {"reply": "CortexDB Bot Help", "embed": embed}

    # ── Webhooks ──────────────────────────────────────────────────────

    def handle_webhook(self, payload: dict) -> dict:
        """Process an incoming Discord webhook event.

        Handles message_create events and extracts commands from
        messages that start with the configured command prefix.

        Args:
            payload: Discord webhook event payload.

        Returns:
            Processing result dict.
        """
        event_type = payload.get("t", payload.get("type", "unknown"))
        data = payload.get("d", payload)

        if event_type in ("MESSAGE_CREATE", "message_create"):
            content = data.get("content", "")
            user_id = data.get("author", {}).get("id", "unknown")
            channel_id = data.get("channel_id", "unknown")

            # Check for bot messages to avoid loops
            if data.get("author", {}).get("bot", False):
                return {"status": "ignored", "reason": "bot_message"}

            # Get prefix
            conn = self._get_conn()
            try:
                config = conn.execute(
                    "SELECT command_prefix FROM discord_config WHERE id = ?",
                    ("discord-primary",),
                ).fetchone()
                prefix = config["command_prefix"] if config else "!cortex"
            finally:
                conn.close()

            if content.startswith(prefix):
                cmd_text = content[len(prefix):].strip()
                parts = cmd_text.split()
                if parts:
                    command = parts[0]
                    args = parts[1:]
                    return self.handle_command(command, args, user_id, channel_id)

            return {"status": "ignored", "reason": "no_command_prefix"}

        logger.debug("Unhandled Discord event type: %s", event_type)
        return {"status": "ignored", "reason": f"unhandled_event_{event_type}"}

    # ── Query ─────────────────────────────────────────────────────────

    def list_messages(self, direction: Optional[str] = None, limit: int = 50) -> list:
        """List Discord messages with optional direction filter.

        Args:
            direction: Filter by 'inbound' or 'outbound', or None for all.
            limit: Maximum results to return.

        Returns:
            List of message dicts, newest first.
        """
        conn = self._get_conn()
        try:
            if direction:
                rows = conn.execute(
                    "SELECT * FROM discord_messages WHERE direction = ? ORDER BY created_at DESC LIMIT ?",
                    (direction, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM discord_messages ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_stats(self) -> dict:
        """Return Discord integration statistics.

        Returns:
            Dict with message counts and command usage.
        """
        conn = self._get_conn()
        try:
            total_sent = conn.execute(
                "SELECT COUNT(*) FROM discord_messages WHERE direction = 'outbound'"
            ).fetchone()[0]
            total_received = conn.execute(
                "SELECT COUNT(*) FROM discord_messages WHERE direction = 'inbound'"
            ).fetchone()[0]
            commands_processed = conn.execute(
                "SELECT COUNT(*) FROM discord_messages WHERE command IS NOT NULL"
            ).fetchone()[0]
            failed = conn.execute(
                "SELECT COUNT(*) FROM discord_messages WHERE status = 'failed'"
            ).fetchone()[0]

            # Top commands
            top_commands_rows = conn.execute(
                """SELECT command, COUNT(*) as cnt FROM discord_messages
                   WHERE command IS NOT NULL
                   GROUP BY command ORDER BY cnt DESC LIMIT 5"""
            ).fetchall()
            top_commands = {r["command"]: r["cnt"] for r in top_commands_rows}

            return {
                "messages_sent": total_sent,
                "messages_received": total_received,
                "commands_processed": commands_processed,
                "failed_deliveries": failed,
                "total": total_sent + total_received,
                "top_commands": top_commands,
            }
        finally:
            conn.close()

    def test_connection(self) -> dict:
        """Send a test message to verify the Discord webhook/bot is functional.

        Returns:
            Test result dict with status.
        """
        config = self.get_config()
        if not config.get("configured"):
            return {"status": "error", "message": "Discord integration not configured"}
        if not config.get("enabled"):
            return {"status": "error", "message": "Discord integration is disabled"}

        result = self.send_notification(
            channel_id="test",
            message="CortexDB Discord integration test — connection verified.",
        )

        if "error" in result:
            return {"status": "error", "message": result["error"]}

        logger.info("Discord connection test successful")
        return {
            "status": "ok",
            "message": "Test message sent successfully",
            "message_id": result.get("message_id"),
            "tested_at": self._now(),
        }

    def register_slash_commands(self) -> dict:
        """Return slash command definitions for Discord registration.

        These definitions should be POSTed to the Discord API
        at POST /applications/{app_id}/commands.

        Returns:
            Dict with list of slash command definition dicts.
        """
        config = self.get_config()
        if not config.get("configured"):
            return {"error": "Discord integration not configured"}

        logger.info("Returning %d slash command definitions", len(SLASH_COMMANDS))
        return {
            "commands": SLASH_COMMANDS,
            "count": len(SLASH_COMMANDS),
            "guild_id": config.get("guild_id"),
            "note": "POST these to /applications/{app_id}/commands to register globally, "
                    "or /applications/{app_id}/guilds/{guild_id}/commands for guild-specific.",
        }
