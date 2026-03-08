'use client';

import { useState, useEffect, useCallback } from 'react';
import { Users, Building2, Shield, RefreshCw } from 'lucide-react';
import { AppShell } from '@/components/shell/AppShell';
import { GlassCard } from '@/components/shared/GlassCard';
import { MetricBadge } from '@/components/shared/MetricBadge';
import { StatusDot } from '@/components/shared/StatusDot';
import { api } from '@/lib/api';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type D = Record<string, any>;

export default function TenantsPage() {
  const [tenants, setTenants] = useState<D[]>([]);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const data = await api.getTenants();
      const list = (data as D).tenants ?? (Array.isArray(data) ? data : []);
      setTenants(list);
    } catch { /* silent */ }
    setLoading(false);
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const planColor = (plan: string) =>
    plan === 'Enterprise' || plan === 'enterprise' ? '#8B5CF6' :
    plan === 'Business' || plan === 'business' ? '#3B82F6' : '#34D399';

  const statusMap = (s: string) => s === 'active' ? 'healthy' : s === 'suspended' ? 'warning' : 'error';

  return (
    <AppShell title="Tenants" icon={Building2} color="#8B5CF6">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-xl font-semibold mb-1">Tenant Management</h2>
          <p className="text-sm text-white/40">Multi-tenant isolation, plans, and resource usage</p>
        </div>
        <button onClick={refresh} className="glass px-3 py-1.5 rounded-lg text-xs text-white/60 hover:text-white/90 transition">
          <RefreshCw className="w-3.5 h-3.5" />
        </button>
      </div>

      {loading ? (
        <div className="text-center py-12 text-white/40">Loading tenants...</div>
      ) : tenants.length === 0 ? (
        <GlassCard className="text-center py-12">
          <Users className="w-10 h-10 text-white/20 mx-auto mb-3" />
          <div className="text-white/50">No tenants found</div>
        </GlassCard>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {tenants.map((t: D) => (
            <GlassCard key={t.tenant_id ?? t.id} className="py-4">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <StatusDot status={statusMap(t.status ?? 'active')} pulse />
                  <span className="text-base font-semibold">{t.name ?? t.tenant_id}</span>
                </div>
                <span className="text-xs px-2 py-0.5 rounded-full font-medium" style={{
                  backgroundColor: `${planColor(t.plan ?? '')}20`,
                  color: planColor(t.plan ?? ''),
                }}>{t.plan}</span>
              </div>

              <div className="grid grid-cols-2 gap-2 mb-3">
                <MetricBadge label="Tenant ID" value={t.tenant_id ?? t.id ?? '-'} color="#6366F1" />
                <MetricBadge label="Status" value={t.status ?? 'active'} color={t.status === 'active' ? '#34D399' : '#F59E0B'} />
              </div>

              {t.config && (
                <div className="text-xs text-white/30 space-y-1">
                  {t.config.max_connections && <div>Max connections: {t.config.max_connections}</div>}
                  {t.config.storage_limit_gb && <div>Storage limit: {t.config.storage_limit_gb} GB</div>}
                  {t.config.rate_limit_rps && <div>Rate limit: {t.config.rate_limit_rps} RPS</div>}
                </div>
              )}

              <div className="flex items-center gap-2 mt-3 pt-2 border-t border-white/5">
                <Shield className="w-3 h-3 text-emerald-400" />
                <span className="text-[10px] text-white/30">Row-Level Security · Per-tenant encryption · Isolated schemas</span>
              </div>
            </GlassCard>
          ))}
        </div>
      )}
    </AppShell>
  );
}
