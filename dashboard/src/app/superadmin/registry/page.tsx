'use client';

import { useEffect, useState, useCallback } from 'react';
import { Layers, RefreshCw, Bot, Activity } from 'lucide-react';
import { superadminApi } from '@/lib/api';
import { useTranslation } from '@/lib/i18n';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type D = Record<string, any>;

const STATUS_COLORS: Record<string, string> = {
  active: 'bg-emerald-500/20 text-emerald-300',
  running: 'bg-blue-500/20 text-blue-300',
  idle: 'bg-white/10 text-white/40',
  error: 'bg-red-500/20 text-red-300',
  stopped: 'bg-red-500/10 text-red-400/50',
};

export default function UnifiedRegistryPage() {
  const { t } = useTranslation();
  const [agents, setAgents] = useState<D[]>([]);
  const [summary, setSummary] = useState<D>({});
  const [filter, setFilter] = useState('all');

  const refresh = useCallback(async () => {
    try {
      const data = await superadminApi.getUnifiedRegistry();
      setAgents((data as D).agents ?? []);
      setSummary((data as D).summary ?? {});
    } catch { /* silent */ }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const categories = [...new Set(agents.map((a: D) => a.category))];

  const filtered = filter === 'all' ? agents : agents.filter((a: D) => a.category === filter);

  // Separate by type: AGT-* (monitoring) vs CDB-* (team)
  const monitoringAgents = filtered.filter((a: D) => a.agent_id.startsWith('AGT-'));
  const teamAgents = filtered.filter((a: D) => a.agent_id.startsWith('CDB-'));

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold mb-1 flex items-center gap-2">
            <Layers className="w-6 h-6 text-cyan-400" /> {t('registry.title')}
          </h1>
          <p className="text-sm text-white/40">{t('registry.subtitle')}</p>
        </div>
        <button onClick={refresh} className="glass px-3 py-2 rounded-lg text-xs text-white/60 hover:text-white/90">
          <RefreshCw className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* Summary */}
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 mb-6">
        <div className="glass rounded-xl p-3">
          <div className="text-xs text-white/40">Total Agents</div>
          <div className="text-2xl font-bold">{summary.total_agents ?? 0}</div>
        </div>
        <div className="glass rounded-xl p-3">
          <div className="text-xs text-white/40">Active</div>
          <div className="text-2xl font-bold text-emerald-400">{summary.active ?? 0}</div>
        </div>
        <div className="glass rounded-xl p-3">
          <div className="text-xs text-white/40">Idle</div>
          <div className="text-2xl font-bold text-white/40">{summary.idle ?? 0}</div>
        </div>
        <div className="glass rounded-xl p-3">
          <div className="text-xs text-white/40">Errors</div>
          <div className="text-2xl font-bold text-red-400">{summary.error ?? 0}</div>
        </div>
        <div className="glass rounded-xl p-3">
          <div className="text-xs text-white/40">Total Runs</div>
          <div className="text-2xl font-bold">{summary.total_runs ?? 0}</div>
        </div>
      </div>

      {/* Category Filter */}
      <div className="flex gap-2 mb-6 flex-wrap">
        <button onClick={() => setFilter('all')}
          className={`px-3 py-1.5 rounded-lg text-xs transition ${filter === 'all' ? 'glass-heavy text-white' : 'glass text-white/50 hover:text-white/80'}`}>
          {t('common.all')} ({agents.length})
        </button>
        {categories.map((c) => (
          <button key={c} onClick={() => setFilter(c)}
            className={`px-3 py-1.5 rounded-lg text-xs transition ${filter === c ? 'glass-heavy text-white' : 'glass text-white/50 hover:text-white/80'}`}>
            {c} ({agents.filter((a: D) => a.category === c).length})
          </button>
        ))}
      </div>

      {/* Monitoring Agents */}
      {monitoringAgents.length > 0 && (
        <div className="mb-8">
          <h2 className="text-lg font-semibold mb-3 flex items-center gap-2">
            <Activity className="w-5 h-5 text-blue-400" /> Monitoring Agents ({monitoringAgents.length})
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {monitoringAgents.map((a: D) => (
              <div key={a.agent_id} className="glass rounded-xl p-4">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <div className="w-8 h-8 rounded-lg bg-blue-500/20 flex items-center justify-center">
                      <Activity className="w-4 h-4 text-blue-400" />
                    </div>
                    <div>
                      <div className="text-sm font-semibold">{a.title}</div>
                      <div className="text-[10px] text-white/30 font-mono">{a.agent_id}</div>
                    </div>
                  </div>
                  <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${STATUS_COLORS[a.status] ?? ''}`}>{a.status}</span>
                </div>
                <div className="text-xs text-white/40 mb-2">{a.role}</div>
                <div className="grid grid-cols-3 gap-2 text-[10px]">
                  <div className="glass rounded p-1.5">
                    <div className="text-white/30">Runs</div>
                    <div className="font-bold">{a.run_count}</div>
                  </div>
                  <div className="glass rounded p-1.5">
                    <div className="text-white/30">Errors</div>
                    <div className="font-bold text-red-400">{a.errors}</div>
                  </div>
                  <div className="glass rounded p-1.5">
                    <div className="text-white/30">Avg ms</div>
                    <div className="font-bold">{a.avg_run_ms}</div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Team Agents */}
      {teamAgents.length > 0 && (
        <div>
          <h2 className="text-lg font-semibold mb-3 flex items-center gap-2">
            <Bot className="w-5 h-5 text-purple-400" /> Development Team ({teamAgents.length})
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {teamAgents.map((a: D) => (
              <div key={a.agent_id} className="glass rounded-xl p-4">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <div className="w-8 h-8 rounded-lg bg-purple-500/20 flex items-center justify-center">
                      <Bot className="w-4 h-4 text-purple-400" />
                    </div>
                    <div>
                      <div className="text-sm font-semibold">{a.title}</div>
                      <div className="text-[10px] text-white/30 font-mono">{a.agent_id}</div>
                    </div>
                  </div>
                  <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${STATUS_COLORS[a.status] ?? ''}`}>{a.status}</span>
                </div>
                <div className="text-xs text-white/40 mb-2">{a.role}</div>
                <div className="flex flex-wrap gap-1">
                  {(a.responsibilities ?? []).slice(0, 3).map((r: string, i: number) => (
                    <span key={i} className="text-[10px] px-1.5 py-0.5 rounded-full bg-white/5 text-white/40">{r}</span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
