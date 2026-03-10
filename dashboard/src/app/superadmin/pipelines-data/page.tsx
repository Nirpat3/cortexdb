'use client';

import { useEffect, useState, useCallback } from 'react';
import { Workflow, RefreshCw, Play, Plus, ChevronDown, ChevronRight, Clock, ArrowDown } from 'lucide-react';
import { superadminApi } from '@/lib/api';
import { useTranslation } from '@/lib/i18n';

type D = Record<string, unknown>;

const STATUS_COLORS: Record<string, string> = {
  draft: 'bg-white/10 text-white/50',
  active: 'bg-emerald-500/20 text-emerald-300',
  paused: 'bg-amber-500/20 text-amber-300',
  error: 'bg-red-500/20 text-red-300',
  running: 'bg-blue-500/20 text-blue-300',
  success: 'bg-emerald-500/20 text-emerald-300',
  failed: 'bg-red-500/20 text-red-300',
};

const STAGE_TYPES = [
  'extract_sql', 'extract_api', 'extract_file',
  'transform_map', 'transform_filter', 'transform_aggregate',
  'load_table', 'load_api',
];

const STAGE_ICONS: Record<string, string> = {
  extract_sql: 'DB', extract_api: 'API', extract_file: 'FILE',
  transform_map: 'MAP', transform_filter: 'FLT', transform_aggregate: 'AGG',
  load_table: 'TBL', load_api: 'OUT',
};

const MOCK_PIPELINES: D[] = [
  { id: 'pip-1', name: 'User Analytics ETL', description: 'Daily user metrics extraction', stage_count: 4, schedule: '0 2 * * *', status: 'active', last_run: '2026-03-08T01:55:00Z', run_count: 142, stages: [
    { type: 'extract_sql', name: 'Extract Users', config: 'SELECT * FROM users WHERE updated > $1' },
    { type: 'transform_filter', name: 'Filter Active', config: 'status = active' },
    { type: 'transform_aggregate', name: 'Aggregate Metrics', config: 'GROUP BY region, COUNT(*)' },
    { type: 'load_table', name: 'Load Analytics', config: 'analytics.user_metrics' },
  ]},
  { id: 'pip-2', name: 'Agent Log Ingestion', description: 'Stream agent logs to warehouse', stage_count: 3, schedule: '*/15 * * * *', status: 'active', last_run: '2026-03-08T08:30:00Z', run_count: 1847, stages: [
    { type: 'extract_api', name: 'Fetch Logs', config: 'GET /api/v1/agents/logs?since=$last' },
    { type: 'transform_map', name: 'Normalize Fields', config: 'map(timestamp, agent_id, level, message)' },
    { type: 'load_table', name: 'Insert Warehouse', config: 'warehouse.agent_logs' },
  ]},
  { id: 'pip-3', name: 'Cost Report Pipeline', description: 'Weekly cost aggregation', stage_count: 5, schedule: '0 0 * * 1', status: 'paused', last_run: '2026-03-03T00:00:00Z', run_count: 23, stages: [] },
  { id: 'pip-4', name: 'Backup Export', description: 'Nightly DB export', stage_count: 2, schedule: '0 3 * * *', status: 'error', last_run: '2026-03-08T03:01:00Z', run_count: 89, stages: [] },
];

const MOCK_RUNS: D[] = [
  { pipeline: 'User Analytics ETL', status: 'success', duration: '2m 14s', stages_completed: '4/4', timestamp: '2026-03-08T01:57:14Z' },
  { pipeline: 'Agent Log Ingestion', status: 'success', duration: '18s', stages_completed: '3/3', timestamp: '2026-03-08T08:30:18Z' },
  { pipeline: 'Backup Export', status: 'failed', duration: '4m 02s', stages_completed: '1/2', timestamp: '2026-03-08T03:05:02Z' },
  { pipeline: 'User Analytics ETL', status: 'success', duration: '2m 08s', stages_completed: '4/4', timestamp: '2026-03-07T01:56:08Z' },
];

