'use client';

import { useEffect, useState, useCallback } from 'react';
import { ClipboardList, Plus, RefreshCw, Play, Loader2 } from 'lucide-react';
import { superadminApi } from '@/lib/api';
import { useTranslation } from '@/lib/i18n';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type D = Record<string, any>;

const PRIORITIES = ['critical', 'high', 'medium', 'low'];
const CATEGORIES = ['bug', 'feature', 'enhancement', 'qa', 'docs', 'security', 'ops', 'general'];
const STATUSES = ['pending', 'awaiting_approval', 'approved', 'in_progress', 'review', 'completed', 'failed', 'rejected'];

const PRIORITY_COLORS: Record<string, string> = {
  critical: 'bg-red-500/20 text-red-300', high: 'bg-amber-500/20 text-amber-300',
  medium: 'bg-blue-500/20 text-blue-300', low: 'bg-white/10 text-white/40',
};

const STATUS_COLORS: Record<string, string> = {
  pending: 'bg-white/10 text-white/40', awaiting_approval: 'bg-amber-500/20 text-amber-300',
  approved: 'bg-cyan-500/20 text-cyan-300', in_progress: 'bg-blue-500/20 text-blue-300',
  review: 'bg-purple-500/20 text-purple-300', completed: 'bg-emerald-500/20 text-emerald-300',
  failed: 'bg-red-500/20 text-red-300', rejected: 'bg-red-500/20 text-red-400',
};

