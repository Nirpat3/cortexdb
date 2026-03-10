'use client';

import { useEffect, useState, useCallback } from 'react';
import { Boxes, CheckCircle2, XCircle, AlertTriangle, Clock, Cpu, MemoryStick, RefreshCw } from 'lucide-react';
import { AppShell } from '@/components/shell/AppShell';
import { GlassCard } from '@/components/shared/GlassCard';
import { MetricBadge } from '@/components/shared/MetricBadge';
import { StatusDot } from '@/components/shared/StatusDot';
import { api } from '@/lib/api';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type D = Record<string, any>;

export default function ServicesPage() {
  const [services, setServices] = useState<D[]>([]);
  const [summary, setSummary] = useState<D | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [s, sum] = await Promise.all([
        api.serviceMonitor().catch(() => null),
        api.serviceMonitorSummary().catch(() => null),
      ]);
      if (s) setServices((s as D).services ?? []);
      if (sum) setSummary(sum);
    } catch { /* silent */ }
  }, []);

  useEffect(() => {
    refresh();
    const iv = setInterval(refresh, 5000);
    return () => clearInterval(iv);
  }, [refresh]);

  const statusIcon = (status: string) => {
    if (status === 'healthy') return <CheckCircle2 className="w-4 h-4 text-emerald-400" />;
    if (status === 'degraded') return <AlertTriangle className="w-4 h-4 text-amber-400" />;
    return <XCircle className="w-4 h-4 text-red-400" />;
  };

  const statusColor = (status: string) => status === 'healthy' ? 'healthy' : status === 'degraded' ? 'warning' : 'error';

  return (
    <AppShell title="Services" icon={Boxes} color="#6366F1">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-xl font-semibold mb-1">Microservices</h2>
          <p className="text-sm text-white/40">Real-time service health from Service Monitor Agent</p>
        </div>
        <button onClick={refresh} className="glass px-3 py-1.5 rounded-lg text-xs text-white/60 hover:text-white/90 transition">
          <RefreshCw className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* Summary Bar */}
      {summary && (
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 mb-6">
          <GlassCard><MetricBadge label="Total" value={String(summary.total)} color="#6366F1" /></GlassCard>
          <GlassCard><MetricBadge label="Healthy" value={String(summary.healthy)} color="#34D399" /></GlassCard>
          <GlassCard><MetricBadge label="Degraded" value={String(summary.degraded)} color="#FBBF24" /></GlassCard>
          <GlassCard><MetricBadge label="Health Score" value={`${summary.health_score}%`} color={summary.health_score > 90 ? '#34D399' : '#F59E0B'} /></GlassCard>
          <GlassCard><MetricBadge label="Avg Error Rate" value={`${summary.avg_error_rate}%`} color={summary.avg_error_rate > 1 ? '#EF4444' : '#34D399'} /></GlassCard>
        </div>
      )}

      {/* Service Cards */}
      <div className="space-y-3">
        {services.map((svc: D) => {
          const upDays = Math.floor((svc.uptime_seconds ?? 0) / 86400);
          const upHours = Math.floor(((svc.uptime_seconds ?? 0) % 86400) / 3600);
          return (
            <GlassCard key={svc.name} className={`py-3 ${svc.status === 'degraded' ? 'border border-amber-500/20' : svc.status === 'down' ? 'border border-red-500/30' : ''}`}>
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <StatusDot status={statusColor(svc.status)} pulse={svc.status !== 'healthy'} />
                  <span className="font-medium text-sm">{svc.display_name}</span>
                  <span className="text-xs text-white/30 font-mono">:{svc.port}</span>
                </div>
                <div className="flex items-center gap-2">
                  {statusIcon(svc.status)}
                  <span className="text-xs text-white/40">v{svc.version}</span>
                </div>
              </div>
              <div className="grid grid-cols-3 sm:grid-cols-6 gap-2 text-xs">
                <div className="flex items-center gap-1 text-white/50">
                  <Cpu className="w-3 h-3" /> {svc.cpu_pct}%
                </div>
                <div className="flex items-center gap-1 text-white/50">
                  <MemoryStick className="w-3 h-3" /> {svc.memory_mb} MB
                </div>
                <div className="text-white/50">{svc.requests_per_min} rpm</div>
                <div className={svc.error_rate_pct > 1 ? 'text-red-400' : 'text-white/50'}>
                  {svc.error_rate_pct}% err
                </div>
                <div className="text-white/50">{svc.avg_latency_ms}ms avg</div>
                <div className="flex items-center gap-1 text-white/50">
                  <Clock className="w-3 h-3" /> {upDays}d {upHours}h
                </div>
              </div>
              {svc.dependencies?.length > 0 && (
                <div className="text-[10px] text-white/25 mt-1.5">
                  Depends on: {svc.dependencies.join(', ')}
                </div>
              )}
            </GlassCard>
          );
        })}
      </div>
    </AppShell>
  );
}
