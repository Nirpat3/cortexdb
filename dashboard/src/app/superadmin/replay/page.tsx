'use client';

import { useEffect, useState, useCallback } from 'react';
import { Play, Clock, ChevronRight, BarChart3, RefreshCw, Activity, ChevronDown } from 'lucide-react';
import { superadminApi } from '@/lib/api';
import { useTranslation } from '@/lib/i18n';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type D = Record<string, any>;

type Tab = 'traces' | 'stats';

export default function ReplayPage() {
  const { t } = useTranslation();
  const [tab, setTab] = useState<Tab>('traces');
  const [traces, setTraces] = useState<D[]>([]);
  const [activeTraces, setActiveTraces] = useState<D>({ count: 0 });
  const [stepStats, setStepStats] = useState<D>({});
  const [selectedTrace, setSelectedTrace] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const [t, a, s] = await Promise.all([
        superadminApi.getRecentTraces(20).catch(() => ({ traces: [] })),
        superadminApi.getActiveTraces().catch(() => ({ active_traces: {}, count: 0 })),
        superadminApi.getReplayStats().catch(() => ({ step_stats: {} })),
      ]);
      setTraces((t as D).traces ?? []);
      setActiveTraces(a as D);
      setStepStats((s as D).step_stats ?? {});
    } catch { /* silent */ }
    setLoading(false);
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const fmtTime = (ts: string) => {
    if (!ts) return '-';
    const d = new Date(ts);
    return d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit' });
  };

  const fmtMs = (ms: number) => ms >= 1000 ? `${(ms / 1000).toFixed(2)}s` : `${Math.round(ms)}ms`;

  const summarize = (obj: D) => {
    if (!obj || typeof obj !== 'object') return '-';
    const keys = Object.keys(obj);
    if (keys.length === 0) return '-';
    return keys.slice(0, 3).join(', ') + (keys.length > 3 ? ` +${keys.length - 3}` : '');
  };

  const sortedStats = Object.entries(stepStats)
    .map(([name, s]) => ({ name, ...(s as D) }) as D)
    .sort((a, b) => (b.count ?? 0) - (a.count ?? 0));

  const tabs: { key: Tab; label: string; icon: typeof Play }[] = [
    { key: 'traces', label: 'Recent Traces', icon: Clock },
    { key: 'stats', label: 'Step Stats', icon: BarChart3 },
  ];

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold mb-1 flex items-center gap-2">
            <Play className="w-6 h-6 text-violet-400" /> {t('replay.title')}
          </h1>
          <p className="text-sm text-white/40">{t('replay.subtitle')}</p>
        </div>
        <button onClick={refresh} className="glass px-3 py-2 rounded-lg text-xs text-white/60 hover:text-white/90">
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {/* Tabs */}
      <div className="flex gap-2 mb-6">
        {tabs.map(t => (
          <button key={t.key} onClick={() => setTab(t.key)}
            className={`flex items-center gap-1.5 px-4 py-2 rounded-xl text-sm transition-colors ${
              tab === t.key ? 'bg-violet-500/20 text-violet-300' : 'bg-white/5 text-white/40 hover:text-white/70'
            }`}>
            <t.icon className="w-4 h-4" /> {t.label}
          </button>
        ))}
      </div>

      {tab === 'traces' && (
        <div className="space-y-4">
          {/* Active Traces */}
          {activeTraces.count > 0 && (
            <div className="bg-white/5 border border-violet-500/30 rounded-xl p-4 mb-2">
              <div className="text-sm font-semibold mb-2 flex items-center gap-2">
                <Activity className="w-4 h-4 text-violet-400 animate-pulse" /> Active Traces ({activeTraces.count})
              </div>
              <div className="flex flex-wrap gap-2">
                {Object.keys(activeTraces.active_traces ?? {}).map((tid: string) => (
                  <span key={tid} className="text-xs px-2 py-1 rounded-lg bg-violet-500/20 text-violet-300 font-mono">{tid}</span>
                ))}
              </div>
            </div>
          )}

          {/* Trace List */}
          {traces.length === 0 && !loading && (
            <div className="text-center py-12 text-white/30 text-sm">{t('common.noData')}</div>
          )}
          {traces.map((trace: D) => {
            const isOpen = selectedTrace === trace.task_id;
            return (
              <div key={trace.task_id} className="bg-white/5 border border-white/10 rounded-xl overflow-hidden">
                <button onClick={() => setSelectedTrace(isOpen ? null : trace.task_id)}
                  className="w-full flex items-center justify-between p-4 text-left hover:bg-white/5 transition-colors">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-xs font-mono text-white/50">{trace.task_id}</span>
                      <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-blue-500/20 text-blue-300">
                        {trace.step_count} steps
                      </span>
                      <span className="text-[10px] text-white/30">{fmtMs(trace.total_ms)}</span>
                    </div>
                    <div className="text-xs text-white/40">
                      Agent: <span className="text-white/60 font-mono">{trace.agent_id}</span>
                      <span className="ml-3">{fmtTime(trace.started_at)}</span>
                    </div>
                  </div>
                  {isOpen
                    ? <ChevronDown className="w-4 h-4 text-white/30 shrink-0" />
                    : <ChevronRight className="w-4 h-4 text-white/30 shrink-0" />}
                </button>

                {/* Expanded Steps Timeline */}
                {isOpen && (
                  <div className="border-t border-white/10 px-4 py-3">
                    {(trace.steps ?? []).length === 0 && (
                      <div className="text-xs text-white/30 py-2">No steps recorded.</div>
                    )}
                    <div className="relative ml-3">
                      {(trace.steps ?? []).map((step: D, i: number) => {
                        const isLast = i === (trace.steps ?? []).length - 1;
                        return (
                          <div key={i} className="flex gap-3 relative">
                            {/* Timeline line + dot */}
                            <div className="flex flex-col items-center">
                              <div className="w-2.5 h-2.5 rounded-full bg-violet-400 border-2 border-violet-500/50 shrink-0 mt-1 z-10" />
                              {!isLast && <div className="w-px flex-1 bg-white/10" />}
                            </div>
                            {/* Step content */}
                            <div className={`flex-1 ${isLast ? 'pb-1' : 'pb-4'}`}>
                              <div className="flex items-center gap-2 mb-0.5">
                                <span className="text-[10px] text-white/30">#{step.index}</span>
                                <span className="text-xs font-semibold text-white/80">{step.step}</span>
                                <span className="text-[10px] text-amber-300/70">{fmtMs(step.duration_ms)}</span>
                              </div>
                              <div className="text-[10px] text-white/30 space-y-0.5">
                                <div>In: {summarize(step.inputs)}</div>
                                <div>Out: {summarize(step.outputs)}</div>
                              </div>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {tab === 'stats' && (
        <div className="bg-white/5 border border-white/10 rounded-xl overflow-hidden">
          {sortedStats.length === 0 ? (
            <div className="text-center py-12 text-white/30 text-sm">{t('common.noData')}</div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-white/10 text-left text-white/40">
                  <th className="px-4 py-3 font-medium">Step Name</th>
                  <th className="px-4 py-3 font-medium text-right">Count</th>
                  <th className="px-4 py-3 font-medium text-right">Avg</th>
                  <th className="px-4 py-3 font-medium text-right">Max</th>
                </tr>
              </thead>
              <tbody>
                {sortedStats.map(s => (
                  <tr key={s.name} className="border-b border-white/5 hover:bg-white/5 transition-colors">
                    <td className="px-4 py-2.5 font-mono text-xs text-white/70">{s.name}</td>
                    <td className="px-4 py-2.5 text-right text-white/60">{s.count}</td>
                    <td className="px-4 py-2.5 text-right text-amber-300/70">{fmtMs(s.avg_ms)}</td>
                    <td className="px-4 py-2.5 text-right text-red-300/70">{fmtMs(s.max_ms)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}
