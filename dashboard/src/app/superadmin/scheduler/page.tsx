'use client';

import { useState, useEffect, useCallback } from 'react';
import { Calendar, Plus, RefreshCw, Trash2, Pause, Play, Clock, CheckCircle } from 'lucide-react';
import { superadminApi } from '@/lib/api';
import { useTranslation } from '@/lib/i18n';

const INTERVALS = ['every_5min', 'every_15min', 'every_30min', 'hourly', 'every_4h', 'every_8h', 'daily', 'weekly'];

export default function SchedulerPage() {
  const { t } = useTranslation();
  const [jobs, setJobs] = useState<any[]>([]);
  const [status, setStatus] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [creating, setCreating] = useState(false);

  // Create form
  const [agentId, setAgentId] = useState('');
  const [title, setTitle] = useState('');
  const [prompt, setPrompt] = useState('');
  const [interval, setInterval] = useState('daily');
  const [category, setCategory] = useState('general');

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [j, s] = await Promise.allSettled([
        superadminApi.getScheduledJobs(),
        superadminApi.getSchedulerStatus(),
      ]);
      if (j.status === 'fulfilled') setJobs((j.value as any).jobs || []);
      if (s.status === 'fulfilled') setStatus(s.value);
    } catch { /* silent */ }
    setLoading(false);
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  const handleCreate = async () => {
    if (!agentId.trim() || !title.trim() || !prompt.trim()) return;
    setCreating(true);
    try {
      await superadminApi.createScheduledJob(agentId, title, prompt, interval, category);
      setShowCreate(false);
      setAgentId(''); setTitle(''); setPrompt('');
      await loadData();
    } catch { /* silent */ }
    setCreating(false);
  };

  const handleToggle = async (jobId: string, enabled: boolean) => {
    try {
      await superadminApi.updateScheduledJob(jobId, { enabled: !enabled });
      await loadData();
    } catch { /* silent */ }
  };

  const handleDelete = async (jobId: string) => {
    try {
      await superadminApi.deleteScheduledJob(jobId);
      await loadData();
    } catch { /* silent */ }
  };

  const formatInterval = (i: string) => i.replace(/_/g, ' ').replace('every ', '');

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-sky-500/20 flex items-center justify-center">
            <Calendar className="w-5 h-5 text-sky-400" />
          </div>
          <div>
            <h1 className="text-xl font-bold">{t('scheduler.title')}</h1>
            <p className="text-xs text-white/40">{t('scheduler.subtitle')}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => setShowCreate(!showCreate)}
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-sky-500/20 text-xs text-sky-300 hover:bg-sky-500/30 transition">
            <Plus className="w-3.5 h-3.5" /> New Job
          </button>
          <button onClick={loadData} disabled={loading}
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg glass text-xs text-white/60 hover:text-white transition">
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} /> {t('common.refresh')}
          </button>
        </div>
      </div>

      {/* Status KPIs */}
      {status && (
        <div className="grid grid-cols-4 gap-4">
          <div className="glass rounded-xl p-4 border border-white/5">
            <div className="text-xs text-white/40 mb-1">Scheduler</div>
            <div className={`text-lg font-bold ${status.running ? 'text-green-400' : 'text-red-400'}`}>
              {status.running ? t('common.running') : t('common.stopped')}
            </div>
          </div>
          <div className="glass rounded-xl p-4 border border-white/5">
            <div className="text-xs text-white/40 mb-1">Total Jobs</div>
            <div className="text-2xl font-bold">{status.total_jobs}</div>
          </div>
          <div className="glass rounded-xl p-4 border border-white/5">
            <div className="text-xs text-white/40 mb-1">Enabled</div>
            <div className="text-2xl font-bold text-green-400">{status.enabled_jobs}</div>
          </div>
          <div className="glass rounded-xl p-4 border border-white/5">
            <div className="text-xs text-white/40 mb-1">Intervals</div>
            <div className="text-lg font-bold">{status.available_intervals?.length || 0}</div>
          </div>
        </div>
      )}

      {/* Create Form */}
      {showCreate && (
        <div className="glass rounded-xl p-5 border border-sky-500/20 space-y-4">
          <h3 className="text-sm font-medium text-sky-300">Schedule New Job</h3>
          <div className="grid grid-cols-3 gap-4">
            <div>
              <label className="text-xs text-white/40 block mb-1">Agent ID</label>
              <input value={agentId} onChange={e => setAgentId(e.target.value)}
                placeholder="CDB-ENG-001"
                className="w-full glass rounded-lg px-3 py-2 text-sm bg-white/5 border border-white/10 focus:border-sky-500/50 focus:outline-none" />
            </div>
            <div>
              <label className="text-xs text-white/40 block mb-1">Title</label>
              <input value={title} onChange={e => setTitle(e.target.value)}
                placeholder="Daily health check"
                className="w-full glass rounded-lg px-3 py-2 text-sm bg-white/5 border border-white/10 focus:border-sky-500/50 focus:outline-none" />
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="text-xs text-white/40 block mb-1">Interval</label>
                <select value={interval} onChange={e => setInterval(e.target.value)}
                  className="w-full glass rounded-lg px-3 py-2 text-sm bg-white/5 border border-white/10 focus:border-sky-500/50 focus:outline-none">
                  {INTERVALS.map(i => <option key={i} value={i}>{formatInterval(i)}</option>)}
                </select>
              </div>
              <div>
                <label className="text-xs text-white/40 block mb-1">Category</label>
                <input value={category} onChange={e => setCategory(e.target.value)}
                  className="w-full glass rounded-lg px-3 py-2 text-sm bg-white/5 border border-white/10 focus:border-sky-500/50 focus:outline-none" />
              </div>
            </div>
          </div>
          <div>
            <label className="text-xs text-white/40 block mb-1">Prompt</label>
            <textarea value={prompt} onChange={e => setPrompt(e.target.value)} rows={3}
              placeholder="What should the agent do on each run?"
              className="w-full glass rounded-lg px-3 py-2 text-sm bg-white/5 border border-white/10 focus:border-sky-500/50 focus:outline-none" />
          </div>
          <button onClick={handleCreate} disabled={creating || !agentId.trim() || !title.trim()}
            className="px-4 py-2 rounded-lg bg-sky-500/20 text-sky-300 text-xs font-medium hover:bg-sky-500/30 transition disabled:opacity-50">
            {creating ? 'Creating...' : 'Schedule Job'}
          </button>
        </div>
      )}

      {/* Jobs List */}
      {jobs.length === 0 ? (
        <div className="glass rounded-xl p-8 border border-white/5 text-center">
          <p className="text-sm text-white/30">{t('common.noData')}</p>
        </div>
      ) : (
        <div className="glass rounded-xl border border-white/5 overflow-hidden">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-white/30 border-b border-white/5">
                <th className="text-left py-3 px-4 font-medium">Status</th>
                <th className="text-left py-3 px-4 font-medium">Title</th>
                <th className="text-left py-3 px-4 font-medium">Agent</th>
                <th className="text-left py-3 px-4 font-medium">Interval</th>
                <th className="text-left py-3 px-4 font-medium">Runs</th>
                <th className="text-left py-3 px-4 font-medium">Last Run</th>
                <th className="text-left py-3 px-4 font-medium">Next Run</th>
                <th className="text-right py-3 px-4 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((job: any) => (
                <tr key={job.job_id} className="border-b border-white/5 hover:bg-white/5">
                  <td className="py-3 px-4">
                    {job.enabled
                      ? <CheckCircle className="w-3.5 h-3.5 text-green-400" />
                      : <Pause className="w-3.5 h-3.5 text-white/30" />}
                  </td>
                  <td className="py-3 px-4">
                    <div className="font-medium">{job.title}</div>
                    <div className="text-[10px] text-white/20 truncate max-w-[200px]">{job.prompt}</div>
                  </td>
                  <td className="py-3 px-4 text-white/50">{job.agent_id}</td>
                  <td className="py-3 px-4">
                    <span className="px-1.5 py-0.5 rounded bg-sky-500/10 text-sky-400">{formatInterval(job.interval)}</span>
                  </td>
                  <td className="py-3 px-4 text-white/50">{job.run_count}</td>
                  <td className="py-3 px-4 text-white/40">
                    {job.last_run ? new Date(job.last_run * 1000).toLocaleString() : 'Never'}
                  </td>
                  <td className="py-3 px-4 text-white/40">
                    {job.next_run ? new Date(job.next_run * 1000).toLocaleString() : 'Pending'}
                  </td>
                  <td className="py-3 px-4 text-right">
                    <div className="flex items-center justify-end gap-1">
                      <button onClick={() => handleToggle(job.job_id, job.enabled)}
                        className="p-1 rounded hover:bg-white/10 transition"
                        title={job.enabled ? 'Disable' : 'Enable'}>
                        {job.enabled
                          ? <Pause className="w-3.5 h-3.5 text-amber-400" />
                          : <Play className="w-3.5 h-3.5 text-green-400" />}
                      </button>
                      <button onClick={() => handleDelete(job.job_id)}
                        className="p-1 rounded hover:bg-red-500/10 transition">
                        <Trash2 className="w-3.5 h-3.5 text-red-400/60 hover:text-red-400" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
