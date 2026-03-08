'use client';

import { useState, useEffect, useCallback } from 'react';
import { GitBranch, Play, Plus, RefreshCw, CheckCircle, XCircle, Clock, ChevronDown, ChevronUp } from 'lucide-react';
import { superadminApi } from '@/lib/api';
import { useTranslation } from '@/lib/i18n';

const CONDITION_COLORS: Record<string, string> = {
  always: 'text-blue-400 bg-blue-500/10',
  on_success: 'text-green-400 bg-green-500/10',
  on_failure: 'text-red-400 bg-red-500/10',
};

export default function WorkflowsPage() {
  const { t } = useTranslation();
  const [workflows, setWorkflows] = useState<any[]>([]);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [executing, setExecuting] = useState<string | null>(null);

  // Create form
  const [showCreate, setShowCreate] = useState(false);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [stepsJson, setStepsJson] = useState('[\n  {\n    "name": "step-1",\n    "agent_id": "CDB-ENG-001",\n    "prompt": "Analyze the codebase for improvements",\n    "depends_on": [],\n    "condition": "always"\n  }\n]');

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const res = await superadminApi.listWorkflows();
      setWorkflows((res as any).workflows || []);
    } catch { /* silent */ }
    setLoading(false);
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  const handleCreate = async () => {
    if (!name.trim()) return;
    try {
      const steps = JSON.parse(stepsJson);
      setCreating(true);
      await superadminApi.createWorkflow(name, description, steps);
      setShowCreate(false);
      setName('');
      setDescription('');
      await loadData();
    } catch (e: any) {
      alert('Error: ' + (e.message || 'Invalid steps JSON'));
    }
    setCreating(false);
  };

  const handleExecute = async (workflowId: string) => {
    setExecuting(workflowId);
    try {
      await superadminApi.executeWorkflow(workflowId);
      await loadData();
    } catch { /* silent */ }
    setExecuting(null);
  };

  const statusIcon = (s: string) => {
    if (s === 'completed') return <CheckCircle className="w-3.5 h-3.5 text-green-400" />;
    if (s === 'failed') return <XCircle className="w-3.5 h-3.5 text-red-400" />;
    if (s === 'running') return <Clock className="w-3.5 h-3.5 text-amber-400 animate-pulse" />;
    return <Clock className="w-3.5 h-3.5 text-white/30" />;
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-violet-500/20 flex items-center justify-center">
            <GitBranch className="w-5 h-5 text-violet-400" />
          </div>
          <div>
            <h1 className="text-xl font-bold">{t('workflows.title')}</h1>
            <p className="text-xs text-white/40">{t('workflows.subtitle')}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => setShowCreate(!showCreate)}
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-violet-500/20 text-xs text-violet-300 hover:bg-violet-500/30 transition">
            <Plus className="w-3.5 h-3.5" /> New Workflow
          </button>
          <button onClick={loadData} disabled={loading}
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg glass text-xs text-white/60 hover:text-white transition">
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} /> {t('common.refresh')}
          </button>
        </div>
      </div>

      {/* Create Form */}
      {showCreate && (
        <div className="glass rounded-xl p-5 border border-violet-500/20 space-y-4">
          <h3 className="text-sm font-medium text-violet-300">Create Workflow</h3>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-xs text-white/40 block mb-1">Name</label>
              <input value={name} onChange={e => setName(e.target.value)}
                className="w-full glass rounded-lg px-3 py-2 text-sm bg-white/5 border border-white/10 focus:border-violet-500/50 focus:outline-none" />
            </div>
            <div>
              <label className="text-xs text-white/40 block mb-1">Description</label>
              <input value={description} onChange={e => setDescription(e.target.value)}
                className="w-full glass rounded-lg px-3 py-2 text-sm bg-white/5 border border-white/10 focus:border-violet-500/50 focus:outline-none" />
            </div>
          </div>
          <div>
            <label className="text-xs text-white/40 block mb-1">Steps (JSON Array)</label>
            <textarea value={stepsJson} onChange={e => setStepsJson(e.target.value)} rows={6}
              className="w-full glass rounded-lg px-3 py-2 text-xs font-mono bg-white/5 border border-white/10 focus:border-violet-500/50 focus:outline-none" />
          </div>
          <button onClick={handleCreate} disabled={creating || !name.trim()}
            className="px-4 py-2 rounded-lg bg-violet-500/20 text-violet-300 text-xs font-medium hover:bg-violet-500/30 transition disabled:opacity-50">
            {creating ? 'Creating...' : 'Create Workflow'}
          </button>
        </div>
      )}

      {/* Workflow List */}
      {workflows.length === 0 ? (
        <div className="glass rounded-xl p-8 border border-white/5 text-center">
          <p className="text-sm text-white/30">{t('common.noData')}</p>
        </div>
      ) : (
        <div className="space-y-3">
          {workflows.map((wf: any) => (
            <div key={wf.workflow_id} className="glass rounded-xl border border-white/5 overflow-hidden">
              <div className="p-4 flex items-center justify-between cursor-pointer hover:bg-white/5 transition"
                onClick={() => setExpanded(expanded === wf.workflow_id ? null : wf.workflow_id)}>
                <div className="flex items-center gap-3">
                  {statusIcon(wf.status)}
                  <div>
                    <div className="text-sm font-medium">{wf.name}</div>
                    <div className="text-[10px] text-white/30">{wf.description} | {wf.steps?.length || 0} steps</div>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <span className={`text-[10px] px-2 py-0.5 rounded-full ${
                    wf.status === 'completed' ? 'bg-green-500/10 text-green-400' :
                    wf.status === 'failed' ? 'bg-red-500/10 text-red-400' :
                    wf.status === 'running' ? 'bg-amber-500/10 text-amber-400' :
                    'bg-white/5 text-white/40'
                  }`}>{wf.status}</span>
                  <button onClick={(e) => { e.stopPropagation(); handleExecute(wf.workflow_id); }}
                    disabled={executing === wf.workflow_id || wf.status === 'running'}
                    className="p-1.5 rounded-lg bg-violet-500/10 text-violet-400 hover:bg-violet-500/20 transition disabled:opacity-30">
                    <Play className="w-3.5 h-3.5" />
                  </button>
                  {expanded === wf.workflow_id ? <ChevronUp className="w-4 h-4 text-white/30" /> : <ChevronDown className="w-4 h-4 text-white/30" />}
                </div>
              </div>

              {expanded === wf.workflow_id && wf.steps && (
                <div className="border-t border-white/5 p-4 space-y-2">
                  {wf.steps.map((step: any, i: number) => (
                    <div key={i} className="flex items-center gap-3 p-3 rounded-lg bg-white/5">
                      {statusIcon(step.status)}
                      <div className="flex-1 min-w-0">
                        <div className="text-xs font-medium">{step.name}</div>
                        <div className="text-[10px] text-white/30 truncate">{step.prompt}</div>
                      </div>
                      <span className="text-[10px] text-white/30">{step.agent_id}</span>
                      {step.depends_on?.length > 0 && (
                        <span className="text-[10px] text-white/20">deps: {step.depends_on.join(', ')}</span>
                      )}
                      <span className={`text-[10px] px-1.5 py-0.5 rounded ${CONDITION_COLORS[step.condition] || 'text-white/30'}`}>
                        {step.condition}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
