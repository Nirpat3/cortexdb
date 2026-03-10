'use client';

import { HeartPulse, Zap, ZapOff, Activity } from 'lucide-react';
import { AppShell } from '@/components/shell/AppShell';
import { GlassCard } from '@/components/shared/GlassCard';
import { StatusDot } from '@/components/shared/StatusDot';
import { HealthRing } from '@/components/shared/HealthRing';
import { MetricBadge } from '@/components/shared/MetricBadge';
import { useApi } from '@/lib/hooks/useApi';
import { api } from '@/lib/api';
import { formatMs } from '@/lib/utils';

export default function HeartbeatPage() {
  const { data: status } = useApi('heartbeat', api.heartbeatStatus, { refreshInterval: 5000 });
  const { data: breakers } = useApi('breakers', api.circuitBreakers, { refreshInterval: 5000 });

  const statusData = (status || {}) as Record<string, unknown>;
  const components = (statusData.components || {}) as Record<string, { status: string; latency_ms: number }>;
  const breakerData = (breakers || {}) as Record<string, unknown>;
  const breakerList = (breakerData.breakers || breakerData.circuit_breakers || []) as Record<string, unknown>[];

  const totalComponents = Object.keys(components).length;
  const healthyComponents = Object.values(components).filter((c) => c.status === 'ok' || c.status === 'healthy').length;
  const overallScore = totalComponents > 0 ? Math.round((healthyComponents / totalComponents) * 100) : 0;

  return (
    <AppShell title="Heartbeat" icon={HeartPulse} color="#EC4899">
      <div className="mb-6">
        <h2 className="text-xl font-semibold mb-1">Health Monitoring</h2>
        <p className="text-sm text-white/40">Real-time component health and circuit breaker status</p>
      </div>

      {/* Overall Health */}
      <GlassCard className="mb-6 flex items-center gap-6">
        <HealthRing value={overallScore} size={80} strokeWidth={6} label="overall" />
        <div>
          <div className="text-2xl font-bold">{healthyComponents}/{totalComponents}</div>
          <div className="text-sm text-white/40">Components healthy</div>
          <div className="flex items-center gap-1.5 mt-1">
            <StatusDot status={String(statusData.overall || 'unknown')} pulse />
            <span className="text-xs capitalize text-white/60">{String(statusData.overall || 'unknown')}</span>
          </div>
        </div>
      </GlassCard>

      {/* Component Health */}
      <h3 className="text-base font-semibold mb-3 text-white/80">
        <Activity className="w-4 h-4 inline mr-1.5" />
        Components
      </h3>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 mb-8">
        {Object.entries(components).map(([name, comp]) => (
          <GlassCard key={name} className="flex items-center justify-between">
            <div>
              <div className="text-sm font-medium capitalize">{name.replace(/_/g, ' ')}</div>
              <div className="text-xs text-white/30 mt-0.5">
                {comp.latency_ms ? formatMs(comp.latency_ms) : '--'}
              </div>
            </div>
            <StatusDot status={comp.status} pulse={comp.status === 'ok'} />
          </GlassCard>
        ))}
        {totalComponents === 0 && (
          <GlassCard className="col-span-full text-center py-6 text-white/30 text-sm">
            Waiting for heartbeat data...
          </GlassCard>
        )}
      </div>

      {/* Circuit Breakers */}
      <h3 className="text-base font-semibold mb-3 text-white/80">
        <Zap className="w-4 h-4 inline mr-1.5" />
        Circuit Breakers
      </h3>
      {breakerList.length > 0 ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {breakerList.map((cb, i) => {
            const state = String(cb.state || 'closed');
            const isClosed = state === 'closed';
            return (
              <GlassCard key={i}>
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    {isClosed ? (
                      <Zap className="w-4 h-4 text-emerald-400" />
                    ) : (
                      <ZapOff className="w-4 h-4 text-red-400" />
                    )}
                    <span className="text-sm font-medium">{String(cb.name)}</span>
                  </div>
                  <StatusDot status={state} />
                </div>
                <div className="flex gap-4">
                  <MetricBadge label="Failures" value={String(cb.failure_count || 0)} />
                  <MetricBadge label="State" value={state.replace('_', ' ')} />
                </div>
              </GlassCard>
            );
          })}
        </div>
      ) : (
        <GlassCard className="text-center py-6 text-white/30 text-sm">
          All circuits nominal
        </GlassCard>
      )}
    </AppShell>
  );
}
