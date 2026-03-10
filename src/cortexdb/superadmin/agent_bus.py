"""
Agent Communication Bus — Message passing between CDB agents.
Supports: direct messages, delegation (Chief > Lead > Agent),
escalation (Agent > Lead > Chief), broadcasts, and department channels.
"""

import time
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass, field, asdict
from enum import Enum

logger = logging.getLogger(__name__)


class MessageType(str, Enum):
    DIRECT = "direct"           # Agent-to-agent
    DELEGATION = "delegation"   # Supervisor assigns work to subordinate
    ESCALATION = "escalation"   # Subordinate escalates to supervisor
    BROADCAST = "broadcast"     # To all agents or a department
    STATUS = "status"           # Status update / heartbeat
    RESULT = "result"           # Task result delivery


class MessagePriority(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


@dataclass
class AgentMessage:
    message_id: str
    msg_type: MessageType
    from_agent: str
    to_agent: Optional[str]  # None for broadcasts
    subject: str
    content: str
    priority: MessagePriority = MessagePriority.NORMAL
    department: Optional[str] = None  # For department broadcasts
    task_id: Optional[str] = None     # Related task
    parent_id: Optional[str] = None   # Reply chain
    status: str = "sent"  # sent, delivered, read, acknowledged
    created_at: float = 0
    read_at: float = 0
    metadata: Dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["msg_type"] = self.msg_type.value if isinstance(self.msg_type, MessageType) else self.msg_type
        d["priority"] = self.priority.value if isinstance(self.priority, MessagePriority) else self.priority
        return d


class AgentBus:
    """Central message bus for agent-to-agent communication."""

    def __init__(self):
        self._messages: Dict[str, AgentMessage] = {}
        self._counter = 0
        self._persistence = None

    def set_persistence(self, store):
        """Attach persistence store."""
        self._persistence = store
        # Load existing messages
        saved = store.load("messages")
        if isinstance(saved, dict):
            for mid, mdata in saved.items():
                self._messages[mid] = AgentMessage(**{
                    k: v for k, v in mdata.items()
                    if k in AgentMessage.__dataclass_fields__
                })
            self._counter = len(self._messages)

    def _next_id(self) -> str:
        self._counter += 1
        return f"MSG-{self._counter:05d}"

    def _save(self):
        if self._persistence:
            self._persistence.save("messages", {
                mid: m.to_dict() for mid, m in self._messages.items()
            })

    # ── Send messages ──

    def send(self, from_agent: str, to_agent: str, subject: str, content: str,
             msg_type: str = "direct", priority: str = "normal",
             task_id: str = None, parent_id: str = None,
             department: str = None) -> dict:
        """Send a message between agents."""
        mid = self._next_id()
        msg = AgentMessage(
            message_id=mid,
            msg_type=MessageType(msg_type),
            from_agent=from_agent,
            to_agent=to_agent,
            subject=subject,
            content=content,
            priority=MessagePriority(priority),
            task_id=task_id,
            parent_id=parent_id,
            department=department,
            created_at=time.time(),
        )
        self._messages[mid] = msg
        self._save()

        if self._persistence:
            self._persistence.audit(
                "message_sent", "message", mid,
                {"from": from_agent, "to": to_agent, "type": msg_type},
            )

        logger.info("Message %s: %s -> %s [%s] %s", mid, from_agent, to_agent, msg_type, subject)
        return msg.to_dict()

    def delegate(self, from_agent: str, to_agent: str, task_id: str,
                 instructions: str) -> dict:
        """Delegate a task from supervisor to subordinate."""
        return self.send(
            from_agent=from_agent,
            to_agent=to_agent,
            subject=f"Delegated: Task {task_id}",
            content=instructions,
            msg_type="delegation",
            priority="high",
            task_id=task_id,
        )

    def escalate(self, from_agent: str, to_agent: str, task_id: str,
                 reason: str) -> dict:
        """Escalate a task from subordinate to supervisor."""
        return self.send(
            from_agent=from_agent,
            to_agent=to_agent,
            subject=f"Escalation: Task {task_id}",
            content=reason,
            msg_type="escalation",
            priority="high",
            task_id=task_id,
        )

    def broadcast(self, from_agent: str, subject: str, content: str,
                  department: str = None) -> dict:
        """Broadcast to all agents or a specific department."""
        mid = self._next_id()
        msg = AgentMessage(
            message_id=mid,
            msg_type=MessageType.BROADCAST,
            from_agent=from_agent,
            to_agent=None,
            subject=subject,
            content=content,
            department=department,
            created_at=time.time(),
        )
        self._messages[mid] = msg
        self._save()
        logger.info("Broadcast %s from %s to %s: %s", mid, from_agent, department or "ALL", subject)
        return msg.to_dict()

    # ── Read messages ──

    def get_inbox(self, agent_id: str, unread_only: bool = False, limit: int = 50) -> List[dict]:
        """Get messages for an agent (direct + department broadcasts)."""
        msgs = []
        for m in self._messages.values():
            is_recipient = (
                m.to_agent == agent_id or
                (m.msg_type == MessageType.BROADCAST and m.to_agent is None)
            )
            if is_recipient:
                if unread_only and m.status in ("read", "acknowledged"):
                    continue
                msgs.append(m)
        return [m.to_dict() for m in sorted(msgs, key=lambda x: -x.created_at)[:limit]]

    def get_sent(self, agent_id: str, limit: int = 50) -> List[dict]:
        """Get messages sent by an agent."""
        msgs = [m for m in self._messages.values() if m.from_agent == agent_id]
        return [m.to_dict() for m in sorted(msgs, key=lambda x: -x.created_at)[:limit]]

    def get_thread(self, message_id: str) -> List[dict]:
        """Get a message thread (message + all replies)."""
        root = message_id
        # Walk up to find root
        msg = self._messages.get(root)
        while msg and msg.parent_id and msg.parent_id in self._messages:
            root = msg.parent_id
            msg = self._messages.get(root)

        # Collect thread
        thread = []
        def collect(mid):
            m = self._messages.get(mid)
            if m:
                thread.append(m.to_dict())
                for child in self._messages.values():
                    if child.parent_id == mid:
                        collect(child.message_id)
        collect(root)
        return sorted(thread, key=lambda x: x.get("created_at", 0))

    def mark_read(self, message_id: str) -> bool:
        msg = self._messages.get(message_id)
        if not msg:
            return False
        msg.status = "read"
        msg.read_at = time.time()
        self._save()
        return True

    def acknowledge(self, message_id: str) -> bool:
        msg = self._messages.get(message_id)
        if not msg:
            return False
        msg.status = "acknowledged"
        self._save()
        return True

    # ── Stats ──

    def get_stats(self) -> dict:
        msgs = list(self._messages.values())
        by_type = {}
        for m in msgs:
            t = m.msg_type.value if isinstance(m.msg_type, MessageType) else m.msg_type
            by_type[t] = by_type.get(t, 0) + 1
        return {
            "total_messages": len(msgs),
            "unread": sum(1 for m in msgs if m.status == "sent"),
            "by_type": by_type,
            "recent": [m.to_dict() for m in sorted(msgs, key=lambda x: -x.created_at)[:5]],
        }

    def get_all_messages(self, msg_type: str = None, limit: int = 100) -> List[dict]:
        msgs = list(self._messages.values())
        if msg_type:
            msgs = [m for m in msgs if (m.msg_type.value if isinstance(m.msg_type, MessageType) else m.msg_type) == msg_type]
        return [m.to_dict() for m in sorted(msgs, key=lambda x: -x.created_at)[:limit]]
