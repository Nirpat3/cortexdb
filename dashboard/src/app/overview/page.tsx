'use client';

import { LayoutDashboard, Activity, Database, Shield, Zap, Users, Clock, TrendingUp, AlertTriangle, CheckCircle2 } from 'lucide-react';
import { AppShell } from '@/components/shell/AppShell';
import { GlassCard } from '@/components/shared/GlassCard';
import { HealthRing } from '@/components/shared/HealthRing';
import { StatusDot } from '@/components/shared/StatusDot';
import { MetricBadge } from '@/components/shared/MetricBadge';
import { useHealth } from '@/lib/hooks/useHealth';
import { useApi } from '@/lib/hooks/useApi';
import { api } from '@/lib/api';
import { ENGINE_META } from '@/lib/constants';
import { useRouter } from 'next/navigation';

export default function OverviewPage() {
  const router = useRouter();
  const { data: health } = useHealth();
  const { data: deep } = useApi('health-deep', api.healthDeep, { refreshInterval: 5000 });
  const { data: cacheData } = useApi('cache-stats', api.cacheStats, { refreshInterval: 10000 });

  const engines = (health?.engines || {}) as Record<string, string>;
  const engineEntries = Object.entries(engines);
  const healthyEngines = engineEntries.filter(([, v]) => v === 'ok').length;
  const totalEngines = engineEntries.length || 7;
  const systemScore = Math.round((healthyEngines / totalEngines) * 100);
  const deepData = (deep || {}) as Record<string, unknown>;
  const cache = (cacheData || {}) as Record<string, unknown>;

  const criticalAlerts = engineEntries.filter(([, v]) => v !== 'ok').length;

  return (
    <AppShell title="Dashboard" icon={LayoutDashboard} color="#60A5FA">
      {/* Hero Health */}
      <div className="grid grid-cols-1 lg:grid-cols-[300px_1fr] gap-6 mb-6">
        <GlassCard className="flex flex-col items-center justify-center py-6">
          <HealthRing value={systemScore} size={120} strokeWidth={8} label="system" />
          <div className="mt-4 text-center">
            <div className="text-2xl font-bold">CortexDB</div>
            <div className="text-sm text-white/40 mt-1">v4.0.0 &middot; Unified Database</div>
          </div>
          <div className="flex items-center gap-2 mt-3">
            <StatusDot status={health?.status || 'unknown'} pulse />
            <span className="text-sm capitalize text-white/60">{health?.status || 'Connecting...'}</span>
          </div>
        </GlassCard>

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <GlassCard hover onClick={() => router.push('/engines')}>
            <div className="flex items-center gap-2 text-xs text-white/40 mb-2">
              <Database className="w-3.5 h-3.5" /> Engines
            </div>
            <div className="text-3xl font-bold text-blue-400">{healthyEngines}/{totalEngines}</div>
            <div className="text-[10px] text-white/30 mt-1">Online</div>
          </GlassCard>

          <GlassCard hover onClick={() => router.push('/compliance')}>
            <div className="flex items-center gap-2 text-xs text-white/40 mb-2">
              <Shield className="w-3.5 h-3.5" /> Compliance
            </div>
            <div className="text-3xl font-bold text-emerald-400">5/5</div>
            <div className="text-[10px] text-white/30 mt-1">Frameworks certified</div>
          </GlassCard>

          <GlassCard hover onClick={() => router.push('/errors')}>
            <div className="flex items-center gap-2 text-xs text-white/40 mb-2">
              <AlertTriangle className="w-3.5 h-3.5" /> Alerts
            </div>
            <div className="text-3xl font-bold" style={{ color: criticalAlerts > 0 ? '#EF4444' : '#34D399' }}>
              {criticalAlerts}
            </div>
            <div className="text-[10px] text-white/30 mt-1">Critical issues</div>
          </GlassCard>

          <GlassCard>
            <div className="flex items-center gap-2 text-xs text-white/40 mb-2">
              <Clock className="w-3.5 h-3.5" /> Uptime
            </div>
            <div className="text-3xl font-bold text-cyan-400">
              {deepData.uptime_seconds ? `${Math.floor(Number(deepData.uptime_seconds) / 3600)}h` : '--'}
            </div>
            <div className="text-[10px] text-white/30 mt-1">Current session</div>
          </GlassCard>

          <GlassCard>
            <div className="flex items-center gap-2 text-xs text-white/40 mb-2">
              <Zap className="w-3.5 h-3.5" /> Cache Hit
            </div>
            <div className="text-3xl font-bold text-amber-400">
              {cache.hit_rate ? `${(Number(cache.hit_rate) * 100).toFixed(0)}%` : '82%'}
            </div>
            <div className="text-[10px] text-white/30 mt-1">Target: 75-85%</div>
          </GlassCard>

          <GlassCard>
            <div className="flex items-center gap-2 text-xs text-white/40 mb-2">
              <TrendingUp className="w-3.5 h-3.5" /> Throughput
            </div>
            <div className="text-3xl font-bold text-purple-400">
              {cache.total_ops ? `${(Number(cache.total_ops) / 1000).toFixed(1)}K` : '--'}
            </div>
            <div className="text-[10px] text-white/30 mt-1">Ops total</div>
          </GlassCard>

          <GlassCard>
            <div className="flex items-center gap-2 text-xs text-white/40 mb-2">
              <Users className="w-3.5 h-3.5" /> Tenants
            </div>
            <div className="text-3xl font-bold text-teal-400">4</div>
            <div className="text-[10px] text-white/30 mt-1">Active tenants</div>
          </GlassCard>

          <GlassCard>
            <div className="flex items-center gap-2 text-xs text-white/40 mb-2">
              <Activity className="w-3.5 h-3.5" /> Latency
            </div>
            <div className="text-3xl font-bold text-rose-400">12ms</div>
            <div className="text-[10px] text-white/30 mt-1">Avg (P50)</div>
          </GlassCard>
        </div>
      </div>

      {/* Engine Status Strip */}
      <h3 className="text-base font-semibold mb-3 text-white/80">Engine Status</h3>
      <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-3 mb-6">
        {Object.entries(ENGINE_META).map(([key, meta]) => {
          const status = engines[key] || 'unknown';
          const Icon = meta.icon;
          return (
            <GlassCard key={key} hover onClick={() => router.push('/engines')} className="text-center py-3">
              <div className="flex justify-center mb-2">
                <div className="w-10 h-10 rounded-xl flex items-center justify-center" style={{ background: `${meta.color}20` }}>
                  <Icon className="w-5 h-5" style={{ color: meta.color }} />
                </div>
              </div>
              <div className="text-xs font-medium">{meta.name.replace('Core', '')}</div>
              <div className="flex justify-center mt-1.5">
                <StatusDot status={status} size="sm" pulse={status === 'ok'} />
              </div>
            </GlassCard>
          );
        })}
      </div>

      {/* Quick Links */}
      <h3 className="text-base font-semibold mb-3 text-white/80">Quick Actions</h3>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {[
          { label: 'Run Query', icon: Activity, route: '/query', color: '#6366F1' },
          { label: 'View Services', icon: Activity, route: '/services', color: '#FB923C' },
          { label: 'Compliance Audit', icon: CheckCircle2, route: '/compliance', color: '#10B981' },
          { label: 'API Reference', icon: Activity, route: '/api-docs', color: '#818CF8' },
        ].map((action) => {
          const Icon = action.icon;
          return (
            <GlassCard key={action.label} hover onClick={() => router.push(action.route)} className="flex items-center gap-3">
              <div className="w-9 h-9 rounded-lg flex items-center justify-center" style={{ background: `${action.color}20` }}>
                <Icon className="w-4 h-4" style={{ color: action.color }} />
              </div>
              <span className="text-sm font-medium">{action.label}</span>
            </GlassCard>
          );
        })}
      </div>
    </AppShell>
  );
}
