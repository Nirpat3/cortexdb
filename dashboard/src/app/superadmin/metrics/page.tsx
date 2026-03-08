'use client';

import { useEffect, useState } from 'react';
import { BarChart3, Users, CheckCircle2, XCircle, Clock, DollarSign, Star, Zap, Award, Brain } from 'lucide-react';
import { superadminApi } from '@/lib/api';
import { useTranslation } from '@/lib/i18n';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type D = Record<string, any>;

const STATE_COLORS: Record<string, string> = {
  active: 'bg-emerald-500/20 text-emerald-400',
  idle: 'bg-yellow-500/20 text-yellow-400',
  busy: 'bg-blue-500/20 text-blue-400',
  offline: 'bg-white/10 text-white/40',
  error: 'bg-red-500/20 text-red-400',
};

function KpiCard({ icon: Icon, label, value, color = 'text-blue-400' }: { icon: any; label: string; value: string | number; color?: string }) {
  return (
    <div className="bg-white/5 border border-white/10 rounded-xl p-4 flex items-center gap-3">
      <div className={`w-10 h-10 rounded-lg flex items-center justify-center bg-white/5 ${color}`}>
        <Icon className="w-5 h-5" />
      </div>
      <div>
        <p className="text-xs text-white/40">{label}</p>
        <p className="text-lg font-bold">{value}</p>
      </div>
    </div>
  );
}

export default function MetricsPage() {
  const { t } = useTranslation();
  const [tab, setTab] = useState<'team' | 'departments'>('team');
  const [summary, setSummary] = useState<D | null>(null);
  const [departments, setDepartments] = useState<D[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      setLoading(true);
      try {
        const [sumData, deptData] = await Promise.all([
          superadminApi.getMetricsSummary(),
          superadminApi.getAllDepartmentMetrics(),
        ]);
        setSummary(sumData as D);
        setDepartments(((deptData as D).departments ?? []) as D[]);
      } catch { /* silent */ }
      setLoading(false);
    }
    load();
  }, []);

  return (
    <div>
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold mb-1 flex items-center gap-2">
          <BarChart3 className="w-6 h-6 text-blue-400" /> {t('metricsPage.title')}
        </h1>
        <p className="text-sm text-white/40">{t('metricsPage.subtitle')}</p>
      </div>

      {/* Tabs */}
      <div className="flex gap-2 mb-6">
        {(['team', 'departments'] as const).map((t) => (
          <button key={t} onClick={() => setTab(t)}
            className={`px-4 py-2 rounded-lg text-sm transition ${tab === t ? 'bg-white/10 border border-white/20 text-white' : 'bg-white/5 border border-white/10 text-white/50 hover:text-white/80'}`}>
            {t === 'team' ? 'Team Overview' : 'Department Breakdown'}
          </button>
        ))}
      </div>

      {loading && <p className="text-white/40 text-sm">{t('common.loading')}</p>}

      {/* Team Overview */}
      {!loading && tab === 'team' && summary && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <KpiCard icon={Users} label="Total Agents" value={summary.total_agents ?? 0} color="text-blue-400" />
            <KpiCard icon={Zap} label="Active Agents" value={summary.active_agents ?? 0} color="text-emerald-400" />
            <KpiCard icon={CheckCircle2} label="Completed Tasks" value={summary.completed_tasks ?? 0} color="text-green-400" />
            <KpiCard icon={XCircle} label="Failed Tasks" value={summary.failed_tasks ?? 0} color="text-red-400" />
          </div>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
            <KpiCard icon={Star} label="Avg Grade" value={typeof summary.avg_grade === 'number' ? summary.avg_grade.toFixed(1) : '--'} color="text-yellow-400" />
            <KpiCard icon={DollarSign} label="Total Cost" value={typeof summary.total_cost === 'number' ? `$${summary.total_cost.toFixed(2)}` : '$0.00'} color="text-purple-400" />
            <KpiCard icon={Clock} label="Tasks This Week" value={summary.tasks_this_week ?? 0} color="text-cyan-400" />
          </div>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
            <KpiCard icon={Brain} label="Total Skills" value={summary.total_skills ?? 0} color="text-pink-400" />
            <KpiCard icon={Award} label="Total XP" value={summary.total_xp ?? 0} color="text-orange-400" />
            <KpiCard icon={Star} label="Expert Skills" value={summary.expert_skills ?? 0} color="text-amber-400" />
          </div>
        </div>
      )}

      {/* Department Breakdown */}
      {!loading && tab === 'departments' && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {departments.map((dept: D) => (
            <div key={dept.department} className="bg-white/5 border border-white/10 rounded-xl p-6">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-bold">{dept.department}</h3>
                <span className="text-xs text-white/40">{dept.agent_count} agent{dept.agent_count !== 1 ? 's' : ''}</span>
              </div>
              <div className="grid grid-cols-3 gap-3 mb-4">
                <div className="text-center">
                  <p className="text-xs text-white/40">Tasks</p>
                  <p className="text-sm font-semibold">{dept.total_tasks ?? 0}</p>
                </div>
                <div className="text-center">
                  <p className="text-xs text-white/40">Completed</p>
                  <p className="text-sm font-semibold text-emerald-400">{dept.completed ?? 0}</p>
                </div>
                <div className="text-center">
                  <p className="text-xs text-white/40">Avg Grade</p>
                  <p className="text-sm font-semibold text-yellow-400">
                    {typeof dept.avg_grade === 'number' ? dept.avg_grade.toFixed(1) : '--'}
                  </p>
                </div>
              </div>
              {dept.agents?.length > 0 && (
                <div className="border-t border-white/10 pt-3 space-y-1.5">
                  {dept.agents.map((a: D) => (
                    <div key={a.agent_id} className="flex items-center justify-between text-xs">
                      <span className="text-white/70 truncate mr-2">{a.name ?? a.agent_id}</span>
                      <span className={`px-2 py-0.5 rounded-full text-[10px] font-medium ${STATE_COLORS[a.state] ?? STATE_COLORS.offline}`}>
                        {a.state ?? 'unknown'}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
          {departments.length === 0 && (
            <p className="text-white/40 text-sm col-span-2">{t('common.noData')}</p>
          )}
        </div>
      )}
    </div>
  );
}
