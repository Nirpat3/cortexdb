'use client';

import { useState, useEffect, useCallback } from 'react';
import { DollarSign, BarChart3, RefreshCw, TrendingUp, Cpu, Users } from 'lucide-react';
import { superadminApi } from '@/lib/api';
import { useTranslation } from '@/lib/i18n';

export default function CostsPage() {
  const { t } = useTranslation();
  const [totals, setTotals] = useState<any>(null);
  const [recent, setRecent] = useState<any[]>([]);
  const [departments, setDepartments] = useState<any>({});
  const [loading, setLoading] = useState(true);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [t, r, d] = await Promise.allSettled([
        superadminApi.getCosts(),
        superadminApi.getRecentCosts(30),
        superadminApi.getDepartmentCosts(),
      ]);
      if (t.status === 'fulfilled') setTotals(t.value);
      if (r.status === 'fulfilled') setRecent((r.value as any).entries || []);
      if (d.status === 'fulfilled') setDepartments((d.value as any).departments || {});
    } catch { /* silent */ }
    setLoading(false);
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  const totalCost = totals?.total_cost || 0;
  const totalTokens = totals?.total_tokens || 0;
  const totalCalls = totals?.total_calls || 0;
  const byProvider = totals?.by_provider || {};

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-green-500/20 flex items-center justify-center">
            <DollarSign className="w-5 h-5 text-green-400" />
          </div>
          <div>
            <h1 className="text-xl font-bold">{t('costs.title')}</h1>
            <p className="text-xs text-white/40">{t('costs.subtitle')}</p>
          </div>
        </div>
        <button onClick={loadData} disabled={loading}
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg glass text-xs text-white/60 hover:text-white transition">
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} /> {t('common.refresh')}
        </button>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-4 gap-4">
        <div className="glass rounded-xl p-4 border border-white/5">
          <div className="text-xs text-white/40 mb-2">Total Cost</div>
          <div className="text-2xl font-bold text-green-400">${totalCost.toFixed(4)}</div>
        </div>
        <div className="glass rounded-xl p-4 border border-white/5">
          <div className="text-xs text-white/40 mb-2">Total Tokens</div>
          <div className="text-2xl font-bold">{totalTokens.toLocaleString()}</div>
        </div>
        <div className="glass rounded-xl p-4 border border-white/5">
          <div className="text-xs text-white/40 mb-2">Total Calls</div>
          <div className="text-2xl font-bold">{totalCalls}</div>
        </div>
        <div className="glass rounded-xl p-4 border border-white/5">
          <div className="text-xs text-white/40 mb-2">Avg Cost/Call</div>
          <div className="text-2xl font-bold">${totalCalls > 0 ? (totalCost / totalCalls).toFixed(4) : '0'}</div>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4">
        {/* By Provider */}
        <div className="glass rounded-xl p-5 border border-white/5">
          <h3 className="text-sm font-medium mb-4 flex items-center gap-2">
            <Cpu className="w-4 h-4 text-cyan-400" /> Cost by Provider
          </h3>
          {Object.keys(byProvider).length === 0 ? (
            <p className="text-xs text-white/30">{t('common.noData')}</p>
          ) : (
            <div className="space-y-3">
              {Object.entries(byProvider).map(([prov, data]: [string, any]) => (
                <div key={prov} className="flex items-center justify-between">
                  <div>
                    <div className="text-xs font-medium capitalize">{prov}</div>
                    <div className="text-[10px] text-white/30">{data.calls} calls | {data.tokens?.toLocaleString()} tokens</div>
                  </div>
                  <span className="text-sm font-bold text-green-400">${data.cost?.toFixed(4)}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* By Department */}
        <div className="glass rounded-xl p-5 border border-white/5">
          <h3 className="text-sm font-medium mb-4 flex items-center gap-2">
            <Users className="w-4 h-4 text-amber-400" /> Cost by Department
          </h3>
          {Object.keys(departments).length === 0 ? (
            <p className="text-xs text-white/30">{t('common.noData')}</p>
          ) : (
            <div className="space-y-3">
              {Object.entries(departments).map(([dept, data]: [string, any]) => (
                <div key={dept} className="flex items-center justify-between">
                  <div>
                    <div className="text-xs font-medium capitalize">{dept}</div>
                    <div className="text-[10px] text-white/30">{data.calls} calls | {data.tokens?.toLocaleString()} tokens</div>
                  </div>
                  <span className="text-sm font-bold text-green-400">${data.cost?.toFixed(4)}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Recent Log */}
      <div className="glass rounded-xl p-5 border border-white/5">
        <h3 className="text-sm font-medium mb-4 flex items-center gap-2">
          <TrendingUp className="w-4 h-4 text-purple-400" /> Recent LLM Calls
        </h3>
        {recent.length === 0 ? (
          <p className="text-xs text-white/30">No cost entries yet. Execute tasks or chat with agents to populate.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-white/30 border-b border-white/5">
                  <th className="text-left py-2 font-medium">Time</th>
                  <th className="text-left py-2 font-medium">Provider</th>
                  <th className="text-left py-2 font-medium">Model</th>
                  <th className="text-left py-2 font-medium">Agent</th>
                  <th className="text-right py-2 font-medium">In Tokens</th>
                  <th className="text-right py-2 font-medium">Out Tokens</th>
                  <th className="text-right py-2 font-medium">Cost</th>
                </tr>
              </thead>
              <tbody>
                {[...recent].reverse().map((entry: any, i: number) => (
                  <tr key={i} className="border-b border-white/5 hover:bg-white/5">
                    <td className="py-2 text-white/40">
                      {entry.timestamp ? new Date(entry.timestamp * 1000).toLocaleTimeString() : '-'}
                    </td>
                    <td className="py-2 text-white/60 capitalize">{entry.provider}</td>
                    <td className="py-2 text-white/50 max-w-[120px] truncate">{entry.model || 'default'}</td>
                    <td className="py-2 text-white/50 max-w-[100px] truncate">{entry.agent_id || '-'}</td>
                    <td className="py-2 text-right text-white/40">{entry.input_tokens?.toLocaleString()}</td>
                    <td className="py-2 text-right text-white/40">{entry.output_tokens?.toLocaleString()}</td>
                    <td className="py-2 text-right font-medium text-green-400">${entry.cost_usd?.toFixed(6)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
