'use client';

import { useEffect, useState, useCallback } from 'react';
import { Globe, RefreshCw, Plus, ArrowRight, AlertTriangle, Zap, Check } from 'lucide-react';
import { superadminApi } from '@/lib/api';
import { useTranslation } from '@/lib/i18n';

type D = Record<string, unknown>;

const STATUS_COLORS: Record<string, string> = {
  active: 'bg-emerald-500/20 text-emerald-300', standby: 'bg-amber-500/20 text-amber-300',
  offline: 'bg-red-500/20 text-red-300', healthy: 'bg-emerald-500/20 text-emerald-300',
  degraded: 'bg-amber-500/20 text-amber-300', error: 'bg-red-500/20 text-red-300',
};

const MOCK_REGIONS: D[] = [
  { id: 'reg-1', name: 'us-east-1', display_name: 'US East (Virginia)', endpoint: 'https://us-east-1.cortexdb.io', status: 'active', is_primary: true, latency: 12 },
  { id: 'reg-2', name: 'eu-west-1', display_name: 'EU West (Ireland)', endpoint: 'https://eu-west-1.cortexdb.io', status: 'active', is_primary: false, latency: 85 },
  { id: 'reg-3', name: 'ap-southeast-1', display_name: 'Asia Pacific (Singapore)', endpoint: 'https://ap-se-1.cortexdb.io', status: 'active', is_primary: false, latency: 145 },
  { id: 'reg-4', name: 'us-west-2', display_name: 'US West (Oregon)', endpoint: 'https://us-west-2.cortexdb.io', status: 'standby', is_primary: false, latency: 52 },
];

const MOCK_STREAMS: D[] = [
  { id: 's-1', source: 'us-east-1', target: 'eu-west-1', status: 'healthy', lag_ms: 120, last_synced: '2026-03-08T09:14:50Z', tables: ['agents', 'tasks', 'missions'] },
  { id: 's-2', source: 'us-east-1', target: 'ap-southeast-1', status: 'degraded', lag_ms: 890, last_synced: '2026-03-08T09:13:20Z', tables: ['agents', 'tasks'] },
  { id: 's-3', source: 'us-east-1', target: 'us-west-2', status: 'healthy', lag_ms: 45, last_synced: '2026-03-08T09:14:55Z', tables: ['agents', 'tasks', 'missions', 'pipelines'] },
];

const MOCK_CONFLICTS: D[] = [
  { id: 'c-1', stream: 'us-east-1 -> eu-west-1', table: 'tasks', record_id: 'task-4829', source_value: 'completed', target_value: 'running', detected: '2026-03-08T08:45:00Z' },
  { id: 'c-2', stream: 'us-east-1 -> ap-southeast-1', table: 'agents', record_id: 'AGT-MON-012', source_value: 'active', target_value: 'idle', detected: '2026-03-08T09:10:00Z' },
];

const MOCK_FAILOVER_LOG: D[] = [
  { from: 'us-east-1', to: 'us-west-2', reason: 'Scheduled DR test', status: 'completed', timestamp: '2026-02-15T03:00:00Z' },
  { from: 'eu-west-1', to: 'us-east-1', reason: 'Network degradation', status: 'completed', timestamp: '2026-01-20T14:30:00Z' },
];

