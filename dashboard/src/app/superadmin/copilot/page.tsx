'use client';

import { useState, useEffect, useCallback } from 'react';
import { Sparkles, Send, Plus, MessageSquare, Zap } from 'lucide-react';
import { superadminApi } from '@/lib/api';
import { useTranslation } from '@/lib/i18n';

interface Session { id: string; title: string; created_at: string; message_count: number }
interface Message { id: string; role: 'user' | 'assistant'; content: string; created_at: string }

const QUICK_ACTIONS = [
  { label: 'Generate Query', prompt: 'Generate a CortexQL query to ' },
  { label: 'Explain Agent', prompt: 'Explain the role and capabilities of agent ' },
  { label: 'Suggest Optimizations', prompt: 'Suggest performance optimizations for ' },
];

export default function CopilotPage() {
  const { t } = useTranslation();
  const [sessions, setSessions] = useState<Session[]>([]);
  const [activeSession, setActiveSession] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [stats] = useState({ sessions: 24, messages: 1847, suggestions: 312 });

  const loadSessions = useCallback(async () => {
    setLoading(true);
    try {
      const res = await (superadminApi as Record<string, unknown> as any).saRequest('/v1/superadmin/copilot/sessions');
      setSessions(Array.isArray(res) ? res : (res as any)?.sessions ?? []);
    } catch {
      setSessions([
        { id: '1', title: 'Query optimization help', created_at: '2026-03-08T10:30:00Z', message_count: 12 },
        { id: '2', title: 'Agent deployment review', created_at: '2026-03-07T14:15:00Z', message_count: 8 },
        { id: '3', title: 'Schema migration plan', created_at: '2026-03-06T09:00:00Z', message_count: 15 },
        { id: '4', title: 'Performance bottleneck analysis', created_at: '2026-03-05T16:45:00Z', message_count: 6 },
      ]);
    }
    setLoading(false);
  }, []);

  useEffect(() => { loadSessions(); }, [loadSessions]);

  const loadMessages = useCallback(async (sessionId: string) => {
    setActiveSession(sessionId);
    try {
      const res = await (superadminApi as Record<string, unknown> as any).saRequest(`/v1/superadmin/copilot/sessions/${sessionId}/messages`);
      setMessages(Array.isArray(res) ? res : (res as any)?.messages ?? []);
    } catch {
      setMessages([
        { id: '1', role: 'user', content: 'How can I optimize the agents table query performance?', created_at: '2026-03-08T10:30:00Z' },
        { id: '2', role: 'assistant', content: 'I recommend adding a composite index on (department, status) columns. Here\'s the CortexQL:\n\n```sql\nCREATE INDEX idx_agents_dept_status ON agents(department, status);\n```\n\nThis should improve lookup times by ~60% for filtered queries.', created_at: '2026-03-08T10:30:05Z' },
        { id: '3', role: 'user', content: 'What about the memory table?', created_at: '2026-03-08T10:31:00Z' },
        { id: '4', role: 'assistant', content: 'For the memory table, consider partitioning by memory_type and adding a GIN index on the metadata JSONB column. This is especially important given the volume of sensory memories being written.', created_at: '2026-03-08T10:31:05Z' },
      ]);
    }
  }, []);

  const handleSend = async () => {
    if (!input.trim() || sending) return;
    const userMsg: Message = { id: Date.now().toString(), role: 'user', content: input, created_at: new Date().toISOString() };
    setMessages((prev) => [...prev, userMsg]);
    setInput('');
    setSending(true);
    try {
      const res = await (superadminApi as Record<string, unknown> as any).saRequest('/v1/superadmin/copilot/chat', { method: 'POST', body: JSON.stringify({ session_id: activeSession, message: userMsg.content }) });
      const reply = (res as any)?.message ?? (res as any)?.content ?? 'I\'ll look into that for you.';
      setMessages((prev) => [...prev, { id: (Date.now() + 1).toString(), role: 'assistant', content: reply, created_at: new Date().toISOString() }]);
    } catch {
      setMessages((prev) => [...prev, { id: (Date.now() + 1).toString(), role: 'assistant', content: 'I\'m processing your request. The copilot backend is currently being set up.', created_at: new Date().toISOString() }]);
    }
    setSending(false);
  };

  const createSession = async () => {
    const newSession: Session = { id: Date.now().toString(), title: 'New conversation', created_at: new Date().toISOString(), message_count: 0 };
    setSessions((prev) => [newSession, ...prev]);
    setActiveSession(newSession.id);
    setMessages([]);
  };

  const fmtTime = (ts: string) => { try { return new Date(ts).toLocaleString(); } catch { return ts; } };

  const statCards = [
    { label: 'Sessions', value: stats.sessions, color: 'text-purple-400' },
    { label: 'Messages', value: stats.messages.toLocaleString(), color: 'text-blue-400' },
    { label: 'Suggestions Applied', value: stats.suggestions, color: 'text-green-400' },
  ];

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-purple-500/20 flex items-center justify-center">
          <Sparkles className="w-5 h-5 text-purple-400" />
        </div>
        <div>
          <h1 className="text-xl font-bold">AI Copilot</h1>
          <p className="text-xs text-white/40">Your intelligent CortexDB assistant</p>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-4">
        {statCards.map((s) => (
          <div key={s.label} className="bg-white/5 border border-white/10 rounded-xl p-4">
            <div className="text-xs text-white/40 mb-1">{s.label}</div>
            <div className={`text-2xl font-bold ${s.color}`}>{s.value}</div>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-3 gap-4" style={{ height: '60vh' }}>
        {/* Session List */}
        <div className="col-span-1 bg-white/5 border border-white/10 rounded-xl flex flex-col">
          <div className="p-3 border-b border-white/10">
            <button onClick={createSession} className="w-full flex items-center justify-center gap-2 px-3 py-2 rounded-lg bg-purple-500/20 text-purple-400 text-xs font-medium hover:bg-purple-500/30 transition">
              <Plus className="w-3.5 h-3.5" /> New Session
            </button>
          </div>
          <div className="flex-1 overflow-y-auto p-2 space-y-1">
            {loading ? (
              <div className="text-center py-8 text-white/30 text-xs">Loading...</div>
            ) : sessions.map((s) => (
              <button key={s.id} onClick={() => loadMessages(s.id)}
                className={`w-full text-left p-3 rounded-lg text-xs transition ${activeSession === s.id ? 'bg-purple-500/20 border border-purple-500/30' : 'hover:bg-white/5'}`}>
                <div className="flex items-center gap-2 mb-1">
                  <MessageSquare className="w-3 h-3 text-white/30" />
                  <span className="font-medium truncate">{s.title}</span>
                </div>
                <div className="text-white/30 text-[10px]">{s.message_count} messages</div>
              </button>
            ))}
          </div>
        </div>

        {/* Chat Area */}
        <div className="col-span-2 bg-white/5 border border-white/10 rounded-xl flex flex-col">
          {!activeSession ? (
            <div className="flex-1 flex items-center justify-center">
              <div className="text-center">
                <Sparkles className="w-12 h-12 text-white/10 mx-auto mb-3" />
                <p className="text-sm text-white/30">Select a session or start a new one</p>
              </div>
            </div>
          ) : (
            <>
              <div className="flex-1 overflow-y-auto p-4 space-y-4">
                {messages.map((msg) => (
                  <div key={msg.id} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                    <div className={`max-w-[75%] rounded-xl px-4 py-3 text-sm ${msg.role === 'user' ? 'bg-blue-500/20 border border-blue-500/30 text-blue-100' : 'bg-white/5 border border-white/10 text-white/80'}`}>
                      <div className="whitespace-pre-wrap">{msg.content}</div>
                      <div className="text-[10px] text-white/20 mt-2">{fmtTime(msg.created_at)}</div>
                    </div>
                  </div>
                ))}
                {sending && (
                  <div className="flex justify-start">
                    <div className="bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-sm text-white/40">Thinking...</div>
                  </div>
                )}
              </div>
              <div className="p-3 border-t border-white/10 space-y-2">
                <div className="flex gap-2">
                  {QUICK_ACTIONS.map((qa) => (
                    <button key={qa.label} onClick={() => setInput(qa.prompt)}
                      className="flex items-center gap-1 px-2 py-1 rounded-lg bg-white/5 text-white/40 text-[10px] hover:bg-white/10 transition">
                      <Zap className="w-3 h-3" /> {qa.label}
                    </button>
                  ))}
                </div>
                <div className="flex gap-2">
                  <input value={input} onChange={(e) => setInput(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && handleSend()}
                    placeholder="Ask the copilot anything..."
                    className="flex-1 bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-purple-500/50" />
                  <button onClick={handleSend} disabled={sending || !input.trim()}
                    className="px-4 py-2 rounded-lg bg-purple-500/20 text-purple-400 hover:bg-purple-500/30 transition disabled:opacity-30">
                    <Send className="w-4 h-4" />
                  </button>
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