export default function DataPipelineBuilderPage() {
  const { t } = useTranslation();
  const [pipelines, setPipelines] = useState<D[]>(MOCK_PIPELINES);
  const [runs] = useState<D[]>(MOCK_RUNS);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState('');
  const [newDesc, setNewDesc] = useState('');
  const [addingStage, setAddingStage] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const data = await superadminApi.pipelineList() as D;
      if ((data as D).pipelines) setPipelines((data as D).pipelines as D[]);
    } catch { /* use mock */ }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const stats = {
    total: pipelines.length,
    active: pipelines.filter(p => p.status === 'active').length,
    runsToday: 24,
    successRate: '96.2%',
  };

  const handleCreate = () => {
    if (!newName) return;
    setPipelines(prev => [...prev, { id: `pip-${Date.now()}`, name: newName, description: newDesc, stage_count: 0, schedule: 'manual', status: 'draft', last_run: null, run_count: 0, stages: [] }]);
    setNewName(''); setNewDesc(''); setShowCreate(false);
  };

  const addStage = (pipId: string, type: string) => {
    setPipelines(prev => prev.map(p => p.id === pipId ? { ...p, stages: [...(p.stages as D[] || []), { type, name: type.replace('_', ' '), config: '' }], stage_count: ((p.stage_count as number) || 0) + 1 } : p));
    setAddingStage(null);
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold mb-1 flex items-center gap-2">
            <Workflow className="w-6 h-6 text-cyan-400" /> Data Pipeline Builder
          </h1>
          <p className="text-sm text-white/40">Visual ETL pipeline designer</p>
        </div>
        <div className="flex gap-2">
          <button onClick={() => setShowCreate(!showCreate)} className="glass px-3 py-2 rounded-lg text-xs text-cyan-400 hover:text-cyan-300 flex items-center gap-1"><Plus className="w-3.5 h-3.5" /> Create Pipeline</button>
          <button onClick={refresh} className="glass px-3 py-2 rounded-lg text-xs text-white/60 hover:text-white/90"><RefreshCw className="w-3.5 h-3.5" /></button>
        </div>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
        {[['Total Pipelines', stats.total, ''], ['Active', stats.active, 'text-emerald-400'], ['Runs Today', stats.runsToday, 'text-blue-400'], ['Success Rate', stats.successRate, 'text-cyan-400']].map(([l, v, c]) => (
          <div key={l as string} className="glass rounded-xl p-3">
            <div className="text-xs text-white/40">{l as string}</div>
            <div className={`text-2xl font-bold ${c}`}>{v as string}</div>
          </div>
        ))}
      </div>

      {showCreate && (
        <div className="glass-heavy rounded-xl p-4 mb-6">
          <h3 className="text-sm font-semibold mb-3">New Pipeline</h3>
          <div className="flex gap-3">
            <input value={newName} onChange={e => setNewName(e.target.value)} placeholder="Pipeline name" className="flex-1 bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm" />
            <input value={newDesc} onChange={e => setNewDesc(e.target.value)} placeholder="Description" className="flex-1 bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm" />
            <button onClick={handleCreate} className="glass px-4 py-2 rounded-lg text-xs text-emerald-400">Create</button>
          </div>
        </div>
      )}

      <div className="space-y-3 mb-8">
        {pipelines.map((p) => (
          <div key={p.id as string} className="glass rounded-xl">
            <div className="p-4 flex items-center justify-between cursor-pointer" onClick={() => setExpanded(expanded === p.id ? null : p.id as string)}>
              <div className="flex items-center gap-3">
                {expanded === p.id ? <ChevronDown className="w-4 h-4 text-white/40" /> : <ChevronRight className="w-4 h-4 text-white/40" />}
                <div>
                  <div className="text-sm font-semibold">{p.name as string}</div>
                  <div className="text-[10px] text-white/30">{p.description as string}</div>
                </div>
              </div>
              <div className="flex items-center gap-4 text-xs">
                <span className="text-white/40">{p.stage_count as number} stages</span>
                <span className="text-white/40 flex items-center gap-1"><Clock className="w-3 h-3" />{p.schedule as string}</span>
                <span className={`px-2 py-0.5 rounded-full text-[10px] ${STATUS_COLORS[(p.status as string)] ?? ''}`}>{p.status as string}</span>
                <span className="text-white/30">{p.run_count as number} runs</span>
              </div>
            </div>
            {expanded === p.id && (
              <div className="border-t border-white/5 p-4">
                <div className="flex items-center gap-2 mb-4">
                  <button className="glass px-3 py-1.5 rounded-lg text-xs text-emerald-400 flex items-center gap-1"><Play className="w-3 h-3" /> Run Pipeline</button>
                  <div className="relative">
                    <button onClick={() => setAddingStage(addingStage === p.id ? null : p.id as string)} className="glass px-3 py-1.5 rounded-lg text-xs text-cyan-400 flex items-center gap-1"><Plus className="w-3 h-3" /> Add Stage</button>
                    {addingStage === p.id && (
                      <div className="absolute top-full mt-1 left-0 glass-heavy rounded-lg p-2 z-10 min-w-[180px]">
                        {STAGE_TYPES.map(st => (
                          <button key={st} onClick={() => addStage(p.id as string, st)} className="block w-full text-left px-2 py-1 text-xs text-white/60 hover:text-white hover:bg-white/5 rounded">{st}</button>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
                <div className="flex flex-col items-center gap-1">
                  {((p.stages as D[]) ?? []).map((s, i) => (
                    <div key={i} className="w-full max-w-md">
                      <div className="glass-heavy rounded-lg p-3 flex items-center gap-3">
                        <div className="w-8 h-8 rounded bg-cyan-500/20 flex items-center justify-center text-[10px] font-bold text-cyan-300">{STAGE_ICONS[(s.type as string)] ?? '?'}</div>
                        <div className="flex-1">
                          <div className="text-xs font-semibold">{s.name as string}</div>
                          <div className="text-[10px] text-white/30 font-mono truncate">{(s.config as string) || 'No config'}</div>
                        </div>
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-white/5 text-white/40">{s.type as string}</span>
                      </div>
                      {i < ((p.stages as D[]).length - 1) && <div className="flex justify-center py-1"><ArrowDown className="w-4 h-4 text-white/20" /></div>}
                    </div>
                  ))}
                  {((p.stages as D[]) ?? []).length === 0 && <div className="text-xs text-white/30 py-4">No stages defined. Add stages to build your pipeline.</div>}
                </div>
              </div>
            )}
          </div>
        ))}
      </div>

      <h2 className="text-lg font-semibold mb-3">Recent Runs</h2>
      <div className="glass rounded-xl overflow-hidden">
        <table className="w-full text-xs">
          <thead><tr className="border-b border-white/5 text-white/40">
            <th className="text-left p-3">Pipeline</th><th className="text-left p-3">Status</th><th className="text-left p-3">Duration</th><th className="text-left p-3">Stages</th><th className="text-left p-3">Timestamp</th>
          </tr></thead>
          <tbody>
            {runs.map((r, i) => (
              <tr key={i} className="border-b border-white/5 last:border-0">
                <td className="p-3 text-white/80">{r.pipeline as string}</td>
                <td className="p-3"><span className={`px-2 py-0.5 rounded-full ${STATUS_COLORS[(r.status as string)] ?? ''}`}>{r.status as string}</span></td>
                <td className="p-3 text-white/50">{r.duration as string}</td>
                <td className="p-3 text-white/50">{r.stages_completed as string}</td>
                <td className="p-3 text-white/30">{new Date(r.timestamp as string).toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
