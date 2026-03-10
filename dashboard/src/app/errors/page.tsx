'use client';

import { useState, useEffect, useCallback } from 'react';
import { Bug, AlertTriangle, Filter, XCircle, AlertOctagon, CheckCircle2, RefreshCw } from 'lucide-react';
import { AppShell } from '@/components/shell/AppShell';
import { GlassCard } from '@/components/shared/GlassCard';
import { MetricBadge } from '@/components/shared/MetricBadge';
import { api } from '@/lib/api';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type D = Record<string, any>;

export default function ErrorsPage() {
  const [errors, setErrors] = useState<D[]>([]);
  const [summary, setSummary] = useState<D | null>(null);
  const [filter, setFilter] = useState<string>('all');
  const [expanded, setExpanded] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const level = filter === 'all' ? undefined : filter;
      const [e, s] = await Promise.all([
        api.getErrors(level).catch(() => null),
        api.errorSummary().catch(() => null),
      ]);
      if (e) setErrors((e as D).errors ?? []);
      if (s) setSummary(s);
    } catch { /* silent */ }
  }, [filter]);

  useEffect(() => {
    refresh();
    const iv = setInterval(refresh, 10000);
    return () => clearInterval(iv);
  }, [refresh]);

  const handleResolve = async (errorId: string) => {
    try {
      await api.resolveError(errorId, 'Resolved via dashboard');
      refresh();
    } catch { /* silent */ }
  };

  const levelIcon = (level: string) => {
    if (level === 'critical') return <AlertOctagon className="w-4 h-4 text-red-400" />;
    if (level === 'error') return <XCircle className="w-4 h-4 text-amber-400" />;
    return <AlertTriangle className="w-4 h-4 text-yellow-400" />;
  };

  const levelColor = (level: string) =>
    level === 'critical' ? 'border-red-500/30' : level === 'error' ? 'border-amber-500/20' : 'border-yellow-500/10';

  return (
    <AppShell title="Error Tracking" icon={Bug} color="#EF4444">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-xl font-semibold mb-1">Error Tracking</h2>
          <p className="text-sm text-white/40">Real-time error monitoring from Error Tracking Agent</p>
        </div>
        <button onClick={refresh} className="glass px-3 py-1.5 rounded-lg text-xs text-white/60 hover:text-white/90 transition">
          <RefreshCw className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* Summary */}
      {summary && (
        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-3 mb-6">
          <GlassCard><MetricBadge label="Total" value={String(summary.total_errors)} color="#6366F1" /></GlassCard>
          <GlassCard><MetricBadge label="Unresolved" value={String(summary.unresolved)} color="#EF4444" /></GlassCard>
          <GlassCard><MetricBadge label="Resolved" value={String(summary.resolved)} color="#34D399" /></GlassCard>
          <GlassCard><MetricBadge label="Last Hour" value={String(summary.last_hour)} color="#F59E0B" /></GlassCard>
          <GlassCard><MetricBadge label="Occurrences" value={String(summary.total_occurrences)} color="#8B5CF6" /></GlassCard>
          <GlassCard><MetricBadge label="Affected Users" value={String(summary.affected_users)} color="#EC4899" /></GlassCard>
        </div>
      )}

      {/* By Level + Service */}
      {summary && (
        <div className="grid grid-cols-2 gap-4 mb-6">
          <GlassCard>
            <div className="text-xs text-white/40 mb-2">By Level</div>
            <div className="space-y-1">
              {Object.entries(summary.by_level ?? {}).map(([level, count]) => (
                <div key={level} className="flex justify-between text-sm">
                  <span className="capitalize">{level}</span>
                  <span className="font-mono">{String(count)}</span>
                </div>
              ))}
            </div>
          </GlassCard>
          <GlassCard>
            <div className="text-xs text-white/40 mb-2">By Service</div>
            <div className="space-y-1">
              {Object.entries(summary.by_service ?? {}).map(([svc, count]) => (
                <div key={svc} className="flex justify-between text-sm">
                  <span>{svc}</span>
                  <span className="font-mono">{String(count)}</span>
                </div>
              ))}
            </div>
          </GlassCard>
        </div>
      )}

      {/* Filter */}
      <div className="flex items-center gap-2 mb-4">
        <Filter className="w-4 h-4 text-white/40" />
        {['all', 'critical', 'error', 'warning'].map((f) => (
          <button key={f} onClick={() => setFilter(f)}
            className={`px-3 py-1 rounded-lg text-xs capitalize transition ${filter === f ? 'glass-heavy text-white' : 'glass text-white/50 hover:text-white/80'}`}>
            {f}
          </button>
        ))}
      </div>

      {/* Error List */}
      <div className="space-y-2">
        {errors.map((e: D) => (
          <GlassCard key={e.error_id} className={`py-3 border ${levelColor(e.level)} cursor-pointer`}
            onClick={() => setExpanded(expanded === e.error_id ? null : e.error_id)}>
            <div className="flex items-center justify-between mb-1">
              <div className="flex items-center gap-2">
                {levelIcon(e.level)}
                <span className="text-xs font-mono text-white/40">{e.error_id}</span>
                <span className="text-xs text-white/30">{e.service}</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-xs text-white/40">x{e.count}</span>
                {e.resolved ? (
                  <span className="text-xs px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-300">resolved</span>
                ) : (
                  <button onClick={(ev) => { ev.stopPropagation(); handleResolve(e.error_id); }}
                    className="text-xs px-1.5 py-0.5 rounded bg-blue-500/20 text-blue-300 hover:bg-blue-500/30">
                    resolve
                  </button>
                )}
              </div>
            </div>
            <div className="text-sm text-white/70">{e.message}</div>
            {e.affected_users > 0 && (
              <div className="text-[10px] text-white/30 mt-1">{e.affected_users} users affected</div>
            )}
            {expanded === e.error_id && (
              <div className="mt-3 space-y-2">
                <div className="bg-black/30 rounded-lg p-3 text-xs font-mono text-white/50 whitespace-pre-wrap">
                  {e.stack_trace}
                </div>
                {e.resolution && (
                  <div className="flex items-center gap-2 text-xs text-emerald-400">
                    <CheckCircle2 className="w-3 h-3" /> {e.resolution}
                  </div>
                )}
                <div className="text-[10px] text-white/25">
                  First seen: {e.first_seen ? new Date(e.first_seen * 1000).toLocaleString() : '-'} ·
                  Last seen: {e.last_seen ? new Date(e.last_seen * 1000).toLocaleString() : '-'}
                </div>
              </div>
            )}
          </GlassCard>
        ))}
      </div>
    </AppShell>
  );
}
