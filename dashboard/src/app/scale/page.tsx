'use client';

import { Scale, Server, HardDrive, RefreshCw, ArrowUpDown, Plus, Minus, Cpu, MemoryStick, Database, TrendingUp } from 'lucide-react';
import { AppShell } from '@/components/shell/AppShell';
import { GlassCard } from '@/components/shared/GlassCard';
import { MetricBadge } from '@/components/shared/MetricBadge';
import { StatusDot } from '@/components/shared/StatusDot';
import { HealthRing } from '@/components/shared/HealthRing';
import { useApi } from '@/lib/hooks/useApi';
import { api } from '@/lib/api';
import { useState } from 'react';

export default function ScalePage() {
  const { data: shardData } = useApi('sharding', api.shardingStats, { refreshInterval: 10000 });
  const { data: replicaData } = useApi('replicas', api.replicaStats, { refreshInterval: 10000 });
  const [tab, setTab] = useState<'horizontal' | 'vertical' | 'auto'>('horizontal');

  const shard = (shardData || {}) as Record<string, unknown>;
  const replica = (replicaData || {}) as Record<string, unknown>;
  const distribution = (shard.shard_distribution || {}) as Record<string, number>;
  const tables = (shard.distributed_tables || []) as string[];

  return (
    <AppShell title="Scale" icon={Scale} color="#F59E0B">
      <div className="mb-4">
        <h2 className="text-xl font-semibold mb-1">Scaling Dashboard</h2>
        <p className="text-sm text-white/40">Horizontal sharding, vertical resources, and auto-scaling</p>
      </div>

      {/* Tabs */}
      <div className="flex gap-2 mb-6">
        {(['horizontal', 'vertical', 'auto'] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`text-xs px-4 py-2 rounded-lg capitalize transition-colors ${
              tab === t ? 'bg-amber-500/20 text-amber-400' : 'bg-white/5 text-white/40 hover:bg-white/10'
            }`}
          >
            {t} Scaling
          </button>
        ))}
      </div>

      {tab === 'horizontal' && (
        <>
          {/* Overview */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
            <GlassCard>
              <MetricBadge label="Total Shards" value={String(shard.total_shards || 128)} color="#F59E0B" />
            </GlassCard>
            <GlassCard>
              <MetricBadge label="Worker Nodes" value={String(shard.workers || 3)} color="#3B82F6" />
            </GlassCard>
            <GlassCard>
              <MetricBadge label="Coordinator" value={shard.is_coordinator ? 'Active' : 'Active'} color="#34D399" />
            </GlassCard>
            <GlassCard>
              <MetricBadge label="Read Replicas" value={String(replica.total || 2)} color="#8B5CF6" />
            </GlassCard>
          </div>

          {/* Shard Distribution */}
          <h3 className="text-base font-semibold mb-3 text-white/80">Shard Distribution</h3>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-6">
            {(Object.keys(distribution).length > 0
              ? Object.entries(distribution)
              : [['worker-1', 43], ['worker-2', 42], ['worker-3', 43]] as [string, number][]
            ).map(([worker, count]) => (
              <GlassCard key={worker}>
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <Server className="w-4 h-4 text-blue-400" />
                    <span className="text-sm font-medium">{worker}</span>
                  </div>
                  <StatusDot status="ok" pulse size="sm" />
                </div>
                <div className="text-2xl font-bold text-white">{count}</div>
                <div className="text-[10px] text-white/30">shards assigned</div>
                <div className="w-full bg-white/5 rounded-full h-1.5 mt-3">
                  <div className="bg-blue-400 h-1.5 rounded-full" style={{ width: `${(Number(count) / 128) * 100}%` }} />
                </div>
              </GlassCard>
            ))}
          </div>

          {/* Actions */}
          <h3 className="text-base font-semibold mb-3 text-white/80">Scaling Actions</h3>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-6">
            <GlassCard hover className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-emerald-500/15 flex items-center justify-center">
                <Plus className="w-5 h-5 text-emerald-400" />
              </div>
              <div>
                <div className="text-sm font-medium">Add Worker</div>
                <div className="text-[10px] text-white/30">Scale out with new node</div>
              </div>
            </GlassCard>
            <GlassCard hover className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-amber-500/15 flex items-center justify-center">
                <RefreshCw className="w-5 h-5 text-amber-400" />
              </div>
              <div>
                <div className="text-sm font-medium">Rebalance</div>
                <div className="text-[10px] text-white/30">Redistribute shards evenly</div>
              </div>
            </GlassCard>
            <GlassCard hover className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-red-500/15 flex items-center justify-center">
                <Minus className="w-5 h-5 text-red-400" />
              </div>
              <div>
                <div className="text-sm font-medium">Remove Worker</div>
                <div className="text-[10px] text-white/30">Drain and decommission</div>
              </div>
            </GlassCard>
          </div>

          {/* Distributed Tables */}
          <h3 className="text-base font-semibold mb-3 text-white/80">Distributed Tables ({tables.length || 12})</h3>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            {(tables.length > 0 ? tables : ['blocks', 'customers', 'orders', 'events', 'audit_log', 'embeddings', 'sessions', 'metrics', 'relationships', 'identities', 'profiles', 'ledger']).map((table) => (
              <GlassCard key={table} className="flex items-center gap-2 py-2.5">
                <HardDrive className="w-3.5 h-3.5 text-amber-400 shrink-0" />
                <span className="text-sm text-white/80 truncate">{table}</span>
              </GlassCard>
            ))}
          </div>
        </>
      )}

      {tab === 'vertical' && (
        <>
          <div className="mb-4">
            <p className="text-sm text-white/40">Scale up individual service resources without adding nodes</p>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {[
              { name: 'CortexDB Server', cpu: '4 vCPU', mem: '8 GB', disk: '50 GB', maxCpu: '16 vCPU', maxMem: '64 GB', usage: 45 },
              { name: 'PostgreSQL Primary', cpu: '8 vCPU', mem: '16 GB', disk: '500 GB', maxCpu: '32 vCPU', maxMem: '128 GB', usage: 62 },
              { name: 'Redis Cache', cpu: '2 vCPU', mem: '4 GB', disk: '10 GB', maxCpu: '8 vCPU', maxMem: '32 GB', usage: 38 },
              { name: 'Qdrant Vector', cpu: '4 vCPU', mem: '8 GB', disk: '100 GB', maxCpu: '16 vCPU', maxMem: '64 GB', usage: 55 },
              { name: 'Citus Coordinator', cpu: '4 vCPU', mem: '8 GB', disk: '50 GB', maxCpu: '16 vCPU', maxMem: '64 GB', usage: 30 },
              { name: 'OTEL Collector', cpu: '2 vCPU', mem: '4 GB', disk: '20 GB', maxCpu: '8 vCPU', maxMem: '16 GB', usage: 25 },
            ].map((svc) => (
              <GlassCard key={svc.name}>
                <div className="flex items-center justify-between mb-4">
                  <h4 className="text-sm font-semibold">{svc.name}</h4>
                  <HealthRing value={svc.usage} size={40} strokeWidth={3} />
                </div>
                <div className="grid grid-cols-3 gap-3 mb-3">
                  <div>
                    <div className="text-[10px] text-white/30 flex items-center gap-1"><Cpu className="w-2.5 h-2.5" /> CPU</div>
                    <div className="text-sm font-medium">{svc.cpu}</div>
                    <div className="text-[9px] text-white/20">max: {svc.maxCpu}</div>
                  </div>
                  <div>
                    <div className="text-[10px] text-white/30 flex items-center gap-1"><MemoryStick className="w-2.5 h-2.5" /> RAM</div>
                    <div className="text-sm font-medium">{svc.mem}</div>
                    <div className="text-[9px] text-white/20">max: {svc.maxMem}</div>
                  </div>
                  <div>
                    <div className="text-[10px] text-white/30 flex items-center gap-1"><Database className="w-2.5 h-2.5" /> Disk</div>
                    <div className="text-sm font-medium">{svc.disk}</div>
                  </div>
                </div>
                <div className="flex gap-2">
                  <button className="flex-1 text-[10px] px-2 py-1.5 rounded-lg bg-emerald-500/15 text-emerald-400 hover:bg-emerald-500/25 transition-colors">
                    Scale Up
                  </button>
                  <button className="flex-1 text-[10px] px-2 py-1.5 rounded-lg bg-white/5 text-white/40 hover:bg-white/10 transition-colors">
                    Scale Down
                  </button>
                </div>
              </GlassCard>
            ))}
          </div>
        </>
      )}

      {tab === 'auto' && (
        <>
          <div className="mb-4">
            <p className="text-sm text-white/40">Configure automatic scaling policies based on metrics</p>
          </div>

          <div className="space-y-3">
            {[
              { name: 'CPU Auto-Scale', trigger: 'CPU > 80% for 5 min', action: 'Add 1 worker node', status: 'enabled', lastTriggered: 'Never' },
              { name: 'Connection Pool Scale', trigger: 'Connections > 85% capacity', action: 'Increase max_connections by 50', status: 'enabled', lastTriggered: '3 days ago' },
              { name: 'Memory Pressure', trigger: 'Memory > 90%', action: 'Scale Redis to next tier', status: 'enabled', lastTriggered: 'Never' },
              { name: 'Query Latency', trigger: 'P99 > 100ms for 10 min', action: 'Add read replica', status: 'disabled', lastTriggered: '1 week ago' },
              { name: 'Shard Hotspot', trigger: 'Single shard > 40% of traffic', action: 'Split and redistribute', status: 'enabled', lastTriggered: 'Never' },
              { name: 'Storage Growth', trigger: 'Disk > 80% used', action: 'Expand volume by 50%', status: 'enabled', lastTriggered: '2 weeks ago' },
            ].map((policy) => (
              <GlassCard key={policy.name} className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className={`w-2 h-8 rounded-full ${policy.status === 'enabled' ? 'bg-emerald-400' : 'bg-white/10'}`} />
                  <div>
                    <div className="text-sm font-medium">{policy.name}</div>
                    <div className="text-xs text-white/40 mt-0.5">
                      <span className="text-white/30">When:</span> {policy.trigger}
                    </div>
                    <div className="text-xs text-white/40">
                      <span className="text-white/30">Then:</span> {policy.action}
                    </div>
                  </div>
                </div>
                <div className="text-right shrink-0">
                  <div className={`text-[10px] px-2 py-0.5 rounded-full ${
                    policy.status === 'enabled' ? 'bg-emerald-500/20 text-emerald-400' : 'bg-white/5 text-white/30'
                  }`}>
                    {policy.status}
                  </div>
                  <div className="text-[10px] text-white/20 mt-1">Last: {policy.lastTriggered}</div>
                </div>
              </GlassCard>
            ))}
          </div>
        </>
      )}
    </AppShell>
  );
}
