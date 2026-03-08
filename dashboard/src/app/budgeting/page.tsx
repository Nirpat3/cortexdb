'use client';

import { useEffect, useState, useCallback } from 'react';
import {
  DollarSign, TrendingUp, TrendingDown, BarChart3, PieChart, CalendarDays,
  AlertTriangle, Brain, RefreshCw, Zap, ShieldAlert, ArrowRight, Activity,
} from 'lucide-react';
import { AppShell } from '@/components/shell/AppShell';
import { GlassCard } from '@/components/shared/GlassCard';
import { HealthRing } from '@/components/shared/HealthRing';
import { MetricBadge } from '@/components/shared/MetricBadge';
import { api } from '@/lib/api';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type AnyData = Record<string, any>;

function useBudgetData() {
  const [summary, setSummary] = useState<AnyData | null>(null);
  const [resources, setResources] = useState<AnyData[]>([]);
  const [tenants, setTenants] = useState<AnyData[]>([]);
  const [monthly, setMonthly] = useState<AnyData[]>([]);
  const [forecast, setForecast] = useState<AnyData | null>(null);
  const [loading, setLoading] = useState(true);
  const [forecastLoading, setForecastLoading] = useState(false);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const [s, r, t, m, f] = await Promise.all([
        api.budgetSummary().catch(() => null),
        api.budgetResources().catch(() => null),
        api.budgetTenants().catch(() => null),
        api.budgetMonthly().catch(() => null),
        api.latestForecast().catch(() => null),
      ]);
      if (s) setSummary(s);
      if (r) setResources(Array.isArray(r) ? r : (r as AnyData).resources ?? []);
      if (t) setTenants(Array.isArray(t) ? t : (t as AnyData).tenants ?? []);
      if (m) setMonthly(Array.isArray(m) ? m : (m as AnyData).months ?? []);
      if (f) setForecast(f);
    } catch { /* fallback handled per-field */ }
    setLoading(false);
  }, []);

  const runForecast = useCallback(async () => {
    setForecastLoading(true);
    try {
      const result = await api.runForecast();
      setForecast(result);
    } catch { /* silent */ }
    setForecastLoading(false);
  }, []);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  return { summary, resources, tenants, monthly, forecast, loading, forecastLoading, runForecast, refresh: fetchAll };
}

