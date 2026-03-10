'use client';

import { useEffect, useState, useCallback } from 'react';
import { Bot, ClipboardList, MessageSquare, Activity, Users, Cpu, Mail, Zap, Database } from 'lucide-react';
import { superadminApi } from '@/lib/api';
import { useTranslation } from '@/lib/i18n';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type D = Record<string, any>;

export default function SuperAdminDashboard() {
  const [team, setTeam] = useState<D | null>(null);
  const [providers, setProviders] = useState<D | null>(null);
  const [busStats, setBusStats] = useState<D>({});
  const [execStatus, setExecStatus] = useState<D>({});
  const { t } = useTranslation();

  const refresh = useCallback(async () => {
    try {
      const [te, p, b, e] = await Promise.all([
        superadminApi.getTeam().catch(() => null),
        superadminApi.getLLMProviders().catch(() => null),
        superadminApi.busStats().catch(() => null),
        superadminApi.executorStatus().catch(() => null),
      ]);
      if (te) setTeam(te);
      if (p) setProviders(p);
      if (b) setBusStats(b);
      if (e) setExecStatus(e);
    } catch { /* silent */ }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const summary = (team as D)?.summary ?? {};
  const agents = (team as D)?.agents ?? [];
  const providerStatus = (providers as D)?.providers ?? {};

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold mb-1">{t('dashboard.title')}</h1>
        <p className="text-sm text-white/40">{t('dashboard.subtitle')}</p>
      </div>

      {/* KPI Grid */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-8">
        <div className="glass rounded-xl p-4">
          <div className="flex items-center gap-2 text-white/40 mb-2">
            <Bot className="w-4 h-4" /><span className="text-xs">{t('dashboard.totalAgents')}</span>
          </div>
          <div className="text-3xl font-bold">{summary.total_agents ?? 0}</div>
        </div>
        <div className="glass rounded-xl p-4">
          <div className="flex items-center gap-2 text-white/40 mb-2">
            <Activity className="w-4 h-4" /><span className="text-xs">{t('dashboard.working')}</span>
          </div>
          <div className="text-3xl font-bold text-emerald-400">{summary.agents_working ?? 0}</div>
        </div>
        <div className="glass rounded-xl p-4">
          <div className="flex items-center gap-2 text-white/40 mb-2">
            <ClipboardList className="w-4 h-4" /><span className="text-xs">{t('dashboard.tasks')}</span>
          </div>
          <div className="text-3xl font-bold text-blue-400">{summary.total_tasks ?? 0}</div>
          <div className="text-xs text-white/30">{summary.tasks_in_progress ?? 0} {t('dashboard.inProgress')}</div>
        </div>
        <div className="glass rounded-xl p-4">
          <div className="flex items-center gap-2 text-white/40 mb-2">
            <MessageSquare className="w-4 h-4" /><span className="text-xs">{t('dashboard.instructions')}</span>
          </div>
          <div className="text-3xl font-bold text-purple-400">{summary.total_instructions ?? 0}</div>
        </div>
      </div>

      {/* System Status */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-8">
        <div className="glass rounded-xl p-4">
          <div className="flex items-center gap-2 mb-2">
            <Zap className="w-4 h-4 text-amber-400" />
            <span className="text-sm font-medium">{t('dashboard.taskExecutor')}</span>
          </div>
          <div className={`text-sm ${execStatus.running ? 'text-emerald-400' : 'text-red-400'}`}>
            {execStatus.running ? t('common.running') : t('common.stopped')}
          </div>
          <div className="text-xs text-white/30 mt-1">
            {t('dashboard.queue')}: {execStatus.queue_size ?? 0} | {t('dashboard.active')}: {(execStatus.active_tasks ?? []).length}/{execStatus.max_concurrent ?? 3}
          </div>
        </div>
        <div className="glass rounded-xl p-4">
          <div className="flex items-center gap-2 mb-2">
            <Mail className="w-4 h-4 text-blue-400" />
            <span className="text-sm font-medium">{t('dashboard.agentBus')}</span>
          </div>
          <div className="text-sm">{busStats.total_messages ?? 0} {t('common.messages')}</div>
          <div className="text-xs text-white/30 mt-1">
            {busStats.unread ?? 0} {t('common.unread')}
          </div>
        </div>
        <div className="glass rounded-xl p-4">
          <div className="flex items-center gap-2 mb-2">
            <Database className="w-4 h-4 text-emerald-400" />
            <span className="text-sm font-medium">{t('dashboard.persistence')}</span>
          </div>
          <div className="text-sm text-emerald-400">{t('common.active')}</div>
          <div className="text-xs text-white/30 mt-1">{t('dashboard.autoSave')}</div>
        </div>
      </div>

      {/* LLM Providers */}
      <h2 className="text-lg font-semibold mb-3">{t('dashboard.llmProviders')}</h2>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-8">
        {Object.entries(providerStatus).map(([name, status]) => {
          const s = status as D;
          return (
            <div key={name} className="glass rounded-xl p-4">
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <Cpu className="w-4 h-4 text-cyan-400" />
                  <span className="text-sm font-medium capitalize">{name}</span>
                </div>
                <span className={`text-xs px-2 py-0.5 rounded-full ${
                  s.connected === true || (name !== 'ollama' && s.configured) ? 'bg-emerald-500/20 text-emerald-300' :
                  s.connected === false ? 'bg-red-500/20 text-red-300' : 'bg-white/10 text-white/40'
                }`}>
                  {s.connected === true ? t('common.connected') : s.connected === false ? t('common.disconnected') : s.configured ? t('common.configured') : t('common.notSet')}
                </span>
              </div>
              <div className="text-xs text-white/40">{t('common.model')}: {s.model}</div>
            </div>
          );
        })}
      </div>

      {/* Department Overview */}
      <h2 className="text-lg font-semibold mb-3">{t('dashboard.departments')}</h2>
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 mb-8">
        {['EXEC', 'ENG', 'QA', 'OPS', 'SEC', 'DOC'].map((dept) => {
          const deptAgents = agents.filter((a: D) => a.department === dept);
          const colors: Record<string, string> = {
            EXEC: '#EF4444', ENG: '#3B82F6', QA: '#34D399', OPS: '#F59E0B', SEC: '#EC4899', DOC: '#8B5CF6',
          };
          return (
            <div key={dept} className="glass rounded-xl p-3 text-center">
              <div className="w-8 h-8 rounded-lg mx-auto mb-2 flex items-center justify-center" style={{ backgroundColor: `${colors[dept]}20` }}>
                <Users className="w-4 h-4" style={{ color: colors[dept] }} />
              </div>
              <div className="text-sm font-medium">{dept}</div>
              <div className="text-xs text-white/40">{deptAgents.length} {t('common.agents')}</div>
            </div>
          );
        })}
      </div>

      {/* Agent Roster */}
      <h2 className="text-lg font-semibold mb-3">{t('dashboard.agentRoster')}</h2>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        {agents.slice(0, 12).map((a: D) => (
          <div key={a.agent_id} className="glass rounded-xl p-3">
            <div className="flex items-center justify-between mb-1">
              <span className="text-sm font-medium">{a.name}</span>
              <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${
                a.state === 'active' ? 'bg-emerald-500/20 text-emerald-300' :
                a.state === 'working' ? 'bg-blue-500/20 text-blue-300' : 'bg-white/10 text-white/40'
              }`}>{a.state}</span>
            </div>
            <div className="text-xs text-white/40">{a.title}</div>
            <div className="text-[10px] text-white/25 mt-1 font-mono">{a.agent_id}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
