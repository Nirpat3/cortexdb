'use client';

import { Brain, Users, Activity, GitBranch, BarChart3 } from 'lucide-react';
import { AppShell } from '@/components/shell/AppShell';
import { GlassCard } from '@/components/shared/GlassCard';
import { MetricBadge } from '@/components/shared/MetricBadge';
import { HealthRing } from '@/components/shared/HealthRing';
import { useApi } from '@/lib/hooks/useApi';
import { api } from '@/lib/api';

export default function CortexGraphPage() {
  const { data: stats } = useApi('cg-stats', api.cortexGraphStats, { refreshInterval: 10000 });
  const { data: churnData } = useApi('churn', () => api.churnRisk(0.7));

  const s = (stats || {}) as Record<string, unknown>;
  const churnList = (churnData || []) as Record<string, unknown>[];

  const layers = [
    { name: 'Identity Resolution', icon: Users, desc: 'Deterministic + probabilistic matching across 9 identifier types', color: '#8B5CF6' },
    { name: 'Event Database', icon: Activity, desc: 'Real-time streaming + time-series analytics', color: '#3B82F6' },
    { name: 'Relationship Graph', icon: GitBranch, desc: 'Customer ↔ Product ↔ Store ↔ Campaign', color: '#10B981' },
    { name: 'Behavioral Profile', icon: BarChart3, desc: 'RFM scoring, churn prediction, health score', color: '#F59E0B' },
  ];

  return (
    <AppShell title="CortexGraph" icon={Brain} color="#8B5CF6">
      <div className="mb-6">
        <h2 className="text-xl font-semibold mb-1">Customer Intelligence</h2>
        <p className="text-sm text-white/40">4-layer customer intelligence replacing Segment, mParticle, and Amperity</p>
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
        {[
          { label: 'Customers', value: s.total_customers ?? '--' },
          { label: 'Events Today', value: s.events_today ?? '--' },
          { label: 'Relationships', value: s.total_relationships ?? '--' },
          { label: 'Avg Health', value: s.avg_health_score ? `${s.avg_health_score}%` : '--' },
        ].map((m) => (
          <GlassCard key={m.label}>
            <MetricBadge label={m.label} value={String(m.value)} />
          </GlassCard>
        ))}
      </div>

      {/* 4 Layers */}
      <h3 className="text-base font-semibold mb-3 text-white/80">Intelligence Layers</h3>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-8">
        {layers.map((layer) => {
          const Icon = layer.icon;
          return (
            <GlassCard key={layer.name} hover>
              <div className="flex items-start gap-3">
                <div
                  className="w-10 h-10 rounded-xl flex items-center justify-center shrink-0"
                  style={{ background: `${layer.color}25` }}
                >
                  <Icon className="w-5 h-5" style={{ color: layer.color }} />
                </div>
                <div>
                  <div className="text-sm font-semibold">{layer.name}</div>
                  <div className="text-xs text-white/40 mt-0.5">{layer.desc}</div>
                </div>
              </div>
            </GlassCard>
          );
        })}
      </div>

      {/* Churn Risk */}
      <h3 className="text-base font-semibold mb-3 text-white/80">High Churn Risk</h3>
      {churnList.length > 0 ? (
        <div className="space-y-2">
          {churnList.slice(0, 10).map((c, i) => (
            <GlassCard key={i} className="flex items-center justify-between py-3">
              <div>
                <div className="text-sm font-medium">{String(c.customer_id || `Customer ${i + 1}`)}</div>
                <div className="text-xs text-white/40">{String(c.segment || 'Unknown segment')}</div>
              </div>
              <HealthRing
                value={Math.round(100 - (Number(c.churn_risk) || 0) * 100)}
                size={40}
                strokeWidth={3}
                label="risk"
              />
            </GlassCard>
          ))}
        </div>
      ) : (
        <GlassCard className="text-center py-8 text-white/30 text-sm">
          No high-risk customers detected
        </GlassCard>
      )}
    </AppShell>
  );
}
