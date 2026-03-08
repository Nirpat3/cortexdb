'use client';

import { useState, useEffect, useCallback } from 'react';
import { TrendingDown, DollarSign, Zap, ListChecks, RefreshCw, CheckCircle, ToggleLeft, ToggleRight } from 'lucide-react';
import { superadminApi } from '@/lib/api';
import { useTranslation } from '@/lib/i18n';

export default function CostOptimizerPage() {
  const { t } = useTranslation();
  const [report, setReport] = useState<any>(null);
  const [providers, setProviders] = useState<Record<string, number>>({});
  const [savings, setSavings] = useState<any>(null);
  const [changes, setChanges] = useState<any[] | null>(null);
  const [dryRun, setDryRun] = useState(true);
  const [loading, setLoading] = useState(true);
  const [applying, setApplying] = useState(false);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [r, p, s] = await Promise.allSettled([
        superadminApi.getCostOptimizationReport(),
        superadminApi.getProviderCosts(),
        superadminApi.getPotentialSavings(),
      ]);
      if (r.status === 'fulfilled') setReport(r.value);
      if (p.status === 'fulfilled') setProviders((p.value as any).providers || {});
      if (s.status === 'fulfilled') setSavings(s.value);
    } catch { /* silent */ }
    setLoading(false);
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  const handleApply = async () => {
    setApplying(true);
    try {
      const result = await superadminApi.applyCostOptimizations(dryRun);
      setChanges((result as any).changes || []);
    } catch { /* silent */ }
    setApplying(false);
  };

  const recs = report?.recommendations || {};
  const recCount = report?.recommendation_count || Object.keys(recs).length;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-emerald-500/20 flex items-center justify-center">
            <TrendingDown className="w-5 h-5 text-emerald-400" />
          </div>
          <div>
            <h1 className="text-xl font-bold">{t('costOptimizer.title')}</h1>
            <p className="text-xs text-white/40">{t('costOptimizer.subtitle')}</p>
          </div>
        </div>
        <button onClick={loadData} disabled={loading}
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg glass text-xs text-white/60 hover:text-white transition">
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} /> {t('common.refresh')}
        </button>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-4 gap-4">
        {[
          { label: 'Current Total Cost', value: `$${(report?.current_total_cost || 0).toFixed(4)}`, icon: DollarSign, color: 'text-green-400' },
          { label: 'Potential Savings', value: `$${(report?.potential_savings || 0).toFixed(4)}`, icon: TrendingDown, color: 'text-emerald-400' },
          { label: 'Savings %', value: `${(savings?.savings_pct || 0).toFixed(1)}%`, icon: Zap, color: 'text-amber-400' },
          { label: 'Recommendations', value: recCount, icon: ListChecks, color: 'text-cyan-400' },
        ].map((kpi) => (
          <div key={kpi.label} className="bg-white/5 border border-white/10 rounded-xl p-4">
            <div className="flex items-center gap-2 text-xs text-white/40 mb-2">
              <kpi.icon className="w-3.5 h-3.5" /> {kpi.label}
            </div>
            <div className={`text-2xl font-bold ${kpi.color}`}>{kpi.value}</div>
          </div>
        ))}
      </div>

      {/* Provider Pricing Table */}
      <div className="bg-white/5 border border-white/10 rounded-xl p-5">
        <h3 className="text-sm font-medium mb-4">Provider Pricing (per 1M tokens)</h3>
        {Object.keys(providers).length === 0 ? (
          <p className="text-xs text-white/30">{t('common.noData')}</p>
        ) : (
          <div className="space-y-2">
            {Object.entries(providers).map(([name, cost]) => (
              <div key={name} className="flex items-center justify-between py-1.5 border-b border-white/5 last:border-0">
                <span className="text-xs font-medium capitalize">{name}</span>
                <span className={`text-sm font-bold ${cost === 0 ? 'text-emerald-400' : 'text-green-400'}`}>
                  {cost === 0 ? 'Free' : `$${cost.toFixed(2)}`}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Recommendations Grid */}
      <div>
        <h3 className="text-sm font-medium mb-3">Recommendations by Category</h3>
        {Object.keys(recs).length === 0 ? (
          <p className="text-xs text-white/30">No recommendations yet</p>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {Object.entries(recs).map(([category, rec]: [string, any]) => (
              <div key={category} className="bg-white/5 border border-white/10 rounded-xl p-4">
                <div className="text-xs text-white/40 mb-1 uppercase tracking-wider">{category}</div>
                <div className="text-sm font-medium capitalize">{rec.provider} / {rec.model}</div>
                <div className="flex items-center justify-between mt-3">
                  <span className="text-[10px] text-white/30">Avg Grade: {rec.avg_grade}</span>
                  {rec.cost_per_1m === 0 ? (
                    <span className="text-[10px] px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-400 font-medium">Free</span>
                  ) : (
                    <span className="text-xs text-green-400 font-bold">${rec.cost_per_1m?.toFixed(2)}/1M</span>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Apply Optimizations */}
      <div className="bg-white/5 border border-white/10 rounded-xl p-5 space-y-4">
        <h3 className="text-sm font-medium">Apply Optimizations</h3>
        <div className="flex items-center gap-4">
          <button onClick={() => setDryRun(!dryRun)} className="flex items-center gap-2 text-xs text-white/60 hover:text-white transition">
            {dryRun ? <ToggleLeft className="w-5 h-5 text-amber-400" /> : <ToggleRight className="w-5 h-5 text-emerald-400" />}
            Dry Run: {dryRun ? 'ON' : 'OFF'}
          </button>
          <button onClick={handleApply} disabled={applying}
            className="px-4 py-1.5 rounded-lg bg-emerald-500/20 text-emerald-400 text-xs font-medium hover:bg-emerald-500/30 transition disabled:opacity-50">
            {applying ? 'Applying...' : 'Apply'}
          </button>
        </div>
        {changes && (
          <div className="space-y-2 mt-2">
            {changes.map((c: any, i: number) => (
              <div key={i} className="flex items-center justify-between py-1.5 border-b border-white/5 last:border-0 text-xs">
                <div className="flex items-center gap-2">
                  <CheckCircle className="w-3.5 h-3.5 text-emerald-400" />
                  <span className="text-white/60 uppercase">{c.category}</span>
                  <span className="text-white/40">-&gt;</span>
                  <span className="capitalize">{c.recommended_provider} / {c.model}</span>
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-white/30">Q: {c.expected_quality}</span>
                  <span className={`px-1.5 py-0.5 rounded text-[10px] ${c.applied ? 'bg-emerald-500/20 text-emerald-400' : 'bg-amber-500/20 text-amber-400'}`}>
                    {c.applied ? 'Applied' : 'Dry Run'}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Savings Summary */}
      {savings && savings.potential_savings > 0 && (
        <div className="bg-emerald-500/10 border border-emerald-500/20 rounded-xl p-5 flex items-center justify-between">
          <div>
            <div className="text-xs text-emerald-400/60 mb-1">Estimated Monthly Savings</div>
            <div className="text-2xl font-bold text-emerald-400">${savings.potential_savings.toFixed(4)}</div>
          </div>
          <div className="text-right">
            <div className="text-xs text-white/30 mb-1">Current vs Optimized</div>
            <div className="text-sm">
              <span className="text-white/40">${savings.current_cost?.toFixed(4)}</span>
              <span className="text-white/20 mx-2">-&gt;</span>
              <span className="text-emerald-400">${(savings.current_cost - savings.potential_savings).toFixed(4)}</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
