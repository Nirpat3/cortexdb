'use client';

import { useEffect, useState, useCallback } from 'react';
import { RadioTower, RefreshCw, Plus, ArrowUpDown, Zap, Trash2, ChevronDown, ChevronRight } from 'lucide-react';
import { superadminApi } from '@/lib/api';
import { useTranslation } from '@/lib/i18n';

type D = Record<string, unknown>;

const STATUS_DOT: Record<string, string> = { online: 'bg-emerald-400', syncing: 'bg-amber-400 animate-pulse', offline: 'bg-red-400' };
const REGION_COLORS: Record<string, string> = {
  'us-east': 'bg-blue-500/20 text-blue-300', 'us-west': 'bg-cyan-500/20 text-cyan-300',
  'eu-west': 'bg-purple-500/20 text-purple-300', 'eu-central': 'bg-indigo-500/20 text-indigo-300',
  'ap-southeast': 'bg-amber-500/20 text-amber-300', 'ap-northeast': 'bg-teal-500/20 text-teal-300',
};

const MOCK_NODES: D[] = [
  { id: 'edge-1', name: 'NYC-Primary', location: 'New York, US', region: 'us-east', status: 'online', last_heartbeat: '2026-03-08T09:14:55Z', storage_used: 42, storage_max: 100, sync_status: 'synced', offline_queue: 0, lat: 40, lng: -74 },
  { id: 'edge-2', name: 'LAX-Secondary', location: 'Los Angeles, US', region: 'us-west', status: 'online', last_heartbeat: '2026-03-08T09:14:50Z', storage_used: 28, storage_max: 80, sync_status: 'synced', offline_queue: 0, lat: 34, lng: -118 },
  { id: 'edge-3', name: 'FRA-Edge', location: 'Frankfurt, DE', region: 'eu-central', status: 'syncing', last_heartbeat: '2026-03-08T09:14:30Z', storage_used: 55, storage_max: 60, sync_status: 'syncing', offline_queue: 12, lat: 50, lng: 8 },
  { id: 'edge-4', name: 'LDN-Edge', location: 'London, UK', region: 'eu-west', status: 'online', last_heartbeat: '2026-03-08T09:14:48Z', storage_used: 31, storage_max: 80, sync_status: 'synced', offline_queue: 0, lat: 51, lng: 0 },
  { id: 'edge-5', name: 'SGP-Edge', location: 'Singapore', region: 'ap-southeast', status: 'offline', last_heartbeat: '2026-03-08T07:30:00Z', storage_used: 18, storage_max: 50, sync_status: 'stale', offline_queue: 340, lat: 1, lng: 103 },
  { id: 'edge-6', name: 'TYO-Edge', location: 'Tokyo, JP', region: 'ap-northeast', status: 'online', last_heartbeat: '2026-03-08T09:14:52Z', storage_used: 22, storage_max: 60, sync_status: 'synced', offline_queue: 0, lat: 35, lng: 139 },
];

const MOCK_SYNC_LOG: D[] = [
  { node: 'FRA-Edge', direction: 'pull', records: 1248, duration: '3.2s', status: 'in_progress' },
  { node: 'NYC-Primary', direction: 'push', records: 5620, duration: '1.8s', status: 'success' },
  { node: 'SGP-Edge', direction: 'pull', records: 0, duration: '-', status: 'failed' },
  { node: 'TYO-Edge', direction: 'push', records: 890, duration: '2.1s', status: 'success' },
];

