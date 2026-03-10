'use client';

import { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import {
  Beaker,
  Plus,
  Play,
  ArrowLeft,
  CheckCircle2,
  XCircle,
  Clock,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';
import { superadminApi } from '@/lib/api';
import { useTranslation } from '@/lib/i18n';

type D = Record<string, any>;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function passRate(passed: number, total: number): number {
  return total === 0 ? 0 : Math.round((passed / total) * 100);
}

function fmtDate(iso: string | undefined): string {
  if (!iso) return '';
  const d = new Date(iso);
  return d.toLocaleString();
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function BehaviorTestsPage() {
  const { t } = useTranslation();
  const router = useRouter();

  // --- state ---------------------------------------------------------------
  const [suites, setSuites] = useState<D[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedSuite, setExpandedSuite] = useState<string | null>(null);
  const [runningSuiteId, setRunningSuiteId] = useState<string | null>(null);

  // create modal
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState('');
  const [newDesc, setNewDesc] = useState('');
  const [newCases, setNewCases] = useState<D[]>([
    { prompt: '', expected_keywords: '', must_not_contain: '', agent_id: '' },
  ]);
  const [creating, setCreating] = useState(false);

  // results viewer
  const [viewingResults, setViewingResults] = useState<D | null>(null);

  // history viewer
  const [historySuiteId, setHistorySuiteId] = useState<string | null>(null);
  const [history, setHistory] = useState<D[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);

  // --- data loading --------------------------------------------------------
  const fetchSuites = useCallback(async () => {
    setLoading(true);
    try {
      const res = await superadminApi.listTestSuites();
      setSuites((res as any)?.suites ?? (Array.isArray(res) ? res : []));
    } catch {
      setSuites([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchSuites();
  }, [fetchSuites]);

  // --- handlers ------------------------------------------------------------
  const handleRun = async (suiteId: string) => {
    setRunningSuiteId(suiteId);
    try {
      const res = await superadminApi.runTestSuite(suiteId);
      const runId = (res as any)?.run_id;
      if (runId) {
        const results = await superadminApi.getTestRunResults(runId);
        setViewingResults(results as D);
      }
    } catch (err) {
      console.error('Run failed', err);
    } finally {
      setRunningSuiteId(null);
    }
  };

  const handleViewHistory = async (suiteId: string) => {
    setHistorySuiteId(suiteId);
    setHistoryLoading(true);
    try {
      const res = await superadminApi.getTestSuiteHistory(suiteId, 20);
      setHistory((res as any)?.runs ?? (Array.isArray(res) ? res : []));
    } catch {
      setHistory([]);
    } finally {
      setHistoryLoading(false);
    }
  };

  const handleCreate = async () => {
    if (!newName.trim()) return;
    setCreating(true);
    try {
      const cases = newCases
        .filter((c) => c.prompt.trim())
        .map((c) => ({
          prompt: c.prompt.trim(),
          expected_keywords: c.expected_keywords
            ? c.expected_keywords
                .split(',')
                .map((k: string) => k.trim())
                .filter(Boolean)
            : [],
          must_not_contain: c.must_not_contain
            ? c.must_not_contain
                .split(',')
                .map((k: string) => k.trim())
                .filter(Boolean)
            : [],
          agent_id: c.agent_id.trim() || undefined,
        }));
      await superadminApi.createTestSuite(newName.trim(), newDesc.trim(), cases);
      setShowCreate(false);
      setNewName('');
      setNewDesc('');
      setNewCases([{ prompt: '', expected_keywords: '', must_not_contain: '', agent_id: '' }]);
      fetchSuites();
    } catch (err) {
      console.error('Create failed', err);
    } finally {
      setCreating(false);
    }
  };

  const addCase = () =>
    setNewCases((prev) => [
      ...prev,
      { prompt: '', expected_keywords: '', must_not_contain: '', agent_id: '' },
    ]);

  const removeCase = (idx: number) =>
    setNewCases((prev) => prev.filter((_, i) => i !== idx));

  const updateCase = (idx: number, field: string, value: string) =>
    setNewCases((prev) => prev.map((c, i) => (i === idx ? { ...c, [field]: value } : c)));

  // --- render helpers ------------------------------------------------------
  const inputCls =
    'w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-sm focus:border-emerald-500/50 focus:outline-none';
  const primaryBtn =
    'px-4 py-2 rounded-xl bg-emerald-500/20 text-emerald-300 hover:bg-emerald-500/30 text-sm transition';
  const cardCls = 'bg-white/5 border border-white/10 rounded-2xl p-5';

  // -----------------------------------------------------------------------
  return (
    <div className="min-h-screen bg-black text-white p-8 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <button
            onClick={() => router.push('/superadmin/simulations')}
            className="p-2 rounded-xl hover:bg-white/5 transition"
          >
            <ArrowLeft size={18} className="text-white/60" />
          </button>
          <Beaker size={22} className="text-emerald-400" />
          <h1 className="text-2xl font-semibold">{t('simulations.tests.title')}</h1>
        </div>
        <button onClick={() => setShowCreate(true)} className={primaryBtn}>
          <span className="flex items-center gap-2">
            <Plus size={14} /> New Suite
          </span>
        </button>
      </div>

      {/* Suite List */}
      {loading ? (
        <p className="text-white/40 text-sm">{t('common.loading')}</p>
      ) : suites.length === 0 ? (
        <p className="text-white/40 text-sm">{t('common.noData')}</p>
      ) : (
        <div className="space-y-4">
          {suites.map((suite) => {
            const sid = suite.id ?? suite.suite_id;
            const expanded = expandedSuite === sid;
            const cases: D[] = suite.test_cases ?? [];
            const lastRun: D | undefined = suite.last_run;
            const lastTotal = lastRun?.total ?? 0;
            const lastPassed = lastRun?.passed ?? 0;
            const lastFailed = lastTotal - lastPassed;
            const rate = passRate(lastPassed, lastTotal);

            return (
              <div key={sid} className={cardCls}>
                {/* Suite header row */}
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    <button
                      className="flex items-center gap-2 text-left"
                      onClick={() => setExpandedSuite(expanded ? null : sid)}
                    >
                      {expanded ? (
                        <ChevronUp size={16} className="text-white/40" />
                      ) : (
                        <ChevronDown size={16} className="text-white/40" />
                      )}
                      <h2 className="text-base font-medium truncate">{suite.name}</h2>
                    </button>
                    {suite.description && (
                      <p className="text-xs text-white/40 mt-1 ml-6">{suite.description}</p>
                    )}
                    <p className="text-[11px] text-white/30 mt-1 ml-6">
                      {cases.length} test case{cases.length !== 1 ? 's' : ''}
                    </p>
                  </div>

                  {/* Last run summary */}
                  {lastRun && (
                    <div className="shrink-0 text-right space-y-1">
                      <div className="flex items-center gap-2 justify-end">
                        <span className="px-2 py-0.5 rounded-full text-[10px] bg-emerald-500/20 text-emerald-300">
                          {lastPassed} passed
                        </span>
                        {lastFailed > 0 && (
                          <span className="px-2 py-0.5 rounded-full text-[10px] bg-red-500/20 text-red-300">
                            {lastFailed} failed
                          </span>
                        )}
                      </div>
                      <div className="h-2 rounded-full bg-white/10 overflow-hidden flex w-32 ml-auto">
                        {lastTotal > 0 && (
                          <>
                            <div
                              className="bg-emerald-500 h-full"
                              style={{ width: `${rate}%` }}
                            />
                            <div className="bg-red-500 h-full flex-1" />
                          </>
                        )}
                      </div>
                      <p className="text-[10px] text-white/30">
                        {lastRun.run_id && <span className="mr-2">#{lastRun.run_id.slice(0, 8)}</span>}
                        {fmtDate(lastRun.created_at ?? lastRun.timestamp)}
                      </p>
                    </div>
                  )}

                  {/* Actions */}
                  <div className="flex items-center gap-2 shrink-0">
                    <button
                      onClick={() => handleRun(sid)}
                      disabled={runningSuiteId === sid}
                      className="px-3 py-1.5 rounded-xl bg-emerald-500/20 text-emerald-300 hover:bg-emerald-500/30 text-xs transition disabled:opacity-40 flex items-center gap-1"
                    >
                      {runningSuiteId === sid ? (
                        <Clock size={12} className="animate-spin" />
                      ) : (
                        <Play size={12} />
                      )}
                      Run
                    </button>
                    <button
                      onClick={() => handleViewHistory(sid)}
                      className="px-3 py-1.5 rounded-xl bg-white/5 text-white/60 hover:bg-white/10 text-xs transition"
                    >
                      History
                    </button>
                    <button
                      onClick={() => router.push(`/superadmin/simulations/tests/${sid}/edit`)}
                      className="px-3 py-1.5 rounded-xl bg-white/5 text-white/60 hover:bg-white/10 text-xs transition"
                    >
                      Edit
                    </button>
                  </div>
                </div>

                {/* Expanded test cases */}
                {expanded && cases.length > 0 && (
                  <div className="mt-4 ml-6 space-y-3">
                    {cases.map((tc: D, idx: number) => (
                      <div
                        key={tc.id ?? idx}
                        className="bg-white/[0.03] border border-white/5 rounded-xl p-3 text-xs space-y-1"
                      >
                        <p className="text-white/80 font-mono">{tc.prompt}</p>
                        {tc.expected_keywords?.length > 0 && (
                          <p className="text-emerald-400/70">
                            Expected: {(tc.expected_keywords as string[]).join(', ')}
                          </p>
                        )}
                        {tc.must_not_contain?.length > 0 && (
                          <p className="text-red-400/70">
                            Must not contain: {(tc.must_not_contain as string[]).join(', ')}
                          </p>
                        )}
                        {tc.agent_id && (
                          <p className="text-white/30">Agent: {tc.agent_id}</p>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* ----------------------------------------------------------------- */}
      {/* Create Suite Modal                                                */}
      {/* ----------------------------------------------------------------- */}
      {showCreate && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-zinc-900 border border-white/10 rounded-2xl p-6 w-full max-w-2xl max-h-[80vh] overflow-y-auto">
            <h2 className="text-lg font-semibold mb-4">Create Test Suite</h2>

            <div className="space-y-4">
              <div>
                <label className="text-xs text-white/40 mb-1 block">Suite Name</label>
                <input
                  className={inputCls}
                  placeholder="e.g. Core Safety Checks"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                />
              </div>
              <div>
                <label className="text-xs text-white/40 mb-1 block">Description</label>
                <input
                  className={inputCls}
                  placeholder="Optional description"
                  value={newDesc}
                  onChange={(e) => setNewDesc(e.target.value)}
                />
              </div>

              {/* Test cases builder */}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <label className="text-xs text-white/40">Test Cases</label>
                  <button onClick={addCase} className="text-xs text-emerald-400 hover:text-emerald-300 transition">
                    + Add Case
                  </button>
                </div>

                <div className="space-y-4">
                  {newCases.map((tc, idx) => (
                    <div key={idx} className="bg-white/[0.03] border border-white/5 rounded-xl p-4 space-y-3 relative">
                      {newCases.length > 1 && (
                        <button
                          onClick={() => removeCase(idx)}
                          className="absolute top-2 right-2 text-red-400/60 hover:text-red-400 text-xs transition"
                        >
                          <XCircle size={14} />
                        </button>
                      )}
                      <div>
                        <label className="text-[11px] text-white/30 mb-1 block">
                          Prompt
                        </label>
                        <textarea
                          className={`${inputCls} min-h-[60px] resize-y`}
                          placeholder="Enter the test prompt..."
                          value={tc.prompt}
                          onChange={(e) => updateCase(idx, 'prompt', e.target.value)}
                        />
                      </div>
                      <div>
                        <label className="text-[11px] text-white/30 mb-1 block">
                          Expected Keywords (comma-separated)
                        </label>
                        <input
                          className={inputCls}
                          placeholder="e.g. safety, protocol, approved"
                          value={tc.expected_keywords}
                          onChange={(e) => updateCase(idx, 'expected_keywords', e.target.value)}
                        />
                      </div>
                      <div>
                        <label className="text-[11px] text-white/30 mb-1 block">
                          Must Not Contain (comma-separated)
                        </label>
                        <input
                          className={inputCls}
                          placeholder="e.g. error, unauthorized"
                          value={tc.must_not_contain}
                          onChange={(e) => updateCase(idx, 'must_not_contain', e.target.value)}
                        />
                      </div>
                      <div>
                        <label className="text-[11px] text-white/30 mb-1 block">
                          Agent ID (optional)
                        </label>
                        <input
                          className={inputCls}
                          placeholder="e.g. T1-OPS-POS-001"
                          value={tc.agent_id}
                          onChange={(e) => updateCase(idx, 'agent_id', e.target.value)}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            <div className="flex items-center justify-end gap-3 mt-6">
              <button
                onClick={() => setShowCreate(false)}
                className="px-4 py-2 rounded-xl text-white/40 hover:text-white/60 text-sm transition"
              >
                {t('common.cancel')}
              </button>
              <button onClick={handleCreate} disabled={creating} className={primaryBtn}>
                {creating ? `${t('common.create')}...` : `${t('common.create')} Suite`}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ----------------------------------------------------------------- */}
      {/* Run Results Viewer Modal                                          */}
      {/* ----------------------------------------------------------------- */}
      {viewingResults && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-zinc-900 border border-white/10 rounded-2xl p-6 w-full max-w-2xl max-h-[80vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold">Run Results</h2>
              <button
                onClick={() => setViewingResults(null)}
                className="text-white/40 hover:text-white/60 transition"
              >
                <XCircle size={18} />
              </button>
            </div>

            {/* Summary */}
            {(() => {
              const results: D[] = viewingResults.results ?? [];
              const total = results.length;
              const passed = results.filter((r) => r.passed).length;
              const failed = total - passed;
              const rate = passRate(passed, total);

              return (
                <>
                  <div className="flex items-center gap-4 mb-4">
                    <span className="text-sm text-white/60">Total: {total}</span>
                    <span className="px-2 py-0.5 rounded-full text-[10px] bg-emerald-500/20 text-emerald-300">
                      {passed} passed
                    </span>
                    <span className="px-2 py-0.5 rounded-full text-[10px] bg-red-500/20 text-red-300">
                      {failed} failed
                    </span>
                    <span className="text-sm text-white/40">{rate}% pass rate</span>
                  </div>
                  <div className="h-2 rounded-full bg-white/10 overflow-hidden flex mb-6">
                    {total > 0 && (
                      <>
                        <div className="bg-emerald-500 h-full" style={{ width: `${rate}%` }} />
                        <div className="bg-red-500 h-full flex-1" />
                      </>
                    )}
                  </div>

                  {/* Per-result list */}
                  <div className="space-y-3">
                    {results.map((r, idx) => (
                      <div key={r.id ?? idx} className={cardCls}>
                        <div className="flex items-center gap-3">
                          {r.passed ? (
                            <CheckCircle2 size={16} className="text-emerald-400 shrink-0" />
                          ) : (
                            <XCircle size={16} className="text-red-400 shrink-0" />
                          )}
                          <div className="flex-1 min-w-0">
                            {r.agent_id && (
                              <span className="text-[11px] text-white/30 mr-2">{r.agent_id}</span>
                            )}
                            <span className="text-xs text-white/70 truncate block">
                              {(r.prompt ?? '').slice(0, 120)}
                              {(r.prompt ?? '').length > 120 ? '...' : ''}
                            </span>
                          </div>
                          {r.passed ? (
                            <span className="px-2 py-0.5 rounded-full text-[10px] bg-emerald-500/20 text-emerald-300">
                              PASS
                            </span>
                          ) : (
                            <span className="px-2 py-0.5 rounded-full text-[10px] bg-red-500/20 text-red-300">
                              FAIL
                            </span>
                          )}
                        </div>

                        {/* Failure details */}
                        {!r.passed && (
                          <div className="mt-2 ml-7 text-[11px] space-y-1">
                            {r.missing_keywords?.length > 0 && (
                              <p className="text-red-400/70">
                                Missing keywords: {(r.missing_keywords as string[]).join(', ')}
                              </p>
                            )}
                            {r.forbidden_found?.length > 0 && (
                              <p className="text-red-400/70">
                                Forbidden found: {(r.forbidden_found as string[]).join(', ')}
                              </p>
                            )}
                          </div>
                        )}

                        {/* Response preview */}
                        {r.response_preview && (
                          <p className="mt-2 ml-7 text-[11px] text-white/30 truncate">
                            Response: {r.response_preview}
                          </p>
                        )}
                      </div>
                    ))}
                  </div>
                </>
              );
            })()}
          </div>
        </div>
      )}

      {/* ----------------------------------------------------------------- */}
      {/* Suite History Modal                                               */}
      {/* ----------------------------------------------------------------- */}
      {historySuiteId && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-zinc-900 border border-white/10 rounded-2xl p-6 w-full max-w-2xl max-h-[80vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold">Suite History</h2>
              <button
                onClick={() => {
                  setHistorySuiteId(null);
                  setHistory([]);
                }}
                className="text-white/40 hover:text-white/60 transition"
              >
                <XCircle size={18} />
              </button>
            </div>

            {historyLoading ? (
              <p className="text-white/40 text-sm">{t('common.loading')}</p>
            ) : history.length === 0 ? (
              <p className="text-white/40 text-sm">{t('common.noData')}</p>
            ) : (
              <div className="space-y-3">
                {history.map((run, idx) => {
                  const total = run.total ?? 0;
                  const passed = run.passed ?? 0;
                  const failed = total - passed;
                  const rate = passRate(passed, total);

                  return (
                    <div key={run.run_id ?? idx} className={cardCls}>
                      <div className="flex items-center justify-between gap-4">
                        <div className="space-y-1">
                          <div className="flex items-center gap-2">
                            <Clock size={12} className="text-white/30" />
                            <span className="text-xs text-white/60">
                              {fmtDate(run.created_at ?? run.timestamp)}
                            </span>
                            {run.run_id && (
                              <span className="text-[10px] text-white/20 font-mono">
                                #{run.run_id.slice(0, 8)}
                              </span>
                            )}
                          </div>
                          <div className="flex items-center gap-2 ml-5">
                            <span className="px-2 py-0.5 rounded-full text-[10px] bg-emerald-500/20 text-emerald-300">
                              {passed} passed
                            </span>
                            {failed > 0 && (
                              <span className="px-2 py-0.5 rounded-full text-[10px] bg-red-500/20 text-red-300">
                                {failed} failed
                              </span>
                            )}
                            <span className="text-[11px] text-white/30">{rate}%</span>
                          </div>
                        </div>

                        <div className="flex items-center gap-3 shrink-0">
                          <div className="h-2 rounded-full bg-white/10 overflow-hidden flex w-24">
                            {total > 0 && (
                              <>
                                <div
                                  className="bg-emerald-500 h-full"
                                  style={{ width: `${rate}%` }}
                                />
                                <div className="bg-red-500 h-full flex-1" />
                              </>
                            )}
                          </div>
                          <button
                            onClick={async () => {
                              if (!run.run_id) return;
                              try {
                                const res = await superadminApi.getTestRunResults(run.run_id);
                                setHistorySuiteId(null);
                                setHistory([]);
                                setViewingResults(res as D);
                              } catch (err) {
                                console.error('Failed to load results', err);
                              }
                            }}
                            className="text-xs text-emerald-400 hover:text-emerald-300 transition"
                          >
                            View Results
                          </button>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
