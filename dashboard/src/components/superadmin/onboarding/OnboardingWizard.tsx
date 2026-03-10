'use client';

import { useState, useEffect } from 'react';
import {
  Shield, ChevronRight, ChevronLeft, Wifi, Cpu, Bot, Users,
  ClipboardList, Star, BarChart3, Settings, Crosshair, Rocket,
  CheckCircle, XCircle, Loader2, SkipForward,
} from 'lucide-react';
import { superadminApi } from '@/lib/api';
import { useSuperAdminStore } from '@/stores/superadmin-store';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type D = Record<string, any>;

const STEPS = ['Welcome', 'Connection', 'LLM Setup', 'Your Team', 'Quick Tour', 'Ready'];

interface CheckResult {
  label: string;
  status: 'pending' | 'checking' | 'ok' | 'error';
  detail?: string;
}

const DEPT_COLORS: Record<string, string> = {
  EXEC: '#EF4444', ENG: '#3B82F6', QA: '#34D399', OPS: '#F59E0B', SEC: '#EC4899', DOC: '#8B5CF6',
};

const TOUR_ITEMS = [
  { icon: ClipboardList, label: 'Tasks', desc: 'Create and assign work to your AI agents' },
  { icon: Star, label: 'Skills', desc: 'View skill profiles, XP, and auto-enhancement' },
  { icon: Crosshair, label: 'Autonomy', desc: 'Delegation, goals, sprints, self-improvement' },
  { icon: BarChart3, label: 'Metrics', desc: 'Team performance, throughput, and quality' },
  { icon: Settings, label: 'LLM Config', desc: 'Manage AI providers and models' },
];

