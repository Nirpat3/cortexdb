'use client';

import { Grid3X3, Heart, Skull, RotateCcw } from 'lucide-react';
import { AppShell } from '@/components/shell/AppShell';
import { GlassCard } from '@/components/shared/GlassCard';
import { StatusDot } from '@/components/shared/StatusDot';
import { HealthRing } from '@/components/shared/HealthRing';
import { useApi } from '@/lib/hooks/useApi';
import { api } from '@/lib/api';
import { timeAgo } from '@/lib/utils';

export default function GridPage() {
  const { data: nodes } = useApi('grid-nodes', () => api.gridNodes(), { refreshInterval: 5000 });
  const { data: cemetery } = useApi('cemetery', api.gridCemetery);
  const { data: resurrections } = useApi('resurrections', api.gridResurrections);

  const nodeList = (nodes || []) as Record<string, unknown>[];
  const deadList = (cemetery || []) as Record<string, unknown>[];
  const rezzList = (resurrections || []) as Record<string, unknown>[];

  return (
    <AppShell title="Grid" icon={Grid3X3} color="#EF4444">
      <div className="mb-6">
        <h2 className="text-xl font-semibold mb-1">Self-Healing Grid</h2>
        <p className="text-sm text-white/40">Automatic failure detection, repair, and resurrection</p>
      </div>

      {/* Node Grid */}
      <h3 className="text-base font-semibold mb-3 text-white/80">
        <Heart className="w-4 h-4 inline mr-1.5" />
        Active Nodes ({nodeList.length})
      </h3>
      {nodeList.length > 0 ? (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3 mb-8">
          {nodeList.map((node, i) => (
            <GlassCard key={i}>
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-medium truncate">{String(node.node_id)}</span>
                <StatusDot status={String(node.state)} />
              </div>
              <div className="flex items-center justify-between">
                <HealthRing value={Number(node.health_score) || 0} size={40} strokeWidth={3} />
                <div className="text-[10px] text-white/30">
                  {node.last_heartbeat ? timeAgo(String(node.last_heartbeat)) : '--'}
                </div>
              </div>
            </GlassCard>
          ))}
        </div>
      ) : (
        <GlassCard className="mb-8 text-center py-6 text-white/30 text-sm">
          No active nodes detected
        </GlassCard>
      )}

      {/* Cemetery */}
      <h3 className="text-base font-semibold mb-3 text-white/80">
        <Skull className="w-4 h-4 inline mr-1.5" />
        Cemetery ({deadList.length})
      </h3>
      {deadList.length > 0 ? (
        <div className="space-y-2 mb-8">
          {deadList.slice(0, 10).map((d, i) => (
            <GlassCard key={i} className="flex items-center justify-between py-2.5">
              <span className="text-sm text-white/60">{String(d.node_id)}</span>
              <span className="text-xs text-red-400">{String(d.cause_of_death || 'Unknown')}</span>
            </GlassCard>
          ))}
        </div>
      ) : (
        <GlassCard className="mb-8 text-center py-6 text-white/30 text-sm">
          No dead nodes — system is healthy
        </GlassCard>
      )}

      {/* Resurrections */}
      <h3 className="text-base font-semibold mb-3 text-white/80">
        <RotateCcw className="w-4 h-4 inline mr-1.5" />
        Resurrections ({rezzList.length})
      </h3>
      {rezzList.length > 0 ? (
        <div className="space-y-2">
          {rezzList.slice(0, 10).map((r, i) => (
            <GlassCard key={i} className="flex items-center justify-between py-2.5">
              <span className="text-sm">{String(r.node_id)}</span>
              <span className="text-xs text-emerald-400">Resurrected</span>
            </GlassCard>
          ))}
        </div>
      ) : (
        <GlassCard className="text-center py-6 text-white/30 text-sm">
          No resurrections recorded
        </GlassCard>
      )}
    </AppShell>
  );
}
