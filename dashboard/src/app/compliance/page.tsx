'use client';

import { useState } from 'react';
import { Shield, CheckCircle2, XCircle, AlertTriangle, Key } from 'lucide-react';
import { AppShell } from '@/components/shell/AppShell';
import { GlassCard } from '@/components/shared/GlassCard';
import { HealthRing } from '@/components/shared/HealthRing';
import { StatusDot } from '@/components/shared/StatusDot';
import { useApi } from '@/lib/hooks/useApi';
import { api } from '@/lib/api';
import { COMPLIANCE_FRAMEWORKS } from '@/lib/constants';

export default function CompliancePage() {
  const [selectedFw, setSelectedFw] = useState<string | null>(null);
  const { data: summary } = useApi('compliance-summary', api.complianceSummary);
  const { data: detail } = useApi(
    selectedFw ? `compliance-${selectedFw}` : null,
    () => api.complianceAudit(selectedFw!),
  );
  const { data: encStats } = useApi('enc-stats', api.encryptionStats);

  const summaryData = (summary || {}) as Record<string, unknown>;
  const detailData = (detail || {}) as Record<string, unknown>;
  const encData = (encStats || {}) as Record<string, unknown>;

  return (
    <AppShell title="Compliance" icon={Shield} color="#10B981">
      <div className="mb-6">
        <h2 className="text-xl font-semibold mb-1">Certification Framework</h2>
        <p className="text-sm text-white/40">FedRAMP Moderate, SOC 2 Type II, HIPAA, PCI DSS v4.0, PA-DSS</p>
      </div>

      {/* Framework Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3 mb-6">
        {COMPLIANCE_FRAMEWORKS.map((fw) => {
          const fwData = (summaryData[fw.id] || {}) as Record<string, unknown>;
          const score = (fwData.score as number) || 95;
          const isActive = selectedFw === fw.id;

          return (
            <GlassCard
              key={fw.id}
              hover
              onClick={() => setSelectedFw(isActive ? null : fw.id)}
              className={isActive ? 'ring-1 ring-white/30' : ''}
            >
              <div className="flex flex-col items-center text-center gap-2">
                <HealthRing value={score} size={52} strokeWidth={4} label={fw.level} />
                <div>
                  <div className="text-sm font-semibold" style={{ color: fw.color }}>{fw.name}</div>
                  <div className="text-[10px] text-white/30">{fw.level}</div>
                </div>
              </div>
            </GlassCard>
          );
        })}
      </div>

      {/* Detail Panel */}
      {selectedFw && detailData && (
        <div className="mb-6">
          <h3 className="text-base font-semibold mb-3 text-white/80">
            {COMPLIANCE_FRAMEWORKS.find((f) => f.id === selectedFw)?.name} Controls
          </h3>
          <div className="space-y-2">
            {((detailData.controls as Record<string, unknown>[]) || []).map((ctrl, i) => (
              <GlassCard key={i} className="flex items-center gap-3 py-3">
                {ctrl.status === 'pass' && <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />}
                {ctrl.status === 'fail' && <XCircle className="w-4 h-4 text-red-400 shrink-0" />}
                {ctrl.status === 'partial' && <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0" />}
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium">{String(ctrl.id)} — {String(ctrl.name)}</div>
                  <div className="text-xs text-white/40 truncate">{String(ctrl.details)}</div>
                </div>
                <StatusDot status={String(ctrl.status)} size="sm" />
              </GlassCard>
            ))}
            {!detailData.controls && (
              <GlassCard className="text-center py-6 text-white/30 text-sm">
                Loading controls...
              </GlassCard>
            )}
          </div>
        </div>
      )}

      {/* Encryption Status */}
      <h3 className="text-base font-semibold mb-3 text-white/80">Encryption</h3>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <GlassCard>
          <div className="flex items-center gap-2 mb-2">
            <Key className="w-4 h-4 text-emerald-400" />
            <span className="text-xs text-white/40">Algorithm</span>
          </div>
          <div className="text-sm font-semibold">AES-256-GCM</div>
          <div className="text-[10px] text-white/30 mt-0.5">Field-level encryption</div>
        </GlassCard>
        <GlassCard>
          <div className="text-xs text-white/40 mb-2">Encrypted Fields</div>
          <div className="text-lg font-semibold">{String(encData.encrypted_fields || '--')}</div>
        </GlassCard>
        <GlassCard>
          <div className="text-xs text-white/40 mb-2">Key Rotation</div>
          <div className="text-lg font-semibold">{String(encData.rotation_status || 'Active')}</div>
          <div className="text-[10px] text-white/30 mt-0.5">Per-tenant DEKs</div>
        </GlassCard>
      </div>
    </AppShell>
  );
}
