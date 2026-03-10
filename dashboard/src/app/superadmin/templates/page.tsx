'use client';

import { useState, useEffect, useCallback } from 'react';
import { Copy, Plus, RefreshCw, Rocket, Users, Shield, Code, Database, PenTool, Server } from 'lucide-react';
import { superadminApi } from '@/lib/api';
import { useTranslation } from '@/lib/i18n';

const DEPT_ICONS: Record<string, any> = {
  qa: Shield, engineering: Code, documentation: PenTool,
  security: Shield, operations: Server, default: Database,
};

const DEPT_COLORS: Record<string, string> = {
  qa: 'text-amber-400 bg-amber-500/10',
  engineering: 'text-blue-400 bg-blue-500/10',
  documentation: 'text-purple-400 bg-purple-500/10',
  security: 'text-red-400 bg-red-500/10',
  operations: 'text-cyan-400 bg-cyan-500/10',
};

export default function TemplatesPage() {
  const { t } = useTranslation();
  const [templates, setTemplates] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [spawning, setSpawning] = useState<string | null>(null);
  const [spawnResult, setSpawnResult] = useState<any>(null);
  const [showCreate, setShowCreate] = useState(false);

  // Create form
  const [form, setForm] = useState({ name: '', title: '', department: 'engineering', skills: '', system_prompt: '', llm_provider: 'ollama' });

  // Clone form
  const [cloneId, setCloneId] = useState('');
  const [cloneName, setCloneName] = useState('');
  const [cloning, setCloning] = useState(false);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const res = await superadminApi.getTemplates();
      setTemplates((res as any).templates || []);
    } catch { /* silent */ }
    setLoading(false);
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  const handleSpawn = async (templateId: string) => {
    setSpawning(templateId);
    setSpawnResult(null);
    try {
      const res = await superadminApi.spawnFromTemplate(templateId);
      setSpawnResult(res);
    } catch (e: any) {
      setSpawnResult({ error: e.message });
    }
    setSpawning(null);
  };

  const handleCreate = async () => {
    if (!form.name.trim()) return;
    try {
      await superadminApi.createTemplate({
        name: form.name, title: form.title, department: form.department,
        skills: form.skills.split(',').map(s => s.trim()).filter(Boolean),
        system_prompt: form.system_prompt, llm_provider: form.llm_provider,
      });
      setShowCreate(false);
      setForm({ name: '', title: '', department: 'engineering', skills: '', system_prompt: '', llm_provider: 'ollama' });
      await loadData();
    } catch { /* silent */ }
  };

  const handleClone = async () => {
    if (!cloneId.trim()) return;
    setCloning(true);
    try {
      const res = await superadminApi.cloneAgent(cloneId, cloneName || undefined);
      setSpawnResult(res);
      setCloneId('');
      setCloneName('');
    } catch (e: any) {
      setSpawnResult({ error: e.message });
    }
    setCloning(false);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-orange-500/20 flex items-center justify-center">
            <Users className="w-5 h-5 text-orange-400" />
          </div>
          <div>
            <h1 className="text-xl font-bold">{t('templates.title')}</h1>
            <p className="text-xs text-white/40">{t('templates.subtitle')}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => setShowCreate(!showCreate)}
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-orange-500/20 text-xs text-orange-300 hover:bg-orange-500/30 transition">
            <Plus className="w-3.5 h-3.5" /> New Template
          </button>
          <button onClick={loadData} disabled={loading}
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg glass text-xs text-white/60 hover:text-white transition">
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} /> {t('common.refresh')}
          </button>
        </div>
      </div>

      {/* Spawn/Clone Result */}
      {spawnResult && (
        <div className={`p-3 rounded-lg text-xs ${spawnResult.error ? 'bg-red-500/10 text-red-400' : 'bg-green-500/10 text-green-400'}`}>
          {spawnResult.error || `Agent spawned: ${spawnResult.agent_id} — ${spawnResult.name}`}
          <button onClick={() => setSpawnResult(null)} className="ml-2 underline">dismiss</button>
        </div>
      )}

      {/* Create Template Form */}
      {showCreate && (
        <div className="glass rounded-xl p-5 border border-orange-500/20 space-y-4">
          <h3 className="text-sm font-medium text-orange-300">Create Custom Template</h3>
          <div className="grid grid-cols-3 gap-4">
            <div>
              <label className="text-xs text-white/40 block mb-1">Name</label>
              <input value={form.name} onChange={e => setForm({...form, name: e.target.value})}
                className="w-full glass rounded-lg px-3 py-2 text-sm bg-white/5 border border-white/10 focus:border-orange-500/50 focus:outline-none" />
            </div>
            <div>
              <label className="text-xs text-white/40 block mb-1">Title</label>
              <input value={form.title} onChange={e => setForm({...form, title: e.target.value})}
                className="w-full glass rounded-lg px-3 py-2 text-sm bg-white/5 border border-white/10 focus:border-orange-500/50 focus:outline-none" />
            </div>
            <div>
              <label className="text-xs text-white/40 block mb-1">Department</label>
              <select value={form.department} onChange={e => setForm({...form, department: e.target.value})}
                className="w-full glass rounded-lg px-3 py-2 text-sm bg-white/5 border border-white/10 focus:border-orange-500/50 focus:outline-none">
                <option value="engineering">Engineering</option>
                <option value="qa">QA</option>
                <option value="security">Security</option>
                <option value="operations">Operations</option>
                <option value="documentation">Documentation</option>
              </select>
            </div>
          </div>
          <div>
            <label className="text-xs text-white/40 block mb-1">Skills (comma-separated)</label>
            <input value={form.skills} onChange={e => setForm({...form, skills: e.target.value})}
              placeholder="e.g., code-review, testing, analysis"
              className="w-full glass rounded-lg px-3 py-2 text-sm bg-white/5 border border-white/10 focus:border-orange-500/50 focus:outline-none" />
          </div>
          <div>
            <label className="text-xs text-white/40 block mb-1">System Prompt</label>
            <textarea value={form.system_prompt} onChange={e => setForm({...form, system_prompt: e.target.value})} rows={3}
              className="w-full glass rounded-lg px-3 py-2 text-sm bg-white/5 border border-white/10 focus:border-orange-500/50 focus:outline-none" />
          </div>
          <button onClick={handleCreate} disabled={!form.name.trim()}
            className="px-4 py-2 rounded-lg bg-orange-500/20 text-orange-300 text-xs font-medium hover:bg-orange-500/30 transition disabled:opacity-50">
            Create Template
          </button>
        </div>
      )}

      {/* Clone Agent */}
      <div className="glass rounded-xl p-5 border border-white/5">
        <h3 className="text-sm font-medium mb-3 flex items-center gap-2">
          <Copy className="w-4 h-4 text-cyan-400" /> Clone Existing Agent
        </h3>
        <div className="flex gap-3">
          <input value={cloneId} onChange={e => setCloneId(e.target.value)}
            placeholder="Source Agent ID (e.g., CDB-ENG-001)"
            className="flex-1 glass rounded-lg px-3 py-2 text-sm bg-white/5 border border-white/10 focus:border-cyan-500/50 focus:outline-none" />
          <input value={cloneName} onChange={e => setCloneName(e.target.value)}
            placeholder="New name (optional)"
            className="flex-1 glass rounded-lg px-3 py-2 text-sm bg-white/5 border border-white/10 focus:border-cyan-500/50 focus:outline-none" />
          <button onClick={handleClone} disabled={cloning || !cloneId.trim()}
            className="px-4 py-2 rounded-lg bg-cyan-500/20 text-cyan-300 text-xs font-medium hover:bg-cyan-500/30 transition disabled:opacity-50">
            {cloning ? 'Cloning...' : 'Clone'}
          </button>
        </div>
      </div>

      {/* Template Grid */}
      <div className="grid grid-cols-2 gap-4">
        {templates.map((tpl: any) => {
          const Icon = DEPT_ICONS[tpl.department] || DEPT_ICONS.default;
          const color = DEPT_COLORS[tpl.department] || 'text-white/40 bg-white/5';
          return (
            <div key={tpl.template_id} className="glass rounded-xl p-5 border border-white/5">
              <div className="flex items-start justify-between mb-3">
                <div className="flex items-center gap-3">
                  <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${color}`}>
                    <Icon className="w-4 h-4" />
                  </div>
                  <div>
                    <div className="text-sm font-medium">{tpl.name}</div>
                    <div className="text-[10px] text-white/30">{tpl.title}</div>
                  </div>
                </div>
                {tpl.builtin && <span className="text-[10px] px-1.5 py-0.5 rounded bg-white/5 text-white/30">built-in</span>}
              </div>
              <div className="flex flex-wrap gap-1 mb-3">
                {tpl.skills?.map((s: string) => (
                  <span key={s} className="text-[10px] px-1.5 py-0.5 rounded bg-white/5 text-white/40">{s}</span>
                ))}
              </div>
              <p className="text-[11px] text-white/40 mb-3 line-clamp-2">{tpl.system_prompt}</p>
              <button onClick={() => handleSpawn(tpl.template_id)}
                disabled={spawning === tpl.template_id}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-orange-500/10 text-orange-400 text-xs hover:bg-orange-500/20 transition disabled:opacity-50">
                <Rocket className="w-3.5 h-3.5" />
                {spawning === tpl.template_id ? 'Spawning...' : 'Spawn Agent'}
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}
