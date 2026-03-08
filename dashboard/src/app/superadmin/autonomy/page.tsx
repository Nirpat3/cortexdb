'use client';

import { useEffect, useState, useCallback } from 'react';
import {
  Brain, GitBranch, Target, UserPlus, Timer, TrendingUp,
  Play, Check, X, Loader2, RefreshCw, Plus, Send,
} from 'lucide-react';
import { superadminApi } from '@/lib/api';
import { useTranslation } from '@/lib/i18n';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type D = Record<string, any>;

const TAB_DEFS = [
  { key: 'delegation', tKey: 'autonomy.tabs.delegation', icon: GitBranch },
  { key: 'goals', tKey: 'autonomy.tabs.goals', icon: Target },
  { key: 'hiring', tKey: 'autonomy.tabs.hiring', icon: UserPlus },
  { key: 'sprints', tKey: 'autonomy.tabs.sprints', icon: Timer },
  { key: 'improvement', tKey: 'autonomy.tabs.improvement', icon: TrendingUp },
] as const;

type Tab = typeof TAB_DEFS[number]['key'];

const STATUS_STYLE: Record<string, string> = {
  active: 'bg-emerald-500/20 text-emerald-300',
  completed: 'bg-blue-500/20 text-blue-300',
  pending: 'bg-amber-500/20 text-amber-300',
  approved: 'bg-emerald-500/20 text-emerald-300',
  rejected: 'bg-red-500/20 text-red-300',
  planning: 'bg-violet-500/20 text-violet-300',
};

function Badge({ status }: { status: string }) {
  return (
    <span className={`text-[10px] px-2 py-0.5 rounded-full ${STATUS_STYLE[status] ?? 'bg-white/10 text-white/40'}`}>
      {status}
    </span>
  );
}