export default function OnboardingWizard() {
  const { completeOnboarding } = useSuperAdminStore();
  const [step, setStep] = useState(0);

  // Step 2: Connection
  const [checks, setChecks] = useState<CheckResult[]>([
    { label: 'SuperAdmin API Session', status: 'pending' },
    { label: 'Task Executor', status: 'pending' },
    { label: 'System Health', status: 'pending' },
  ]);

  // Step 3: LLM
  const [providers, setProviders] = useState<D>({});
  const [ollamaStatus, setOllamaStatus] = useState<D | null>(null);
  const [ollamaModels, setOllamaModels] = useState<string[]>([]);
  const [llmLoading, setLlmLoading] = useState(false);

  // Step 4: Team
  const [team, setTeam] = useState<D | null>(null);

  useEffect(() => {
    if (step === 1) runConnectionChecks();
    if (step === 2) loadLLMProviders();
    if (step === 3) loadTeam();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step]);

  const runConnectionChecks = async () => {
    const update = (idx: number, patch: Partial<CheckResult>) => {
      setChecks(prev => prev.map((c, i) => i === idx ? { ...c, ...patch } : c));
    };

    update(0, { status: 'checking' });
    try {
      await superadminApi.session();
      update(0, { status: 'ok', detail: 'Session active' });
    } catch { update(0, { status: 'error', detail: 'Session check failed' }); }

    update(1, { status: 'checking' });
    try {
      const s = await superadminApi.executorStatus() as D;
      update(1, { status: s.running ? 'ok' : 'error', detail: s.running ? 'Running' : 'Not running' });
    } catch { update(1, { status: 'error', detail: 'Unreachable' }); }

    update(2, { status: 'checking' });
    try {
      const h = await superadminApi.getUnifiedHealth() as D;
      update(2, { status: 'ok', detail: `${Object.keys(h.components ?? {}).length} components healthy` });
    } catch { update(2, { status: 'error', detail: 'Health check failed' }); }
  };

  const loadLLMProviders = async () => {
    setLlmLoading(true);
    try {
      const p = await superadminApi.getLLMProviders() as D;
      setProviders(p.providers ?? {});
    } catch {}
    try {
      const h = await superadminApi.ollamaHealth() as D;
      setOllamaStatus(h);
      if (h.status === 'ok' || h.connected) {
        const m = await superadminApi.ollamaModels() as D;
        setOllamaModels((m.models ?? []).map((x: D) => x.name ?? x));
      }
    } catch {}
    setLlmLoading(false);
  };

  const loadTeam = async () => {
    try {
      const t = await superadminApi.getTeam() as D;
      setTeam(t);
    } catch {}
  };

  const next = () => setStep(s => Math.min(s + 1, STEPS.length - 1));
  const prev = () => setStep(s => Math.max(s - 1, 0));
  const finish = () => completeOnboarding();

  return (
    <div className="min-h-screen bg-black flex items-center justify-center p-4">
      <div className="w-full max-w-2xl">
        {/* Progress */}
        <div className="flex items-center justify-center gap-2 mb-8">
          {STEPS.map((s, i) => (
            <div key={s} className="flex items-center gap-2">
              <div className={`w-2.5 h-2.5 rounded-full transition-all ${
                i < step ? 'bg-emerald-400' : i === step ? 'bg-white scale-125' : 'bg-white/20'
              }`} />
              {i < STEPS.length - 1 && <div className="w-6 h-px bg-white/10" />}
            </div>
          ))}
        </div>

        {/* Step Content */}
        <div className="bg-white/5 border border-white/10 rounded-2xl p-8 min-h-[400px] flex flex-col">

          {/* Step 1: Welcome */}
          {step === 0 && (
            <div className="flex-1 flex flex-col items-center justify-center text-center">
              <div className="w-16 h-16 rounded-2xl bg-red-500/20 flex items-center justify-center mb-6">
                <Shield className="w-8 h-8 text-red-400" />
              </div>
              <h2 className="text-2xl font-bold mb-2">Welcome to SuperAdmin</h2>
              <p className="text-sm text-white/40 max-w-md mb-8">
                CortexDB Agent Command Center lets you manage an AI workforce of 24 agents across 6 departments.
              </p>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 w-full max-w-md text-left">
                {[
                  'Manage & monitor AI agents',
                  'Assign and track tasks',
                  'Configure LLM providers',
                  'Auto-skill enhancement',
                  'Agent autonomy & delegation',
                  'Real-time observability',
                ].map(item => (
                  <div key={item} className="flex items-center gap-2 text-xs text-white/60">
                    <CheckCircle className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                    {item}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Step 2: Connection */}
          {step === 1 && (
            <div className="flex-1">
              <div className="flex items-center gap-3 mb-6">
                <Wifi className="w-5 h-5 text-blue-400" />
                <h2 className="text-lg font-bold">Backend Connection Check</h2>
              </div>
              <p className="text-sm text-white/40 mb-6">Verifying your CortexDB instance is reachable and ready.</p>
              <div className="space-y-3">
                {checks.map((c, i) => (
                  <div key={i} className="flex items-center justify-between bg-white/5 rounded-xl p-4">
                    <div className="flex items-center gap-3">
                      {c.status === 'checking' && <Loader2 className="w-4 h-4 text-blue-400 animate-spin" />}
                      {c.status === 'ok' && <CheckCircle className="w-4 h-4 text-emerald-400" />}
                      {c.status === 'error' && <XCircle className="w-4 h-4 text-red-400" />}
                      {c.status === 'pending' && <div className="w-4 h-4 rounded-full bg-white/10" />}
                      <span className="text-sm">{c.label}</span>
                    </div>
                    {c.detail && <span className="text-xs text-white/40">{c.detail}</span>}
                  </div>
                ))}
              </div>
              {checks.some(c => c.status === 'error') && (
                <p className="text-xs text-amber-400/70 mt-4">
                  Some checks failed — you can still proceed. Ensure the CortexDB backend is running on port 5400.
                </p>
              )}
            </div>
          )}

          {/* Step 3: LLM Setup */}
          {step === 2 && (
            <div className="flex-1">
              <div className="flex items-center gap-3 mb-6">
                <Cpu className="w-5 h-5 text-cyan-400" />
                <h2 className="text-lg font-bold">LLM Provider Setup</h2>
              </div>
              <p className="text-sm text-white/40 mb-6">At least one provider is needed for agents to function.</p>
              {llmLoading ? (
                <div className="flex items-center justify-center py-12">
                  <Loader2 className="w-6 h-6 text-white/30 animate-spin" />
                </div>
              ) : (
                <div className="space-y-3">
                  <div className="bg-white/5 rounded-xl p-4">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-sm font-medium">Ollama (Local)</span>
                      <span className={`text-[10px] px-2 py-0.5 rounded-full ${
                        ollamaStatus?.status === 'ok' || ollamaStatus?.connected
                          ? 'bg-emerald-500/20 text-emerald-300' : 'bg-red-500/20 text-red-300'
                      }`}>
                        {ollamaStatus?.status === 'ok' || ollamaStatus?.connected ? 'Connected' : 'Not Connected'}
                      </span>
                    </div>
                    {ollamaModels.length > 0 && (
                      <div className="text-xs text-white/40">Models: {ollamaModels.slice(0, 5).join(', ')}</div>
                    )}
                    {!ollamaStatus?.connected && ollamaStatus?.status !== 'ok' && (
                      <div className="text-xs text-white/30 mt-1">Install Ollama at ollama.com and run a model</div>
                    )}
                  </div>
                  {['claude', 'openai'].map(name => {
                    const p = providers[name] ?? {};
                    return (
                      <div key={name} className="bg-white/5 rounded-xl p-4">
                        <div className="flex items-center justify-between mb-2">
                          <span className="text-sm font-medium capitalize">
                            {name === 'claude' ? 'Anthropic Claude' : 'OpenAI'}
                          </span>
                          <span className={`text-[10px] px-2 py-0.5 rounded-full ${
                            p.configured ? 'bg-emerald-500/20 text-emerald-300' : 'bg-white/10 text-white/40'
                          }`}>
                            {p.configured ? 'Configured' : 'Not Set'}
                          </span>
                        </div>
                        <div className="text-xs text-white/30">
                          {p.configured ? `Model: ${p.model}` : 'Configure API key in LLM Config page'}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}

          {/* Step 4: Meet the Team */}
          {step === 3 && (
            <div className="flex-1">
              <div className="flex items-center gap-3 mb-6">
                <Bot className="w-5 h-5 text-emerald-400" />
                <h2 className="text-lg font-bold">Meet Your AI Team</h2>
              </div>
              <p className="text-sm text-white/40 mb-4">
                {(team as D)?.summary?.total_agents ?? 24} agents across 6 departments, ready to work.
              </p>
              <div className="grid grid-cols-3 sm:grid-cols-6 gap-2 mb-4">
                {['EXEC', 'ENG', 'QA', 'OPS', 'SEC', 'DOC'].map(dept => {
                  const deptAgents = ((team as D)?.agents ?? []).filter((a: D) => a.department === dept);
                  return (
                    <div key={dept} className="bg-white/5 rounded-xl p-3 text-center">
                      <div className="w-8 h-8 rounded-lg mx-auto mb-1 flex items-center justify-center"
                        style={{ backgroundColor: `${DEPT_COLORS[dept]}20` }}>
                        <Users className="w-4 h-4" style={{ color: DEPT_COLORS[dept] }} />
                      </div>
                      <div className="text-xs font-medium">{dept}</div>
                      <div className="text-[10px] text-white/30">{deptAgents.length} agents</div>
                    </div>
                  );
                })}
              </div>
              <div className="grid grid-cols-2 gap-2 max-h-[180px] overflow-y-auto">
                {((team as D)?.agents ?? []).slice(0, 12).map((a: D) => (
                  <div key={a.agent_id} className="bg-white/5 rounded-lg p-2 flex items-center gap-2">
                    <div className="w-6 h-6 rounded-md flex items-center justify-center text-[10px] font-bold"
                      style={{ backgroundColor: `${DEPT_COLORS[a.department] ?? '#888'}20`, color: DEPT_COLORS[a.department] }}>
                      {a.department?.charAt(0)}
                    </div>
                    <div className="min-w-0">
                      <div className="text-xs font-medium truncate">{a.name}</div>
                      <div className="text-[10px] text-white/30 truncate">{a.title}</div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Step 5: Quick Tour */}
          {step === 4 && (
            <div className="flex-1">
              <div className="flex items-center gap-3 mb-6">
                <Star className="w-5 h-5 text-amber-400" />
                <h2 className="text-lg font-bold">Key Features</h2>
              </div>
              <p className="text-sm text-white/40 mb-6">Here are the most important pages to get started.</p>
              <div className="space-y-3">
                {TOUR_ITEMS.map(item => (
                  <div key={item.label} className="flex items-center gap-4 bg-white/5 rounded-xl p-4">
                    <div className="w-10 h-10 rounded-xl bg-white/5 flex items-center justify-center shrink-0">
                      <item.icon className="w-5 h-5 text-white/60" />
                    </div>
                    <div>
                      <div className="text-sm font-medium">{item.label}</div>
                      <div className="text-xs text-white/40">{item.desc}</div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Step 6: Ready */}
          {step === 5 && (
            <div className="flex-1 flex flex-col items-center justify-center text-center">
              <div className="w-16 h-16 rounded-2xl bg-emerald-500/20 flex items-center justify-center mb-6">
                <Rocket className="w-8 h-8 text-emerald-400" />
              </div>
              <h2 className="text-2xl font-bold mb-2">You&apos;re All Set!</h2>
              <p className="text-sm text-white/40 max-w-md mb-6">
                Your CortexDB Agent Command Center is ready. Start by creating a task or exploring the agent roster.
              </p>
              <div className="grid grid-cols-3 gap-4 mb-8 text-center">
                <div>
                  <div className="text-2xl font-bold text-emerald-400">
                    {checks.filter(c => c.status === 'ok').length}/{checks.length}
                  </div>
                  <div className="text-[10px] text-white/30">Systems OK</div>
                </div>
                <div>
                  <div className="text-2xl font-bold text-cyan-400">
                    {Object.values(providers).filter((p: D) => p?.configured || p?.connected).length +
                      (ollamaStatus?.connected || ollamaStatus?.status === 'ok' ? 1 : 0)}
                  </div>
                  <div className="text-[10px] text-white/30">LLM Providers</div>
                </div>
                <div>
                  <div className="text-2xl font-bold text-blue-400">
                    {(team as D)?.summary?.total_agents ?? 24}
                  </div>
                  <div className="text-[10px] text-white/30">Agents</div>
                </div>
              </div>
              <button onClick={finish}
                className="px-8 py-3 rounded-xl bg-emerald-500/20 text-emerald-300 hover:bg-emerald-500/30 transition font-medium text-sm">
                Launch Command Center
              </button>
            </div>
          )}
        </div>

        {/* Navigation */}
        <div className="flex items-center justify-between mt-4">
          <button onClick={prev} disabled={step === 0}
            className="flex items-center gap-1 px-4 py-2 rounded-lg text-sm text-white/40 hover:text-white/70 transition disabled:opacity-0">
            <ChevronLeft className="w-4 h-4" /> Back
          </button>

          <button onClick={finish}
            className="flex items-center gap-1 text-xs text-white/20 hover:text-white/40 transition">
            <SkipForward className="w-3 h-3" /> Skip Setup
          </button>

          {step < STEPS.length - 1 ? (
            <button onClick={next}
              className="flex items-center gap-1 px-4 py-2 rounded-lg text-sm bg-white/10 text-white hover:bg-white/20 transition">
              Next <ChevronRight className="w-4 h-4" />
            </button>
          ) : <div className="w-20" />}
        </div>
      </div>
    </div>
  );
}
