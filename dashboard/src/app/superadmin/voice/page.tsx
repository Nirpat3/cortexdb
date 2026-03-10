'use client';

import { useEffect, useState, useCallback } from 'react';
import { Mic, MicOff, RefreshCw, Volume2, Settings, MessageSquare } from 'lucide-react';
import { superadminApi } from '@/lib/api';
import { useTranslation } from '@/lib/i18n';

type D = Record<string, unknown>;

const COMMAND_CATEGORIES: Record<string, string[]> = {
  Status: ['What is the system status?', 'How many agents are active?', 'Show me error count'],
  Tasks: ['List running tasks', 'Cancel task 1234', 'Assign task to agent X'],
  Agents: ['Restart agent MON-001', 'Scale workers to 5', 'Show agent performance'],
  Queries: ['Run query on users table', 'Show top 10 slow queries', 'Explain query plan'],
  Navigation: ['Go to dashboard', 'Open agent registry', 'Show pipelines'],
};

const MOCK_HISTORY: D[] = [
  { id: 'vh-1', transcript: 'What is the current system status?', intent: 'system_status', confidence: 0.96, response: 'All 24 agents are online. 3 tasks running. No errors in the last hour.', processing_ms: 420 },
  { id: 'vh-2', transcript: 'Show me active pipelines', intent: 'list_pipelines', confidence: 0.91, response: 'Found 2 active pipelines: User Analytics ETL and Agent Log Ingestion.', processing_ms: 380 },
  { id: 'vh-3', transcript: 'How many errors today?', intent: 'error_count', confidence: 0.88, response: 'There have been 3 errors today: 2 task failures and 1 sync error.', processing_ms: 350 },
  { id: 'vh-4', transcript: 'Restart agent MON-003', intent: 'restart_agent', confidence: 0.94, response: 'Agent MON-003 has been restarted successfully. Current status: active.', processing_ms: 890 },
  { id: 'vh-5', transcript: 'Scale workers to five', intent: 'scale_component', confidence: 0.82, response: 'Scaling worker replicas from 3 to 5. ETA: 45 seconds.', processing_ms: 1200 },
];