export default function EdgeDeploymentPage() {
  const { t } = useTranslation();
  const [nodes, setNodes] = useState<D[]>(MOCK_NODES);
  const [syncLog] = useState<D[]>(MOCK_SYNC_LOG);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [showRegister, setShowRegister] = useState(false);
  const [newNode, setNewNode] = useState({ name: '', location: '', region: 'us-east' });

  const refresh = useCallback(async () => {
    try {
      const data = await superadminApi.edgeListNodes() as D;
      if ((data as D).nodes) setNodes((data as D).nodes as D[]);
    } catch { /* use mock */ }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const stats = {
    total: nodes.length,
    online: nodes.filter(n => n.status === 'online').length,
    syncing: nodes.filter(n => n.status === 'syncing').length,
    offline: nodes.filter(n => n.status === 'offline').length,
    storage: `${nodes.reduce((s, n) => s + ((n.storage_used as number) || 0), 0)} / ${nodes.reduce((s, n) => s + ((n.storage_max as number) || 0), 0)} GB`,
  };

  const handleRegister = () => {
    if (!newNode.name) return;
    setNodes(prev => [...prev, { id: `edge-${Date.now()}`, ...newNode, status: 'offline', last_heartbeat: null, storage_used: 0, storage_max: 50, sync_status: 'pending', offline_queue: 0 }]);
    setNewNode({ name: '', location: '', region: 'us-east' }); setShowRegister(false);
  };

  const storagePercent = (n: D) => Math.round(((n.storage_used as number) / (n.storage_max as number)) * 100);

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold mb-1 flex items-center gap-2">
            <RadioTower className="w-6 h-6 text-amber-400" /> Edge Deployment
          </h1>
          <p className="text-sm text-white/40">Edge node management and sync monitoring</p>
        </div>
        <div className="flex gap-2">
          <button onClick={() => setShowRegister(!showRegister)} className="glass px-3 py-2 rounded-lg text-xs text-amber-400 flex items-center gap-1"><Plus className="w-3.5 h-3.5" /> Register Node</button>
          <button onClick={refresh} className="glass px-3 py-2 rounded-lg text-xs text-white/60 hover:text-white/90"><RefreshCw className="w-3.5 h-3.5" /></button>
        </div>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 mb-6">
        {[['Total Nodes', stats.total, ''], ['Online', stats.online, 'text-emerald-400'], ['Syncing', stats.syncing, 'text-amber-400'], ['Offline', stats.offline, 'text-red-400'], ['Storage', stats.storage, 'text-cyan-400']].map(([l, v, c]) => (
          <div key={l as string} className="glass rounded-xl p-3">
            <div className="text-xs text-white/40">{l as string}</div>
            <div className={`text-2xl font-bold ${c}`}>{String(v)}</div>
          </div>
        ))}
      </div>

      {/* World map placeholder */}
      <div className="glass rounded-xl p-4 mb-6 relative overflow-hidden" style={{ height: 200 }}>
        <div className="text-xs text-white/30 mb-2">Global Node Distribution</div>
        <div className="absolute inset-0 flex items-center justify-center">
          <div className="w-full h-full relative opacity-20 border border-white/10 rounded-xl">
            <div className="absolute inset-4 border border-white/10 rounded-lg" />
          </div>
        </div>
        {nodes.map(n => (
          <div key={n.id as string} className="absolute" style={{ left: `${((n.lng as number) + 180) / 360 * 90 + 5}%`, top: `${(90 - (n.lat as number)) / 180 * 80 + 10}%` }}>
            <div className={`w-3 h-3 rounded-full ${STATUS_DOT[(n.status as string)] ?? 'bg-gray-400'} ring-2 ring-black/50`} title={n.name as string} />
            <div className="text-[8px] text-white/40 mt-0.5 whitespace-nowrap">{n.name as string}</div>
          </div>
        ))}
      </div>

      {showRegister && (
        <div className="glass-heavy rounded-xl p-4 mb-6">
          <h3 className="text-sm font-semibold mb-3">Register New Node</h3>
          <div className="flex gap-3">
            <input value={newNode.name} onChange={e => setNewNode({ ...newNode, name: e.target.value })} placeholder="Node name" className="flex-1 bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm" />
            <input value={newNode.location} onChange={e => setNewNode({ ...newNode, location: e.target.value })} placeholder="Location" className="flex-1 bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm" />
            <select value={newNode.region} onChange={e => setNewNode({ ...newNode, region: e.target.value })} className="bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm">
              {Object.keys(REGION_COLORS).map(r => <option key={r} value={r}>{r}</option>)}
            </select>
            <button onClick={handleRegister} className="glass px-4 py-2 rounded-lg text-xs text-emerald-400">Register</button>
          </div>
        </div>
      )}

      <div className="space-y-3 mb-8">
        {nodes.map(n => (
          <div key={n.id as string} className="glass rounded-xl">
            <div className="p-4 flex items-center justify-between cursor-pointer" onClick={() => setExpanded(expanded === n.id ? null : n.id as string)}>
              <div className="flex items-center gap-3">
                {expanded === n.id ? <ChevronDown className="w-4 h-4 text-white/40" /> : <ChevronRight className="w-4 h-4 text-white/40" />}
                <div className={`w-2.5 h-2.5 rounded-full ${STATUS_DOT[(n.status as string)] ?? 'bg-gray-400'}`} />
                <div>
                  <div className="text-sm font-semibold">{n.name as string}</div>
                  <div className="text-[10px] text-white/30">{n.location as string}</div>
                </div>
              </div>
              <div className="flex items-center gap-4 text-xs">
                <span className={`px-2 py-0.5 rounded-full text-[10px] ${REGION_COLORS[(n.region as string)] ?? ''}`}>{n.region as string}</span>
                <span className="text-white/40">{n.last_heartbeat ? new Date(n.last_heartbeat as string).toLocaleTimeString() : 'never'}</span>
                <div className="w-24">
                  <div className="flex justify-between text-[10px] text-white/30"><span>{n.storage_used as number}GB</span><span>{n.storage_max as number}GB</span></div>
                  <div className="w-full bg-white/10 rounded-full h-1.5"><div className={`h-1.5 rounded-full ${storagePercent(n) > 80 ? 'bg-red-400' : 'bg-cyan-400'}`} style={{ width: `${storagePercent(n)}%` }} /></div>
                </div>
                <span className="text-white/40">{n.sync_status as string}</span>
              </div>
            </div>
            {expanded === n.id && (
              <div className="border-t border-white/5 p-4">
                <div className="grid grid-cols-4 gap-3 mb-4 text-xs">
                  <div className="glass rounded-lg p-2"><div className="text-white/30">Queue</div><div className="font-bold">{n.offline_queue as number}</div></div>
                  <div className="glass rounded-lg p-2"><div className="text-white/30">Storage</div><div className="font-bold">{storagePercent(n)}%</div></div>
                  <div className="glass rounded-lg p-2"><div className="text-white/30">Status</div><div className="font-bold">{n.sync_status as string}</div></div>
                  <div className="glass rounded-lg p-2"><div className="text-white/30">Region</div><div className="font-bold">{n.region as string}</div></div>
                </div>
                <div className="flex gap-2">
                  <button className="glass px-3 py-1.5 rounded-lg text-xs text-cyan-400 flex items-center gap-1"><ArrowUpDown className="w-3 h-3" /> Force Sync</button>
                  <button className="glass px-3 py-1.5 rounded-lg text-xs text-amber-400 flex items-center gap-1"><Zap className="w-3 h-3" /> Promote Primary</button>
                  <button className="glass px-3 py-1.5 rounded-lg text-xs text-red-400 flex items-center gap-1"><Trash2 className="w-3 h-3" /> Remove</button>
                </div>
              </div>
            )}
          </div>
        ))}
      </div>

      <h2 className="text-lg font-semibold mb-3">Sync Log</h2>
      <div className="glass rounded-xl overflow-hidden">
        <table className="w-full text-xs">
          <thead><tr className="border-b border-white/5 text-white/40">
            <th className="text-left p-3">Node</th><th className="text-left p-3">Direction</th><th className="text-left p-3">Records</th><th className="text-left p-3">Duration</th><th className="text-left p-3">Status</th>
          </tr></thead>
          <tbody>
            {syncLog.map((s, i) => (
              <tr key={i} className="border-b border-white/5 last:border-0">
                <td className="p-3 text-white/80">{s.node as string}</td>
                <td className="p-3 text-white/50">{s.direction as string}</td>
                <td className="p-3 text-white/50">{s.records as number}</td>
                <td className="p-3 text-white/50">{s.duration as string}</td>
                <td className="p-3"><span className={`px-2 py-0.5 rounded-full text-[10px] ${s.status === 'success' ? 'bg-emerald-500/20 text-emerald-300' : s.status === 'failed' ? 'bg-red-500/20 text-red-300' : 'bg-blue-500/20 text-blue-300'}`}>{s.status as string}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