export default function BudgetingPage() {
  const { summary, resources, tenants, monthly, forecast, loading, forecastLoading, runForecast, refresh } = useBudgetData();
  const [activeTab, setActiveTab] = useState<'overview' | 'forecast'>('overview');

  const totalBudget = summary?.total_budget ?? 11100;
  const totalUsed = summary?.total_used ?? 0;
  const usedPct = Math.round(summary?.usage_pct ?? (totalUsed / totalBudget) * 100);
  const alerts = summary?.alerts ?? [];

  const forecasts = forecast?.forecasts ?? [];
  const anomalies = forecast?.anomalies ?? [];
  const recommendations = forecast?.recommendations ?? [];
  const overallForecast = forecast?.overall_forecast ?? {};
  const tenantForecasts = forecast?.tenant_forecasts ?? [];
  const runMeta = forecast?.run_metadata ?? {};

  if (loading) {
    return (
      <AppShell title="Budgeting" icon={DollarSign} color="#34D399">
        <div className="flex items-center justify-center h-64 text-white/40">
          <RefreshCw className="w-6 h-6 animate-spin mr-2" /> Loading budget data...
        </div>
      </AppShell>
    );
  }

  return (
    <AppShell title="Budgeting" icon={DollarSign} color="#34D399">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-xl font-semibold mb-1">Cost & Resource Budgets</h2>
          <p className="text-sm text-white/40">Track spending, forecast costs, and manage resource allocation</p>
        </div>
        <button onClick={refresh} className="glass px-3 py-1.5 rounded-lg text-xs text-white/60 hover:text-white/90 transition flex items-center gap-1.5">
          <RefreshCw className="w-3.5 h-3.5" /> Refresh
        </button>
      </div>

      {/* Tabs */}
      <div className="flex gap-2 mb-6">
        {(['overview', 'forecast'] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-4 py-2 rounded-xl text-sm font-medium transition ${
              activeTab === tab ? 'glass-heavy text-white' : 'glass text-white/50 hover:text-white/80'
            }`}
          >
            {tab === 'overview' ? (
              <><BarChart3 className="w-4 h-4 inline mr-1.5" />Budget Overview</>
            ) : (
              <><Brain className="w-4 h-4 inline mr-1.5" />AI Forecasting</>
            )}
          </button>
        ))}
      </div>

      {activeTab === 'overview' ? (
        <>
          {/* Overview KPIs */}
          <div className="grid grid-cols-1 sm:grid-cols-[200px_1fr] gap-6 mb-6">
            <GlassCard className="flex flex-col items-center justify-center py-4">
              <HealthRing value={usedPct} size={100} strokeWidth={7} label="budget" />
              <div className="mt-3 text-center">
                <div className="text-xl font-bold">${totalUsed.toLocaleString()}</div>
                <div className="text-xs text-white/40">of ${totalBudget.toLocaleString()} monthly</div>
              </div>
            </GlassCard>

            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <GlassCard>
                <MetricBadge label="Monthly Budget" value={`$${(totalBudget / 1000).toFixed(1)}K`} color="#34D399" />
              </GlassCard>
              <GlassCard>
                <MetricBadge label="Spent MTD" value={`$${(totalUsed / 1000).toFixed(1)}K`} color="#FBBF24" />
              </GlassCard>
              <GlassCard>
                <MetricBadge label="Remaining" value={`$${((totalBudget - totalUsed) / 1000).toFixed(1)}K`} color="#3B82F6" />
              </GlassCard>
              <GlassCard>
                <MetricBadge label="Budget Health" value={summary?.budget_health ?? 'N/A'} color={
                  summary?.budget_health === 'healthy' ? '#34D399' : summary?.budget_health === 'warning' ? '#FBBF24' : '#EF4444'
                } />
              </GlassCard>
            </div>
          </div>

          {/* Alerts */}
          {alerts.length > 0 && (
            <div className="mb-6 space-y-2">
              {alerts.map((a: AnyData, i: number) => (
                <div key={i} className={`glass rounded-xl px-4 py-2.5 flex items-center gap-2 text-sm ${
                  a.severity === 'critical' ? 'border border-red-500/30 text-red-300' : 'border border-amber-500/20 text-amber-300'
                }`}>
                  <AlertTriangle className="w-4 h-4 shrink-0" />
                  {a.message}
                </div>
              ))}
            </div>
          )}

          {/* Resource Budgets */}
          <h3 className="text-base font-semibold mb-3 text-white/80">
            <BarChart3 className="w-4 h-4 inline mr-1.5" /> Resource Budgets
          </h3>
          <div className="space-y-2 mb-6">
            {resources.map((b: AnyData) => {
              const pct = Math.round(b.usage_pct ?? (b.used / b.allocated) * 100);
              const isHigh = pct > 90;
              const barColor = isHigh ? '#EF4444' : pct > 70 ? '#FBBF24' : '#34D399';
              return (
                <GlassCard key={b.resource} className="py-3">
                  <div className="flex items-center justify-between mb-2">
                    <div className="text-sm font-medium capitalize">{String(b.resource).replace(/_/g, ' ')}</div>
                    <div className="flex items-center gap-3">
                      <span className="text-xs text-white/40">{b.unit_name}</span>
                      <span className="text-xs text-white/50">${b.used?.toLocaleString()} / ${b.allocated?.toLocaleString()}</span>
                      {isHigh && <AlertTriangle className="w-3.5 h-3.5 text-red-400" />}
                    </div>
                  </div>
                  <div className="w-full bg-white/5 rounded-full h-2">
                    <div className="h-2 rounded-full transition-all duration-500" style={{ width: `${Math.min(pct, 100)}%`, backgroundColor: barColor }} />
                  </div>
                  <div className="text-[10px] text-white/30 mt-1 text-right">{pct}% used — ${b.remaining?.toLocaleString()} remaining</div>
                </GlassCard>
              );
            })}
          </div>

          {/* Tenant Cost Breakdown */}
          <h3 className="text-base font-semibold mb-3 text-white/80">
            <PieChart className="w-4 h-4 inline mr-1.5" /> Cost by Tenant
          </h3>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 mb-6">
            {tenants.map((t: AnyData) => {
              const totalAll = tenants.reduce((s: number, x: AnyData) => s + (x.total ?? 0), 0);
              const pct = totalAll > 0 ? Math.round(((t.total ?? 0) / totalAll) * 100) : 0;
              return (
                <GlassCard key={t.tenant_id}>
                  <div className="text-sm font-medium mb-1">{t.tenant_name}</div>
                  <div className="text-xs text-white/30 mb-2">{t.plan}</div>
                  <div className="text-xl font-bold" style={{ color: pct > 30 ? '#F59E0B' : '#34D399' }}>
                    ${(t.total ?? 0).toLocaleString()}
                  </div>
                  <div className="w-full bg-white/5 rounded-full h-1.5 mt-2">
                    <div className="bg-emerald-400/60 h-1.5 rounded-full" style={{ width: `${pct}%` }} />
                  </div>
                  <div className="text-[10px] text-white/30 mt-1">{pct}% of total</div>
                </GlassCard>
              );
            })}
          </div>

          {/* Monthly History */}
          <h3 className="text-base font-semibold mb-3 text-white/80">
            <CalendarDays className="w-4 h-4 inline mr-1.5" /> Monthly Trend
          </h3>
          <GlassCard>
            <div className="flex items-end gap-2 h-40">
              {monthly.map((m: AnyData) => {
                const maxCost = Math.max(...monthly.map((h: AnyData) => h.cost ?? 0));
                const heightPct = maxCost > 0 ? ((m.cost ?? 0) / maxCost) * 100 : 0;
                return (
                  <div key={m.month} className="flex-1 flex flex-col items-center gap-1">
                    <span className="text-[10px] text-white/50">${((m.cost ?? 0) / 1000).toFixed(1)}K</span>
                    <div className="w-full flex flex-col justify-end" style={{ height: '100px' }}>
                      <div
                        className={`w-full rounded-t-lg transition-all ${m.partial ? 'bg-blue-400/40 border border-dashed border-blue-400/40' : 'bg-emerald-400/40'}`}
                        style={{ height: `${heightPct}%` }}
                      />
                    </div>
                    <span className="text-[10px] text-white/40">{m.month}</span>
                  </div>
                );
              })}
            </div>
          </GlassCard>
        </>
      ) : (
        /* AI Forecasting Tab */
        <>
          {/* Run Forecast Button */}
          <div className="flex items-center justify-between mb-6">
            <div className="text-sm text-white/40">
              {runMeta.timestamp ? (
                <>Last run: {new Date(runMeta.timestamp * 1000).toLocaleString()} ({runMeta.data_points_analyzed} data points, {runMeta.duration_ms}ms)</>
              ) : forecast?.status === 'no_data' ? 'No forecast data yet — run analysis to generate predictions' : 'AI Forecasting Agent ready'}
            </div>
            <button
              onClick={runForecast}
              disabled={forecastLoading}
              className="glass-heavy px-4 py-2 rounded-xl text-sm font-medium text-emerald-300 hover:text-emerald-200 transition flex items-center gap-2 disabled:opacity-50"
            >
              {forecastLoading ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Brain className="w-4 h-4" />}
              {forecastLoading ? 'Running Analysis...' : 'Run AI Forecast'}
            </button>
          </div>

          {/* Overall Forecast */}
          {overallForecast.next_month && (
            <>
              <h3 className="text-base font-semibold mb-3 text-white/80">
                <Activity className="w-4 h-4 inline mr-1.5" /> Overall Cost Forecast
              </h3>
              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 mb-6">
                <GlassCard>
                  <MetricBadge label="EOM Projected" value={`$${(overallForecast.current_month_projected / 1000).toFixed(1)}K`} color="#3B82F6" />
                </GlassCard>
                <GlassCard>
                  <MetricBadge label="Next Month" value={`$${(overallForecast.next_month / 1000).toFixed(1)}K`} color="#8B5CF6" />
                </GlassCard>
                <GlassCard>
                  <MetricBadge label="Next Quarter" value={`$${(overallForecast.next_quarter / 1000).toFixed(1)}K`} color="#EC4899" />
                </GlassCard>
                <GlassCard>
                  <MetricBadge label="Annual Est." value={`$${(overallForecast.annual_projected / 1000).toFixed(1)}K`} color="#F59E0B" />
                </GlassCard>
                <GlassCard>
                  <MetricBadge label="Avg Monthly" value={`$${(overallForecast.avg_monthly / 1000).toFixed(1)}K`} color="#34D399" />
                </GlassCard>
                <GlassCard>
                  <MetricBadge label="Growth Rate" value={`${overallForecast.growth_rate_pct}%`} color={overallForecast.growth_rate_pct > 5 ? '#EF4444' : '#34D399'} />
                  <div className="text-[10px] text-white/30 mt-0.5">per month</div>
                </GlassCard>
              </div>
            </>
          )}

          {/* Recommendations */}
          {recommendations.length > 0 && (
            <>
              <h3 className="text-base font-semibold mb-3 text-white/80">
                <Zap className="w-4 h-4 inline mr-1.5" /> AI Recommendations
              </h3>
              <div className="space-y-2 mb-6">
                {recommendations.map((r: AnyData, i: number) => (
                  <GlassCard key={i} className={`py-3 border ${
                    r.severity === 'critical' ? 'border-red-500/30' : r.severity === 'high' ? 'border-amber-500/30' : 'border-emerald-500/20'
                  }`}>
                    <div className="flex items-start gap-3">
                      <div className={`mt-0.5 ${r.severity === 'critical' ? 'text-red-400' : r.severity === 'high' ? 'text-amber-400' : 'text-emerald-400'}`}>
                        {r.type === 'breach_warning' ? <ShieldAlert className="w-5 h-5" /> :
                         r.type === 'increase_budget' ? <TrendingUp className="w-5 h-5" /> :
                         <TrendingDown className="w-5 h-5" />}
                      </div>
                      <div className="flex-1">
                        <div className="text-sm">{r.message}</div>
                        <div className="flex items-center gap-3 mt-1.5">
                          <span className="text-xs text-white/30">Confidence: {r.confidence}</span>
                          {r.suggested_budget && (
                            <span className="text-xs text-white/50">
                              Suggested: <span className="text-emerald-300">${r.suggested_budget.toLocaleString()}</span>
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                  </GlassCard>
                ))}
              </div>
            </>
          )}

          {/* Per-Resource Forecasts */}
          {forecasts.length > 0 && (
            <>
              <h3 className="text-base font-semibold mb-3 text-white/80">
                <BarChart3 className="w-4 h-4 inline mr-1.5" /> Resource Forecasts
              </h3>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 mb-6">
                {forecasts.map((f: AnyData) => {
                  const trendColor = f.trend === 'up' ? '#FBBF24' : f.trend === 'down' ? '#34D399' : f.trend === 'volatile' ? '#EF4444' : '#94A3B8';
                  const confColor = f.confidence === 'high' ? '#34D399' : f.confidence === 'medium' ? '#FBBF24' : '#EF4444';
                  return (
                    <GlassCard key={f.resource}>
                      <div className="flex items-center justify-between mb-2">
                        <div className="text-sm font-medium capitalize">{String(f.resource).replace(/_/g, ' ')}</div>
                        <span className="text-xs px-2 py-0.5 rounded-full" style={{ backgroundColor: `${confColor}20`, color: confColor }}>
                          {f.confidence}
                        </span>
                      </div>
                      <div className="text-2xl font-bold mb-1">${f.predicted_cost?.toLocaleString()}</div>
                      <div className="text-xs text-white/40 mb-2">predicted next month</div>
                      <div className="flex items-center gap-3 text-xs">
                        <span className="flex items-center gap-1" style={{ color: trendColor }}>
                          {f.trend === 'up' ? <TrendingUp className="w-3 h-3" /> : f.trend === 'down' ? <TrendingDown className="w-3 h-3" /> : <ArrowRight className="w-3 h-3" />}
                          {f.trend} ({f.trend_pct > 0 ? '+' : ''}{f.trend_pct}%)
                        </span>
                        {f.details?.volatility !== undefined && (
                          <span className="text-white/30">Vol: {f.details.volatility}</span>
                        )}
                        {f.details?.r_squared !== undefined && (
                          <span className="text-white/30">R²: {f.details.r_squared}</span>
                        )}
                      </div>
                      {f.breach_date && (
                        <div className="mt-2 text-xs text-red-400 flex items-center gap-1">
                          <ShieldAlert className="w-3 h-3" /> Budget breach by {f.breach_date}
                        </div>
                      )}
                      {f.details?.eom_projected && (
                        <div className="mt-1 text-[10px] text-white/30">
                          EOM estimate: ${f.details.eom_projected.toLocaleString()} | Daily rate: ${f.details.daily_rate}
                        </div>
                      )}
                    </GlassCard>
                  );
                })}
              </div>
            </>
          )}

          {/* Anomalies */}
          {anomalies.length > 0 && (
            <>
              <h3 className="text-base font-semibold mb-3 text-white/80">
                <AlertTriangle className="w-4 h-4 inline mr-1.5" /> Detected Anomalies
              </h3>
              <div className="space-y-2 mb-6">
                {anomalies.slice(0, 10).map((a: AnyData, i: number) => (
                  <GlassCard key={i} className={`py-2.5 border ${
                    a.severity === 'critical' ? 'border-red-500/30' : a.severity === 'warning' ? 'border-amber-500/20' : 'border-white/5'
                  }`}>
                    <div className="flex items-center justify-between">
                      <div className="text-sm">{a.description}</div>
                      <div className="flex items-center gap-3 text-xs text-white/40">
                        <span className={a.severity === 'critical' ? 'text-red-400' : a.severity === 'warning' ? 'text-amber-400' : 'text-white/50'}>
                          {a.severity}
                        </span>
                        <span>{a.deviation_pct > 0 ? '+' : ''}{a.deviation_pct}%</span>
                        <span>Expected: {a.expected} / Actual: {a.actual}</span>
                      </div>
                    </div>
                  </GlassCard>
                ))}
              </div>
            </>
          )}

          {/* Tenant Forecasts */}
          {tenantForecasts.length > 0 && (
            <>
              <h3 className="text-base font-semibold mb-3 text-white/80">
                <PieChart className="w-4 h-4 inline mr-1.5" /> Tenant Cost Forecasts
              </h3>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 mb-6">
                {tenantForecasts.map((t: AnyData) => (
                  <GlassCard key={t.tenant_id}>
                    <div className="text-sm font-medium mb-0.5">{t.tenant_name}</div>
                    <div className="text-xs text-white/30 mb-2">{t.plan}</div>
                    <div className="flex items-baseline gap-2 mb-1">
                      <span className="text-lg font-bold">${t.current_cost?.toLocaleString()}</span>
                      <ArrowRight className="w-3 h-3 text-white/30" />
                      <span className="text-lg font-bold text-blue-300">${t.predicted_next_month?.toLocaleString()}</span>
                    </div>
                    <div className="text-xs text-amber-300 flex items-center gap-1">
                      <TrendingUp className="w-3 h-3" /> +{t.growth_pct}% projected
                    </div>
                  </GlassCard>
                ))}
              </div>
            </>
          )}

          {/* Empty State */}
          {forecasts.length === 0 && !forecastLoading && (
            <GlassCard className="text-center py-12">
              <Brain className="w-12 h-12 text-white/20 mx-auto mb-3" />
              <div className="text-lg font-medium text-white/50 mb-2">No Forecast Data</div>
              <div className="text-sm text-white/30 mb-4">Click &quot;Run AI Forecast&quot; to analyze usage patterns and generate predictions</div>
              <button onClick={runForecast} className="glass-heavy px-6 py-2.5 rounded-xl text-sm font-medium text-emerald-300 hover:text-emerald-200 transition">
                <Brain className="w-4 h-4 inline mr-1.5" /> Generate Forecast
              </button>
            </GlassCard>
          )}
        </>
      )}
    </AppShell>
  );
}
