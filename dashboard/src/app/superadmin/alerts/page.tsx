'use client';

import { useState, useEffect, useCallback } from 'react';
import { Bell, AlertTriangle, CheckCircle, Info, Filter } from 'lucide-react';
import { superadminApi } from '@/lib/api';
import { useTranslation } from '@/lib/i18n';

const SEV_CONFIG: Record<string, { icon: any; color: string; bg: string; badge: string }> = {
  critical: { icon: AlertTriangle, color: 'text-red-400', bg: 'bg-red-500/10', badge: 'bg-red-500/20 text-red-400' },
  warning:  { icon: AlertTriangle, color: 'text-amber-400', bg: 'bg-amber-500/10', badge: 'bg-amber-500/20 text-amber-400' },
  info:     { icon: Info, color: 'text-blue-400', bg: 'bg-blue-500/10', badge: 'bg-blue-500/20 text-blue-400' },
};

export default function AlertsPage() {
  const { t } = useTranslation();
  const [summary, setSummary] = useState<any>(null);
  const [alerts, setAlerts] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [severity, setSeverity] = useState('all');
  const [unackedOnly, setUnackedOnly] = useState(false);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [sum, list] = await Promise.all([
        superadminApi.getAlertSummary(),
        superadminApi.getAlerts(
          severity !== 'all' ? severity : undefined,
          unackedOnly || undefined,
        ),
      ]);
      setSummary(sum);
      setAlerts(Array.isArray(list) ? list : (list as any)?.alerts ?? []);
    } catch { /* silent */ }
    setLoading(false);
  }, [severity, unackedOnly]);

  useEffect(() => { loadData(); }, [loadData]);

  const handleAck = async (id: string) => {
    try { await superadminApi.acknowledgeAlert(id); await loadData(); } catch { /* silent */ }
  };

  const handleAckAll = async () => {
    try { await superadminApi.acknowledgeAllAlerts(); await loadData(); } catch { /* silent */ }
  };

  const bySeverity = summary?.by_severity ?? {};
  const total = summary?.total ?? alerts.length;
  const unacked = summary?.unacknowledged ?? 0;

  const fmtTime = (ts: string | number) => {
    try { return new Date(ts).toLocaleString(); } catch { return String(ts); }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-orange-500/20 flex items-center justify-center">
            <Bell className="w-5 h-5 text-orange-400" />
          </div>
          <div>
            <h1 className="text-xl font-bold">{t('alerts.title')}</h1>
            <p className="text-xs text-white/40">{t('alerts.subtitle')}</p>
          </div>
        </div>
      </div>

      {/* Summary Bar */}
      <div className="bg-white/5 border border-white/10 rounded-xl p-4 flex flex-wrap items-center gap-4">
        <div className="text-sm">
          <span className="text-white/40">Total:</span>{' '}
          <span className="font-bold">{total}</span>
        </div>
        <div className="text-sm">
          <span className="text-white/40">Unacknowledged:</span>{' '}
          <span className="font-bold text-orange-400">{unacked}</span>
        </div>
        <div className="flex items-center gap-2 ml-auto">
          {(['critical', 'warning', 'info'] as const).map((s) => (
            <span key={s} className={`text-[11px] px-2 py-0.5 rounded-full font-medium ${SEV_CONFIG[s].badge}`}>
              {s}: {bySeverity[s] ?? 0}
            </span>
          ))}
        </div>
      </div>

      {/* Filters + Ack All */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2">
          <Filter className="w-3.5 h-3.5 text-white/40" />
          <select value={severity} onChange={(e) => setSeverity(e.target.value)}
            className="bg-white/5 border border-white/10 rounded-lg px-3 py-1.5 text-xs focus:outline-none">
            <option value="all">{t('common.all')} Severities</option>
            <option value="critical">Critical</option>
            <option value="warning">Warning</option>
            <option value="info">Info</option>
          </select>
        </div>
        <label className="flex items-center gap-2 text-xs text-white/60 cursor-pointer select-none">
          <input type="checkbox" checked={unackedOnly} onChange={(e) => setUnackedOnly(e.target.checked)}
            className="accent-orange-500 w-3.5 h-3.5" />
          Unacknowledged only
        </label>
        <button onClick={handleAckAll}
          className="ml-auto flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-green-500/20 text-green-400 text-xs font-medium hover:bg-green-500/30 transition">
          <CheckCircle className="w-3.5 h-3.5" /> Acknowledge All
        </button>
      </div>

      {/* Alert List */}
      {loading ? (
        <div className="text-center py-16 text-white/30 text-sm">{t('common.loading')}</div>
      ) : alerts.length === 0 ? (
        <div className="bg-white/5 border border-white/10 rounded-xl p-12 text-center">
          <Bell className="w-10 h-10 text-white/10 mx-auto mb-3" />
          <p className="text-sm text-white/30">{t('common.noData')}</p>
        </div>
      ) : (
        <div className="space-y-3">
          {alerts.map((alert: any) => {
            const sev = alert.severity || 'info';
            const cfg = SEV_CONFIG[sev] || SEV_CONFIG.info;
            const Icon = cfg.icon;
            const acked = !!alert.acknowledged_at;
            const details = alert.details && typeof alert.details === 'object' ? alert.details : null;

            return (
              <div key={alert.id} className={`bg-white/5 border border-white/10 rounded-xl p-4 ${cfg.bg}`}>
                <div className="flex items-start gap-3">
                  <Icon className={`w-5 h-5 mt-0.5 shrink-0 ${cfg.color}`} />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap mb-1">
                      <span className="text-sm font-medium">{alert.title || 'Untitled Alert'}</span>
                      <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${cfg.badge}`}>{sev}</span>
                      {alert.type && (
                        <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-white/10 text-white/50">
                          {alert.type}
                        </span>
                      )}
                    </div>
                    <div className="text-[11px] text-white/30 mb-2">{fmtTime(alert.created_at)}</div>
                    {details && (
                      <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-[11px] mt-1">
                        {Object.entries(details).map(([k, v]) => (
                          <div key={k} className="flex gap-1">
                            <span className="text-white/30">{k}:</span>
                            <span className="text-white/60 truncate">{String(v)}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                  <div className="shrink-0">
                    {acked ? (
                      <span className="flex items-center gap-1 text-[11px] text-green-400">
                        <CheckCircle className="w-3.5 h-3.5" /> Acked
                      </span>
                    ) : (
                      <button onClick={() => handleAck(alert.id)}
                        className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-green-500/20 text-green-400 text-[11px] font-medium hover:bg-green-500/30 transition">
                        <CheckCircle className="w-3.5 h-3.5" /> Ack
                      </button>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
