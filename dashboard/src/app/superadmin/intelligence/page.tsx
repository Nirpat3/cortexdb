'use client';

import { useState, useEffect, useCallback } from 'react';
import {
  Brain, TrendingUp, BarChart3, Zap, Moon, RefreshCw,
  ArrowUpRight, ArrowDownRight, Minus, Clock, Award, Target,
} from 'lucide-react';
import { superadminApi } from '@/lib/api';
import { useTranslation } from '@/lib/i18n';

type TabId = 'overview' | 'models' | 'prompts' | 'sleep';

function KpiCard({ label, value, sub, icon: Icon, color = 'cyan' }: {
  label: string; value: string | number; sub?: string;
  icon: React.ElementType; color?: string;
}) {
  const colors: Record<string, string> = {
    cyan: 'text-cyan-400 bg-cyan-500/10',
    green: 'text-green-400 bg-green-500/10',
    amber: 'text-amber-400 bg-amber-500/10',
    purple: 'text-purple-400 bg-purple-500/10',
    red: 'text-red-400 bg-red-500/10',
  };
  return (
    <div className="glass rounded-xl p-4 border border-white/5">
      <div className="flex items-center justify-between mb-3">
        <span className="text-xs text-white/40">{label}</span>
        <div className={`w-7 h-7 rounded-lg flex items-center justify-center ${colors[color]}`}>
          <Icon className="w-3.5 h-3.5" />
        </div>
      </div>
      <div className="text-2xl font-bold">{value}</div>
      {sub && <div className="text-xs text-white/30 mt-1">{sub}</div>}
    </div>
  );
}

function GradeBar({ label, count, total, color }: {
  label: string; count: number; total: number; color: string;
}) {
  const pct = total > 0 ? (count / total) * 100 : 0;
  return (
    <div className="flex items-center gap-3">
      <span className="text-xs text-white/50 w-24">{label}</span>
      <div className="flex-1 h-2 bg-white/5 rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-white/40 w-10 text-right">{count}</span>
    </div>
  );
}

function GradeBadge({ grade }: { grade: number }) {
  const color = grade >= 8 ? 'text-green-400' : grade >= 5 ? 'text-amber-400' : 'text-red-400';
  return <span className={`text-sm font-bold ${color}`}>{grade}/10</span>;
}