export default function TasksPage() {
  const { t } = useTranslation();
  const [tasks, setTasks] = useState<D[]>([]);
  const [agents, setAgents] = useState<D[]>([]);
  const [showCreate, setShowCreate] = useState(false);
  const [filter, setFilter] = useState('all');
  const [form, setForm] = useState({ title: '', description: '', assigned_to: '', priority: 'medium', category: 'general', microservice: '', auto_execute: false });
  const [executing, setExecuting] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [tasksRes, agentsRes] = await Promise.all([
        superadminApi.getTasks().catch(() => null),
        superadminApi.getTeam().catch(() => null),
      ]);
      if (tasksRes) setTasks((tasksRes as D).tasks ?? []);
      if (agentsRes) setAgents((agentsRes as D).agents ?? []);
    } catch { /* silent */ }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const handleCreate = async () => {
    if (!form.title) return;
    try {
      await superadminApi.createTask(form);
      setShowCreate(false);
      setForm({ title: '', description: '', assigned_to: '', priority: 'medium', category: 'general', microservice: '', auto_execute: false });
      refresh();
    } catch { /* silent */ }
  };

  const handleExecute = async (taskId: string) => {
    setExecuting(taskId);
    try {
      await superadminApi.executeTask(taskId);
      refresh();
    } catch { /* silent */ }
    setExecuting(null);
  };

  const handleStatusChange = async (taskId: string, status: string) => {
    try {
      await superadminApi.updateTask(taskId, { status });
      refresh();
    } catch { /* silent */ }
  };

  const filtered = filter === 'all' ? tasks : tasks.filter((tk: D) => tk.status === filter);

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold mb-1 flex items-center gap-2">
            <ClipboardList className="w-6 h-6 text-amber-400" /> {t('taskPage.title')}
          </h1>
          <p className="text-sm text-white/40">{t('taskPage.subtitle')}</p>
        </div>
        <div className="flex gap-2">
          <button onClick={refresh} className="glass px-3 py-2 rounded-lg text-xs text-white/60 hover:text-white/90">
            <RefreshCw className="w-3.5 h-3.5" />
          </button>
          <button onClick={() => setShowCreate(!showCreate)}
            className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-amber-500/20 text-amber-300 hover:bg-amber-500/30 text-sm">
            <Plus className="w-4 h-4" /> {t('taskPage.newTask')}
          </button>
        </div>
      </div>

      {/* Create Task Form */}
      {showCreate && (
        <div className="glass rounded-xl p-4 mb-6 space-y-3">
          <div className="text-sm font-semibold">{t('taskPage.createTask')}</div>
          <input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })}
            placeholder={t('taskPage.taskTitlePlaceholder')} className="w-full glass rounded-lg px-3 py-2 text-sm bg-white/5 border border-white/10" />
          <textarea value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })}
            placeholder={t('taskPage.descriptionPlaceholder')} rows={3} className="w-full glass rounded-lg px-3 py-2 text-sm bg-white/5 border border-white/10 resize-none" />
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            <select value={form.assigned_to} onChange={(e) => setForm({ ...form, assigned_to: e.target.value })}
              className="glass rounded-lg px-3 py-2 text-xs bg-white/5 border border-white/10">
              <option value="">{t('taskPage.unassigned')}</option>
              {agents.map((a: D) => <option key={a.agent_id} value={a.agent_id}>{a.name} ({a.agent_id})</option>)}
            </select>
            <select value={form.priority} onChange={(e) => setForm({ ...form, priority: e.target.value })}
              className="glass rounded-lg px-3 py-2 text-xs bg-white/5 border border-white/10">
              {PRIORITIES.map((p) => <option key={p} value={p}>{p}</option>)}
            </select>
            <select value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}
              className="glass rounded-lg px-3 py-2 text-xs bg-white/5 border border-white/10">
              {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
            <input value={form.microservice} onChange={(e) => setForm({ ...form, microservice: e.target.value })}
              placeholder={t('taskPage.microservicePlaceholder')} className="glass rounded-lg px-3 py-2 text-xs bg-white/5 border border-white/10" />
          </div>
          <div className="flex items-center gap-4">
            <label className="flex items-center gap-2 text-xs text-white/50 cursor-pointer">
              <input type="checkbox" checked={form.auto_execute}
                onChange={(e) => setForm({ ...form, auto_execute: e.target.checked })}
                className="rounded" />
              {t('taskPage.autoExecute')}
            </label>
            <div className="flex gap-2">
              <button onClick={handleCreate} className="px-4 py-2 rounded-lg text-sm bg-emerald-500/20 text-emerald-300 hover:bg-emerald-500/30">{t('common.create')}</button>
              <button onClick={() => setShowCreate(false)} className="px-4 py-2 rounded-lg text-sm bg-white/5 text-white/40 hover:bg-white/10">{t('common.cancel')}</button>
            </div>
          </div>
        </div>
      )}

      {/* Status Filter */}
      <div className="flex gap-2 mb-4 flex-wrap">
        {['all', ...STATUSES].map((s) => (
          <button key={s} onClick={() => setFilter(s)}
            className={`px-3 py-1 rounded-lg text-xs capitalize transition ${filter === s ? 'glass-heavy text-white' : 'glass text-white/50 hover:text-white/80'}`}>
            {s === 'all' ? t('common.all') : s.replace('_', ' ')}
          </button>
        ))}
      </div>

      {/* Task List */}
      <div className="space-y-2">
        {filtered.length === 0 && (
          <div className="text-center py-12 text-white/30">{t('taskPage.noTasks')}</div>
        )}
        {filtered.map((task: D) => {
          const assignee = agents.find((a: D) => a.agent_id === task.assigned_to);
          return (
            <div key={task.task_id} className="glass rounded-xl p-4">
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-mono text-white/30">{task.task_id}</span>
                  <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${PRIORITY_COLORS[task.priority] ?? ''}`}>{task.priority}</span>
                  <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${STATUS_COLORS[task.status] ?? ''}`}>{task.status}</span>
                  <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-white/5 text-white/40">{task.category}</span>
                </div>
                <div className="flex items-center gap-2">
                  {task.assigned_to && (task.status === 'pending' || task.status === 'in_progress' || task.status === 'failed') && (
                    <button onClick={() => handleExecute(task.task_id)} disabled={executing === task.task_id}
                      className="text-[10px] glass rounded px-2 py-1 bg-amber-500/10 text-amber-300 hover:bg-amber-500/20 disabled:opacity-30 flex items-center gap-1">
                      {executing === task.task_id ? <Loader2 className="w-3 h-3 animate-spin" /> : <Play className="w-3 h-3" />}
                      {t('common.execute')}
                    </button>
                  )}
                  <select value={task.status} onChange={(e) => handleStatusChange(task.task_id, e.target.value)}
                    className="text-[10px] glass rounded px-2 py-1 bg-white/5 border border-white/10">
                    {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
                  </select>
                </div>
              </div>
              <div className="text-sm font-medium mb-1">{task.title}</div>
              {task.description && <div className="text-xs text-white/40 mb-2">{task.description}</div>}
              {task.result && (
                <div className="glass rounded-lg p-2 mb-2 text-xs text-white/60 whitespace-pre-wrap max-h-32 overflow-y-auto">
                  {task.result}
                </div>
              )}
              <div className="flex items-center gap-3 text-[10px] text-white/25">
                {assignee && <span>{t('taskPage.assigned')} {assignee.name} ({task.assigned_to})</span>}
                {task.microservice && <span>{t('taskPage.service')} {task.microservice}</span>}
                {task.created_at && <span>{new Date(task.created_at * 1000).toLocaleString()}</span>}
                {task.metadata?.elapsed_ms && <span>{task.metadata.elapsed_ms.toFixed(0)}ms</span>}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
