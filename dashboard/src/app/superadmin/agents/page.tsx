'use client';

import { useEffect, useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { Bot, ChevronDown, ChevronUp, Settings, ExternalLink, Cpu, Zap, RefreshCw, Check, Users } from 'lucide-react';
import { superadminApi } from '@/lib/api';
import { useTranslation } from '@/lib/i18n';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type D = Record<string, any>;

const DEPT_COLORS: Record<string, string> = {
  EXEC: '#EF4444', ENG: '#3B82F6', QA: '#34D399', OPS: '#F59E0B', SEC: '#EC4899', DOC: '#8B5CF6',
};

const PROVIDER_META: Record<string, { label: string; color: string; icon: string }> = {
  ollama: { label: 'Ollama (Local)', color: '#22c55e', icon: 'OL' },
  claude: { label: 'Claude (Anthropic)', color: '#d97706', icon: 'CL' },
  openai: { label: 'OpenAI (GPT)', color: '#3b82f6', icon: 'AI' },
};

export default function AgentsManagePage() {
  const [agents, setAgents] = useState<D[]>([]);
  const [expanded, setExpanded] = useState<string | null>(null);
  const router = useRouter();
  const [editing, setEditing] = useState<string | null>(null);
  const [editForm, setEditForm] = useState<D>({});
  const [filter, setFilter] = useState('all');
  const { t } = useTranslation();
  const [ollamaModels, setOllamaModels] = useState<string[]>([]);
  const [ollamaStatus, setOllamaStatus] = useState<'connected' | 'disconnected' | 'loading'>('loading');
  const [defaultProvider, setDefaultProvider] = useState('ollama');
  const [defaultModel, setDefaultModel] = useState('llama3.1:8b');
  const [applyingDefault, setApplyingDefault] = useState(false);
  const [showDefaultConfig, setShowDefaultConfig] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const data = await superadminApi.getTeam();
      setAgents((data as D).agents ?? []);
    } catch { /* silent */ }
  }, []);

  const fetchOllamaModels = useCallback(async () => {
    try {
      setOllamaStatus('loading');
      const health = await superadminApi.ollamaHealth() as D;
      if (health.status === 'connected' || health.connected) {
        setOllamaStatus('connected');
        const data = await superadminApi.ollamaModels() as D;
        const models = (data.models as D[] ?? []).map((m: D) => String(m.name || m.model || m));
        if (models.length > 0) setOllamaModels(models);
      } else {
        setOllamaStatus('disconnected');
      }
    } catch {
      setOllamaStatus('disconnected');
    }
  }, []);

  useEffect(() => { refresh(); fetchOllamaModels(); }, [refresh, fetchOllamaModels]);

  const handleSave = async (agentId: string) => {
    try {
      await superadminApi.updateTeamAgent(agentId, editForm);
      setEditing(null);
      refresh();
    } catch { /* silent */ }
  };

  const applyDefaultToAll = async () => {
    setApplyingDefault(true);
    try {
      for (const a of agents) {
        await superadminApi.updateTeamAgent(a.agent_id, { llm_provider: defaultProvider, llm_model: defaultModel });
      }
      await refresh();
    } catch { /* silent */ }
    setApplyingDefault(false);
    setShowDefaultConfig(false);
  };

  const filtered = filter === 'all' ? agents : agents.filter((a: D) => a.department === filter);

  // Model distribution stats
  const modelStats = agents.reduce((acc: Record<string, number>, a: D) => {
    const key = `${a.llm_provider}:${a.llm_model}`;
    acc[key] = (acc[key] || 0) + 1;
    return acc;
  }, {});

  const providerCounts = agents.reduce((acc: Record<string, number>, a: D) => {
    acc[a.llm_provider] = (acc[a.llm_provider] || 0) + 1;
    return acc;
  }, {});

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold mb-1 flex items-center gap-2">
            <Bot className="w-6 h-6 text-blue-400" /> {t('agents.title')}
          </h1>
          <p className="text-sm text-white/40">{t('agents.subtitle')}</p>
        </div>
        <button onClick={() => setShowDefaultConfig(!showDefaultConfig)}
          className="glass px-3 py-2 rounded-lg text-xs text-cyan-400 hover:text-cyan-300 flex items-center gap-1.5">
          <Cpu className="w-3.5 h-3.5" /> Default Model
        </button>
      </div>

      {/* System Default Model Banner */}
      <div className="glass-heavy rounded-xl p-4 mb-6">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className="w-12 h-12 rounded-xl bg-emerald-500/15 flex items-center justify-center">
              <Cpu className="w-6 h-6 text-emerald-400" />
            </div>
            <div>
              <div className="text-xs text-white/40 mb-0.5">System Default Model</div>
              <div className="text-lg font-bold flex items-center gap-2">
                <span className="text-emerald-400">{PROVIDER_META[defaultProvider]?.label ?? defaultProvider}</span>
                <span className="text-white/20">/</span>
                <span className="text-white/80 font-mono text-sm">{defaultModel}</span>
              </div>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-1.5">
              <div className={`w-2 h-2 rounded-full ${ollamaStatus === 'connected' ? 'bg-emerald-400' : ollamaStatus === 'loading' ? 'bg-amber-400 animate-pulse' : 'bg-red-400'}`} />
              <span className="text-[10px] text-white/40">
                Ollama {ollamaStatus === 'connected' ? 'Connected' : ollamaStatus === 'loading' ? 'Checking...' : 'Offline'}
              </span>
            </div>
            {ollamaModels.length > 0 && (
              <span className="text-[10px] text-white/30">{ollamaModels.length} models available</span>
            )}
          </div>
        </div>

        {/* Provider distribution */}
        <div className="flex gap-3 mt-3 pt-3 border-t border-white/5">
          {Object.entries(providerCounts).map(([prov, count]) => {
            const meta = PROVIDER_META[prov];
            return (
              <div key={prov} className="flex items-center gap-2">
                <div className="w-5 h-5 rounded text-[8px] font-bold flex items-center justify-center" style={{ backgroundColor: `${meta?.color ?? '#666'}20`, color: meta?.color ?? '#666' }}>
                  {meta?.icon ?? '?'}
                </div>
                <span className="text-xs text-white/50">{count} agents</span>
              </div>
            );
          })}
          <div className="flex-1" />
          {Object.entries(modelStats).map(([key, count]) => (
            <span key={key} className="text-[10px] px-2 py-0.5 rounded-full bg-white/5 text-white/30 font-mono">{key} ({count})</span>
          ))}
        </div>
      </div>

      {/* Default Model Configuration Panel */}
      {showDefaultConfig && (
        <div className="glass-heavy rounded-xl p-5 mb-6 border border-cyan-500/20">
          <h3 className="text-sm font-semibold mb-3 flex items-center gap-2">
            <Settings className="w-4 h-4 text-cyan-400" /> Configure Default Model
          </h3>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-4">
            <div>
              <label className="text-xs text-white/40 block mb-1.5">LLM Provider</label>
              <div className="space-y-2">
                {Object.entries(PROVIDER_META).map(([key, meta]) => (
                  <button key={key} onClick={() => setDefaultProvider(key)}
                    className={`w-full flex items-center gap-3 p-3 rounded-lg text-left transition ${defaultProvider === key ? 'glass-heavy ring-1 ring-emerald-500/40' : 'glass hover:bg-white/5'}`}>
                    <div className="w-8 h-8 rounded-lg text-xs font-bold flex items-center justify-center" style={{ backgroundColor: `${meta.color}20`, color: meta.color }}>
                      {meta.icon}
                    </div>
                    <div className="flex-1">
                      <div className="text-sm font-medium">{meta.label}</div>
                      <div className="text-[10px] text-white/30">
                        {key === 'ollama' ? 'Self-hosted, private, no API costs' : key === 'claude' ? 'Anthropic API, strong reasoning' : 'OpenAI API, GPT models'}
                      </div>
                    </div>
                    {defaultProvider === key && <Check className="w-4 h-4 text-emerald-400" />}
                  </button>
                ))}
              </div>
            </div>
            <div>
              <label className="text-xs text-white/40 block mb-1.5">Model</label>
              {defaultProvider === 'ollama' && ollamaModels.length > 0 ? (
                <div className="space-y-1.5 max-h-[200px] overflow-y-auto pr-1">
                  {ollamaModels.map(m => (
                    <button key={m} onClick={() => setDefaultModel(m)}
                      className={`w-full flex items-center gap-2 p-2.5 rounded-lg text-left text-xs font-mono transition ${defaultModel === m ? 'glass-heavy ring-1 ring-emerald-500/40 text-emerald-300' : 'glass text-white/60 hover:text-white/90'}`}>
                      <Zap className={`w-3 h-3 ${defaultModel === m ? 'text-emerald-400' : 'text-white/20'}`} />
                      {m}
                      {defaultModel === m && <Check className="w-3 h-3 text-emerald-400 ml-auto" />}
                    </button>
                  ))}
                </div>
              ) : (
                <input value={defaultModel} onChange={e => setDefaultModel(e.target.value)}
                  placeholder={defaultProvider === 'ollama' ? 'llama3.1:8b' : defaultProvider === 'claude' ? 'claude-sonnet-4-20250514' : 'gpt-4o'}
                  className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2.5 text-sm font-mono" />
              )}
              {defaultProvider === 'ollama' && ollamaStatus === 'disconnected' && (
                <div className="mt-2 text-[10px] text-amber-400/70 flex items-center gap-1">
                  <RefreshCw className="w-3 h-3" /> Ollama not detected. Start with: <code className="bg-white/5 px-1 rounded">ollama serve</code>
                </div>
              )}
              {defaultProvider === 'ollama' && ollamaModels.length === 0 && ollamaStatus === 'connected' && (
                <div className="mt-2 text-[10px] text-amber-400/70">
                  No models pulled yet. Run: <code className="bg-white/5 px-1 rounded">ollama pull llama3.1:8b</code>
                </div>
              )}
            </div>
          </div>
          <div className="flex items-center gap-3 pt-3 border-t border-white/5">
            <button onClick={applyDefaultToAll} disabled={applyingDefault}
              className="px-4 py-2 rounded-lg text-xs bg-emerald-500/20 text-emerald-300 hover:bg-emerald-500/30 disabled:opacity-50 flex items-center gap-1.5">
              <Users className="w-3.5 h-3.5" />
              {applyingDefault ? 'Applying...' : `Apply to All ${agents.length} Agents`}
            </button>
            <button onClick={() => setShowDefaultConfig(false)} className="px-4 py-2 rounded-lg text-xs text-white/40 hover:text-white/60">Cancel</button>
            <span className="text-[10px] text-white/20 ml-auto">Sets every agent to {defaultProvider}:{defaultModel}</span>
          </div>
        </div>
      )}

      {/* Department Filter */}
      <div className="flex gap-2 mb-6 flex-wrap">
        {['all', 'EXEC', 'ENG', 'QA', 'OPS', 'SEC', 'DOC'].map((d) => (
          <button key={d} onClick={() => setFilter(d)}
            className={`px-3 py-1.5 rounded-lg text-xs transition ${filter === d ? 'glass-heavy text-white' : 'glass text-white/50 hover:text-white/80'}`}>
            {d === 'all' ? t('common.all') : d} {d !== 'all' && `(${agents.filter((a: D) => a.department === d).length})`}
          </button>
        ))}
      </div>

      {/* Agent List */}
      <div className="space-y-2">
        {filtered.map((a: D) => {
          const color = DEPT_COLORS[a.department] ?? '#6366F1';
          const isExpanded = expanded === a.agent_id;
          const isEditing = editing === a.agent_id;
          const provMeta = PROVIDER_META[a.llm_provider] ?? { label: a.llm_provider, color: '#666', icon: '?' };

          return (
            <div key={a.agent_id} className="glass rounded-xl p-4">
              <div className="flex items-center justify-between cursor-pointer"
                onClick={() => setExpanded(isExpanded ? null : a.agent_id)}>
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-xl flex items-center justify-center" style={{ backgroundColor: `${color}20` }}>
                    <Bot className="w-5 h-5" style={{ color }} />
                  </div>
                  <div>
                    <div className="text-sm font-semibold flex items-center gap-1.5">
                      {a.name} <span className="text-white/30 font-normal">({a.agent_id})</span>
                      <button onClick={(e) => { e.stopPropagation(); router.push(`/superadmin/agents/${a.agent_id}`); }}
                        className="p-0.5 rounded hover:bg-white/10 transition" title={t('agents.viewProfile')}>
                        <ExternalLink className="w-3 h-3 text-white/30 hover:text-white/60" />
                      </button>
                    </div>
                    <div className="text-xs text-white/40">{a.title} · {a.department}</div>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  {/* Model badge */}
                  <div className="flex items-center gap-1.5 glass rounded-lg px-2 py-1">
                    <div className="w-4 h-4 rounded text-[7px] font-bold flex items-center justify-center" style={{ backgroundColor: `${provMeta.color}20`, color: provMeta.color }}>
                      {provMeta.icon}
                    </div>
                    <span className="text-[10px] font-mono text-white/50">{a.llm_model}</span>
                  </div>
                  <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${
                    a.state === 'active' ? 'bg-emerald-500/20 text-emerald-300' :
                    a.state === 'working' ? 'bg-blue-500/20 text-blue-300' : 'bg-white/10 text-white/40'
                  }`}>{a.state}</span>
                  {isExpanded ? <ChevronUp className="w-4 h-4 text-white/30" /> : <ChevronDown className="w-4 h-4 text-white/30" />}
                </div>
              </div>

              {isExpanded && (
                <div className="mt-4 pt-4 border-t border-white/5 space-y-3">
                  {/* Responsibilities */}
                  <div>
                    <div className="text-xs text-white/40 mb-1.5">{t('agents.responsibilities')}</div>
                    <div className="flex flex-wrap gap-1">
                      {(a.responsibilities ?? []).map((r: string, i: number) => (
                        <span key={i} className="text-xs glass px-2 py-0.5 rounded-full text-white/60">{r}</span>
                      ))}
                    </div>
                  </div>

                  {/* Skills */}
                  <div>
                    <div className="text-xs text-white/40 mb-1.5">{t('agents.skills')}</div>
                    <div className="flex flex-wrap gap-1">
                      {(a.skills ?? []).map((s: string, i: number) => (
                        <span key={i} className="text-[10px] px-2 py-0.5 rounded-full" style={{ backgroundColor: `${color}15`, color }}>{s}</span>
                      ))}
                    </div>
                  </div>

                  {/* Stats */}
                  <div className="grid grid-cols-3 gap-3 text-xs">
                    <div className="glass rounded-lg p-2">
                      <div className="text-white/30">{t('agents.completed')}</div>
                      <div className="text-lg font-bold">{a.tasks_completed}</div>
                    </div>
                    <div className="glass rounded-lg p-2">
                      <div className="text-white/30">{t('agents.failed')}</div>
                      <div className="text-lg font-bold text-red-400">{a.tasks_failed}</div>
                    </div>
                    <div className="glass rounded-lg p-2">
                      <div className="text-white/30">{t('agents.reportsTo')}</div>
                      <div className="text-sm font-mono">{a.reports_to ?? t('common.none')}</div>
                    </div>
                  </div>

                  {/* Edit LLM Config */}
                  {isEditing ? (
                    <div className="glass rounded-xl p-3 space-y-2">
                      <div className="text-xs text-white/40 mb-1">{t('agents.configureLlm')}</div>
                      <div className="grid grid-cols-2 gap-2">
                        <select value={editForm.llm_provider ?? a.llm_provider}
                          onChange={(e) => setEditForm({ ...editForm, llm_provider: e.target.value })}
                          className="glass rounded-lg px-3 py-2 text-xs bg-white/5 border border-white/10">
                          {Object.entries(PROVIDER_META).map(([key, meta]) => (
                            <option key={key} value={key}>{meta.label}</option>
                          ))}
                        </select>
                        {(editForm.llm_provider ?? a.llm_provider) === 'ollama' && ollamaModels.length > 0 ? (
                          <select value={editForm.llm_model ?? a.llm_model}
                            onChange={(e) => setEditForm({ ...editForm, llm_model: e.target.value })}
                            className="glass rounded-lg px-3 py-2 text-xs bg-white/5 border border-white/10 font-mono">
                            {ollamaModels.map(m => <option key={m} value={m}>{m}</option>)}
                          </select>
                        ) : (
                          <input value={editForm.llm_model ?? a.llm_model}
                            onChange={(e) => setEditForm({ ...editForm, llm_model: e.target.value })}
                            placeholder={t('agents.modelName')}
                            className="glass rounded-lg px-3 py-2 text-xs bg-white/5 border border-white/10 font-mono" />
                        )}
                      </div>
                      <div className="flex gap-2">
                        <button onClick={() => handleSave(a.agent_id)}
                          className="px-3 py-1.5 rounded-lg text-xs bg-emerald-500/20 text-emerald-300 hover:bg-emerald-500/30">{t('common.save')}</button>
                        <button onClick={() => setEditing(null)}
                          className="px-3 py-1.5 rounded-lg text-xs bg-white/5 text-white/40 hover:bg-white/10">{t('common.cancel')}</button>
                      </div>
                    </div>
                  ) : (
                    <button onClick={() => { setEditing(a.agent_id); setEditForm({ llm_provider: a.llm_provider, llm_model: a.llm_model }); }}
                      className="flex items-center gap-1.5 text-xs text-white/40 hover:text-white/70 transition">
                      <Settings className="w-3 h-3" /> {t('agents.configureLlm')}
                    </button>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