export default function IntelligencePage() {
  const { t } = useTranslation();
  const [tab, setTab] = useState<TabId>('overview');
  const [insights, setInsights] = useState<Record<string, any> | null>(null);
  const [analyses, setAnalyses] = useState<any[]>([]);
  const [scores, setScores] = useState<Record<string, any> | null>(null);
  const [models, setModels] = useState<Record<string, any> | null>(null);
  const [recommendations, setRecommendations] = useState<Record<string, any> | null>(null);
  const [promptPerf, setPromptPerf] = useState<Record<string, any> | null>(null);
  const [evolutions, setEvolutions] = useState<any[]>([]);
  const [sleepStatus, setSleepStatus] = useState<Record<string, any> | null>(null);
  const [loading, setLoading] = useState(true);
  const [sleepRunning, setSleepRunning] = useState(false);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [ins, ana, sc, mod, rec, pp, evo, ss] = await Promise.allSettled([
        superadminApi.getLearningInsights(),
        superadminApi.getLearningAnalyses(50),
        superadminApi.getLearningScores(),
        superadminApi.getModelPerformance(),
        superadminApi.getAllModelRecommendations(),
        superadminApi.getPromptPerformance(),
        superadminApi.getPromptEvolutions(undefined, 20),
        superadminApi.getSleepCycleStatus(),
      ]);
      if (ins.status === 'fulfilled') setInsights(ins.value);
      if (ana.status === 'fulfilled') setAnalyses((ana.value as any).analyses || []);
      if (sc.status === 'fulfilled') setScores(sc.value);
      if (mod.status === 'fulfilled') setModels(mod.value);
      if (rec.status === 'fulfilled') setRecommendations(rec.value);
      if (pp.status === 'fulfilled') setPromptPerf(pp.value);
      if (evo.status === 'fulfilled') setEvolutions((evo.value as any).evolutions || []);
      if (ss.status === 'fulfilled') setSleepStatus(ss.value);
    } catch { /* silent */ }
    setLoading(false);
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  const triggerSleep = async () => {
    setSleepRunning(true);
    try {
      await superadminApi.triggerSleepCycle();
      await loadData();
    } catch { /* silent */ }
    setSleepRunning(false);
  };

  const tabs: { id: TabId; label: string; icon: React.ElementType }[] = [
    { id: 'overview', label: 'Overview', icon: Brain },
    { id: 'models', label: 'Model Performance', icon: BarChart3 },
    { id: 'prompts', label: 'Prompt Evolution', icon: Zap },
    { id: 'sleep', label: 'Sleep Cycle', icon: Moon },
  ];

  const gradeDistribution = insights?.grade_distribution || {};
  const qualityDistribution = insights?.quality_distribution || {};
  const categoryScores = scores?.categories || {};

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-purple-500/20 flex items-center justify-center">
            <Brain className="w-5 h-5 text-purple-400" />
          </div>
          <div>
            <h1 className="text-xl font-bold">{t('intelligence.title')}</h1>
            <p className="text-xs text-white/40">{t('intelligence.subtitle')}</p>
          </div>
        </div>
        <button onClick={loadData} disabled={loading}
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg glass text-xs text-white/60 hover:text-white transition">
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} /> {t('common.refresh')}
        </button>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 p-1 glass rounded-xl w-fit">
        {tabs.map((tb) => (
          <button key={tb.id} onClick={() => setTab(tb.id)}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs transition ${
              tab === tb.id ? 'bg-white/10 text-white' : 'text-white/40 hover:text-white/70'
            }`}>
            <tb.icon className="w-3.5 h-3.5" /> {tb.label}
          </button>
        ))}
      </div>

      {/* Overview Tab */}
      {tab === 'overview' && (
        <div className="space-y-6">
          {/* KPI Row */}
          <div className="grid grid-cols-4 gap-4">
            <KpiCard label="Tasks Analyzed" value={insights?.total_analyzed || 0}
              icon={Target} color="cyan" />
            <KpiCard label="Avg Grade" value={insights?.avg_grade || '-'}
              sub="out of 10" icon={Award} color={
                (insights?.avg_grade || 0) >= 7 ? 'green' :
                (insights?.avg_grade || 0) >= 5 ? 'amber' : 'red'
              } />
            <KpiCard label="Models Tracked"
              value={models?.total_tracked || 0} icon={BarChart3} color="purple" />
            <KpiCard label="Sleep Cycles"
              value={sleepStatus?.cycle_count || 0}
              sub={sleepStatus?.running ? t('common.running') : 'Idle'}
              icon={Moon} color="amber" />
          </div>

          {/* Grade Distribution + Quality */}
          <div className="grid grid-cols-2 gap-4">
            <div className="glass rounded-xl p-5 border border-white/5">
              <h3 className="text-sm font-medium mb-4">Grade Distribution</h3>
              <div className="space-y-3">
                <GradeBar label="9-10 (excellent)" count={gradeDistribution['9-10 (excellent)'] || 0}
                  total={insights?.total_analyzed || 1} color="bg-green-500" />
                <GradeBar label="7-8 (good)" count={gradeDistribution['7-8 (good)'] || 0}
                  total={insights?.total_analyzed || 1} color="bg-cyan-500" />
                <GradeBar label="4-6 (fair)" count={gradeDistribution['4-6 (fair)'] || 0}
                  total={insights?.total_analyzed || 1} color="bg-amber-500" />
                <GradeBar label="1-3 (poor)" count={gradeDistribution['1-3 (poor)'] || 0}
                  total={insights?.total_analyzed || 1} color="bg-red-500" />
              </div>
            </div>

            <div className="glass rounded-xl p-5 border border-white/5">
              <h3 className="text-sm font-medium mb-4">Quality Breakdown</h3>
              <div className="space-y-3">
                {['excellent', 'good', 'fair', 'poor'].map((q) => {
                  const count = qualityDistribution[q] || 0;
                  const colors: Record<string, string> = {
                    excellent: 'bg-green-500', good: 'bg-cyan-500',
                    fair: 'bg-amber-500', poor: 'bg-red-500',
                  };
                  return (
                    <GradeBar key={q} label={q} count={count}
                      total={insights?.total_analyzed || 1} color={colors[q]} />
                  );
                })}
              </div>
            </div>
          </div>

          {/* Category Scores */}
          <div className="glass rounded-xl p-5 border border-white/5">
            <h3 className="text-sm font-medium mb-4">Scores by Category</h3>
            {Object.keys(categoryScores).length === 0 ? (
              <p className="text-xs text-white/30">No category scores yet. Execute and analyze tasks to populate.</p>
            ) : (
              <div className="grid grid-cols-4 gap-3">
                {Object.entries(categoryScores).map(([cat, data]: [string, any]) => (
                  <div key={cat} className="glass rounded-lg p-3 border border-white/5">
                    <div className="text-xs text-white/40 mb-1 capitalize">{cat}</div>
                    <div className="flex items-baseline gap-2">
                      <span className="text-lg font-bold">{data.avg}</span>
                      <span className="text-[10px] text-white/30">{data.total} tasks</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Recent Analyses */}
          <div className="glass rounded-xl p-5 border border-white/5">
            <h3 className="text-sm font-medium mb-4">Recent Analyses</h3>
            {analyses.length === 0 ? (
              <p className="text-xs text-white/30">No analyses yet.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-white/30 border-b border-white/5">
                      <th className="text-left py-2 font-medium">Task</th>
                      <th className="text-left py-2 font-medium">Agent</th>
                      <th className="text-left py-2 font-medium">Category</th>
                      <th className="text-center py-2 font-medium">Grade</th>
                      <th className="text-left py-2 font-medium">Quality</th>
                      <th className="text-center py-2 font-medium">Learnings</th>
                      <th className="text-right py-2 font-medium">Time</th>
                    </tr>
                  </thead>
                  <tbody>
                    {analyses.slice(-20).reverse().map((a: any, i: number) => (
                      <tr key={i} className="border-b border-white/5 hover:bg-white/5">
                        <td className="py-2 text-white/70 max-w-[150px] truncate">{a.task_id || '-'}</td>
                        <td className="py-2 text-white/50 max-w-[120px] truncate">{a.agent_id || '-'}</td>
                        <td className="py-2">
                          <span className="px-2 py-0.5 rounded-full bg-white/5 text-white/50 capitalize">{a.category}</span>
                        </td>
                        <td className="py-2 text-center"><GradeBadge grade={a.grade || 0} /></td>
                        <td className="py-2">
                          <span className={`capitalize ${
                            a.quality === 'excellent' ? 'text-green-400' :
                            a.quality === 'good' ? 'text-cyan-400' :
                            a.quality === 'fair' ? 'text-amber-400' : 'text-red-400'
                          }`}>{a.quality}</span>
                        </td>
                        <td className="py-2 text-center text-white/40">{a.learnings_count || 0}</td>
                        <td className="py-2 text-right text-white/30">
                          {a.timestamp ? new Date(a.timestamp * 1000).toLocaleString() : '-'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Models Tab */}
      {tab === 'models' && (
        <div className="space-y-6">
          <div className="glass rounded-xl p-5 border border-white/5">
            <h3 className="text-sm font-medium mb-4">Model Performance Data</h3>
            {!models || !models.entries || Object.keys(models.entries || {}).length === 0 ? (
              <p className="text-xs text-white/30">No model performance data yet. Execute tasks to populate.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-white/30 border-b border-white/5">
                      <th className="text-left py-2 font-medium">Provider</th>
                      <th className="text-left py-2 font-medium">Model</th>
                      <th className="text-left py-2 font-medium">Category</th>
                      <th className="text-center py-2 font-medium">Requests</th>
                      <th className="text-center py-2 font-medium">Success %</th>
                      <th className="text-center py-2 font-medium">Avg Grade</th>
                      <th className="text-center py-2 font-medium">Avg Latency</th>
                      <th className="text-center py-2 font-medium">Score</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(models.entries || {}).map(([key, data]: [string, any]) => {
                      const parts = key.split(':');
                      return (
                        <tr key={key} className="border-b border-white/5 hover:bg-white/5">
                          <td className="py-2 text-white/70">{parts[0] || '-'}</td>
                          <td className="py-2 text-white/50">{parts[1] || 'default'}</td>
                          <td className="py-2">
                            <span className="px-2 py-0.5 rounded-full bg-white/5 text-white/50 capitalize">{parts[2] || 'general'}</span>
                          </td>
                          <td className="py-2 text-center text-white/50">{data.total_requests || 0}</td>
                          <td className="py-2 text-center">
                            <span className={data.success_rate >= 0.9 ? 'text-green-400' : data.success_rate >= 0.7 ? 'text-amber-400' : 'text-red-400'}>
                              {((data.success_rate || 0) * 100).toFixed(0)}%
                            </span>
                          </td>
                          <td className="py-2 text-center"><GradeBadge grade={Math.round(data.avg_grade || 0)} /></td>
                          <td className="py-2 text-center text-white/40">{(data.avg_latency_ms || 0).toFixed(0)}ms</td>
                          <td className="py-2 text-center font-medium">
                            <span className={data.composite_score >= 0.7 ? 'text-green-400' : data.composite_score >= 0.4 ? 'text-amber-400' : 'text-red-400'}>
                              {(data.composite_score || 0).toFixed(2)}
                            </span>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          <div className="glass rounded-xl p-5 border border-white/5">
            <h3 className="text-sm font-medium mb-4">Learned Recommendations (per category)</h3>
            {!recommendations || Object.keys(recommendations.recommendations || {}).length === 0 ? (
              <p className="text-xs text-white/30">No recommendations yet. Need more task data.</p>
            ) : (
              <div className="grid grid-cols-3 gap-3">
                {Object.entries(recommendations.recommendations || {}).map(([cat, rec]: [string, any]) => (
                  <div key={cat} className="glass rounded-lg p-4 border border-white/5">
                    <div className="text-xs text-white/40 capitalize mb-2">{cat}</div>
                    <div className="text-sm font-medium">{rec.provider}/{rec.model || 'default'}</div>
                    <div className="flex items-center gap-2 mt-1">
                      <span className="text-[10px] text-white/30">Score:</span>
                      <span className={`text-xs font-medium ${rec.score >= 0.7 ? 'text-green-400' : 'text-amber-400'}`}>
                        {(rec.score || 0).toFixed(2)}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Prompts Tab */}
      {tab === 'prompts' && (
        <div className="space-y-6">
          <div className="glass rounded-xl p-5 border border-white/5">
            <h3 className="text-sm font-medium mb-4">Prompt Performance by Agent</h3>
            {!promptPerf || Object.keys(promptPerf).length === 0 ? (
              <p className="text-xs text-white/30">No prompt performance data yet.</p>
            ) : (
              <div className="space-y-3">
                {Object.entries(promptPerf).map(([key, data]: [string, any]) => {
                  if (typeof data !== 'object' || !data) return null;
                  return (
                    <div key={key} className="glass rounded-lg p-3 border border-white/5 flex items-center justify-between">
                      <div>
                        <div className="text-xs font-medium text-white/70">{key}</div>
                        <div className="text-[10px] text-white/30 mt-0.5">
                          {data.total_results || 0} results tracked
                        </div>
                      </div>
                      <div className="flex items-center gap-4">
                        {data.avg_grade && (
                          <div className="text-center">
                            <div className="text-[10px] text-white/30">Avg Grade</div>
                            <GradeBadge grade={Math.round(data.avg_grade)} />
                          </div>
                        )}
                        {data.trend !== undefined && (
                          <div className="text-center">
                            <div className="text-[10px] text-white/30">Trend</div>
                            {data.trend > 0 ? (
                              <ArrowUpRight className="w-4 h-4 text-green-400 mx-auto" />
                            ) : data.trend < 0 ? (
                              <ArrowDownRight className="w-4 h-4 text-red-400 mx-auto" />
                            ) : (
                              <Minus className="w-4 h-4 text-white/30 mx-auto" />
                            )}
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          <div className="glass rounded-xl p-5 border border-white/5">
            <h3 className="text-sm font-medium mb-4">Recent Prompt Evolutions</h3>
            {evolutions.length === 0 ? (
              <p className="text-xs text-white/30">No prompt evolutions yet. Evolve prompts from the agent detail page or let sleep cycle auto-evolve.</p>
            ) : (
              <div className="space-y-3">
                {evolutions.map((evo: any, i: number) => (
                  <div key={i} className="glass rounded-lg p-4 border border-white/5">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-xs font-medium text-white/70">{evo.agent_id}</span>
                      <span className="text-[10px] text-white/30">
                        {evo.timestamp ? new Date(evo.timestamp * 1000).toLocaleString() : '-'}
                      </span>
                    </div>
                    {evo.category && (
                      <span className="text-[10px] px-2 py-0.5 rounded-full bg-purple-500/10 text-purple-400 capitalize">{evo.category}</span>
                    )}
                    {evo.applied && (
                      <span className="text-[10px] px-2 py-0.5 rounded-full bg-green-500/10 text-green-400 ml-2">Applied</span>
                    )}
                    {evo.new_prompt && (
                      <div className="mt-2 text-[10px] text-white/30 bg-white/5 rounded p-2 max-h-20 overflow-hidden">
                        {evo.new_prompt.slice(0, 200)}{evo.new_prompt.length > 200 ? '...' : ''}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Sleep Cycle Tab */}
      {tab === 'sleep' && (
        <div className="space-y-6">
          <div className="grid grid-cols-3 gap-4">
            <KpiCard label="Total Cycles" value={sleepStatus?.cycle_count || 0}
              icon={Moon} color="purple" />
            <KpiCard label="Status"
              value={sleepStatus?.running ? t('common.running') : 'Idle'}
              icon={Clock} color={sleepStatus?.running ? 'amber' : 'green'} />
            <div className="glass rounded-xl p-4 border border-white/5 flex items-center justify-center">
              <button onClick={triggerSleep} disabled={sleepRunning || sleepStatus?.running}
                className="flex items-center gap-2 px-4 py-2 rounded-lg bg-purple-500/20 text-purple-300 hover:bg-purple-500/30 transition text-sm disabled:opacity-50">
                <Moon className={`w-4 h-4 ${sleepRunning ? 'animate-pulse' : ''}`} />
                {sleepRunning ? 'Running...' : 'Trigger Sleep Cycle'}
              </button>
            </div>
          </div>

          {/* Last Result */}
          {sleepStatus?.last_result && (
            <div className="glass rounded-xl p-5 border border-white/5">
              <h3 className="text-sm font-medium mb-4">Last Cycle Result</h3>
              <div className="grid grid-cols-5 gap-3">
                {Object.entries(sleepStatus.last_result.tasks || {}).map(([phase, data]: [string, any]) => {
                  const hasError = data && typeof data === 'object' && 'error' in data;
                  return (
                    <div key={phase} className={`glass rounded-lg p-3 border ${hasError ? 'border-red-500/20' : 'border-white/5'}`}>
                      <div className="text-xs text-white/40 capitalize mb-2">{phase}</div>
                      {hasError ? (
                        <div className="text-xs text-red-400">{t('common.error')}</div>
                      ) : (
                        <div className="text-xs text-white/60">
                          {Object.entries(data || {}).map(([k, v]) => (
                            <div key={k} className="flex justify-between">
                              <span className="text-white/30">{k.replace(/_/g, ' ')}</span>
                              <span>{String(v)}</span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
              <div className="mt-3 text-xs text-white/30">
                Duration: {sleepStatus.last_result.duration_s}s | Completed: {
                  sleepStatus.last_result.completed_at
                    ? new Date(sleepStatus.last_result.completed_at * 1000).toLocaleString()
                    : '-'
                }
              </div>
            </div>
          )}

          {/* History */}
          <div className="glass rounded-xl p-5 border border-white/5">
            <h3 className="text-sm font-medium mb-4">Cycle History</h3>
            {!sleepStatus?.history || sleepStatus.history.length === 0 ? (
              <p className="text-xs text-white/30">No sleep cycle history yet. Trigger a cycle or wait for the scheduler (every 6 hours).</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-white/30 border-b border-white/5">
                      <th className="text-left py-2 font-medium">Cycle</th>
                      <th className="text-left py-2 font-medium">Time</th>
                      <th className="text-center py-2 font-medium">Duration</th>
                      <th className="text-left py-2 font-medium">Consolidate</th>
                      <th className="text-left py-2 font-medium">Decay</th>
                      <th className="text-left py-2 font-medium">Strengthen</th>
                      <th className="text-left py-2 font-medium">Precompute</th>
                      <th className="text-left py-2 font-medium">Evolve</th>
                    </tr>
                  </thead>
                  <tbody>
                    {[...sleepStatus.history].reverse().map((h: any, i: number) => (
                      <tr key={i} className="border-b border-white/5 hover:bg-white/5">
                        <td className="py-2 text-white/70">#{h.cycle}</td>
                        <td className="py-2 text-white/50">
                          {h.timestamp ? new Date(h.timestamp * 1000).toLocaleString() : '-'}
                        </td>
                        <td className="py-2 text-center text-white/40">{h.duration_s}s</td>
                        {['consolidate', 'decay', 'strengthen', 'precompute', 'evolve'].map((phase) => (
                          <td key={phase} className="py-2">
                            <span className={`px-2 py-0.5 rounded-full text-[10px] ${
                              h.tasks?.[phase] === 'ok' ? 'bg-green-500/10 text-green-400' : 'bg-red-500/10 text-red-400'
                            }`}>
                              {h.tasks?.[phase] || '-'}
                            </span>
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
