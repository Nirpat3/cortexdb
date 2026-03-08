'use client';

import { Database } from 'lucide-react';
import { AppShell } from '@/components/shell/AppShell';
import { GlassCard } from '@/components/shared/GlassCard';
import { StatusDot } from '@/components/shared/StatusDot';
import { HealthRing } from '@/components/shared/HealthRing';
import { MetricBadge } from '@/components/shared/MetricBadge';
import { CardSkeleton } from '@/components/shared/LoadingSkeleton';
import { useHealth } from '@/lib/hooks/useHealth';
import { useApi } from '@/lib/hooks/useApi';
import { api } from '@/lib/api';
import { ENGINE_META } from '@/lib/constants';
import { formatMs } from '@/lib/utils';

export default function EnginesPage() {
  const { data: health } = useHealth();
  const { data: engineData, isLoading } = useApi('engines', api.getEngines, { refreshInterval: 5000 });

  const engines = health?.engines || {};
  const engineDetails = (engineData as Record<string, Record<string, unknown>>) || {};

  return (
    <AppShell title="Engines" icon={Database} color="#3B82F6">
      <div className="mb-6">
        <h2 className="text-xl font-semibold mb-1">7 Unified Storage Engines</h2>
        <p className="text-sm text-white/40">One database to replace them all</p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
        {isLoading && !health
          ? Array.from({ length: 7 }).map((_, i) => <CardSkeleton key={i} />)
          : Object.entries(ENGINE_META).map(([key, meta]) => {
              const status = (engines as Record<string, string>)[key] || 'unknown';
              const details = engineDetails[key] || {};
              const latency = (details.latency_ms as number) || 0;
              const ops = (details.operations as number) || 0;
              const Icon = meta.icon;
              const healthScore = status === 'ok' ? 100 : status === 'degraded' ? 60 : 0;

              return (
                <GlassCard key={key} hover>
                  <div className="flex items-start justify-between mb-4">
                    <div className="flex items-center gap-3">
                      <div
                        className="w-11 h-11 rounded-xl flex items-center justify-center"
                        style={{ background: `${meta.color}25` }}
                      >
                        <Icon className="w-5 h-5" style={{ color: meta.color }} />
                      </div>
                      <div>
                        <div className="text-sm font-semibold text-white">{meta.name}</div>
                        <div className="text-[11px] text-white/30">Replaces {meta.replaces}</div>
                      </div>
                    </div>
                    <StatusDot status={status} pulse={status === 'ok'} />
                  </div>

                  <div className="flex items-center justify-between">
                    <HealthRing value={healthScore} size={48} strokeWidth={4} />
                    <div className="flex gap-4">
                      <MetricBadge label="Latency" value={latency ? formatMs(latency) : '--'} />
                      <MetricBadge label="Ops" value={ops || '--'} />
                    </div>
                  </div>
                </GlassCard>
              );
            })}
      </div>

      {/* Read Cascade */}
      <div className="mt-8">
        <h3 className="text-base font-semibold mb-3 text-white/80">Read Cascade</h3>
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
          {[
            { tier: 'R0', name: 'Process Cache', target: '< 0.1ms', color: '#34D399' },
            { tier: 'R1', name: 'Redis', target: '< 1ms', color: '#3B82F6' },
            { tier: 'R2', name: 'Semantic', target: '< 5ms', color: '#8B5CF6' },
            { tier: 'R3', name: 'PostgreSQL', target: '< 50ms', color: '#F59E0B' },
            { tier: 'R4', name: 'Deep Retrieval', target: 'Cross-engine', color: '#EF4444' },
          ].map((tier) => (
            <GlassCard key={tier.tier} className="text-center">
              <div className="text-lg font-bold" style={{ color: tier.color }}>
                {tier.tier}
              </div>
              <div className="text-xs text-white/60 mt-1">{tier.name}</div>
              <div className="text-[10px] text-white/30 mt-0.5">{tier.target}</div>
            </GlassCard>
          ))}
        </div>
      </div>
    </AppShell>
  );
}
