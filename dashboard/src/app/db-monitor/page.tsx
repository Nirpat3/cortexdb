'use client';

import { useEffect, useState, useCallback } from 'react';
import { Database, Activity, Lock, AlertTriangle, Clock, RefreshCw, Layers } from 'lucide-react';
import { AppShell } from '@/components/shell/AppShell';
import { GlassCard } from '@/components/shared/GlassCard';
import { HealthRing } from '@/components/shared/HealthRing';
import { MetricBadge } from '@/components/shared/MetricBadge';
import { api } from '@/lib/api';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type D = Record<string, any>;

export default function DbMonitorPage() {
  const [summary, setSummary] = useState<D | null>(null);
  const [slowQueries, setSlowQueries] = useState<D[]>([]);
  const [locks, setLocks] = useState<D[]>([]);

  const refresh = useCallback(async () => {
    try {
      const [s, q, l] = await Promise.all([
        api.dbMonitorSummary().catch(() => null),
        api.dbSlowQueries().catch(() => null),
        api.dbLocks().catch(() => null),
      ]);
      if (s) setSummary(s);
      if (q) setSlowQueries((q as D).queries ?? []);
      if (l) setLocks((l as D).locks ?? []);
    } catch { /* silent */ }
  }, []);

  useEffect(() => {
    refresh();
    const iv = setInterval(refresh, 5000);
    return () => clearInterval(iv);
  }, [refresh]);

  const pool = summary?.connection_pool ?? {};
  const perf = summary?.performance ?? {};
  const issues = summary?.issues ?? {};
  const objects = summary?.objects ?? {};
  const repl = summary?.replication ?? {};

  return (
    <AppShell title="Database Monitor" icon={Database} color="#F59E0B">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-xl font-semibold mb-1">Database Monitor</h2>
          <p className="text-sm text-white/40">Real-time database performance from DB Monitor Agent</p>
        </div>
        <button onClick={refresh} className="glass px-3 py-1.5 rounded-lg text-xs text-white/60 hover:text-white/90 transition">
          <RefreshCw className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* Connection Pool */}
      <h3 className="text-base font-semibold mb-3 text-white/80"><Activity className="w-4 h-4 inline mr-1.5" />Connection Pool</h3>
      <div className="grid grid-cols-2 sm:grid-cols-[140px_1fr] gap-4 mb-6">
        <GlassCard className="flex flex-col items-center py-4">
          <HealthRing value={Math.round(pool.utilization_pct ?? 0)} size={80} strokeWidth={6} label="Pool" />
        </GlassCard>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <GlassCard><MetricBadge label="Max" value={String(pool.max_connections ?? '-')} color="#6366F1" /></GlassCard>
          <GlassCard><MetricBadge label="Active" value={String(pool.active ?? '-')} color="#3B82F6" /></GlassCard>
          <GlassCard><MetricBadge label="Idle" value={String(pool.idle ?? '-')} color="#34D399" /></GlassCard>
          <GlassCard><MetricBadge label="Waiting" value={String(pool.waiting ?? '-')} color={pool.waiting > 5 ? '#EF4444' : '#F59E0B'} /></GlassCard>
        </div>
      </div>

      {/* Performance */}
      <h3 className="text-base font-semibold mb-3 text-white/80"><Clock className="w-4 h-4 inline mr-1.5" />Performance</h3>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
        <GlassCard><MetricBadge label="Queries/sec" value={String(perf.avg_queries_per_second ?? '-')} color="#3B82F6" /></GlassCard>
        <GlassCard><MetricBadge label="Avg Latency" value={`${perf.avg_query_latency_ms ?? '-'} ms`} color="#F59E0B" /></GlassCard>
        <GlassCard><MetricBadge label="Cache Hit" value={perf.cache_hit_ratio ? `${(perf.cache_hit_ratio * 100).toFixed(1)}%` : '-'} color="#34D399" /></GlassCard>
        <GlassCard><MetricBadge label="TPS" value={String(perf.transactions_per_second ?? '-')} color="#8B5CF6" /></GlassCard>
      </div>

      {/* Database Objects */}
      <h3 className="text-base font-semibold mb-3 text-white/80"><Layers className="w-4 h-4 inline mr-1.5" />Database Objects</h3>
      <div className="grid grid-cols-3 sm:grid-cols-5 gap-3 mb-6">
        <GlassCard><MetricBadge label="Tables" value={String(objects.tables ?? '-')} color="#3B82F6" /></GlassCard>
        <GlassCard><MetricBadge label="Indexes" value={String(objects.indexes ?? '-')} color="#34D399" /></GlassCard>
        <GlassCard><MetricBadge label="Views" value={String(objects.views ?? '-')} color="#F59E0B" /></GlassCard>
        <GlassCard><MetricBadge label="Functions" value={String(objects.functions ?? '-')} color="#8B5CF6" /></GlassCard>
        <GlassCard><MetricBadge label="Triggers" value={String(objects.triggers ?? '-')} color="#EC4899" /></GlassCard>
      </div>

      {/* Replication */}
      <h3 className="text-base font-semibold mb-3 text-white/80"><Database className="w-4 h-4 inline mr-1.5" />Replication</h3>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
        <GlassCard><MetricBadge label="Mode" value={String(repl.mode ?? '-')} color="#6366F1" /></GlassCard>
        <GlassCard><MetricBadge label="Replicas" value={String(repl.replicas ?? '-')} color="#3B82F6" /></GlassCard>
        <GlassCard><MetricBadge label="Lag" value={`${repl.lag_ms ?? '-'} ms`} color={repl.lag_ms > 10 ? '#EF4444' : '#34D399'} /></GlassCard>
        <GlassCard><MetricBadge label="WAL Size" value={`${repl.wal_size_mb ?? '-'} MB`} color="#F59E0B" /></GlassCard>
      </div>

      {/* Issues */}
      <div className="grid grid-cols-3 gap-3 mb-6">
        <GlassCard className={issues.slow_queries > 0 ? 'border border-amber-500/30' : ''}>
          <MetricBadge label="Slow Queries" value={String(issues.slow_queries ?? 0)} color="#F59E0B" />
        </GlassCard>
        <GlassCard className={issues.active_locks > 0 ? 'border border-amber-500/30' : ''}>
          <MetricBadge label="Active Locks" value={String(issues.active_locks ?? 0)} color="#EF4444" />
        </GlassCard>
        <GlassCard>
          <MetricBadge label="Deadlocks (1h)" value={String(issues.deadlocks_last_hour ?? 0)} color="#8B5CF6" />
        </GlassCard>
      </div>

      {/* Slow Queries */}
      {slowQueries.length > 0 && (
        <>
          <h3 className="text-base font-semibold mb-3 text-white/80">
            <AlertTriangle className="w-4 h-4 inline mr-1.5" />Slow Queries
          </h3>
          <div className="space-y-2 mb-6">
            {slowQueries.slice(0, 8).map((q: D) => (
              <GlassCard key={q.query_id} className="py-2.5">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs font-mono text-white/50">{q.query_id}</span>
                  <div className="flex items-center gap-2">
                    <span className={`text-xs px-1.5 py-0.5 rounded ${q.status === 'running' ? 'bg-amber-500/20 text-amber-300' : 'bg-emerald-500/20 text-emerald-300'}`}>
                      {q.status}
                    </span>
                    <span className="text-xs text-red-300 font-mono">{q.duration_ms}ms</span>
                  </div>
                </div>
                <div className="text-xs font-mono text-white/60 truncate">{q.query}</div>
                <div className="text-[10px] text-white/30 mt-1">{q.table} · {q.operation} · {q.rows_affected?.toLocaleString()} rows</div>
              </GlassCard>
            ))}
          </div>
        </>
      )}

      {/* Locks */}
      {locks.length > 0 && (
        <>
          <h3 className="text-base font-semibold mb-3 text-white/80">
            <Lock className="w-4 h-4 inline mr-1.5" />Active Locks
          </h3>
          <div className="space-y-2">
            {locks.map((l: D) => (
              <GlassCard key={l.lock_id} className="py-2.5 border border-red-500/20">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-sm font-medium">{l.table}</span>
                  <span className="text-xs text-white/40">{l.lock_type}</span>
                </div>
                <div className="text-xs font-mono text-white/50 truncate">{l.query}</div>
                <div className="text-[10px] text-white/30 mt-1">
                  PID {l.holder_pid} · {l.duration_seconds}s · {l.waiting_pids?.length ?? 0} waiting
                </div>
              </GlassCard>
            ))}
          </div>
        </>
      )}
    </AppShell>
  );
}
