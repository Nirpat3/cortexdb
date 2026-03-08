'use client';

import { useEffect, useState, useCallback } from 'react';
import { Settings, Cpu, CheckCircle2, XCircle, RefreshCw, Key } from 'lucide-react';
import { superadminApi } from '@/lib/api';
import { useTranslation } from '@/lib/i18n';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type D = Record<string, any>;

export default function LLMConfigPage() {
  const { t } = useTranslation();
  const [providers, setProviders] = useState<D>({});
  const [stats, setStats] = useState<D>({});
  const [ollamaHealth, setOllamaHealth] = useState<D | null>(null);
  const [ollamaModels, setOllamaModels] = useState<string[]>([]);
  const [configForm, setConfigForm] = useState<D>({});
  const [editingProvider, setEditingProvider] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [p, oh, om] = await Promise.all([
        superadminApi.getLLMProviders().catch(() => null),
        superadminApi.ollamaHealth().catch(() => null),
        superadminApi.ollamaModels().catch(() => null),
      ]);
      if (p) {
        setProviders((p as D).providers ?? {});
        setStats((p as D).stats ?? {});
      }
      if (oh) setOllamaHealth(oh);
      if (om) setOllamaModels((om as D).models ?? []);
    } catch { /* silent */ }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const handleConfigure = async (provider: string) => {
    try {
      await superadminApi.configureLLM({ provider, ...configForm });
      setEditingProvider(null);
      setConfigForm({});
      refresh();
    } catch { /* silent */ }
  };

  const providerInfo: Record<string, { name: string; description: string; color: string }> = {
    ollama: { name: 'Ollama', description: 'Local LLM inference. No API key needed. Runs on your machine.', color: '#34D399' },
    claude: { name: 'Claude (Anthropic)', description: 'Cloud API. Requires ANTHROPIC_API_KEY or manual configuration.', color: '#8B5CF6' },
    openai: { name: 'OpenAI (GPT)', description: 'Cloud API. Requires OPENAI_API_KEY or manual configuration.', color: '#3B82F6' },
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold mb-1 flex items-center gap-2">
            <Settings className="w-6 h-6 text-cyan-400" /> {t('llmConfig.title')}
          </h1>
          <p className="text-sm text-white/40">{t('llmConfig.subtitle')}</p>
        </div>
        <button onClick={refresh} className="glass px-3 py-2 rounded-lg text-xs text-white/60 hover:text-white/90">
          <RefreshCw className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* Stats */}
      {stats.total_requests > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-8">
          <div className="glass rounded-xl p-3">
            <div className="text-xs text-white/40">Total Requests</div>
            <div className="text-2xl font-bold">{stats.total_requests}</div>
          </div>
          <div className="glass rounded-xl p-3">
            <div className="text-xs text-white/40">Success Rate</div>
            <div className="text-2xl font-bold text-emerald-400">{stats.success_rate}%</div>
          </div>
          <div className="glass rounded-xl p-3">
            <div className="text-xs text-white/40">Avg Latency</div>
            <div className="text-2xl font-bold">{stats.avg_latency_ms}ms</div>
          </div>
          <div className="glass rounded-xl p-3">
            <div className="text-xs text-white/40">By Provider</div>
            <div className="space-y-0.5 mt-1">
              {Object.entries(stats.by_provider ?? {}).map(([p, c]) => (
                <div key={p} className="flex justify-between text-xs">
                  <span className="text-white/50">{p}</span>
                  <span>{String(c)}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Provider Cards */}
      <div className="space-y-4">
        {Object.entries(providerInfo).map(([key, info]) => {
          const prov = providers[key] ?? {};
          const isEditing = editingProvider === key;

          return (
            <div key={key} className="glass rounded-xl p-5">
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-xl flex items-center justify-center" style={{ backgroundColor: `${info.color}20` }}>
                    <Cpu className="w-5 h-5" style={{ color: info.color }} />
                  </div>
                  <div>
                    <div className="text-base font-semibold">{info.name}</div>
                    <div className="text-xs text-white/40">{info.description}</div>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  {prov.connected === true ? (
                    <span className="flex items-center gap-1 text-xs text-emerald-400"><CheckCircle2 className="w-3.5 h-3.5" /> Connected</span>
                  ) : prov.connected === false ? (
                    <span className="flex items-center gap-1 text-xs text-red-400"><XCircle className="w-3.5 h-3.5" /> Disconnected</span>
                  ) : prov.configured ? (
                    <span className="flex items-center gap-1 text-xs text-amber-400"><Key className="w-3.5 h-3.5" /> Configured</span>
                  ) : (
                    <span className="text-xs text-white/30">Not configured</span>
                  )}
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3 mb-3 text-xs">
                <div className="glass rounded-lg p-2">
                  <div className="text-white/30">Default Model</div>
                  <div className="font-mono">{prov.model ?? '-'}</div>
                </div>
                <div className="glass rounded-lg p-2">
                  <div className="text-white/30">Enabled</div>
                  <div>{prov.enabled ? 'Yes' : 'No'}</div>
                </div>
              </div>

              {/* Ollama-specific: model list */}
              {key === 'ollama' && ollamaModels.length > 0 && (
                <div className="mb-3">
                  <div className="text-xs text-white/40 mb-1.5">Available Models ({ollamaModels.length})</div>
                  <div className="flex flex-wrap gap-1">
                    {ollamaModels.map((m) => (
                      <span key={m} className="text-[10px] px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-300">{m}</span>
                    ))}
                  </div>
                </div>
              )}

              {/* Ollama health */}
              {key === 'ollama' && ollamaHealth && (
                <div className="glass rounded-lg p-2 mb-3 text-xs">
                  <div className="text-white/30">Connection</div>
                  <div className={ollamaHealth.status === 'connected' ? 'text-emerald-400' : 'text-red-400'}>
                    {ollamaHealth.status} — {ollamaHealth.url}
                  </div>
                  {ollamaHealth.error && <div className="text-red-400/60 text-[10px] mt-1">{ollamaHealth.error}</div>}
                </div>
              )}

              {/* Configure */}
              {isEditing ? (
                <div className="space-y-2 pt-3 border-t border-white/5">
                  {key !== 'ollama' && (
                    <div>
                      <label className="text-[10px] text-white/30">API Key</label>
                      <input type="password" value={configForm.api_key ?? ''}
                        onChange={(e) => setConfigForm({ ...configForm, api_key: e.target.value })}
                        placeholder="sk-..."
                        className="w-full glass rounded-lg px-3 py-2 text-xs bg-white/5 border border-white/10 mt-1" />
                    </div>
                  )}
                  <div>
                    <label className="text-[10px] text-white/30">Model</label>
                    <input value={configForm.model ?? prov.model ?? ''}
                      onChange={(e) => setConfigForm({ ...configForm, model: e.target.value })}
                      className="w-full glass rounded-lg px-3 py-2 text-xs bg-white/5 border border-white/10 mt-1" />
                  </div>
                  <div className="flex gap-2">
                    <button onClick={() => handleConfigure(key)}
                      className="px-3 py-1.5 rounded-lg text-xs bg-emerald-500/20 text-emerald-300 hover:bg-emerald-500/30">{t('common.save')}</button>
                    <button onClick={() => { setEditingProvider(null); setConfigForm({}); }}
                      className="px-3 py-1.5 rounded-lg text-xs bg-white/5 text-white/40 hover:bg-white/10">{t('common.cancel')}</button>
                  </div>
                </div>
              ) : (
                <button onClick={() => setEditingProvider(key)}
                  className="text-xs text-white/40 hover:text-white/70 transition flex items-center gap-1.5 pt-2">
                  <Settings className="w-3 h-3" /> Configure
                </button>
              )}
            </div>
          );
        })}
      </div>

      {/* Ollama Setup Guide */}
      <div className="glass rounded-xl p-4 mt-6">
        <h3 className="text-sm font-semibold mb-2">Ollama Setup Guide</h3>
        <div className="space-y-2 text-xs text-white/50">
          <p>1. Install Ollama: <code className="bg-white/5 px-1.5 py-0.5 rounded text-emerald-300">curl -fsSL https://ollama.com/install.sh | sh</code></p>
          <p>2. Pull a model: <code className="bg-white/5 px-1.5 py-0.5 rounded text-emerald-300">ollama pull llama3.1:8b</code></p>
          <p>3. Ollama runs on <code className="bg-white/5 px-1.5 py-0.5 rounded text-white/60">http://localhost:11434</code> by default</p>
          <p>4. Recommended models: <code className="text-white/60">llama3.1:8b</code>, <code className="text-white/60">codellama:13b</code>, <code className="text-white/60">mistral:7b</code>, <code className="text-white/60">qwen2.5-coder:7b</code></p>
        </div>
      </div>
    </div>
  );
}
