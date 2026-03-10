'use client';
import { useState, useMemo } from 'react';
import {
  Plus, X, ChevronRight, Pin, PinOff, Trash2, MoreHorizontal,
  PanelLeftClose, FolderPlus, Bot,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { formatDate } from '@/lib/utils';
import { useChatStore } from '@/hooks/useChatStore';
import { useChatSessions } from '@/hooks/useChatSessions';
import type { ChatSession, ChatGroup } from '@/lib/api';

const GROUP_COLORS = ['#6366f1','#f59e0b','#10b981','#ef4444','#8b5cf6','#ec4899','#06b6d4','#f97316'];

export function ChatSidebar() {
  const { sessions, groups, activeSessionId, setSidebarOpen } = useChatStore();
  const { startNewChat, selectSession, deleteSession, togglePin, moveToGroup, createGroup } = useChatSessions();

  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set(['ungrouped']));
  const [sessionMenu, setSessionMenu] = useState<string | null>(null);
  const [showNewGroup, setShowNewGroup] = useState(false);
  const [newGroupName, setNewGroupName] = useState('');

  const pinnedSessions = sessions.filter((s) => s.pinned);

  const groupedSessions = useMemo(() => {
    const map: Record<string, ChatSession[]> = { ungrouped: [] };
    for (const g of groups) map[g.id] = [];
    for (const s of sessions) {
      if (s.pinned) continue;
      if (s.group_id && map[s.group_id]) map[s.group_id].push(s);
      else map.ungrouped.push(s);
    }
    return map;
  }, [sessions, groups]);

  const toggleGroup = (id: string) => {
    setExpandedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const handleCreateGroup = () => {
    if (!newGroupName.trim()) return;
    createGroup(newGroupName.trim(), GROUP_COLORS[groups.length % GROUP_COLORS.length]);
    setNewGroupName('');
    setShowNewGroup(false);
  };

  return (
    <div className="w-64 shrink-0 border-r border-[var(--border-default)] flex flex-col bg-[var(--bg-surface)] mr-3 rounded-xl overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2.5 border-b border-[var(--border-default)]">
        <span className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider">
          Conversations
        </span>
        <div className="flex items-center gap-1">
          <button onClick={() => setShowNewGroup(true)} className="rounded p-1 text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-hover)]" title="New group">
            <FolderPlus className="h-3.5 w-3.5" />
          </button>
          <button onClick={startNewChat} className="rounded p-1 text-[var(--text-muted)] hover:text-amber-400 hover:bg-amber-500/10" title="New chat">
            <Plus className="h-3.5 w-3.5" />
          </button>
          <button onClick={() => setSidebarOpen(false)} className="rounded p-1 text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-hover)]">
            <PanelLeftClose className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {/* New group input */}
      {showNewGroup && (
        <div className="px-2 py-2 border-b border-[var(--border-default)] flex gap-1">
          <input
            value={newGroupName}
            onChange={(e) => setNewGroupName(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleCreateGroup()}
            placeholder="Group name..."
            className="flex-1 rounded bg-[var(--bg-elevated)] border border-[var(--border-default)] px-2 py-1 text-xs outline-none text-[var(--text-primary)]"
            autoFocus
          />
          <button onClick={handleCreateGroup} className="rounded bg-amber-500/20 px-2 py-1 text-xs text-amber-400 hover:bg-amber-500/30">
            Add
          </button>
          <button onClick={() => { setShowNewGroup(false); setNewGroupName(''); }} className="rounded p-1 text-[var(--text-muted)] hover:text-red-400">
            <X className="h-3 w-3" />
          </button>
        </div>
      )}

      {/* Session list */}
      <div className="flex-1 overflow-auto text-xs">
        {/* Pinned */}
        {pinnedSessions.length > 0 && (
          <div className="py-1">
            <div className="px-3 py-1 text-[10px] font-semibold text-amber-400/70 uppercase tracking-wider flex items-center gap-1">
              <Pin className="h-2.5 w-2.5" /> Pinned
            </div>
            {pinnedSessions.map((s) => (
              <SessionItem
                key={s.id}
                session={s}
                active={s.id === activeSessionId}
                onClick={() => { selectSession(s); setSessionMenu(null); }}
                onMenu={() => setSessionMenu(sessionMenu === s.id ? null : s.id)}
                showMenu={sessionMenu === s.id}
                onDelete={() => { deleteSession(s.id); setSessionMenu(null); }}
                onPin={() => { togglePin(s); setSessionMenu(null); }}
                groups={groups}
                onMoveToGroup={(gid) => { moveToGroup(s.id, gid); setSessionMenu(null); }}
              />
            ))}
          </div>
        )}

        {/* Groups */}
        {groups.map((g) => (
          <div key={g.id} className="py-0.5">
            <button
              onClick={() => toggleGroup(g.id)}
              className="w-full flex items-center gap-2 px-3 py-1.5 hover:bg-[var(--bg-hover)] text-[var(--text-secondary)]"
            >
              <ChevronRight className={cn('h-3 w-3 transition-transform', expandedGroups.has(g.id) && 'rotate-90')} />
              <div className="h-2 w-2 rounded-full" style={{ backgroundColor: g.color }} />
              <span className="font-medium truncate">{g.name}</span>
              <span className="ml-auto text-[var(--text-muted)]">{(groupedSessions[g.id] || []).length}</span>
            </button>
            {expandedGroups.has(g.id) &&
              (groupedSessions[g.id] || []).map((s) => (
                <SessionItem
                  key={s.id}
                  session={s}
                  active={s.id === activeSessionId}
                  onClick={() => { selectSession(s); setSessionMenu(null); }}
                  onMenu={() => setSessionMenu(sessionMenu === s.id ? null : s.id)}
                  showMenu={sessionMenu === s.id}
                  onDelete={() => { deleteSession(s.id); setSessionMenu(null); }}
                  onPin={() => { togglePin(s); setSessionMenu(null); }}
                  groups={groups}
                  onMoveToGroup={(gid) => { moveToGroup(s.id, gid); setSessionMenu(null); }}
                  indent
                />
              ))}
          </div>
        ))}

        {/* Ungrouped */}
        <div className="py-0.5">
          <button
            onClick={() => toggleGroup('ungrouped')}
            className="w-full flex items-center gap-2 px-3 py-1.5 hover:bg-[var(--bg-hover)] text-[var(--text-secondary)]"
          >
            <ChevronRight className={cn('h-3 w-3 transition-transform', expandedGroups.has('ungrouped') && 'rotate-90')} />
            <span className="font-medium">Recent</span>
            <span className="ml-auto text-[var(--text-muted)]">{(groupedSessions.ungrouped || []).length}</span>
          </button>
          {expandedGroups.has('ungrouped') &&
            (groupedSessions.ungrouped || []).map((s) => (
              <SessionItem
                key={s.id}
                session={s}
                active={s.id === activeSessionId}
                onClick={() => { selectSession(s); setSessionMenu(null); }}
                onMenu={() => setSessionMenu(sessionMenu === s.id ? null : s.id)}
                showMenu={sessionMenu === s.id}
                onDelete={() => { deleteSession(s.id); setSessionMenu(null); }}
                onPin={() => { togglePin(s); setSessionMenu(null); }}
                groups={groups}
                onMoveToGroup={(gid) => { moveToGroup(s.id, gid); setSessionMenu(null); }}
              />
            ))}
        </div>
      </div>
    </div>
  );
}

/* ── Session item ── */
function SessionItem({
  session, active, onClick, onMenu, showMenu, onDelete, onPin, groups, onMoveToGroup, indent,
}: {
  session: ChatSession; active: boolean; onClick: () => void; onMenu: () => void; showMenu: boolean;
  onDelete: () => void; onPin: () => void; groups: ChatGroup[]; onMoveToGroup: (gid: string | null) => void;
  indent?: boolean;
}) {
  const title = session.title || `${session.agent_name || session.agent_id}`;
  const time = session.last_message_at ? formatDate(new Date(session.last_message_at)) : '';

  return (
    <div className="relative">
      <button
        onClick={onClick}
        className={cn(
          'w-full text-left px-3 py-2 flex items-center gap-2 hover:bg-[var(--bg-hover)] group',
          active && 'bg-amber-500/10 border-r-2 border-amber-400',
          indent && 'pl-7',
        )}
      >
        <Bot className={cn('h-3.5 w-3.5 shrink-0', active ? 'text-amber-400' : 'text-[var(--text-muted)]')} />
        <div className="flex-1 min-w-0">
          <div className="truncate text-[var(--text-primary)] text-xs font-medium">{title}</div>
          <div className="flex items-center gap-1.5 text-[10px] text-[var(--text-muted)]">
            <span>{time}</span>
            {session.message_count > 0 && (
              <span>{session.message_count} msg{session.message_count !== 1 ? 's' : ''}</span>
            )}
          </div>
        </div>
        <button
          onClick={(e) => { e.stopPropagation(); onMenu(); }}
          className="opacity-0 group-hover:opacity-100 rounded p-0.5 text-[var(--text-muted)] hover:text-[var(--text-primary)]"
        >
          <MoreHorizontal className="h-3 w-3" />
        </button>
      </button>

      {showMenu && (
        <div className="absolute right-2 top-full z-50 w-40 rounded-lg border border-[var(--border-default)] bg-[var(--bg-surface)] shadow-xl text-xs py-1">
          <button onClick={onPin} className="w-full text-left px-3 py-1.5 hover:bg-[var(--bg-hover)] flex items-center gap-2">
            {session.pinned ? <PinOff className="h-3 w-3" /> : <Pin className="h-3 w-3" />}
            {session.pinned ? 'Unpin' : 'Pin'}
          </button>
          {groups.length > 0 && (
            <>
              <div className="border-t border-[var(--border-default)] my-1" />
              <div className="px-3 py-1 text-[10px] text-[var(--text-muted)] uppercase">Move to</div>
              {groups.map((g) => (
                <button
                  key={g.id}
                  onClick={() => onMoveToGroup(g.id)}
                  className="w-full text-left px-3 py-1.5 hover:bg-[var(--bg-hover)] flex items-center gap-2"
                >
                  <div className="h-2 w-2 rounded-full" style={{ backgroundColor: g.color }} />
                  {g.name}
                </button>
              ))}
              {session.group_id && (
                <button onClick={() => onMoveToGroup(null)} className="w-full text-left px-3 py-1.5 hover:bg-[var(--bg-hover)] text-[var(--text-muted)]">
                  Remove from group
                </button>
              )}
            </>
          )}
          <div className="border-t border-[var(--border-default)] my-1" />
          <button onClick={onDelete} className="w-full text-left px-3 py-1.5 hover:bg-red-500/10 text-red-400 flex items-center gap-2">
            <Trash2 className="h-3 w-3" /> Delete
          </button>
        </div>
      )}
    </div>
  );
}
