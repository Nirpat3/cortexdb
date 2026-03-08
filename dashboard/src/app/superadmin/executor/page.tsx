'use client';

import { useEffect, useState, useCallback } from 'react';
import { Zap, Play, RefreshCw, Clock, CheckCircle2, XCircle, Loader2 } from 'lucide-react';
import { superadminApi } from '@/lib/api';
import { useTranslation } from '@/lib/i18n';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type D = Record<string, any>;

const STATUS_COLORS: Record<string, string> = {
  pending: 'bg-white/10 text-white/40',
  in_progress: 'bg-blue-500/20 text-blue-300',
  review: 'bg-purple-500/20 text-purple-300',
  completed: 'bg-emerald-500/20 text-emerald-300',
  failed: 'bg-red-500/20 text-red-300',
};

export default function ExecutorPage() {
  const { t } = useTranslation();
  const [executorStatus, setExecutorStatus] = useState<D>({});
  const [tasks, setTasks] = useState<D[]>([]);
  const [executing, setExecuting] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [eRes, tRes] = await Promise.all([
        superadminApi.executorStatus().catch(() => null),
        superadminApi.getTasks().catch(() => null),
      ]);
      if (eRes) setExecutorStatus(eRes);
      if (tRes) setTasks((tRes as D).tasks ?? []);
    } catch { /* silent */ }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const handleExecute = async (taskId: string) => {
    setExecuting(taskId);
    try {
      await superadminApi.executeTask(taskId);
      await refresh();
    } catch { /* silent */ }
    setExecuting(null);
  };

  const handleExecutePending = async () => {
    try {
      const result = await superadminApi.executePending();
      alert(`Queued ${(result as D).queued ?? 0} tasks for execution`);
      await refresh();
    } catch { /* silent */ }
  };

  const assignedTasks = tasks.filter((tk: D) => tk.assigned_to);
  const pendingAssigned = assignedTasks.filter((tk: D) => tk.status === 'pending' || tk.status === 'in_progress');
  const completedTasks = assignedTasks.filter((tk: D) => tk.status === 'completed' || tk.status === 'review');
  const failedTasks = assignedTasks.filter((tk: D) => tk.status === 'failed');

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold mb-1 flex items-center gap-2">
            <Zap className="w-6 h-6 text-amber-400" /> {t('executor.title')}
          </h1>
          <p className="text-sm text-white/40">{t('executor.subtitle')}</p>
        </div>
        <div className="flex gap-2">
          <button onClick={refresh} className="glass px-3 py-2 rounded-lg text-xs text-white/60 hover:text-white/90">
            <RefreshCw className="w-3.5 h-3.5" />
          </button>
          <button onClick={handleExecutePending}
            className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-amber-500/20 text-amber-300 hover:bg-amber-500/30 text-sm">
            <Play className="w-4 h-4" /> Execute All Pending
          </button>
        </div>
      </div>

      {/* Executor Status */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
        <div className="glass rounded-xl p-3">
          <div className="text-xs text-white/40">Engine</div>
          <div className={`text-lg font-bold ${executorStatus.running ? 'text-emerald-400' : 'text-red-400'}`}>
            {executorStatus.running ? t('common.running') : t('common.stopped')}
          </div>
        </div>
        <div className="glass rounded-xl p-3">
          <div className="text-xs text-white/40">Queue Size</div>
          <div className="text-2xl font-bold">{executorStatus.queue_size ?? 0}</div>
        </div>
        <div className="glass rounded-xl p-3">
          <div className="text-xs text-white/40">Active Tasks</div>
          <div className="text-2xl font-bold text-blue-400">{(executorStatus.active_tasks ?? []).length}</div>
        </div>
        <div className="glass rounded-xl p-3">
          <div className="text-xs text-white/40">Max Concurrent</div>
          <div className="text-2xl font-bold">{executorStatus.max_concurrent ?? 3}</div>
        </div>
      </div>

      {/* Active Executions */}
      {(executorStatus.active_tasks ?? []).length > 0 && (
        <div className="glass rounded-xl p-4 mb-6">
          <div className="text-sm font-semibold mb-2 flex items-center gap-2">
            <Loader2 className="w-4 h-4 animate-spin text-blue-400" /> Currently Executing
          </div>
          <div className="flex flex-wrap gap-2">
            {(executorStatus.active_tasks ?? []).map((tid: string) => (
              <span key={tid} className="text-xs px-2 py-1 rounded-lg bg-blue-500/20 text-blue-300 font-mono">{tid}</span>
            ))}
          </div>
        </div>
      )}

      {/* Task Queue */}
      <div className="space-y-6">
        {/* Pending / In Progress */}
        <div>
          <h2 className="text-lg font-semibold mb-3 flex items-center gap-2">
            <Clock className="w-5 h-5 text-amber-400" /> Pending Execution ({pendingAssigned.length})
          </h2>
          <div className="space-y-2">
            {pendingAssigned.length === 0 && (
              <div className="text-center py-6 text-white/30 text-sm">{t('common.noData')}</div>
            )}
            {pendingAssigned.map((tk: D) => (
              <div key={tk.task_id} className="glass rounded-xl p-4 flex items-center justify-between">
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-xs font-mono text-white/30">{tk.task_id}</span>
                    <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${STATUS_COLORS[tk.status] ?? ''}`}>{tk.status}</span>
                  </div>
                  <div className="text-sm font-medium">{tk.title}</div>
                  <div className="text-[10px] text-white/30">
                    Agent: {tk.assigned_to} | Priority: {tk.priority} | Category: {tk.category}
                  </div>
                </div>
                <button onClick={() => handleExecute(tk.task_id)}
                  disabled={executing === tk.task_id}
                  className="px-3 py-1.5 rounded-lg text-xs bg-amber-500/20 text-amber-300 hover:bg-amber-500/30 disabled:opacity-30 flex items-center gap-1.5">
                  {executing === tk.task_id ? <Loader2 className="w-3 h-3 animate-spin" /> : <Play className="w-3 h-3" />}
                  Execute
                </button>
              </div>
            ))}
          </div>
        </div>

        {/* Completed */}
        <div>
          <h2 className="text-lg font-semibold mb-3 flex items-center gap-2">
            <CheckCircle2 className="w-5 h-5 text-emerald-400" /> Completed ({completedTasks.length})
          </h2>
          <div className="space-y-2">
            {completedTasks.map((tk: D) => (
              <div key={tk.task_id} className="glass rounded-xl p-4">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-xs font-mono text-white/30">{tk.task_id}</span>
                  <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${STATUS_COLORS[tk.status] ?? ''}`}>{tk.status}</span>
                </div>
                <div className="text-sm font-medium mb-1">{tk.title}</div>
                {tk.result && (
                  <div className="glass rounded-lg p-2 mt-2 text-xs text-white/60 whitespace-pre-wrap max-h-40 overflow-y-auto">
                    {tk.result}
                  </div>
                )}
                <div className="text-[10px] text-white/25 mt-1">
                  Agent: {tk.assigned_to}
                  {tk.metadata?.elapsed_ms && ` | ${tk.metadata.elapsed_ms.toFixed(0)}ms`}
                  {tk.metadata?.llm_provider && ` | ${tk.metadata.llm_provider}:${tk.metadata.llm_model}`}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Failed */}
        {failedTasks.length > 0 && (
          <div>
            <h2 className="text-lg font-semibold mb-3 flex items-center gap-2">
              <XCircle className="w-5 h-5 text-red-400" /> Failed ({failedTasks.length})
            </h2>
            <div className="space-y-2">
              {failedTasks.map((tk: D) => (
                <div key={tk.task_id} className="glass rounded-xl p-4 border border-red-500/20">
                  <div className="flex items-center justify-between mb-1">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-mono text-white/30">{tk.task_id}</span>
                      <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-red-500/20 text-red-300">failed</span>
                    </div>
                    <button onClick={() => handleExecute(tk.task_id)}
                      disabled={executing === tk.task_id}
                      className="px-3 py-1.5 rounded-lg text-xs bg-amber-500/20 text-amber-300 hover:bg-amber-500/30 disabled:opacity-30">
                      Retry
                    </button>
                  </div>
                  <div className="text-sm font-medium">{tk.title}</div>
                  {tk.result && <div className="text-xs text-red-400/60 mt-1">{tk.result}</div>}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
