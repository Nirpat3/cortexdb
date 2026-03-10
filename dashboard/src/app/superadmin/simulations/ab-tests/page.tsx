'use client';

import { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import {
  GitBranch,
  Plus,
  Play,
  ArrowLeft,
  Trophy,
  BarChart3,
  Check,
  X,
} from 'lucide-react';
import { superadminApi } from '@/lib/api';
import { useTranslation } from '@/lib/i18n';

type D = Record<string, any>;

export default function ABTestsPage() {
  const { t } = useTranslation();
  const router = useRouter();

  const [stats, setStats] = useState<D | null>(null);
  const [experiments, setExperiments] = useState<D[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [running, setRunning] = useState<Record<string, boolean>>({});
  const [applying, setApplying] = useState<Record<string, boolean>>({});

  // Create form state
  const [formName, setFormName] = useState('');
  const [formPromptA, setFormPromptA] = useState('');
  const [formPromptB, setFormPromptB] = useState('');
  const [formAgentIds, setFormAgentIds] = useState('');
  const [formTaskPrompts, setFormTaskPrompts] = useState<string[]>(['']);
  const [creating, setCreating] = useState(false);

  const fetchData = useCallback(async () => {
    try {
      const [statsRes, expRes] = await Promise.all([
        superadminApi.getABStats(),
        superadminApi.listABExperiments(),
      ]);
      setStats(statsRes);
      setExperiments(Array.isArray(expRes) ? expRes : []);
    } catch (err) {
      console.error('Failed to fetch A/B data', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleRun = async (id: string) => {
    setRunning((p) => ({ ...p, [id]: true }));
    try {
      await superadminApi.runABExperiment(id);
      await fetchData();
    } catch (err) {
      console.error('Run failed', err);
    } finally {
      setRunning((p) => ({ ...p, [id]: false }));
    }
  };

  const handleApplyWinner = async (id: string) => {
    setApplying((p) => ({ ...p, [id]: true }));
    try {
      await superadminApi.applyABWinner(id);
      await fetchData();
    } catch (err) {
      console.error('Apply winner failed', err);
    } finally {
      setApplying((p) => ({ ...p, [id]: false }));
    }
  };

  const handleCreate = async () => {
    if (!formName.trim() || !formPromptA.trim() || !formPromptB.trim()) return;
    setCreating(true);
    try {
      const data = {
        name: formName.trim(),
        variant_a: formPromptA.trim(),
        variant_b: formPromptB.trim(),
        agent_ids: formAgentIds
          .split(',')
          .map((s) => s.trim())
          .filter(Boolean),
        task_prompts: formTaskPrompts.filter((t) => t.trim()),
      };
      await superadminApi.createABExperiment(data);
      setShowCreate(false);
      resetForm();
      await fetchData();
    } catch (err) {
      console.error('Create failed', err);
    } finally {
      setCreating(false);
    }
  };

  const resetForm = () => {
    setFormName('');
    setFormPromptA('');
    setFormPromptB('');
    setFormAgentIds('');
    setFormTaskPrompts(['']);
  };

  const addTaskPrompt = () => setFormTaskPrompts((p) => [...p, '']);
  const removeTaskPrompt = (idx: number) =>
    setFormTaskPrompts((p) => p.filter((_, i) => i !== idx));
  const updateTaskPrompt = (idx: number, val: string) =>
    setFormTaskPrompts((p) => p.map((t, i) => (i === idx ? val : t)));

  const statusColor = (status: string) => {
    switch (status) {
      case 'created':
        return 'bg-blue-500/20 text-blue-300';
      case 'running':
        return 'bg-amber-500/20 text-amber-300';
      case 'completed':
        return 'bg-emerald-500/20 text-emerald-300';
      default:
        return 'bg-white/10 text-white/60';
    }
  };

  const scoreBarWidth = (score: number) => `${Math.min((score / 10) * 100, 100)}%`;

  if (loading) {
    return (
      <div className="min-h-screen bg-black text-white flex items-center justify-center">
        <div className="animate-pulse text-white/40 text-sm">{t('common.loading')}</div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-black text-white p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <button
            onClick={() => router.push('/superadmin/simulations')}
            className="p-2 rounded-xl bg-white/5 hover:bg-white/10 transition"
          >
            <ArrowLeft className="w-4 h-4" />
          </button>
          <GitBranch className="w-6 h-6 text-cyan-400" />
          <h1 className="text-2xl font-semibold">{t('simulations.abTests.title')}</h1>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          className="px-4 py-2 rounded-xl bg-cyan-500/20 text-cyan-300 hover:bg-cyan-500/30 text-sm transition flex items-center gap-2"
        >
          <Plus className="w-4 h-4" />
          New Experiment
        </button>
      </div>

      {/* Stats Bar */}
      {stats && (
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
          {[
            { label: 'Total Experiments', value: stats.total ?? 0 },
            { label: 'Completed', value: stats.completed ?? 0 },
            { label: 'A Wins', value: stats.a_wins ?? 0 },
            { label: 'B Wins', value: stats.b_wins ?? 0 },
            { label: 'Ties', value: stats.ties ?? 0 },
          ].map((s) => (
            <div
              key={s.label}
              className="bg-white/5 border border-white/10 rounded-2xl p-4 text-center"
            >
              <div className="text-2xl font-bold">{s.value}</div>
              <div className="text-xs text-white/40 mt-1">{s.label}</div>
            </div>
          ))}
        </div>
      )}

      {/* Experiment List */}
      <div className="space-y-4">
        {experiments.length === 0 && (
          <div className="bg-white/5 border border-white/10 rounded-2xl p-5 text-center text-white/40 text-sm">
            {t('common.noData')}
          </div>
        )}

        {experiments.map((exp) => {
          const isExpanded = expandedId === exp.id;
          const isCompleted = exp.status === 'completed';
          const results: D | undefined = exp.results;
          const overallWinner: string | undefined = results?.overall_winner;
          const meanA: number = results?.mean_a ?? 0;
          const meanB: number = results?.mean_b ?? 0;
          const aWins: number = results?.a_wins ?? 0;
          const bWins: number = results?.b_wins ?? 0;
          const ties: number = results?.ties ?? 0;
          const perTask: D[] = results?.per_task ?? [];

          return (
            <div
              key={exp.id}
              className="bg-white/5 border border-white/10 rounded-2xl p-5 space-y-4"
            >
              {/* Card Header */}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <h2 className="text-lg font-medium">{exp.name}</h2>
                  <span
                    className={`px-2.5 py-0.5 rounded-full text-xs font-medium ${statusColor(exp.status)}`}
                  >
                    {exp.status}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => handleRun(exp.id)}
                    disabled={exp.status !== 'created' || running[exp.id]}
                    className="px-3 py-1.5 rounded-xl bg-cyan-500/20 text-cyan-300 hover:bg-cyan-500/30 text-xs transition disabled:opacity-30 disabled:cursor-not-allowed flex items-center gap-1.5"
                  >
                    <Play className="w-3 h-3" />
                    {running[exp.id] ? 'Running...' : 'Run'}
                  </button>
                  {isCompleted && (
                    <button
                      onClick={() => handleApplyWinner(exp.id)}
                      disabled={applying[exp.id]}
                      className="px-3 py-1.5 rounded-xl bg-emerald-500/20 text-emerald-300 hover:bg-emerald-500/30 text-xs transition disabled:opacity-30 flex items-center gap-1.5"
                    >
                      <Trophy className="w-3 h-3" />
                      {applying[exp.id] ? 'Applying...' : 'Apply Winner'}
                    </button>
                  )}
                  <button
                    onClick={() => setExpandedId(isExpanded ? null : exp.id)}
                    className="px-3 py-1.5 rounded-xl bg-white/5 text-white/60 hover:bg-white/10 text-xs transition flex items-center gap-1.5"
                  >
                    <BarChart3 className="w-3 h-3" />
                    {isExpanded ? 'Collapse' : 'View Details'}
                  </button>
                </div>
              </div>

              {/* Completed Results Summary */}
              {isCompleted && results && (
                <div className="space-y-4">
                  {/* Variant Comparison */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    {/* Variant A */}
                    <div
                      className={`bg-cyan-500/5 border border-cyan-500/20 rounded-xl p-4 space-y-3 ${
                        overallWinner === 'A' ? 'ring-2 ring-emerald-500/50' : ''
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-sm font-medium text-cyan-300">Variant A</span>
                        {overallWinner === 'A' && (
                          <div className="flex items-center gap-1 text-emerald-400 text-xs">
                            <Trophy className="w-3.5 h-3.5" />
                            Winner (+{(meanA - meanB).toFixed(2)})
                          </div>
                        )}
                      </div>
                      <div className="text-2xl font-bold text-cyan-300">{meanA.toFixed(2)}</div>
                      <div className="text-xs text-white/40">Mean Score</div>
                      <div className="w-full bg-white/5 rounded-full h-2">
                        <div
                          className="bg-cyan-500/60 h-2 rounded-full transition-all"
                          style={{ width: scoreBarWidth(meanA) }}
                        />
                      </div>
                    </div>

                    {/* Variant B */}
                    <div
                      className={`bg-amber-500/5 border border-amber-500/20 rounded-xl p-4 space-y-3 ${
                        overallWinner === 'B' ? 'ring-2 ring-emerald-500/50' : ''
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-sm font-medium text-amber-300">Variant B</span>
                        {overallWinner === 'B' && (
                          <div className="flex items-center gap-1 text-emerald-400 text-xs">
                            <Trophy className="w-3.5 h-3.5" />
                            Winner (+{(meanB - meanA).toFixed(2)})
                          </div>
                        )}
                      </div>
                      <div className="text-2xl font-bold text-amber-300">{meanB.toFixed(2)}</div>
                      <div className="text-xs text-white/40">Mean Score</div>
                      <div className="w-full bg-white/5 rounded-full h-2">
                        <div
                          className="bg-amber-500/60 h-2 rounded-full transition-all"
                          style={{ width: scoreBarWidth(meanB) }}
                        />
                      </div>
                    </div>
                  </div>

                  {/* Win Breakdown */}
                  <div className="flex items-center gap-4 text-xs text-white/50">
                    <span className="flex items-center gap-1">
                      <Check className="w-3 h-3 text-cyan-400" /> A Wins: {aWins}
                    </span>
                    <span className="flex items-center gap-1">
                      <Check className="w-3 h-3 text-amber-400" /> B Wins: {bWins}
                    </span>
                    <span>Ties: {ties}</span>
                  </div>

                  {/* Tie Winner */}
                  {overallWinner === 'tie' && (
                    <div className="text-sm text-white/50 flex items-center gap-2">
                      <BarChart3 className="w-4 h-4" />
                      Result: Tie - no clear winner
                    </div>
                  )}
                </div>
              )}

              {/* Expanded: Per-Task Results */}
              {isExpanded && isCompleted && perTask.length > 0 && (
                <div className="border-t border-white/10 pt-4">
                  <h3 className="text-sm font-medium text-white/60 mb-3">Per-Task Results</h3>
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="text-white/40 text-xs border-b border-white/10">
                          <th className="text-left pb-2 pr-4">Agent ID</th>
                          <th className="text-left pb-2 pr-4">Task Prompt</th>
                          <th className="text-center pb-2 pr-4">Grade A</th>
                          <th className="text-center pb-2 pr-4">Grade B</th>
                          <th className="text-center pb-2">Winner</th>
                        </tr>
                      </thead>
                      <tbody>
                        {perTask.map((task: D, idx: number) => (
                          <tr key={idx} className="border-b border-white/5">
                            <td className="py-2 pr-4 text-white/70 font-mono text-xs">
                              {task.agent_id}
                            </td>
                            <td className="py-2 pr-4 text-white/60 text-xs max-w-xs truncate">
                              {task.task_prompt}
                            </td>
                            <td className="py-2 pr-4 text-center">
                              <span className="text-cyan-300 font-medium">
                                {task.grade_a ?? '-'}
                              </span>
                            </td>
                            <td className="py-2 pr-4 text-center">
                              <span className="text-amber-300 font-medium">
                                {task.grade_b ?? '-'}
                              </span>
                            </td>
                            <td className="py-2 text-center">
                              {task.winner === 'A' && (
                                <span className="bg-cyan-500/20 text-cyan-300 px-2 py-0.5 rounded-full text-xs">
                                  A
                                </span>
                              )}
                              {task.winner === 'B' && (
                                <span className="bg-amber-500/20 text-amber-300 px-2 py-0.5 rounded-full text-xs">
                                  B
                                </span>
                              )}
                              {task.winner === 'tie' && (
                                <span className="bg-white/10 text-white/50 px-2 py-0.5 rounded-full text-xs">
                                  Tie
                                </span>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {isExpanded && !isCompleted && (
                <div className="border-t border-white/10 pt-4 text-sm text-white/40">
                  Run the experiment to see detailed results.
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Create Experiment Modal */}
      {showCreate && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-zinc-900 border border-white/10 rounded-2xl p-6 w-full max-w-2xl max-h-[80vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-lg font-semibold">Create A/B Experiment</h2>
              <button
                onClick={() => {
                  setShowCreate(false);
                  resetForm();
                }}
                className="p-1.5 rounded-lg hover:bg-white/10 transition"
              >
                <X className="w-4 h-4 text-white/40" />
              </button>
            </div>

            <div className="space-y-4">
              {/* Name */}
              <div>
                <label className="block text-sm text-white/50 mb-1.5">Experiment Name</label>
                <input
                  value={formName}
                  onChange={(e) => setFormName(e.target.value)}
                  placeholder="e.g. Prompt optimization round 1"
                  className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-sm focus:border-cyan-500/50 focus:outline-none"
                />
              </div>

              {/* Prompt A */}
              <div>
                <label className="block text-sm text-white/50 mb-1.5">System Prompt A</label>
                <textarea
                  value={formPromptA}
                  onChange={(e) => setFormPromptA(e.target.value)}
                  rows={3}
                  placeholder="Enter system prompt for variant A..."
                  className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-sm focus:border-cyan-500/50 focus:outline-none resize-none"
                />
              </div>

              {/* Prompt B */}
              <div>
                <label className="block text-sm text-white/50 mb-1.5">System Prompt B</label>
                <textarea
                  value={formPromptB}
                  onChange={(e) => setFormPromptB(e.target.value)}
                  rows={3}
                  placeholder="Enter system prompt for variant B..."
                  className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-sm focus:border-cyan-500/50 focus:outline-none resize-none"
                />
              </div>

              {/* Agent IDs */}
              <div>
                <label className="block text-sm text-white/50 mb-1.5">
                  Agent IDs (comma-separated)
                </label>
                <input
                  value={formAgentIds}
                  onChange={(e) => setFormAgentIds(e.target.value)}
                  placeholder="e.g. T1-OPS-POS-001, T2-FIN-ANA-001"
                  className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-sm focus:border-cyan-500/50 focus:outline-none"
                />
              </div>

              {/* Task Prompts */}
              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <label className="text-sm text-white/50">Task Prompts</label>
                  <button
                    onClick={addTaskPrompt}
                    className="px-2.5 py-1 rounded-lg bg-white/5 text-white/50 hover:bg-white/10 text-xs transition flex items-center gap-1"
                  >
                    <Plus className="w-3 h-3" />
                    {t('common.add')}
                  </button>
                </div>
                <div className="space-y-2">
                  {formTaskPrompts.map((tp, idx) => (
                    <div key={idx} className="flex items-start gap-2">
                      <textarea
                        value={tp}
                        onChange={(e) => updateTaskPrompt(idx, e.target.value)}
                        rows={2}
                        placeholder={`Task prompt ${idx + 1}...`}
                        className="flex-1 bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-sm focus:border-cyan-500/50 focus:outline-none resize-none"
                      />
                      {formTaskPrompts.length > 1 && (
                        <button
                          onClick={() => removeTaskPrompt(idx)}
                          className="p-2 rounded-lg hover:bg-white/10 transition mt-1"
                        >
                          <X className="w-3.5 h-3.5 text-white/30" />
                        </button>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* Modal Actions */}
            <div className="flex items-center justify-end gap-3 mt-6 pt-4 border-t border-white/10">
              <button
                onClick={() => {
                  setShowCreate(false);
                  resetForm();
                }}
                className="px-4 py-2 rounded-xl bg-white/5 text-white/50 hover:bg-white/10 text-sm transition"
              >
                {t('common.cancel')}
              </button>
              <button
                onClick={handleCreate}
                disabled={creating || !formName.trim() || !formPromptA.trim() || !formPromptB.trim()}
                className="px-4 py-2 rounded-xl bg-cyan-500/20 text-cyan-300 hover:bg-cyan-500/30 text-sm transition disabled:opacity-30 disabled:cursor-not-allowed flex items-center gap-2"
              >
                {creating ? `${t('common.create')}...` : `${t('common.create')} Experiment`}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
