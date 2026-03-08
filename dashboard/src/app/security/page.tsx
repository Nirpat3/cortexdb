'use client';

import { useState, useEffect, useCallback } from 'react';
import { Shield, AlertTriangle, Ban, Key, Eye, Clock, RefreshCw, ShieldCheck } from 'lucide-react';
import { AppShell } from '@/components/shell/AppShell';
import { GlassCard } from '@/components/shared/GlassCard';
import { HealthRing } from '@/components/shared/HealthRing';
import { MetricBadge } from '@/components/shared/MetricBadge';
import { api } from '@/lib/api';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type D = Record<string, any>;

export default function SecurityPage() {
  const [overview, setOverview] = useState<D | null>(null);
  const [threats, setThreats] = useState<D[]>([]);
  const [auditLog, setAuditLog] = useState<D[]>([]);
  const [activeTab, setActiveTab] = useState<'overview' | 'threats' | 'audit' | 'encryption'>('overview');

  const refresh = useCallback(async () => {
    try {
      const [o, t, a] = await Promise.all([
        api.securityOverview().catch(() => null),
        api.securityThreats().catch(() => null),
        api.securityAudit().catch(() => null),
      ]);
      if (o) setOverview(o);
      if (t) setThreats((t as D).threats ?? []);
      if (a) setAuditLog((a as D).entries ?? []);
    } catch { /* silent */ }
  }, []);

  useEffect(() => {
    refresh();
    const iv = setInterval(refresh, 10000);
    return () => clearInterval(iv);
  }, [refresh]);

  const tabs = ['overview', 'threats', 'audit', 'encryption'] as const;
  const enc = overview?.encryption ?? {};
  const scan = overview?.scan_results ?? {};
  const comp = overview?.compliance_status ?? {};

  return (
    <AppShell title="Security" icon={Shield} color="#EF4444">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-xl font-semibold mb-1">Security Center</h2>
          <p className="text-sm text-white/40">Real-time threat detection from Security Agent</p>
        </div>
        <button onClick={refresh} className="glass px-3 py-1.5 rounded-lg text-xs text-white/60 hover:text-white/90 transition">
          <RefreshCw className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* Tabs */}
      <div className="flex gap-2 mb-6 overflow-x-auto">
        {tabs.map((tab) => (
          <button key={tab} onClick={() => setActiveTab(tab)}
            className={`px-4 py-2 rounded-xl text-sm font-medium capitalize whitespace-nowrap transition ${activeTab === tab ? 'glass-heavy text-white' : 'glass text-white/50 hover:text-white/80'}`}>
            {tab}
          </button>
        ))}
      </div>

      {activeTab === 'overview' && overview && (
        <>
          {/* Security Score */}
          <div className="grid grid-cols-2 sm:grid-cols-[160px_1fr] gap-4 mb-6">
            <GlassCard className="flex flex-col items-center py-4">
              <HealthRing value={overview.security_score ?? 0} size={90} strokeWidth={7} label="Score" />
            </GlassCard>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
              <GlassCard>
                <MetricBadge label="Threat Level" value={overview.threat_level ?? '-'} color={
                  overview.threat_level === 'Low' ? '#34D399' : overview.threat_level === 'Medium' ? '#F59E0B' : '#EF4444'
                } />
              </GlassCard>
              <GlassCard><MetricBadge label="Threats (24h)" value={String(overview.threats_24h ?? 0)} color="#EF4444" /></GlassCard>
              <GlassCard><MetricBadge label="Blocked Today" value={String(overview.blocked_today ?? 0)} color="#3B82F6" /></GlassCard>
              <GlassCard><MetricBadge label="Blocked IPs" value={String(overview.blocked_ips ?? 0)} color="#F59E0B" /></GlassCard>
              <GlassCard><MetricBadge label="Active Sessions" value={String(overview.active_sessions ?? 0)} color="#8B5CF6" /></GlassCard>
              <GlassCard><MetricBadge label="Failed Logins" value={String(overview.failed_logins_24h ?? 0)} color="#EC4899" /></GlassCard>
            </div>
          </div>

          {/* Vulnerability Scan */}
          <h3 className="text-base font-semibold mb-3 text-white/80"><Eye className="w-4 h-4 inline mr-1.5" />Vulnerability Scan</h3>
          <div className="grid grid-cols-3 sm:grid-cols-5 gap-3 mb-6">
            {Object.entries(scan.vulnerabilities ?? {}).map(([level, count]) => (
              <GlassCard key={level}>
                <MetricBadge label={level} value={String(count)} color={
                  level === 'critical' ? '#EF4444' : level === 'high' ? '#F59E0B' : level === 'medium' ? '#FBBF24' : '#34D399'
                } />
              </GlassCard>
            ))}
          </div>

          {/* Compliance */}
          <h3 className="text-base font-semibold mb-3 text-white/80"><ShieldCheck className="w-4 h-4 inline mr-1.5" />Compliance Status</h3>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
            {Object.entries(comp).map(([fw, status]) => (
              <GlassCard key={fw}>
                <div className="text-sm font-medium uppercase mb-1">{fw}</div>
                <div className={`text-xs ${status === 'compliant' ? 'text-emerald-400' : 'text-amber-400'}`}>
                  {String(status)}
                </div>
              </GlassCard>
            ))}
          </div>
        </>
      )}

      {activeTab === 'threats' && (
        <div className="space-y-2">
          {threats.map((t: D, i: number) => {
            const sevColor = t.severity === 'critical' ? 'text-red-400 border-red-500/30' :
              t.severity === 'high' ? 'text-amber-400 border-amber-500/30' :
              t.severity === 'medium' ? 'text-yellow-400 border-yellow-500/20' : 'text-white/50 border-white/5';
            return (
              <GlassCard key={i} className={`py-3 border ${sevColor.split(' ')[1]}`}>
                <div className="flex items-center justify-between mb-1">
                  <div className="flex items-center gap-2">
                    <AlertTriangle className={`w-4 h-4 ${sevColor.split(' ')[0]}`} />
                    <span className="text-sm font-medium">{t.category?.replace(/_/g, ' ')}</span>
                    <span className={`text-xs px-1.5 py-0.5 rounded ${sevColor.split(' ')[0]}`}>{t.severity}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className={`text-xs px-1.5 py-0.5 rounded ${t.action_taken === 'blocked' ? 'bg-red-500/20 text-red-300' : t.action_taken === 'flagged' ? 'bg-amber-500/20 text-amber-300' : 'bg-white/10 text-white/50'}`}>
                      {t.action_taken}
                    </span>
                  </div>
                </div>
                <div className="text-sm text-white/70 mb-1">{t.description}</div>
                <div className="flex items-center gap-3 text-[10px] text-white/30">
                  <span>{t.source_ip}</span>
                  <span>{t.target}</span>
                  <span>{t.timestamp ? new Date(t.timestamp * 1000).toLocaleString() : ''}</span>
                </div>
              </GlassCard>
            );
          })}
        </div>
      )}

      {activeTab === 'audit' && (
        <div className="space-y-2">
          {auditLog.map((e: D, i: number) => (
            <GlassCard key={i} className="py-2.5">
              <div className="flex items-center justify-between mb-1">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-mono text-white/40">{e.entry_id}</span>
                  <span className="text-sm font-medium">{e.action}</span>
                </div>
                <span className={`text-xs px-1.5 py-0.5 rounded ${e.outcome === 'success' ? 'bg-emerald-500/20 text-emerald-300' : e.outcome === 'denied' ? 'bg-red-500/20 text-red-300' : 'bg-amber-500/20 text-amber-300'}`}>
                  {e.outcome}
                </span>
              </div>
              <div className="text-xs text-white/50">{e.details}</div>
              <div className="flex items-center gap-3 text-[10px] text-white/30 mt-1">
                <span>{e.actor}</span>
                <span>{e.resource}</span>
                <span>{e.ip_address}</span>
                <span>{e.timestamp ? new Date(e.timestamp * 1000).toLocaleString() : ''}</span>
              </div>
            </GlassCard>
          ))}
        </div>
      )}

      {activeTab === 'encryption' && overview && (
        <>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 mb-6">
            <GlassCard><MetricBadge label="TLS Version" value={enc.tls_version ?? '-'} color="#3B82F6" /></GlassCard>
            <GlassCard><MetricBadge label="Cipher" value={enc.cipher_suite ?? '-'} color="#8B5CF6" /></GlassCard>
            <GlassCard><MetricBadge label="Data at Rest" value={enc.data_at_rest ?? '-'} color="#34D399" /></GlassCard>
            <GlassCard>
              <Key className="w-4 h-4 text-amber-400 mb-1" />
              <MetricBadge label="Key Rotation" value={`${enc.key_rotation_days ?? '-'} days`} color="#F59E0B" />
            </GlassCard>
            <GlassCard>
              <MetricBadge label="Certificates" value={enc.certificates_valid ? 'Valid' : 'Expired'} color={enc.certificates_valid ? '#34D399' : '#EF4444'} />
            </GlassCard>
            <GlassCard><MetricBadge label="Patches Pending" value={String(scan.patches_pending ?? 0)} color="#FBBF24" /></GlassCard>
          </div>
        </>
      )}
    </AppShell>
  );
}