export default function VoiceInterfacePage() {
  const { t } = useTranslation();
  const [listening, setListening] = useState(false);
  const [transcript, setTranscript] = useState('');
  const [response, setResponse] = useState('Ready for voice commands. Click the microphone to start.');
  const [history, setHistory] = useState<D[]>(MOCK_HISTORY);
  const [showSettings, setShowSettings] = useState(false);
  const [settings, setSettings] = useState({ language: 'en-US', speed: 1.0, wake_word: 'cortex', auto_listen: false });

  const refresh = useCallback(async () => {
    try {
      const data = await superadminApi.voiceGetHistory() as D;
      if ((data as D).history) setHistory((data as D).history as D[]);
    } catch { /* use mock */ }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const stats = {
    sessions: 47,
    commands: history.length,
    avgConfidence: (history.reduce((s, h) => s + ((h.confidence as number) || 0), 0) / (history.length || 1) * 100).toFixed(1) + '%',
    topIntent: 'system_status',
  };

  const toggleListening = () => {
    if (listening) {
      setListening(false);
      if (transcript) {
        const mockResponse = `Processed: "${transcript}". Action completed successfully.`;
        setResponse(mockResponse);
        setHistory(prev => [{ id: `vh-${Date.now()}`, transcript, intent: 'custom', confidence: 0.85, response: mockResponse, processing_ms: 450 }, ...prev]);
      }
    } else {
      setListening(true);
      setTranscript('');
      setResponse('Listening...');
      setTimeout(() => {
        setTranscript('What is the system status?');
      }, 2000);
    }
  };

  const confidenceBar = (val: number) => {
    const pct = val * 100;
    const color = pct >= 90 ? 'bg-emerald-400' : pct >= 75 ? 'bg-amber-400' : 'bg-red-400';
    return (
      <div className="flex items-center gap-2">
        <div className="w-16 bg-white/10 rounded-full h-1.5"><div className={`h-1.5 rounded-full ${color}`} style={{ width: `${pct}%` }} /></div>
        <span className="text-[10px] text-white/40">{pct.toFixed(0)}%</span>
      </div>
    );
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold mb-1 flex items-center gap-2">
            <Mic className="w-6 h-6 text-rose-400" /> Voice Interface
          </h1>
          <p className="text-sm text-white/40">Natural language voice command interface</p>
        </div>
        <div className="flex gap-2">
          <button onClick={() => setShowSettings(!showSettings)} className="glass px-3 py-2 rounded-lg text-xs text-white/60 hover:text-white/90"><Settings className="w-3.5 h-3.5" /></button>
          <button onClick={refresh} className="glass px-3 py-2 rounded-lg text-xs text-white/60 hover:text-white/90"><RefreshCw className="w-3.5 h-3.5" /></button>
        </div>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
        {[['Sessions', stats.sessions, ''], ['Commands Processed', stats.commands, 'text-blue-400'], ['Avg Confidence', stats.avgConfidence, 'text-emerald-400'], ['Top Intent', stats.topIntent, 'text-purple-400']].map(([l, v, c]) => (
          <div key={l as string} className="glass rounded-xl p-3">
            <div className="text-xs text-white/40">{l as string}</div>
            <div className={`text-2xl font-bold ${c}`}>{String(v)}</div>
          </div>
        ))}
      </div>

      {showSettings && (
        <div className="glass-heavy rounded-xl p-4 mb-6">
          <h3 className="text-sm font-semibold mb-3">Voice Settings</h3>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <div>
              <label className="text-[10px] text-white/40 block mb-1">Language</label>
              <select value={settings.language} onChange={e => setSettings({ ...settings, language: e.target.value })} className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm">
                {['en-US', 'en-GB', 'es-ES', 'fr-FR', 'de-DE', 'ja-JP', 'zh-CN'].map(l => <option key={l} value={l}>{l}</option>)}
              </select>
            </div>
            <div>
              <label className="text-[10px] text-white/40 block mb-1">Voice Speed</label>
              <input type="range" min="0.5" max="2" step="0.1" value={settings.speed} onChange={e => setSettings({ ...settings, speed: +e.target.value })} className="w-full" />
              <span className="text-[10px] text-white/30">{settings.speed}x</span>
            </div>
            <div>
              <label className="text-[10px] text-white/40 block mb-1">Wake Word</label>
              <input value={settings.wake_word} onChange={e => setSettings({ ...settings, wake_word: e.target.value })} className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm" />
            </div>
            <div>
              <label className="text-[10px] text-white/40 block mb-1">Auto-Listen</label>
              <button onClick={() => setSettings({ ...settings, auto_listen: !settings.auto_listen })} className={`glass px-3 py-2 rounded-lg text-xs ${settings.auto_listen ? 'text-emerald-400' : 'text-white/40'}`}>
                {settings.auto_listen ? 'Enabled' : 'Disabled'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Microphone Area */}
      <div className="flex flex-col items-center py-8 mb-6">
        <button onClick={toggleListening} className={`w-24 h-24 rounded-full flex items-center justify-center transition-all ${listening ? 'bg-rose-500/30 ring-4 ring-rose-400/30 animate-pulse' : 'glass hover:bg-white/10'}`}>
          {listening ? <Mic className="w-10 h-10 text-rose-400" /> : <MicOff className="w-10 h-10 text-white/40" />}
        </button>
        <span className="text-xs text-white/40 mt-3">{listening ? 'Listening... Click to stop' : 'Click to start listening'}</span>
      </div>

      {/* Transcript & Response */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-8">
        <div className="glass rounded-xl p-4">
          <div className="flex items-center gap-2 mb-2">
            <MessageSquare className="w-4 h-4 text-cyan-400" />
            <span className="text-xs font-semibold text-white/60">Transcript</span>
          </div>
          <div className={`text-sm min-h-[48px] ${transcript ? 'text-white/90' : 'text-white/30 italic'}`}>
            {transcript || 'No transcript yet...'}
          </div>
        </div>
        <div className="glass rounded-xl p-4">
          <div className="flex items-center gap-2 mb-2">
            <Volume2 className="w-4 h-4 text-emerald-400" />
            <span className="text-xs font-semibold text-white/60">Response</span>
          </div>
          <div className="text-sm text-white/70 min-h-[48px]">{response}</div>
        </div>
      </div>

      {/* Supported Commands */}
      <h2 className="text-lg font-semibold mb-3">Supported Commands</h2>
      <div className="grid grid-cols-1 sm:grid-cols-3 lg:grid-cols-5 gap-3 mb-8">
        {Object.entries(COMMAND_CATEGORIES).map(([cat, cmds]) => (
          <div key={cat} className="glass rounded-xl p-3">
            <h3 className="text-xs font-semibold text-white/60 mb-2">{cat}</h3>
            <ul className="space-y-1">
              {cmds.map((cmd, i) => (
                <li key={i} className="text-[10px] text-white/40 cursor-pointer hover:text-white/70 transition" onClick={() => { setTranscript(cmd); setResponse(`Simulating: "${cmd}"`); }}>
                  &quot;{cmd}&quot;
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>

      {/* Command History */}
      <h2 className="text-lg font-semibold mb-3">Command History</h2>
      <div className="glass rounded-xl overflow-hidden">
        <table className="w-full text-xs">
          <thead><tr className="border-b border-white/5 text-white/40">
            <th className="text-left p-3">Transcript</th><th className="text-left p-3">Intent</th><th className="text-left p-3">Confidence</th><th className="text-left p-3">Response</th><th className="text-left p-3">Time</th>
          </tr></thead>
          <tbody>
            {history.slice(0, 10).map((h) => (
              <tr key={h.id as string} className="border-b border-white/5 last:border-0">
                <td className="p-3 text-white/80 max-w-[200px] truncate">{h.transcript as string}</td>
                <td className="p-3"><span className="px-1.5 py-0.5 rounded bg-white/5 text-white/50 font-mono">{h.intent as string}</span></td>
                <td className="p-3">{confidenceBar(h.confidence as number)}</td>
                <td className="p-3 text-white/50 max-w-[250px] truncate">{h.response as string}</td>
                <td className="p-3 text-white/30">{h.processing_ms as number}ms</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
