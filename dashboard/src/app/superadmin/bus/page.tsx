'use client';

import { useEffect, useState, useCallback } from 'react';
import { Mail, Send, RefreshCw, ArrowUpRight, ArrowDownRight, Megaphone, MessageCircle } from 'lucide-react';
import { superadminApi } from '@/lib/api';
import { useTranslation } from '@/lib/i18n';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type D = Record<string, any>;

const TYPE_ICONS: Record<string, typeof Send> = {
  direct: MessageCircle,
  delegation: ArrowDownRight,
  escalation: ArrowUpRight,
  broadcast: Megaphone,
};

const TYPE_COLORS: Record<string, string> = {
  direct: 'bg-blue-500/20 text-blue-300',
  delegation: 'bg-amber-500/20 text-amber-300',
  escalation: 'bg-red-500/20 text-red-300',
  broadcast: 'bg-purple-500/20 text-purple-300',
  status: 'bg-white/10 text-white/40',
  result: 'bg-emerald-500/20 text-emerald-300',
};

export default function AgentBusPage() {
  const { t } = useTranslation();
  const [messages, setMessages] = useState<D[]>([]);
  const [stats, setStats] = useState<D>({});
  const [agents, setAgents] = useState<D[]>([]);
  const [showSend, setShowSend] = useState(false);
  const [filter, setFilter] = useState('all');
  const [form, setForm] = useState({
    from_agent: '', to_agent: '', subject: '', content: '',
    msg_type: 'direct', priority: 'normal', department: '',
  });

  const refresh = useCallback(async () => {
    try {
      const [mRes, sRes, tRes] = await Promise.all([
        superadminApi.busMessages(undefined, 200).catch(() => null),
        superadminApi.busStats().catch(() => null),
        superadminApi.getTeam().catch(() => null),
      ]);
      if (mRes) setMessages((mRes as D).messages ?? []);
      if (sRes) setStats(sRes);
      if (tRes) setAgents((tRes as D).agents ?? []);
    } catch { /* silent */ }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const handleSend = async () => {
    if (!form.content.trim()) return;
    try {
      if (form.msg_type === 'broadcast') {
        await superadminApi.busBroadcast({
          from_agent: form.from_agent || 'superadmin',
          subject: form.subject,
          content: form.content,
          department: form.department || undefined,
        });
      } else {
        await superadminApi.busSend(form);
      }
      setShowSend(false);
      setForm({ from_agent: '', to_agent: '', subject: '', content: '', msg_type: 'direct', priority: 'normal', department: '' });
      refresh();
    } catch { /* silent */ }
  };

  const filtered = filter === 'all' ? messages : messages.filter((m: D) => m.msg_type === filter);

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold mb-1 flex items-center gap-2">
            <Mail className="w-6 h-6 text-blue-400" /> {t('bus.title')}
          </h1>
          <p className="text-sm text-white/40">{t('bus.subtitle')}</p>
        </div>
        <div className="flex gap-2">
          <button onClick={refresh} className="glass px-3 py-2 rounded-lg text-xs text-white/60 hover:text-white/90">
            <RefreshCw className="w-3.5 h-3.5" />
          </button>
          <button onClick={() => setShowSend(!showSend)}
            className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-blue-500/20 text-blue-300 hover:bg-blue-500/30 text-sm">
            <Send className="w-4 h-4" /> New Message
          </button>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
        <div className="glass rounded-xl p-3">
          <div className="text-xs text-white/40">Total Messages</div>
          <div className="text-2xl font-bold">{stats.total_messages ?? 0}</div>
        </div>
        <div className="glass rounded-xl p-3">
          <div className="text-xs text-white/40">Unread</div>
          <div className="text-2xl font-bold text-amber-400">{stats.unread ?? 0}</div>
        </div>
        {Object.entries((stats.by_type ?? {}) as Record<string, number>).map(([typ, c]) => (
          <div key={typ} className="glass rounded-xl p-3">
            <div className="text-xs text-white/40 capitalize">{typ}</div>
            <div className="text-2xl font-bold">{c}</div>
          </div>
        ))}
      </div>

      {/* Send Form */}
      {showSend && (
        <div className="glass rounded-xl p-4 mb-6 space-y-3">
          <div className="text-sm font-semibold">Send Message</div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            <select value={form.msg_type} onChange={(e) => setForm({ ...form, msg_type: e.target.value })}
              className="glass rounded-lg px-3 py-2 text-xs bg-white/5 border border-white/10">
              <option value="direct">Direct</option>
              <option value="delegation">Delegation</option>
              <option value="escalation">Escalation</option>
              <option value="broadcast">Broadcast</option>
            </select>
            <select value={form.from_agent} onChange={(e) => setForm({ ...form, from_agent: e.target.value })}
              className="glass rounded-lg px-3 py-2 text-xs bg-white/5 border border-white/10">
              <option value="">From: SuperAdmin</option>
              {agents.map((a: D) => <option key={a.agent_id} value={a.agent_id}>{a.name} ({a.agent_id})</option>)}
            </select>
            {form.msg_type !== 'broadcast' ? (
              <select value={form.to_agent} onChange={(e) => setForm({ ...form, to_agent: e.target.value })}
                className="glass rounded-lg px-3 py-2 text-xs bg-white/5 border border-white/10">
                <option value="">To agent...</option>
                {agents.map((a: D) => <option key={a.agent_id} value={a.agent_id}>{a.name} ({a.agent_id})</option>)}
              </select>
            ) : (
              <select value={form.department} onChange={(e) => setForm({ ...form, department: e.target.value })}
                className="glass rounded-lg px-3 py-2 text-xs bg-white/5 border border-white/10">
                <option value="">All Departments</option>
                {['EXEC', 'ENG', 'QA', 'OPS', 'SEC', 'DOC'].map((d) => <option key={d} value={d}>{d}</option>)}
              </select>
            )}
            <select value={form.priority} onChange={(e) => setForm({ ...form, priority: e.target.value })}
              className="glass rounded-lg px-3 py-2 text-xs bg-white/5 border border-white/10">
              <option value="normal">Normal</option>
              <option value="high">High</option>
              <option value="critical">Critical</option>
              <option value="low">Low</option>
            </select>
          </div>
          <input value={form.subject} onChange={(e) => setForm({ ...form, subject: e.target.value })}
            placeholder="Subject..." className="w-full glass rounded-lg px-3 py-2 text-sm bg-white/5 border border-white/10" />
          <textarea value={form.content} onChange={(e) => setForm({ ...form, content: e.target.value })}
            placeholder="Message content..." rows={3}
            className="w-full glass rounded-lg px-3 py-2 text-sm bg-white/5 border border-white/10 resize-none" />
          <div className="flex gap-2">
            <button onClick={handleSend} className="px-4 py-2 rounded-lg text-sm bg-emerald-500/20 text-emerald-300 hover:bg-emerald-500/30">{t('common.send')}</button>
            <button onClick={() => setShowSend(false)} className="px-4 py-2 rounded-lg text-sm bg-white/5 text-white/40 hover:bg-white/10">{t('common.cancel')}</button>
          </div>
        </div>
      )}

      {/* Filter */}
      <div className="flex gap-2 mb-4 flex-wrap">
        {['all', 'direct', 'delegation', 'escalation', 'broadcast', 'result'].map((f) => (
          <button key={f} onClick={() => setFilter(f)}
            className={`px-3 py-1 rounded-lg text-xs capitalize transition ${filter === f ? 'glass-heavy text-white' : 'glass text-white/50 hover:text-white/80'}`}>
            {f === 'all' ? t('common.all') : f}
          </button>
        ))}
      </div>

      {/* Messages */}
      <div className="space-y-2">
        {filtered.length === 0 && (
          <div className="text-center py-12 text-white/30">{t('common.noData')}</div>
        )}
        {filtered.map((m: D) => {
          const Icon = TYPE_ICONS[m.msg_type] ?? MessageCircle;
          const colorClass = TYPE_COLORS[m.msg_type] ?? 'bg-white/10 text-white/40';
          return (
            <div key={m.message_id} className="glass rounded-xl p-4">
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${colorClass} flex items-center gap-1`}>
                    <Icon className="w-3 h-3" /> {m.msg_type}
                  </span>
                  <span className="text-xs font-mono text-white/30">{m.message_id}</span>
                  {m.priority && m.priority !== 'normal' && (
                    <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${
                      m.priority === 'critical' ? 'bg-red-500/20 text-red-300' :
                      m.priority === 'high' ? 'bg-amber-500/20 text-amber-300' : 'bg-white/10 text-white/40'
                    }`}>{m.priority}</span>
                  )}
                </div>
                <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${
                  m.status === 'sent' ? 'bg-blue-500/20 text-blue-300' :
                  m.status === 'read' ? 'bg-emerald-500/20 text-emerald-300' : 'bg-white/10 text-white/40'
                }`}>{m.status}</span>
              </div>
              <div className="text-sm font-medium mb-1">{m.subject || '(no subject)'}</div>
              <div className="text-xs text-white/50 mb-2 whitespace-pre-wrap">{m.content}</div>
              <div className="flex items-center gap-3 text-[10px] text-white/25">
                <span>From: {m.from_agent}</span>
                <span>To: {m.to_agent ?? (m.department ? `${m.department} dept` : 'All')}</span>
                {m.task_id && <span>Task: {m.task_id}</span>}
                {m.created_at && <span>{new Date(m.created_at * 1000).toLocaleString()}</span>}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