export default function MultiRegionPage() {
  const { t } = useTranslation();
  const [regions, setRegions] = useState<D[]>(MOCK_REGIONS);
  const [streams] = useState<D[]>(MOCK_STREAMS);
  const [conflicts, setConflicts] = useState<D[]>(MOCK_CONFLICTS);
  const [failoverLog] = useState<D[]>(MOCK_FAILOVER_LOG);
  const [showAddRegion, setShowAddRegion] = useState(false);
  const [showAddStream, setShowAddStream] = useState(false);
  const [showFailover, setShowFailover] = useState(false);
  const [newRegion, setNewRegion] = useState({ name: '', display_name: '', endpoint: '' });
  const [newStream, setNewStream] = useState({ source: '', target: '', tables: '' });
  const [failover, setFailover] = useState({ from: '', to: '', reason: '' });

  const refresh = useCallback(async () => {
    try {
      const data = await superadminApi.regionList() as D;
      if ((data as D).regions) setRegions((data as D).regions as D[]);
    } catch { /* use mock */ }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const stats = {
    regions: regions.length,
    activeStreams: streams.length,
    avgLag: Math.round(streams.reduce((s, st) => s + ((st.lag_ms as number) || 0), 0) / (streams.length || 1)) + 'ms',
    conflicts: conflicts.length,
  };

  const resolveConflict = (id: string, winner: 'source' | 'target') => {
    setConflicts(prev => prev.filter(c => c.id !== id));
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold mb-1 flex items-center gap-2">
            <Globe className="w-6 h-6 text-teal-400" /> Multi-Region Replication
          </h1>
          <p className="text-sm text-white/40">Cross-region data replication and failover</p>
        </div>
        <button onClick={refresh} className="glass px-3 py-2 rounded-lg text-xs text-white/60 hover:text-white/90"><RefreshCw className="w-3.5 h-3.5" /></button>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
        {[['Regions', stats.regions, ''], ['Active Streams', stats.activeStreams, 'text-blue-400'], ['Avg Lag', stats.avgLag, 'text-amber-400'], ['Unresolved Conflicts', stats.conflicts, 'text-red-400']].map(([l, v, c]) => (
          <div key={l as string} className="glass rounded-xl p-3">
            <div className="text-xs text-white/40">{l as string}</div>
            <div className={`text-2xl font-bold ${c}`}>{String(v)}</div>
          </div>
        ))}
      </div>

      {/* Regions */}
      <div className="flex justify-between items-center mb-3">
        <h2 className="text-lg font-semibold">Regions</h2>
        <button onClick={() => setShowAddRegion(!showAddRegion)} className="glass px-3 py-1.5 rounded-lg text-xs text-teal-400 flex items-center gap-1"><Plus className="w-3 h-3" /> Add Region</button>
      </div>

      {showAddRegion && (
        <div className="glass-heavy rounded-xl p-4 mb-4">
          <div className="flex gap-3">
            <input value={newRegion.name} onChange={e => setNewRegion({ ...newRegion, name: e.target.value })} placeholder="Region name (e.g. us-central-1)" className="flex-1 bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm" />
            <input value={newRegion.display_name} onChange={e => setNewRegion({ ...newRegion, display_name: e.target.value })} placeholder="Display name" className="flex-1 bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm" />
            <input value={newRegion.endpoint} onChange={e => setNewRegion({ ...newRegion, endpoint: e.target.value })} placeholder="Endpoint URL" className="flex-1 bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm" />
            <button onClick={() => { setRegions(prev => [...prev, { id: `reg-${Date.now()}`, ...newRegion, status: 'standby', is_primary: false, latency: 0 }]); setShowAddRegion(false); }} className="glass px-4 py-2 rounded-lg text-xs text-emerald-400">Add</button>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 mb-8">
        {regions.map(r => (
          <div key={r.id as string} className={`glass rounded-xl p-4 ${r.is_primary ? 'ring-1 ring-teal-400/50' : ''}`}>
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm font-semibold">{r.name as string}</span>
              <div className="flex gap-1">
                {r.is_primary ? <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-teal-500/20 text-teal-300">Primary</span> : null}
                <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${STATUS_COLORS[(r.status as string)] ?? ''}`}>{r.status as string}</span>
              </div>
            </div>
            <div className="text-xs text-white/40 mb-1">{r.display_name as string}</div>
            <div className="text-[10px] text-white/30 font-mono mb-3">{r.endpoint as string}</div>
            <div className="flex items-center justify-between">
              <span className="text-xs text-white/50">Latency: <span className={`font-bold ${(r.latency as number) > 100 ? 'text-amber-400' : 'text-emerald-400'}`}>{r.latency as number}ms</span></span>
              {!r.is_primary && <button onClick={() => setRegions(prev => prev.map(reg => ({ ...reg, is_primary: reg.id === r.id })))} className="glass px-2 py-1 rounded text-[10px] text-amber-400">Set Primary</button>}
            </div>
          </div>
        ))}
      </div>

      {/* Replication Streams */}
      <div className="flex justify-between items-center mb-3">
        <h2 className="text-lg font-semibold">Replication Streams</h2>
        <button onClick={() => setShowAddStream(!showAddStream)} className="glass px-3 py-1.5 rounded-lg text-xs text-blue-400 flex items-center gap-1"><Plus className="w-3 h-3" /> Create Stream</button>
      </div>

      {showAddStream && (
        <div className="glass-heavy rounded-xl p-4 mb-4">
          <div className="flex gap-3">
            <select value={newStream.source} onChange={e => setNewStream({ ...newStream, source: e.target.value })} className="bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm">
              <option value="">Source region</option>
              {regions.map(r => <option key={r.id as string} value={r.name as string}>{r.name as string}</option>)}
            </select>
            <select value={newStream.target} onChange={e => setNewStream({ ...newStream, target: e.target.value })} className="bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm">
              <option value="">Target region</option>
              {regions.map(r => <option key={r.id as string} value={r.name as string}>{r.name as string}</option>)}
            </select>
            <input value={newStream.tables} onChange={e => setNewStream({ ...newStream, tables: e.target.value })} placeholder="Tables (comma-separated)" className="flex-1 bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm" />
            <button onClick={() => setShowAddStream(false)} className="glass px-4 py-2 rounded-lg text-xs text-emerald-400">Create</button>
          </div>
        </div>
      )}

      <div className="space-y-2 mb-8">
        {streams.map(s => (
          <div key={s.id as string} className="glass rounded-xl p-4 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <span className="text-sm font-mono text-white/80">{s.source as string}</span>
              <ArrowRight className="w-4 h-4 text-white/30" />
              <span className="text-sm font-mono text-white/80">{s.target as string}</span>
            </div>
            <div className="flex items-center gap-4 text-xs">
              <span className="text-white/40">{((s.tables as string[]) || []).join(', ')}</span>
              <span className={`font-bold ${(s.lag_ms as number) > 500 ? 'text-amber-400' : 'text-emerald-400'}`}>{s.lag_ms as number}ms lag</span>
              <span className={`px-2 py-0.5 rounded-full text-[10px] ${STATUS_COLORS[(s.status as string)] ?? ''}`}>{s.status as string}</span>
              <span className="text-white/30">{new Date(s.last_synced as string).toLocaleTimeString()}</span>
            </div>
          </div>
        ))}
      </div>

      {/* Conflicts */}
      <h2 className="text-lg font-semibold mb-3 flex items-center gap-2"><AlertTriangle className="w-5 h-5 text-amber-400" /> Conflict Resolution</h2>
      {conflicts.length === 0 ? <div className="glass rounded-xl p-6 text-center text-sm text-white/30 mb-8">No unresolved conflicts</div> : (
        <div className="space-y-2 mb-8">
          {conflicts.map(c => (
            <div key={c.id as string} className="glass rounded-xl p-4 flex items-center justify-between">
              <div className="text-xs">
                <div className="text-white/60 mb-1"><span className="font-mono">{c.stream as string}</span> | <span className="font-semibold">{c.table as string}</span>.{c.record_id as string}</div>
                <div className="text-white/30">Source: <span className="text-cyan-400">{c.source_value as string}</span> vs Target: <span className="text-purple-400">{c.target_value as string}</span></div>
              </div>
              <div className="flex gap-2">
                <button onClick={() => resolveConflict(c.id as string, 'source')} className="glass px-3 py-1.5 rounded text-[10px] text-cyan-400 flex items-center gap-1"><Check className="w-3 h-3" /> Source wins</button>
                <button onClick={() => resolveConflict(c.id as string, 'target')} className="glass px-3 py-1.5 rounded text-[10px] text-purple-400 flex items-center gap-1"><Check className="w-3 h-3" /> Target wins</button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Failover */}
      <div className="flex justify-between items-center mb-3">
        <h2 className="text-lg font-semibold flex items-center gap-2"><Zap className="w-5 h-5 text-red-400" /> Failover</h2>
        <button onClick={() => setShowFailover(!showFailover)} className="glass px-3 py-1.5 rounded-lg text-xs text-red-400 flex items-center gap-1"><Zap className="w-3 h-3" /> Trigger Failover</button>
      </div>

      {showFailover && (
        <div className="glass-heavy rounded-xl p-4 mb-4">
          <div className="flex gap-3">
            <select value={failover.from} onChange={e => setFailover({ ...failover, from: e.target.value })} className="bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm">
              <option value="">From region</option>
              {regions.map(r => <option key={r.id as string} value={r.name as string}>{r.name as string}</option>)}
            </select>
            <select value={failover.to} onChange={e => setFailover({ ...failover, to: e.target.value })} className="bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm">
              <option value="">To region</option>
              {regions.map(r => <option key={r.id as string} value={r.name as string}>{r.name as string}</option>)}
            </select>
            <input value={failover.reason} onChange={e => setFailover({ ...failover, reason: e.target.value })} placeholder="Reason" className="flex-1 bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm" />
            <button onClick={() => setShowFailover(false)} className="glass px-4 py-2 rounded-lg text-xs text-red-400">Execute</button>
          </div>
        </div>
      )}

      <div className="glass rounded-xl overflow-hidden">
        <table className="w-full text-xs">
          <thead><tr className="border-b border-white/5 text-white/40">
            <th className="text-left p-3">From</th><th className="text-left p-3">To</th><th className="text-left p-3">Reason</th><th className="text-left p-3">Status</th><th className="text-left p-3">Timestamp</th>
          </tr></thead>
          <tbody>
            {failoverLog.map((f, i) => (
              <tr key={i} className="border-b border-white/5 last:border-0">
                <td className="p-3 font-mono text-white/80">{f.from as string}</td>
                <td className="p-3 font-mono text-white/80">{f.to as string}</td>
                <td className="p-3 text-white/50">{f.reason as string}</td>
                <td className="p-3"><span className="px-2 py-0.5 rounded-full text-[10px] bg-emerald-500/20 text-emerald-300">{f.status as string}</span></td>
                <td className="p-3 text-white/30">{new Date(f.timestamp as string).toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
