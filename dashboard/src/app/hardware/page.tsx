'use client';

import { useEffect, useState, useCallback } from 'react';
import { HardDrive, Cpu, MemoryStick, Wifi, Thermometer, Server, RefreshCw } from 'lucide-react';
import { AppShell } from '@/components/shell/AppShell';
import { GlassCard } from '@/components/shared/GlassCard';
import { HealthRing } from '@/components/shared/HealthRing';
import { MetricBadge } from '@/components/shared/MetricBadge';
import { api } from '@/lib/api';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type D = Record<string, any>;

export default function HardwarePage() {
  const [hw, setHw] = useState<D | null>(null);

  const refresh = useCallback(async () => {
    try {
      const data = await api.hardwareSummary();
      setHw(data);
    } catch { /* silent */ }
  }, []);

  useEffect(() => {
    refresh();
    const iv = setInterval(refresh, 5000);
    return () => clearInterval(iv);
  }, [refresh]);

  return (
    <AppShell title="Hardware" icon={Server} color="#8B5CF6">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-xl font-semibold mb-1">Hardware Monitor</h2>
          <p className="text-sm text-white/40">
            {hw ? `${hw.platform} ${hw.architecture} — ${hw.processor || 'Unknown CPU'}` : 'Loading...'}
          </p>
        </div>
        <button onClick={refresh} className="glass px-3 py-1.5 rounded-lg text-xs text-white/60 hover:text-white/90 transition">
          <RefreshCw className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* CPU */}
      <h3 className="text-base font-semibold mb-3 text-white/80"><Cpu className="w-4 h-4 inline mr-1.5" />CPU</h3>
      <div className="grid grid-cols-2 sm:grid-cols-[160px_1fr] gap-4 mb-6">
        <GlassCard className="flex flex-col items-center py-4">
          <HealthRing value={Math.round(hw?.cpu?.usage_pct ?? 0)} size={90} strokeWidth={7} label="CPU" />
        </GlassCard>
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
          <GlassCard><MetricBadge label="Cores" value={String(hw?.cpu?.cores ?? '-')} color="#3B82F6" /></GlassCard>
          <GlassCard><MetricBadge label="Frequency" value={`${hw?.cpu?.frequency_mhz ?? '-'} MHz`} color="#6366F1" /></GlassCard>
          <GlassCard><MetricBadge label="Usage" value={`${hw?.cpu?.usage_pct ?? '-'}%`} color="#EF4444" /></GlassCard>
          <GlassCard><MetricBadge label="Load 1m" value={String(hw?.cpu?.load_1m ?? '-')} color="#F59E0B" /></GlassCard>
          <GlassCard><MetricBadge label="Load 5m" value={String(hw?.cpu?.load_5m ?? '-')} color="#F59E0B" /></GlassCard>
          <GlassCard><MetricBadge label="Load 15m" value={String(hw?.cpu?.load_15m ?? '-')} color="#F59E0B" /></GlassCard>
        </div>
      </div>

      {/* Memory */}
      <h3 className="text-base font-semibold mb-3 text-white/80"><MemoryStick className="w-4 h-4 inline mr-1.5" />Memory</h3>
      <div className="grid grid-cols-2 sm:grid-cols-[160px_1fr] gap-4 mb-6">
        <GlassCard className="flex flex-col items-center py-4">
          <HealthRing value={Math.round(hw?.memory?.usage_pct ?? 0)} size={90} strokeWidth={7} label="RAM" />
        </GlassCard>
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
          <GlassCard><MetricBadge label="Total" value={`${hw?.memory?.total_gb ?? '-'} GB`} color="#8B5CF6" /></GlassCard>
          <GlassCard><MetricBadge label="Used" value={`${hw?.memory?.used_gb ?? '-'} GB`} color="#EC4899" /></GlassCard>
          <GlassCard><MetricBadge label="Free" value={`${hw?.memory ? (hw.memory.total_gb - hw.memory.used_gb).toFixed(1) : '-'} GB`} color="#34D399" /></GlassCard>
          <GlassCard><MetricBadge label="Swap Total" value={`${hw?.swap?.total_gb ?? '-'} GB`} color="#6366F1" /></GlassCard>
          <GlassCard><MetricBadge label="Swap Used" value={`${hw?.swap?.used_gb ?? '-'} GB`} color="#F472B6" /></GlassCard>
          <GlassCard><MetricBadge label="Usage" value={`${hw?.memory?.usage_pct ?? '-'}%`} color="#FBBF24" /></GlassCard>
        </div>
      </div>

      {/* Disk */}
      <h3 className="text-base font-semibold mb-3 text-white/80"><HardDrive className="w-4 h-4 inline mr-1.5" />Storage</h3>
      <div className="grid grid-cols-2 sm:grid-cols-[160px_1fr] gap-4 mb-6">
        <GlassCard className="flex flex-col items-center py-4">
          <HealthRing value={Math.round(hw?.disk?.usage_pct ?? 0)} size={90} strokeWidth={7} label="Disk" />
        </GlassCard>
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
          <GlassCard><MetricBadge label="Total" value={`${hw?.disk?.total_gb ?? '-'} GB`} color="#F59E0B" /></GlassCard>
          <GlassCard><MetricBadge label="Used" value={`${hw?.disk?.used_gb ?? '-'} GB`} color="#EF4444" /></GlassCard>
          <GlassCard><MetricBadge label="Free" value={`${hw?.disk ? (hw.disk.total_gb - hw.disk.used_gb).toFixed(1) : '-'} GB`} color="#34D399" /></GlassCard>
          <GlassCard><MetricBadge label="Read" value={`${hw?.disk?.read_mb_s ?? '-'} MB/s`} color="#3B82F6" /></GlassCard>
          <GlassCard><MetricBadge label="Write" value={`${hw?.disk?.write_mb_s ?? '-'} MB/s`} color="#EC4899" /></GlassCard>
          <GlassCard><MetricBadge label="Usage" value={`${hw?.disk?.usage_pct ?? '-'}%`} color="#FBBF24" /></GlassCard>
        </div>
      </div>

      {/* Network */}
      <h3 className="text-base font-semibold mb-3 text-white/80"><Wifi className="w-4 h-4 inline mr-1.5" />Network</h3>
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 mb-6">
        <GlassCard><MetricBadge label="Sent" value={`${hw?.network?.sent_mb_s ?? '-'} MB/s`} color="#3B82F6" /></GlassCard>
        <GlassCard><MetricBadge label="Received" value={`${hw?.network?.recv_mb_s ?? '-'} MB/s`} color="#34D399" /></GlassCard>
        <GlassCard><MetricBadge label="Connections" value={String(hw?.network?.connections ?? '-')} color="#F59E0B" /></GlassCard>
      </div>

      {/* Temperature + System */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <GlassCard>
          <Thermometer className="w-4 h-4 text-red-400 mb-1" />
          <MetricBadge label="CPU Temp" value={
            hw?.temperatures?.cpu ? `${hw.temperatures.cpu}°C` : 'N/A'
          } color="#EF4444" />
        </GlassCard>
        <GlassCard><MetricBadge label="Processes" value={String(hw?.process_count ?? '-')} color="#8B5CF6" /></GlassCard>
        <GlassCard><MetricBadge label="Uptime" value={
          hw?.uptime_seconds ? `${Math.floor(hw.uptime_seconds / 86400)}d` : '-'
        } color="#34D399" /></GlassCard>
        <GlassCard><MetricBadge label="Python" value={hw?.python_version ?? '-'} color="#FBBF24" /></GlassCard>
      </div>
    </AppShell>
  );
}
