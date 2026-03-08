'use client';

import { useState, useEffect, useCallback } from 'react';
import { Activity, RefreshCw, CheckCircle, AlertTriangle, XCircle, Server, Database, Cpu, HardDrive } from 'lucide-react';
import { superadminApi } from '@/lib/api';
import { useTranslation } from '@/lib/i18n';

const STATUS_CONFIG: Record<string, { icon: any; color: string; bg: string }> = {
  healthy: { icon: CheckCircle, color: 'text-green-400', bg: 'bg-green-500/10' },
  degraded: { icon: AlertTriangle, color: 'text-amber-400', bg: 'bg-amber-500/10' },
  unhealthy: { icon: XCircle, color: 'text-red-400', bg: 'bg-red-500/10' },
  unknown: { icon: AlertTriangle, color: 'text-white/30', bg: 'bg-white/5' },
};

export default function HealthPage() {
  const { t } = useTranslation();
  const [health, setHealth] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const res = await superadminApi.getUnifiedHealth();
      setHealth(res);
    } catch { /* silent */ }
    setLoading(false);
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  const overallStatus = health?.overall_status || 'unknown';
  const cfg = STATUS_CONFIG[overallStatus] || STATUS_CONFIG.unknown;
  const OverallIcon = cfg.icon;

  const engines = health?.engines || {};
  const subsystems = health?.subsystems || {};
  const uptime = health?.uptime_seconds ? Math.floor(health.uptime_seconds / 3600) : 0;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-teal-500/20 flex items-center justify-center">
            <Activity className="w-5 h-5 text-teal-400" />
          </div>
          <div>
            <h1 className="text-xl font-bold">{t('health.title')}</h1>
            <p className="text-xs text-white/40">{t('health.subtitle')}</p>
          </div>
        </div>
        <button onClick={loadData} disabled={loading}
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg glass text-xs text-white/60 hover:text-white transition">
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} /> {t('common.refresh')}
        </button>
      </div>

      {/* Overall Status */}
      <div className={`glass rounded-xl p-6 border border-white/5 flex items-center gap-4 ${cfg.bg}`}>
        <OverallIcon className={`w-10 h-10 ${cfg.color}`} />
        <div>
          <div className="text-xs text-white/40 mb-1">{t('health.overallStatus')}</div>
          <div className={`text-2xl font-bold capitalize ${cfg.color}`}>{overallStatus}</div>
        </div>
        <div className="ml-auto text-right">
          <div className="text-xs text-white/40">{t('health.uptime')}</div>
          <div className="text-lg font-bold">{uptime}h</div>
        </div>
      </div>

      {/* Engines */}
      <div className="glass rounded-xl p-5 border border-white/5">
        <h3 className="text-sm font-medium mb-4 flex items-center gap-2">
          <Database className="w-4 h-4 text-blue-400" /> {t('health.storageEngines')}
        </h3>
        {Object.keys(engines).length === 0 ? (
          <p className="text-xs text-white/30">{t('health.noEngineData')}</p>
        ) : (
          <div className="grid grid-cols-2 gap-3">
            {Object.entries(engines).map(([name, data]: [string, any]) => {
              const s = typeof data === 'object' ? (data.status || 'unknown') : (data || 'unknown');
              const sc = STATUS_CONFIG[s] || STATUS_CONFIG.unknown;
              const Icon = sc.icon;
              return (
                <div key={name} className={`flex items-center gap-3 p-3 rounded-lg ${sc.bg}`}>
                  <Icon className={`w-4 h-4 ${sc.color}`} />
                  <div className="flex-1">
                    <div className="text-xs font-medium capitalize">{name.replace(/_/g, ' ')}</div>
                    <div className="text-[10px] text-white/30 capitalize">{s}</div>
                  </div>
                  {typeof data === 'object' && data.details && (
                    <span className="text-[10px] text-white/20">{data.details}</span>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Subsystems */}
      <div className="glass rounded-xl p-5 border border-white/5">
        <h3 className="text-sm font-medium mb-4 flex items-center gap-2">
          <Server className="w-4 h-4 text-purple-400" /> {t('health.subsystems')}
        </h3>
        {Object.keys(subsystems).length === 0 ? (
          <p className="text-xs text-white/30">{t('health.noSubsystemData')}</p>
        ) : (
          <div className="grid grid-cols-2 gap-3">
            {Object.entries(subsystems).map(([name, data]: [string, any]) => {
              const s = typeof data === 'object' ? (data.status || 'unknown') : (data || 'unknown');
              const sc = STATUS_CONFIG[s] || STATUS_CONFIG.unknown;
              const Icon = sc.icon;
              return (
                <div key={name} className={`flex items-center gap-3 p-3 rounded-lg ${sc.bg}`}>
                  <Icon className={`w-4 h-4 ${sc.color}`} />
                  <div className="flex-1">
                    <div className="text-xs font-medium capitalize">{name.replace(/_/g, ' ')}</div>
                    <div className="text-[10px] text-white/30 capitalize">{s}</div>
                  </div>
                  {typeof data === 'object' && data.count !== undefined && (
                    <span className="text-[10px] text-white/30">{data.count} {t('common.items')}</span>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Raw Health Data */}
      {health && (
        <details className="glass rounded-xl p-5 border border-white/5">
          <summary className="text-xs text-white/40 cursor-pointer hover:text-white/60 transition">
            {t('health.rawHealthData')}
          </summary>
          <pre className="mt-3 text-[10px] text-white/30 overflow-x-auto max-h-64 overflow-y-auto">
            {JSON.stringify(health, null, 2)}
          </pre>
        </details>
      )}
    </div>
  );
}
