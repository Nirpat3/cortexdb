'use client';

import { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import {
  FlaskConical,
  Plus,
  Play,
  Archive,
  BarChart3,
  RefreshCw,
  Beaker,
  Zap,
  GitBranch,
} from 'lucide-react';
import { superadminApi } from '@/lib/api';
import { useTranslation } from '@/lib/i18n';

type D = Record<string, any>;

const statusColors: Record<string, string> = {
  created: 'blue',
  running: 'amber',
  completed: 'emerald',
  archived: 'zinc',
};

const typeColors: Record<string, string> = {
  behavior_test: 'purple',
  ab_test: 'cyan',
  chaos: 'red',
  freeform: 'zinc',
};

function StatusBadge({ status }: { status: string }) {
  const color = statusColors[status] || 'zinc';
  return (
    <span
      className={`px-2 py-0.5 rounded-full text-[10px] bg-${color}-500/20 text-${color}-300`}
    >
      {status}
    </span>
  );
}

function TypeBadge({ type }: { type: string }) {
  const color = typeColors[type] || 'zinc';
  return (
    <span
      className={`px-2 py-0.5 rounded-full text-[10px] bg-${color}-500/20 text-${color}-300`}
    >
      {type}
    </span>
  );
}

export default function SimulationsPage() {
  const { t } = useTranslation();
  const router = useRouter();

  const [stats, setStats] = useState<D | null>(null);
  const [simulations, setSimulations] = useState<D[]>([]);
  const [loading, setLoading] = useState(true);

  // Create form
  const [showCreate, setShowCreate] = useState(false);
  const [createName, setCreateName] = useState('');
  const [createType, setCreateType] = useState('behavior_test');
  const [createAgentIds, setCreateAgentIds] = useState('');
  const [createConfig, setCreateConfig] = useState('{}');
  const [creating, setCreating] = useState(false);

  // Run task modal
  const [runModal, setRunModal] = useState<{ simId: string; simName: string } | null>(null);
  const [runAgentId, setRunAgentId] = useState('');
  const [runPrompt, setRunPrompt] = useState('');
  const [running, setRunning] = useState(false);
  const [runResult, setRunResult] = useState<D | null>(null);

  // Expanded sim (view results)
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [expandedData, setExpandedData] = useState<D | null>(null);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const [statsRes, simsRes] = await Promise.all([
        superadminApi.getSimulationStats(),
        superadminApi.listSimulations(),
      ]);
      setStats(statsRes);
      setSimulations(Array.isArray(simsRes) ? simsRes : (simsRes as D)?.simulations ?? []);
    } catch (err) {
      console.error('Failed to load simulations', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAll();
  }, [fetchAll]);

  const handleCreate = async () => {
    if (!createName.trim()) return;
    setCreating(true);
    try {
      const agentIds = createAgentIds
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean);
      let config: D = {};
      try {
        config = JSON.parse(createConfig);
      } catch {
        /* keep empty */
      }
      await superadminApi.createSimulation(
        createName.trim(),
        createType,
        config,
        agentIds.length ? agentIds : undefined,
      );
      setCreateName('');
      setCreateType('behavior_test');
      setCreateAgentIds('');
      setCreateConfig('{}');
      setShowCreate(false);
      await fetchAll();
    } catch (err) {
      console.error('Create simulation failed', err);
    } finally {
      setCreating(false);
    }
  };

  const handleRunTask = async () => {
    if (!runModal || !runAgentId.trim() || !runPrompt.trim()) return;
    setRunning(true);
    setRunResult(null);
    try {
      const result = await superadminApi.runSandboxTask(
        runModal.simId,
        runAgentId.trim(),
        runPrompt.trim(),
      );
      setRunResult(result);
    } catch (err) {
      console.error('Run sandbox task failed', err);
    } finally {
      setRunning(false);
    }
  };

  const handleCleanup = async (simId: string) => {
    try {
      await superadminApi.cleanupSimulation(simId);
      await fetchAll();
    } catch (err) {
      console.error('Cleanup failed', err);
    }
  };

  const handleExpand = async (simId: string) => {
    if (expandedId === simId) {
      setExpandedId(null);
      setExpandedData(null);
      return;
    }
    try {
      const data = await superadminApi.getSimulation(simId);
      setExpandedId(simId);
      setExpandedData(data);
    } catch (err) {
      console.error('Failed to load simulation details', err);
    }
  };

  const formatDate = (d: string) => {
    try {
      return new Date(d).toLocaleString();
    } catch {
      return d;
    }
  };

  // Stats helpers
  const totalSims = stats?.total ?? stats?.totalSimulations ?? 0;
  const byStatus = stats?.byStatus ?? stats?.by_status ?? {};
  const byType = stats?.byType ?? stats?.by_type ?? {};
  const avgResults = stats?.avgResults ?? stats?.avg_results ?? 0;

  return (
    <div className="min-h-screen bg-black text-white p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <FlaskConical className="w-7 h-7 text-cyan-400" />
          <div>
            <h1 className="text-2xl font-bold">{t('simulations.title')}</h1>
            <p className="text-sm text-white/50">
              {t('simulations.subtitle')}
            </p>
          </div>
        </div>
        <button
          onClick={() => fetchAll()}
          className="p-2 rounded-xl bg-white/5 hover:bg-white/10 transition border border-white/10"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {/* Quick Nav */}
      <div className="flex items-center gap-3 flex-wrap">
        <button
          onClick={() => router.push('/superadmin/simulations/tests')}
          className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-white/5 hover:bg-white/10 text-sm transition border border-white/10"
        >
          <Beaker className="w-4 h-4 text-purple-400" />
          Behavior Tests
        </button>
        <button
          onClick={() => router.push('/superadmin/simulations/ab-tests')}
          className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-white/5 hover:bg-white/10 text-sm transition border border-white/10"
        >
          <GitBranch className="w-4 h-4 text-cyan-400" />
          A/B Testing
        </button>
      </div>

      {/* Stats Row */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-white/5 border border-white/10 rounded-2xl p-5">
          <div className="flex items-center gap-2 text-white/50 text-xs mb-2">
            <BarChart3 className="w-4 h-4" />
            Total Simulations
          </div>
          <p className="text-3xl font-bold">{totalSims}</p>
        </div>

        <div className="bg-white/5 border border-white/10 rounded-2xl p-5">
          <div className="flex items-center gap-2 text-white/50 text-xs mb-2">
            <Zap className="w-4 h-4" />
            By Status
          </div>
          <div className="space-y-1 text-sm">
            {Object.entries(byStatus).map(([k, v]) => (
              <div key={k} className="flex items-center justify-between">
                <StatusBadge status={k} />
                <span className="text-white/70">{String(v)}</span>
              </div>
            ))}
            {Object.keys(byStatus).length === 0 && (
              <p className="text-white/30 text-xs">{t('common.noData')}</p>
            )}
          </div>
        </div>

        <div className="bg-white/5 border border-white/10 rounded-2xl p-5">
          <div className="flex items-center gap-2 text-white/50 text-xs mb-2">
            <FlaskConical className="w-4 h-4" />
            By Type
          </div>
          <div className="space-y-1 text-sm">
            {Object.entries(byType).map(([k, v]) => (
              <div key={k} className="flex items-center justify-between">
                <TypeBadge type={k} />
                <span className="text-white/70">{String(v)}</span>
              </div>
            ))}
            {Object.keys(byType).length === 0 && (
              <p className="text-white/30 text-xs">{t('common.noData')}</p>
            )}
          </div>
        </div>

        <div className="bg-white/5 border border-white/10 rounded-2xl p-5">
          <div className="flex items-center gap-2 text-white/50 text-xs mb-2">
            <BarChart3 className="w-4 h-4" />
            Avg Results Count
          </div>
          <p className="text-3xl font-bold">
            {typeof avgResults === 'number' ? avgResults.toFixed(1) : avgResults}
          </p>
        </div>
      </div>

      {/* Create Simulation (Collapsible) */}
      <div className="bg-white/5 border border-white/10 rounded-2xl">
        <button
          onClick={() => setShowCreate((v) => !v)}
          className="w-full flex items-center justify-between px-5 py-4 text-left"
        >
          <div className="flex items-center gap-2 text-sm font-semibold">
            <Plus className="w-4 h-4 text-cyan-400" />
            Create Simulation
          </div>
          <span className="text-white/30 text-xs">{showCreate ? 'Collapse' : 'Expand'}</span>
        </button>

        {showCreate && (
          <div className="px-5 pb-5 space-y-4 border-t border-white/5 pt-4">
            <div>
              <label className="block text-xs text-white/50 mb-1">Name</label>
              <input
                type="text"
                value={createName}
                onChange={(e) => setCreateName(e.target.value)}
                placeholder="My simulation..."
                className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-sm focus:border-cyan-500/50 focus:outline-none"
              />
            </div>

            <div>
              <label className="block text-xs text-white/50 mb-1">Type</label>
              <select
                value={createType}
                onChange={(e) => setCreateType(e.target.value)}
                className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-sm focus:border-cyan-500/50 focus:outline-none"
              >
                <option value="behavior_test">behavior_test</option>
                <option value="ab_test">ab_test</option>
                <option value="chaos">chaos</option>
                <option value="freeform">freeform</option>
              </select>
            </div>

            <div>
              <label className="block text-xs text-white/50 mb-1">
                Agent IDs (comma-separated)
              </label>
              <input
                type="text"
                value={createAgentIds}
                onChange={(e) => setCreateAgentIds(e.target.value)}
                placeholder="T1-OPS-POS-001, T2-FIN-ACC-001"
                className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-sm focus:border-cyan-500/50 focus:outline-none"
              />
            </div>

            <div>
              <label className="block text-xs text-white/50 mb-1">Config (JSON)</label>
              <textarea
                value={createConfig}
                onChange={(e) => setCreateConfig(e.target.value)}
                rows={4}
                className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-sm focus:border-cyan-500/50 focus:outline-none font-mono"
              />
            </div>

            <button
              onClick={handleCreate}
              disabled={creating || !createName.trim()}
              className="px-4 py-2 rounded-xl bg-cyan-500/20 text-cyan-300 hover:bg-cyan-500/30 text-sm transition disabled:opacity-40"
            >
              {creating ? 'Creating...' : 'Create Simulation'}
            </button>
          </div>
        )}
      </div>

      {/* Simulations List */}
      <div className="space-y-3">
        <h2 className="text-lg font-semibold flex items-center gap-2">
          <FlaskConical className="w-5 h-5 text-white/50" />
          Simulations
        </h2>

        {loading && simulations.length === 0 && (
          <p className="text-white/30 text-sm">{t('common.loading')}</p>
        )}

        {!loading && simulations.length === 0 && (
          <p className="text-white/30 text-sm">{t('common.noData')}</p>
        )}

        {simulations.map((sim: D) => {
          const simId = sim.id ?? sim.sim_id ?? '';
          const isExpanded = expandedId === simId;

          return (
            <div
              key={simId}
              className="bg-white/5 border border-white/10 rounded-2xl p-5 space-y-3"
            >
              {/* Sim Header */}
              <div className="flex items-start justify-between gap-4">
                <div className="space-y-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-semibold text-sm">
                      {sim.name ?? sim.sim_name ?? 'Unnamed'}
                    </span>
                    <TypeBadge type={sim.type ?? sim.sim_type ?? 'freeform'} />
                    <StatusBadge status={sim.status ?? 'created'} />
                  </div>
                  <div className="text-xs text-white/40 flex items-center gap-3">
                    <span>Created: {formatDate(sim.created_at ?? '')}</span>
                    {sim.snapshot_count !== undefined && (
                      <span>Snapshots: {sim.snapshot_count}</span>
                    )}
                    {sim.results_count !== undefined && (
                      <span>Results: {sim.results_count}</span>
                    )}
                  </div>
                </div>

                {/* Actions */}
                <div className="flex items-center gap-2 shrink-0">
                  <button
                    onClick={() => handleExpand(simId)}
                    className="px-4 py-2 rounded-xl bg-cyan-500/20 text-cyan-300 hover:bg-cyan-500/30 text-sm transition"
                    title="View details / results"
                  >
                    <BarChart3 className="w-4 h-4" />
                  </button>
                  <button
                    onClick={() => {
                      setRunModal({ simId, simName: sim.name ?? sim.sim_name ?? simId });
                      setRunAgentId('');
                      setRunPrompt('');
                      setRunResult(null);
                    }}
                    className="px-4 py-2 rounded-xl bg-cyan-500/20 text-cyan-300 hover:bg-cyan-500/30 text-sm transition"
                    title="Run task in sandbox"
                  >
                    <Play className="w-4 h-4" />
                  </button>
                  <button
                    onClick={() => handleCleanup(simId)}
                    className="px-4 py-2 rounded-xl bg-white/5 text-white/50 hover:bg-white/10 text-sm transition border border-white/10"
                    title="Cleanup simulation"
                  >
                    <Archive className="w-4 h-4" />
                  </button>
                </div>
              </div>

              {/* Expanded Results */}
              {isExpanded && expandedData && (
                <div className="border-t border-white/5 pt-3 space-y-2">
                  <h3 className="text-xs font-semibold text-white/50">Simulation Details</h3>
                  <pre className="text-xs bg-black/50 border border-white/5 rounded-xl p-3 overflow-auto max-h-64 text-white/70">
                    {JSON.stringify(expandedData, null, 2)}
                  </pre>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Run Task Modal */}
      {runModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
          <div className="bg-zinc-900 border border-white/10 rounded-2xl p-6 w-full max-w-lg space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold flex items-center gap-2">
                <Play className="w-5 h-5 text-cyan-400" />
                Run Task in Sandbox
              </h2>
              <button
                onClick={() => setRunModal(null)}
                className="text-white/40 hover:text-white/80 text-sm"
              >
                Close
              </button>
            </div>

            <div>
              <label className="block text-xs text-white/50 mb-1">Simulation</label>
              <input
                type="text"
                value={`${runModal.simName} (${runModal.simId})`}
                readOnly
                className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-sm focus:border-cyan-500/50 focus:outline-none text-white/40"
              />
            </div>

            <div>
              <label className="block text-xs text-white/50 mb-1">Agent ID</label>
              <input
                type="text"
                value={runAgentId}
                onChange={(e) => setRunAgentId(e.target.value)}
                placeholder="T1-OPS-POS-001"
                className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-sm focus:border-cyan-500/50 focus:outline-none"
              />
            </div>

            <div>
              <label className="block text-xs text-white/50 mb-1">Task Prompt</label>
              <textarea
                value={runPrompt}
                onChange={(e) => setRunPrompt(e.target.value)}
                rows={4}
                placeholder="Describe the task to run..."
                className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-sm focus:border-cyan-500/50 focus:outline-none"
              />
            </div>

            <button
              onClick={handleRunTask}
              disabled={running || !runAgentId.trim() || !runPrompt.trim()}
              className="px-4 py-2 rounded-xl bg-cyan-500/20 text-cyan-300 hover:bg-cyan-500/30 text-sm transition disabled:opacity-40"
            >
              {running ? 'Running...' : 'Run Task'}
            </button>

            {runResult && (
              <div className="border-t border-white/5 pt-3">
                <h3 className="text-xs font-semibold text-white/50 mb-2">Result</h3>
                <pre className="text-xs bg-black/50 border border-white/5 rounded-xl p-3 overflow-auto max-h-48 text-white/70">
                  {JSON.stringify(runResult, null, 2)}
                </pre>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