export default function AutonomyPage() {
  const [tab, setTab] = useState<Tab>('delegation');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { t } = useTranslation();

  // Delegation state
  const [delStats, setDelStats] = useState<D | null>(null);
  const [delLog, setDelLog] = useState<D[]>([]);
  const [delTaskId, setDelTaskId] = useState('');
  const [delFromAgent, setDelFromAgent] = useState('');

  // Goals state
  const [goalText, setGoalText] = useState('');
  const [goalContext, setGoalContext] = useState('');
  const [goalHistory, setGoalHistory] = useState<D[]>([]);
  const [goalResult, setGoalResult] = useState<D | null>(null);

  // Hiring state
  const [gaps, setGaps] = useState<D[]>([]);
  const [recommendations, setRecommendations] = useState<D[]>([]);
  const [hiringHistory, setHiringHistory] = useState<D[]>([]);

  // Sprints state
  const [sprints, setSprints] = useState<D[]>([]);
  const [sprintGoal, setSprintGoal] = useState('');
  const [sprintDays, setSprintDays] = useState(7);
  const [standup, setStandup] = useState<D | null>(null);

  // Improvement state
  const [proposals, setProposals] = useState<D[]>([]);

  const load = useCallback(async (t: Tab) => {
    setLoading(true);
    setError(null);
    try {
      const arr = (obj: unknown, ...keys: string[]): D[] => {
        const o = obj as D;
        for (const k of keys) { if (Array.isArray(o[k])) return o[k]; }
        return Array.isArray(o) ? o : [];
      };
      if (t === 'delegation') {
        const [stats, log] = await Promise.all([
          superadminApi.getDelegationStats(),
          superadminApi.getDelegationLog(),
        ]);
        setDelStats(stats as D);
        setDelLog(arr(log, 'delegations', 'items'));
      } else if (t === 'goals') {
        const h = await superadminApi.getGoalHistory();
        setGoalHistory(arr(h, 'goals', 'items'));
      } else if (t === 'hiring') {
        const [g, r, h] = await Promise.all([
          superadminApi.getHiringGaps(),
          superadminApi.getHiringRecommendations(),
          superadminApi.getHiringHistory(),
        ]);
        setGaps(arr(g, 'gaps', 'items'));
        setRecommendations(arr(r, 'recommendations', 'items'));
        setHiringHistory(arr(h, 'history', 'items'));
      } else if (t === 'sprints') {
        const s = await superadminApi.listSprints();
        setSprints(arr(s, 'sprints', 'items'));
      } else if (t === 'improvement') {
        const p = await superadminApi.getImprovementProposals();
        setProposals(arr(p, 'proposals', 'items'));
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load data');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(tab); }, [tab, load]);

  const handleDelegate = async () => {
    if (!delTaskId || !delFromAgent) return;
    try {
      await superadminApi.autoDelegateTask(delTaskId, delFromAgent);
      setDelTaskId('');
      setDelFromAgent('');
      load('delegation');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Delegation failed');
    }
  };

  const handleDecompose = async () => {
    if (!goalText) return;
    setLoading(true);
    try {
      const result = await superadminApi.decomposeGoal(goalText, goalContext);
      setGoalResult(result as D);
      setGoalText('');
      setGoalContext('');
      load('goals');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Decomposition failed');
    } finally {
      setLoading(false);
    }
  };

  const handleAutoHire = async (templateId: string) => {
    try {
      await superadminApi.autoHire(templateId);
      load('hiring');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Auto-hire failed');
    }
  };

  const handleCreateSprint = async () => {
    if (!sprintGoal) return;
    try {
      await superadminApi.createSprint(sprintGoal, sprintDays);
      setSprintGoal('');
      load('sprints');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Sprint creation failed');
    }
  };

  const handleSprintAction = async (id: string, action: 'activate' | 'complete' | 'standup') => {
    try {
      if (action === 'activate') await superadminApi.activateSprint(id);
      else if (action === 'complete') await superadminApi.completeSprint(id);
      else {
        const s = await superadminApi.sprintStandup(id);
        setStandup(s as D);
        return;
      }
      load('sprints');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Sprint action failed');
    }
  };

  const handleApprove = async (id: string) => {
    try { await superadminApi.approveImprovement(id); load('improvement'); }
    catch (e) { setError(e instanceof Error ? e.message : 'Approve failed'); }
  };

  const handleReject = async (id: string) => {
    try { await superadminApi.rejectImprovement(id); load('improvement'); }
    catch (e) { setError(e instanceof Error ? e.message : 'Reject failed'); }
  };

  const handleGenerateAll = async () => {
    setLoading(true);
    try { await superadminApi.generateAllImprovements(); load('improvement'); }
    catch (e) { setError(e instanceof Error ? e.message : 'Generation failed'); }
    finally { setLoading(false); }
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold mb-1 flex items-center gap-2">
            <Brain className="w-6 h-6 text-violet-400" /> {t('autonomy.title')}
          </h1>
          <p className="text-sm text-white/40">{t('autonomy.subtitle')}</p>
        </div>
        <button onClick={() => load(tab)} className="p-2 rounded-lg bg-white/5 hover:bg-white/10 transition">
          <RefreshCw className={`w-4 h-4 text-white/50 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {/* Tabs */}
      <div className="flex gap-2 mb-6 flex-wrap">
        {TAB_DEFS.map(({ key, tKey, icon: Icon }) => (
          <button key={key} onClick={() => setTab(key)}
            className={`flex items-center gap-1.5 px-4 py-2 rounded-lg text-xs font-medium transition ${
              tab === key ? 'bg-white/10 text-white border border-white/20' : 'bg-white/5 text-white/50 border border-white/10 hover:text-white/80'
            }`}>
            <Icon className="w-3.5 h-3.5" /> {t(tKey)}
          </button>
        ))}
      </div>

      {error && (
        <div className="bg-red-500/10 border border-red-500/20 rounded-xl p-3 mb-4 text-xs text-red-300 flex items-center justify-between">
          {error}
          <button onClick={() => setError(null)} className="text-red-400 hover:text-red-200"><X className="w-3.5 h-3.5" /></button>
        </div>
      )}

      {loading && (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="w-6 h-6 text-white/30 animate-spin" />
        </div>
      )}

      {!loading && tab === 'delegation' && (
        <div className="space-y-4">
          {delStats && (
            <div className="grid grid-cols-2 gap-4">
              <div className="bg-white/5 border border-white/10 rounded-xl p-4">
                <div className="text-xs text-white/40">{t('autonomy.delegation.totalDelegations')}</div>
                <div className="text-2xl font-bold mt-1">{delStats.total ?? 0}</div>
              </div>
              <div className="bg-white/5 border border-white/10 rounded-xl p-4">
                <div className="text-xs text-white/40">{t('autonomy.delegation.successRate')}</div>
                <div className="text-2xl font-bold mt-1 text-emerald-400">{delStats.success_rate ?? 0}%</div>
              </div>
            </div>
          )}
          <div className="bg-white/5 border border-white/10 rounded-xl p-4">
            <div className="text-xs text-white/40 mb-3">{t('autonomy.delegation.autoDelegateTask')}</div>
            <div className="flex gap-2">
              <input value={delTaskId} onChange={(e) => setDelTaskId(e.target.value)} placeholder={t('autonomy.delegation.taskId')}
                className="flex-1 bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-xs" />
              <input value={delFromAgent} onChange={(e) => setDelFromAgent(e.target.value)} placeholder={t('autonomy.delegation.fromAgentId')}
                className="flex-1 bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-xs" />
              <button onClick={handleDelegate}
                className="px-4 py-2 rounded-lg text-xs bg-violet-500/20 text-violet-300 hover:bg-violet-500/30 flex items-center gap-1.5">
                <Send className="w-3 h-3" /> {t('autonomy.delegation.delegate')}
              </button>
            </div>
          </div>
          <div className="bg-white/5 border border-white/10 rounded-xl p-4">
            <div className="text-xs text-white/40 mb-3">{t('autonomy.delegation.delegationLog')}</div>
            <div className="space-y-2">
              {delLog.length === 0 && <p className="text-xs text-white/30">{t('autonomy.delegation.noDelegations')}</p>}
              {delLog.map((d, i) => (
                <div key={i} className="flex items-center justify-between bg-white/5 rounded-lg p-3 text-xs">
                  <div><span className="text-white/70 font-mono">{d.task_id}</span> <span className="text-white/30">from</span> <span className="text-white/70">{d.from_agent}</span> <span className="text-white/30">to</span> <span className="text-white/70">{d.to_agent}</span></div>
                  <Badge status={d.status ?? 'pending'} />
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {!loading && tab === 'goals' && (
        <div className="space-y-4">
          <div className="bg-white/5 border border-white/10 rounded-xl p-4">
            <div className="text-xs text-white/40 mb-3">{t('autonomy.goals.decomposeGoal')}</div>
            <textarea value={goalText} onChange={(e) => setGoalText(e.target.value)} placeholder={t('autonomy.goals.describeGoal')}
              className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-xs min-h-[80px] mb-2" />
            <textarea value={goalContext} onChange={(e) => setGoalContext(e.target.value)} placeholder={t('autonomy.goals.additionalContext')}
              className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-xs min-h-[50px] mb-2" />
            <button onClick={handleDecompose}
              className="px-4 py-2 rounded-lg text-xs bg-blue-500/20 text-blue-300 hover:bg-blue-500/30 flex items-center gap-1.5">
              <Target className="w-3 h-3" /> {t('autonomy.goals.decompose')}
            </button>
          </div>
          {goalResult && (
            <div className="bg-emerald-500/10 border border-emerald-500/20 rounded-xl p-4">
              <div className="text-xs text-emerald-300 font-medium mb-2">{t('autonomy.goals.decompositionResult')}</div>
              <pre className="text-xs text-white/60 whitespace-pre-wrap">{JSON.stringify(goalResult, null, 2)}</pre>
            </div>
          )}
          <div className="bg-white/5 border border-white/10 rounded-xl p-4">
            <div className="text-xs text-white/40 mb-3">{t('autonomy.goals.decompositionHistory')}</div>
            <div className="space-y-2">
              {goalHistory.length === 0 && <p className="text-xs text-white/30">{t('autonomy.goals.noDecompositions')}</p>}
              {goalHistory.map((g, i) => (
                <div key={i} className="bg-white/5 rounded-lg p-3 text-xs">
                  <div className="text-white/70 font-medium">{g.goal}</div>
                  <div className="text-white/30 mt-1">{g.sub_tasks_count ?? 0} {t('autonomy.goals.subTasksGenerated')} · {g.created_at}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {!loading && tab === 'hiring' && (
        <div className="space-y-4">
          <div className="bg-white/5 border border-white/10 rounded-xl p-4">
            <div className="text-xs text-white/40 mb-3">{t('autonomy.hiring.detectedGaps')}</div>
            <div className="space-y-2">
              {gaps.length === 0 && <p className="text-xs text-white/30">{t('autonomy.hiring.noGaps')}</p>}
              {gaps.map((g, i) => (
                <div key={i} className="flex items-center justify-between bg-white/5 rounded-lg p-3 text-xs">
                  <div><span className="text-white/70 font-medium">{g.role ?? g.gap}</span> <span className="text-white/30">({g.department})</span></div>
                  <span className="text-amber-300 text-[10px]">{t('autonomy.hiring.severity')} {g.severity ?? 'medium'}</span>
                </div>
              ))}
            </div>
          </div>
          <div className="bg-white/5 border border-white/10 rounded-xl p-4">
            <div className="text-xs text-white/40 mb-3">{t('autonomy.hiring.recommendations')}</div>
            <div className="space-y-2">
              {recommendations.length === 0 && <p className="text-xs text-white/30">{t('autonomy.hiring.noRecommendations')}</p>}
              {recommendations.map((r, i) => (
                <div key={i} className="flex items-center justify-between bg-white/5 rounded-lg p-3 text-xs">
                  <div><span className="text-white/70 font-medium">{r.name ?? r.template_id}</span> <span className="text-white/30">{r.reason}</span></div>
                  <button onClick={() => handleAutoHire(r.template_id)}
                    className="px-3 py-1 rounded-lg bg-emerald-500/20 text-emerald-300 hover:bg-emerald-500/30 flex items-center gap-1">
                    <Plus className="w-3 h-3" /> {t('autonomy.hiring.hire')}
                  </button>
                </div>
              ))}
            </div>
          </div>
          <div className="bg-white/5 border border-white/10 rounded-xl p-4">
            <div className="text-xs text-white/40 mb-3">{t('autonomy.hiring.hiringHistory')}</div>
            <div className="space-y-2">
              {hiringHistory.length === 0 && <p className="text-xs text-white/30">{t('autonomy.hiring.noHires')}</p>}
              {hiringHistory.map((h, i) => (
                <div key={i} className="flex items-center justify-between bg-white/5 rounded-lg p-3 text-xs">
                  <div><span className="text-white/70">{h.agent_id}</span> <span className="text-white/30">{h.role} · {h.hired_at}</span></div>
                  <Badge status={h.status ?? 'active'} />
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {!loading && tab === 'sprints' && (
        <div className="space-y-4">
          <div className="bg-white/5 border border-white/10 rounded-xl p-4">
            <div className="text-xs text-white/40 mb-3">{t('autonomy.sprints.createSprint')}</div>
            <textarea value={sprintGoal} onChange={(e) => setSprintGoal(e.target.value)} placeholder={t('autonomy.sprints.sprintGoal')}
              className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-xs min-h-[60px] mb-2" />
            <div className="flex gap-2 items-center">
              <label className="text-xs text-white/40">{t('autonomy.sprints.duration')}</label>
              <input type="number" value={sprintDays} onChange={(e) => setSprintDays(Number(e.target.value))} min={1} max={30}
                className="w-20 bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-xs" />
              <button onClick={handleCreateSprint}
                className="px-4 py-2 rounded-lg text-xs bg-blue-500/20 text-blue-300 hover:bg-blue-500/30 flex items-center gap-1.5 ml-auto">
                <Plus className="w-3 h-3" /> {t('autonomy.sprints.createSprint')}
              </button>
            </div>
          </div>
          <div className="bg-white/5 border border-white/10 rounded-xl p-4">
            <div className="text-xs text-white/40 mb-3">{t('autonomy.sprints.sprints')}</div>
            <div className="space-y-2">
              {sprints.length === 0 && <p className="text-xs text-white/30">{t('autonomy.sprints.noSprints')}</p>}
              {sprints.map((s) => (
                <div key={s.id} className="bg-white/5 rounded-lg p-3 text-xs">
                  <div className="flex items-center justify-between mb-2">
                    <div className="text-white/70 font-medium">{s.goal}</div>
                    <Badge status={s.status ?? 'planning'} />
                  </div>
                  <div className="text-white/30 mb-2">{s.duration_days ?? s.days} days · {s.progress ?? 0}% complete</div>
                  <div className="flex gap-2">
                    {s.status === 'planning' && (
                      <button onClick={() => handleSprintAction(s.id, 'activate')}
                        className="px-2 py-1 rounded bg-emerald-500/20 text-emerald-300 hover:bg-emerald-500/30 flex items-center gap-1">
                        <Play className="w-3 h-3" /> {t('autonomy.sprints.activate')}
                      </button>
                    )}
                    {s.status === 'active' && (
                      <>
                        <button onClick={() => handleSprintAction(s.id, 'standup')}
                          className="px-2 py-1 rounded bg-blue-500/20 text-blue-300 hover:bg-blue-500/30 flex items-center gap-1">
                          <RefreshCw className="w-3 h-3" /> {t('autonomy.sprints.standup')}
                        </button>
                        <button onClick={() => handleSprintAction(s.id, 'complete')}
                          className="px-2 py-1 rounded bg-violet-500/20 text-violet-300 hover:bg-violet-500/30 flex items-center gap-1">
                          <Check className="w-3 h-3" /> {t('autonomy.sprints.complete')}
                        </button>
                      </>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
          {standup && (
            <div className="bg-blue-500/10 border border-blue-500/20 rounded-xl p-4">
              <div className="text-xs text-blue-300 font-medium mb-2">{t('autonomy.sprints.sprintStandup')}</div>
              <pre className="text-xs text-white/60 whitespace-pre-wrap">{JSON.stringify(standup, null, 2)}</pre>
            </div>
          )}
        </div>
      )}

      {!loading && tab === 'improvement' && (
        <div className="space-y-4">
          <div className="flex justify-end">
            <button onClick={handleGenerateAll}
              className="px-4 py-2 rounded-lg text-xs bg-violet-500/20 text-violet-300 hover:bg-violet-500/30 flex items-center gap-1.5">
              <TrendingUp className="w-3 h-3" /> {t('autonomy.improvement.generateAll')}
            </button>
          </div>
          <div className="bg-white/5 border border-white/10 rounded-xl p-4">
            <div className="text-xs text-white/40 mb-3">{t('autonomy.improvement.proposals')}</div>
            <div className="space-y-2">
              {proposals.length === 0 && <p className="text-xs text-white/30">{t('autonomy.improvement.noProposals')}</p>}
              {proposals.map((p) => (
                <div key={p.id} className="bg-white/5 rounded-lg p-3 text-xs">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-white/70 font-medium">{p.title ?? p.description}</span>
                    <Badge status={p.status ?? 'pending'} />
                  </div>
                  <div className="text-white/30 mb-2">{p.agent_id} · {t('autonomy.improvement.impact')} {p.impact ?? 'medium'}</div>
                  {(!p.status || p.status === 'pending') && (
                    <div className="flex gap-2">
                      <button onClick={() => handleApprove(p.id)}
                        className="px-2 py-1 rounded bg-emerald-500/20 text-emerald-300 hover:bg-emerald-500/30 flex items-center gap-1">
                        <Check className="w-3 h-3" /> {t('common.approve')}
                      </button>
                      <button onClick={() => handleReject(p.id)}
                        className="px-2 py-1 rounded bg-red-500/20 text-red-300 hover:bg-red-500/30 flex items-center gap-1">
                        <X className="w-3 h-3" /> {t('common.reject')}
                      </button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
