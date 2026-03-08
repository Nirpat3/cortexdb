'use client';

import { useEffect, useState, useCallback } from 'react';
import { Activity, Cpu, HardDrive, Wifi, MemoryStick, RefreshCw, Thermometer } from 'lucide-react';
import { AppShell } from '@/components/shell/AppShell';
import { GlassCard } from '@/components/shared/GlassCard';
import { HealthRing } from '@/components/shared/HealthRing';
import { MetricBadge } from '@/components/shared/MetricBadge';
import { StatusDot } from '@/components/shared/StatusDot';
import { useHealth } from '@/lib/hooks/useHealth';
import { api } from '@/lib/api';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type D = Record<string, any>;

export default function MonitoringPage() {
  const health = useHealth();
  const [metrics, setMetrics] = useState<D | null>(null);
  const [history, setHistory] = useState<D[]>([]);

  const refresh = useCallback(async () => {
    try {
      const [m, h] = await Promise.all([
        api.systemMetrics().catch(() => null),
        api.systemMetricsHistory(10).catch(() => null),
      ]);
      if (m) setMetrics(m);
      if (h) setHistory((h as D).history ?? []);
    } catch { /* silent */ }
  }, []);

  useEffect(() => {
    refresh();
    const iv = setInterval(refresh, 5000);
    return () => clearInterval(iv);
  }, [refresh]);

  const m = metrics;

  return (
    <AppShell title="System Monitoring" icon={Activity} color="#3B82F6">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-xl font-semibold mb-1">Real-Time Monitoring</h2>
          <p className="text-sm text-white/40">Live system metrics from System Metrics Agent</p>
        </div>
        <div className="flex items-center gap-3">
          <StatusDot status={health ? 'healthy' : 'unknown'} pulse />
          <span className="text-xs text-white/40">{health ? 'Connected' : 'Connecting...'}</span>
          <button onClick={refresh} className="glass px-3 py-1.5 rounded-lg text-xs text-white/60 hover:text-white/90 transition">
            <RefreshCw className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Primary Gauges */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-6">
        <GlassCard className="flex flex-col items-center py-4">
          <Cpu className="w-5 h-5 text-blue-400 mb-2" />
          <HealthRing value={Math.round(m?.cpu_usage ?? 0)} size={80} strokeWidth={6} label="CPU" />
          <div className="text-xs text-white/40 mt-2">{m?.cpu_cores ?? '-'} cores @ {m?.cpu_freq_mhz ?? '-'} MHz</div>
        </GlassCard>
        <GlassCard className="flex flex-col items-center py-4">
          <MemoryStick className="w-5 h-5 text-purple-400 mb-2" />
          <HealthRing value={Math.round(m?.memory_pct ?? 0)} size={80} strokeWidth={6} label="RAM" />
          <div className="text-xs text-white/40 mt-2">{m?.memory_used_gb ?? '-'} / {m?.memory_total_gb ?? '-'} GB</div>
        </GlassCard>
        <GlassCard className="flex flex-col items-center py-4">
          <HardDrive className="w-5 h-5 text-amber-400 mb-2" />
          <HealthRing value={Math.round(m?.disk_pct ?? 0)} size={80} strokeWidth={6} label="Disk" />
          <div className="text-xs text-white/40 mt-2">{m?.disk_used_gb ?? '-'} / {m?.disk_total_gb ?? '-'} GB</div>
        </GlassCard>
        <GlassCard className="flex flex-col items-center py-4">
          <Wifi className="w-5 h-5 text-emerald-400 mb-2" />
          <HealthRing value={Math.min(100, Math.round((m?.net_connections ?? 0) / 3))} size={80} strokeWidth={6} label="Net" />
          <div className="text-xs text-white/40 mt-2">{m?.net_connections ?? '-'} connections</div>
        </GlassCard>
      </div>

      {/* Detailed Metrics */}
      <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-3 mb-6">
        <GlassCard><MetricBadge label="Load (1m)" value={String(m?.load_avg_1m ?? '-')} color="#3B82F6" /></GlassCard>
        <GlassCard><MetricBadge label="Load (5m)" value={String(m?.load_avg_5m ?? '-')} color="#6366F1" /></GlassCard>
        <GlassCard><MetricBadge label="Load (15m)" value={String(m?.load_avg_15m ?? '-')} color="#8B5CF6" /></GlassCard>
        <GlassCard><MetricBadge label="Processes" value={String(m?.process_count ?? '-')} color="#F59E0B" /></GlassCard>
        <GlassCard><MetricBadge label="Disk Read" value={`${m?.disk_read_mb_s ?? '-'} MB/s`} color="#34D399" /></GlassCard>
        <GlassCard><MetricBadge label="Disk Write" value={`${m?.disk_write_mb_s ?? '-'} MB/s`} color="#F472B6" /></GlassCard>
      </div>

      {/* Network + Swap */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
        <GlassCard><MetricBadge label="Net Send" value={`${m?.net_sent_mb_s ?? '-'} MB/s`} color="#3B82F6" /></GlassCard>
        <GlassCard><MetricBadge label="Net Recv" value={`${m?.net_recv_mb_s ?? '-'} MB/s`} color="#34D399" /></GlassCard>
        <GlassCard><MetricBadge label="Swap Used" value={`${m?.swap_used_gb ?? '-'} GB`} color="#F59E0B" /></GlassCard>
        <GlassCard>
          <MetricBadge label="Temperature" value={m?.temperatures?.cpu ? `${m.temperatures.cpu}°C` : '-'} color="#EF4444" />
          <Thermometer className="w-3 h-3 text-red-400 mt-1" />
        </GlassCard>
      </div>

      {/* Uptime */}
      <GlassCard className="mb-6">
        <div className="flex items-center justify-between">
          <span className="text-sm text-white/60">System Uptime</span>
          <span className="text-sm font-mono">
            {m?.uptime_seconds ? `${Math.floor(m.uptime_seconds / 86400)}d ${Math.floor((m.uptime_seconds % 86400) / 3600)}h ${Math.floor((m.uptime_seconds % 3600) / 60)}m` : '-'}
          </span>
        </div>
      </GlassCard>

      {/* CPU History Sparkline */}
      {history.length > 0 && (
        <>
          <h3 className="text-base font-semibold mb-3 text-white/80">CPU History (10 min)</h3>
          <GlassCard>
            <div className="flex items-end gap-0.5 h-20">
              {history.slice(-60).map((h: D, i: number) => {
                const cpu = h.cpu_usage ?? 0;
                return (
                  <div key={i} className="flex-1 rounded-t" style={{
                    height: `${cpu}%`,
                    backgroundColor: cpu > 80 ? '#EF4444' : cpu > 60 ? '#FBBF24' : '#34D399',
                    opacity: 0.6,
                  }} />
                );
              })}
            </div>
          </GlassCard>
        </>
      )}
    </AppShell>
  );
}
