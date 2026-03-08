'use client';

import { useState, useEffect } from 'react';
import {
  Users, Plus, Play, Sparkles, MessageSquare, X, RefreshCw, Loader2, CheckCircle2,
} from 'lucide-react';
import { superadminApi } from '@/lib/api';
import { useTranslation } from '@/lib/i18n';

export default function CollabPage() {
  const { t } = useTranslation();
  const [sessions, setSessions] = useState<any[]>([]);
  const [agents, setAgents] = useState<any[]>([]);
  const [selectedSession, setSelectedSession] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [running, setRunning] = useState(false);
  const [synthesizing, setSynthesizing] = useState(false);

  // Create form
  const [goal, setGoal] = useState('');
  const [selectedAgents, setSelectedAgents] = useState<string[]>([]);

  const loadData = async () => {
    setLoading(true);
    try {
      const [sessRes, teamRes] = await Promise.all([
        superadminApi.listCollabSessions(),
        superadminApi.getTeam(),
      ]);
      setSessions((sessRes as any).sessions || []);
      setAgents((teamRes as any).agents || []);
    } catch { /* silent */ }
    setLoading(false);
  };

  useEffect(() => { loadData(); }, []);

  const createSession = async () => {
    if (!goal || selectedAgents.length < 2) return;
    try {
      const result = await superadminApi.createCollabSession(goal, selectedAgents) as any;
      if (result.session_id) {
        setShowCreate(false);
        setGoal('');
        setSelectedAgents([]);
        await loadData();
        setSelectedSession(result);
      }
    } catch { /* silent */ }
  };

  const runRound = async () => {
    if (!selectedSession) return;
    setRunning(true);
    try {
      const result = await superadminApi.runCollabRound(selectedSession.session_id) as any;
      setSelectedSession(result);
      await loadData();
    } catch { /* silent */ }
    setRunning(false);
  };

  const synthesize = async () => {
    if (!selectedSession) return;
    setSynthesizing(true);
    try {
      const result = await superadminApi.synthesizeCollab(selectedSession.session_id) as any;
      setSelectedSession(result);
      await loadData();
    } catch { /* silent */ }
    setSynthesizing(false);
  };

  const closeSession = async () => {
    if (!selectedSession) return;
    await superadminApi.closeCollabSession(selectedSession.session_id);
    setSelectedSession(null);
    await loadData();
  };

  const toggleAgent = (id: string) => {
    setSelectedAgents(prev =>
      prev.includes(id) ? prev.filter(a => a !== id) : [...prev, id]
    );
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-amber-500/20 flex items-center justify-center">
            <Users className="w-5 h-5 text-amber-400" />
          </div>
          <div>
            <h1 className="text-xl font-bold">{t('collab.title')}</h1>
            <p className="text-xs text-white/40">{t('collab.subtitle')}</p>
          </div>
        </div>
        <div className="flex gap-2">
          <button onClick={loadData} className="flex items-center gap-2 px-3 py-1.5 rounded-lg glass text-xs text-white/60 hover:text-white transition">
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} /> {t('common.refresh')}
          </button>
          <button onClick={() => setShowCreate(true)}
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-amber-500/20 text-amber-300 text-xs hover:bg-amber-500/30 transition">
            <Plus className="w-3.5 h-3.5" /> New Session
          </button>
        </div>
      </div>

      {/* Create Modal */}
      {showCreate && (
        <div className="glass rounded-xl p-5 border border-amber-500/20">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-medium">Create Collaboration Session</h3>
            <button onClick={() => setShowCreate(false)} className="text-white/30 hover:text-white/60">
              <X className="w-4 h-4" />
            </button>
          </div>
          <div className="space-y-4">
            <div>
              <label className="text-xs text-white/40 block mb-1.5">Goal</label>
              <input value={goal} onChange={(e) => setGoal(e.target.value)}
                placeholder="What should the agents collaborate on?"
                className="w-full glass rounded-xl px-4 py-2.5 text-sm bg-white/5 border border-white/10 focus:border-amber-500/50 focus:outline-none" />
            </div>
            <div>
              <label className="text-xs text-white/40 block mb-1.5">
                Select Agents ({selectedAgents.length} selected, min 2)
              </label>
              <div className="grid grid-cols-4 gap-2 max-h-48 overflow-y-auto">
                {agents.map((agent: any) => (
                  <button key={agent.agent_id} onClick={() => toggleAgent(agent.agent_id)}
                    className={`text-left px-3 py-2 rounded-lg text-xs transition border ${
                      selectedAgents.includes(agent.agent_id)
                        ? 'border-amber-500/30 bg-amber-500/10 text-amber-300'
                        : 'border-white/5 bg-white/5 text-white/50 hover:border-white/10'
                    }`}>
                    <div className="font-medium truncate">{agent.name}</div>
                    <div className="text-[10px] opacity-60 truncate">{agent.department}</div>
                  </button>
                ))}
              </div>
            </div>
            <button onClick={createSession} disabled={!goal || selectedAgents.length < 2}
              className="px-4 py-2 rounded-lg bg-amber-500/20 text-amber-300 text-xs hover:bg-amber-500/30 transition disabled:opacity-30">
              Create Session
            </button>
          </div>
        </div>
      )}

      <div className="flex gap-4">
        {/* Sessions List */}
        <div className="w-72 shrink-0 space-y-2">
          {sessions.length === 0 && !loading && (
            <div className="glass rounded-xl p-6 border border-white/5 text-center text-white/20 text-xs">
              {t('common.noData')}
            </div>
          )}
          {sessions.map((s: any) => (
            <button key={s.session_id} onClick={() => setSelectedSession(s)}
              className={`w-full text-left glass rounded-lg p-3 border transition ${
                selectedSession?.session_id === s.session_id
                  ? 'border-amber-500/30 bg-amber-500/5'
                  : 'border-white/5 hover:border-white/10'
              }`}>
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs font-medium text-white/70 truncate">{s.goal?.slice(0, 40)}</span>
                <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${
                  s.status === 'active' ? 'bg-green-500/10 text-green-400' :
                  s.status === 'completed' ? 'bg-cyan-500/10 text-cyan-400' :
                  'bg-white/5 text-white/40'
                }`}>{s.status}</span>
              </div>
              <div className="text-[10px] text-white/30">
                {s.agent_ids?.length} agents | {s.turn_count} turns
              </div>
            </button>
          ))}
        </div>

        {/* Session Detail */}
        <div className="flex-1">
          {selectedSession ? (
            <div className="glass rounded-xl border border-white/5 p-5 space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-sm font-medium">{selectedSession.goal}</h3>
                  <div className="text-[10px] text-white/30 mt-0.5">
                    {selectedSession.session_id} | {selectedSession.agent_ids?.length} agents | {selectedSession.turn_count || 0} turns
                  </div>
                </div>
                <div className="flex gap-2">
                  {selectedSession.status === 'active' && (
                    <>
                      <button onClick={runRound} disabled={running}
                        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-green-500/20 text-green-300 text-xs hover:bg-green-500/30 transition disabled:opacity-50">
                        {running ? <Loader2 className="w-3 h-3 animate-spin" /> : <Play className="w-3 h-3" />}
                        Run Round
                      </button>
                      <button onClick={synthesize} disabled={synthesizing || !selectedSession.turns?.length}
                        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-purple-500/20 text-purple-300 text-xs hover:bg-purple-500/30 transition disabled:opacity-50">
                        {synthesizing ? <Loader2 className="w-3 h-3 animate-spin" /> : <Sparkles className="w-3 h-3" />}
                        Synthesize
                      </button>
                      <button onClick={closeSession}
                        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-red-500/10 text-red-400 text-xs hover:bg-red-500/20 transition">
                        <X className="w-3 h-3" /> Close
                      </button>
                    </>
                  )}
                </div>
              </div>

              {/* Agents */}
              <div className="flex gap-2 flex-wrap">
                {selectedSession.agent_ids?.map((aid: string) => {
                  const agent = agents.find((a: any) => a.agent_id === aid);
                  const isCord = aid === selectedSession.coordinator_id;
                  return (
                    <span key={aid} className={`text-[10px] px-2 py-1 rounded-full ${
                      isCord ? 'bg-amber-500/10 text-amber-400 border border-amber-500/20' : 'bg-white/5 text-white/50'
                    }`}>
                      {agent?.name || aid}{isCord ? ' (coordinator)' : ''}
                    </span>
                  );
                })}
              </div>

              {/* Turns */}
              <div className="space-y-3 max-h-[400px] overflow-y-auto">
                {(!selectedSession.turns || selectedSession.turns.length === 0) && (
                  <p className="text-xs text-white/20 text-center py-6">
                    No contributions yet. Click &quot;Run Round&quot; to start collaboration.
                  </p>
                )}
                {selectedSession.turns?.map((turn: any, i: number) => (
                  <div key={i} className="glass rounded-lg p-3 border border-white/5">
                    <div className="flex items-center gap-2 mb-1.5">
                      <span className="text-xs font-medium text-cyan-400">{turn.agent_name}</span>
                      <span className="text-[10px] text-white/20">{turn.agent_id}</span>
                      {!turn.success && <span className="text-[10px] text-red-400">failed</span>}
                    </div>
                    <div className="text-xs text-white/60 whitespace-pre-wrap">{turn.content}</div>
                  </div>
                ))}
              </div>

              {/* Synthesis */}
              {selectedSession.synthesis && (
                <div className="glass rounded-lg p-4 border border-purple-500/20">
                  <div className="flex items-center gap-2 mb-2">
                    <Sparkles className="w-4 h-4 text-purple-400" />
                    <span className="text-xs font-medium text-purple-400">Synthesized Output</span>
                  </div>
                  <div className="text-xs text-white/70 whitespace-pre-wrap">{selectedSession.synthesis}</div>
                </div>
              )}
            </div>
          ) : (
            <div className="glass rounded-xl border border-white/5 p-12 text-center text-white/20">
              <Users className="w-8 h-8 mx-auto mb-3 opacity-30" />
              <p className="text-sm">Select or create a collaboration session</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
