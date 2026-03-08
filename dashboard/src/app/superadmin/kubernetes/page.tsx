'use client';

import { useEffect, useState, useCallback } from 'react';
import { Container, RefreshCw, ChevronDown, ChevronRight, Play, ArrowUpCircle, Database, RotateCcw, FileCode } from 'lucide-react';
import { superadminApi } from '@/lib/api';
import { useTranslation } from '@/lib/i18n';

type D = Record<string, unknown>;

const STATUS_COLORS: Record<string, string> = {
  healthy: 'bg-emerald-500/20 text-emerald-300', degraded: 'bg-amber-500/20 text-amber-300',
  error: 'bg-red-500/20 text-red-300', running: 'bg-blue-500/20 text-blue-300',
  completed: 'bg-emerald-500/20 text-emerald-300', failed: 'bg-red-500/20 text-red-300',
  pending: 'bg-white/10 text-white/50',
};

const MOCK_CLUSTERS: D[] = [
  { id: 'k8s-1', name: 'cortex-prod', namespace: 'cortexdb', status: 'healthy', nodes: 5, pods: 24, components: [
    { name: 'api', replicas: 3, cpu: '120m', memory: '256Mi', status: 'running' },
    { name: 'worker', replicas: 6, cpu: '500m', memory: '512Mi', status: 'running' },
    { name: 'db', replicas: 3, cpu: '250m', memory: '1Gi', status: 'running' },
    { name: 'cache', replicas: 2, cpu: '80m', memory: '128Mi', status: 'running' },
  ], operations: [
    { type: 'scale', component: 'worker', detail: '4 -> 6 replicas', status: 'completed', duration: '45s', timestamp: '2026-03-08T08:00:00Z' },
    { type: 'rolling_upgrade', component: 'api', detail: 'v2.4.1 -> v2.5.0', status: 'completed', duration: '3m 12s', timestamp: '2026-03-07T22:00:00Z' },
  ]},
  { id: 'k8s-2', name: 'cortex-staging', namespace: 'cortexdb-stg', status: 'healthy', nodes: 3, pods: 12, components: [
    { name: 'api', replicas: 2, cpu: '80m', memory: '128Mi', status: 'running' },
    { name: 'worker', replicas: 3, cpu: '250m', memory: '256Mi', status: 'running' },
    { name: 'db', replicas: 1, cpu: '150m', memory: '512Mi', status: 'running' },
  ], operations: [] },
  { id: 'k8s-3', name: 'cortex-dev', namespace: 'cortexdb-dev', status: 'degraded', nodes: 2, pods: 8, components: [
    { name: 'api', replicas: 1, cpu: '50m', memory: '128Mi', status: 'running' },
    { name: 'worker', replicas: 2, cpu: '100m', memory: '128Mi', status: 'degraded' },
    { name: 'db', replicas: 1, cpu: '100m', memory: '256Mi', status: 'running' },
  ], operations: [] },
];

const MOCK_OPS_LOG: D[] = [
  { cluster: 'cortex-prod', operation: 'scale', status: 'completed', duration: '45s', timestamp: '2026-03-08T08:00:00Z' },
  { cluster: 'cortex-prod', operation: 'rolling_upgrade', status: 'completed', duration: '3m 12s', timestamp: '2026-03-07T22:00:00Z' },
  { cluster: 'cortex-staging', operation: 'backup', status: 'completed', duration: '1m 45s', timestamp: '2026-03-07T18:00:00Z' },
  { cluster: 'cortex-dev', operation: 'restart', status: 'failed', duration: '12s', timestamp: '2026-03-08T06:30:00Z' },
];

export default function KubernetesOperatorPage() {
  const { t } = useTranslation();
  const [clusters, setClusters] = useState<D[]>(MOCK_CLUSTERS);
  const [opsLog] = useState<D[]>(MOCK_OPS_LOG);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [showManifest, setShowManifest] = useState(false);
  const [scaleTarget, setScaleTarget] = useState<{ cluster: string; component: string; replicas: number } | null>(null);

  const refresh = useCallback(async () => {
    try {
      const data = await superadminApi.k8sListClusters() as D;
      if ((data as D).clusters) setClusters((data as D).clusters as D[]);
    } catch { /* use mock */ }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const stats = {
    clusters: clusters.length,
    pods: clusters.reduce((s, c) => s + ((c.pods as number) || 0), 0),
    deployments: clusters.reduce((s, c) => s + ((c.components as D[])?.length || 0), 0),
    operations: opsLog.length,
  };

  const manifest = `apiVersion: apps/v1
kind: Deployment
metadata:
  name: cortexdb-api
  namespace: cortexdb
spec:
  replicas: 3
  selector:
    matchLabels:
      app: cortexdb-api
  template:
    metadata:
      labels:
        app: cortexdb-api
    spec:
      containers:
      - name: api
        image: cortexdb/api:v2.5.0
        ports:
        - containerPort: 3001
        resources:
          requests:
            cpu: "120m"
            memory: "256Mi"`;

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold mb-1 flex items-center gap-2">
            <Container className="w-6 h-6 text-blue-400" /> Kubernetes Operator
          </h1>
          <p className="text-sm text-white/40">K8s cluster management and operations</p>
        </div>
        <div className="flex gap-2">
          <button onClick={() => setShowManifest(!showManifest)} className="glass px-3 py-2 rounded-lg text-xs text-blue-400 flex items-center gap-1"><FileCode className="w-3.5 h-3.5" /> Generate Manifests</button>
          <button onClick={refresh} className="glass px-3 py-2 rounded-lg text-xs text-white/60 hover:text-white/90"><RefreshCw className="w-3.5 h-3.5" /></button>
        </div>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
        {[['Clusters', stats.clusters, ''], ['Pods Running', stats.pods, 'text-emerald-400'], ['Deployments', stats.deployments, 'text-blue-400'], ['Operations', stats.operations, 'text-purple-400']].map(([l, v, c]) => (
          <div key={l as string} className="glass rounded-xl p-3">
            <div className="text-xs text-white/40">{l as string}</div>
            <div className={`text-2xl font-bold ${c}`}>{String(v)}</div>
          </div>
        ))}
      </div>

      {showManifest && (
        <div className="glass-heavy rounded-xl p-4 mb-6">
          <h3 className="text-sm font-semibold mb-2">Generated YAML Manifest</h3>
          <pre className="bg-black/50 rounded-lg p-3 text-xs text-emerald-300 font-mono overflow-auto max-h-64">{manifest}</pre>
        </div>
      )}

      <div className="space-y-3 mb-8">
        {clusters.map(c => (
          <div key={c.id as string} className="glass rounded-xl">
            <div className="p-4 flex items-center justify-between cursor-pointer" onClick={() => setExpanded(expanded === c.id ? null : c.id as string)}>
              <div className="flex items-center gap-3">
                {expanded === c.id ? <ChevronDown className="w-4 h-4 text-white/40" /> : <ChevronRight className="w-4 h-4 text-white/40" />}
                <div>
                  <div className="text-sm font-semibold">{c.name as string}</div>
                  <div className="text-[10px] text-white/30 font-mono">{c.namespace as string}</div>
                </div>
              </div>
              <div className="flex items-center gap-4 text-xs">
                <span className={`px-2 py-0.5 rounded-full text-[10px] ${STATUS_COLORS[(c.status as string)] ?? ''}`}>{c.status as string}</span>
                <span className="text-white/40">{c.nodes as number} nodes</span>
                <span className="text-white/40">{c.pods as number} pods</span>
              </div>
            </div>
            {expanded === c.id && (
              <div className="border-t border-white/5 p-4">
                <h4 className="text-xs font-semibold text-white/60 mb-3">Components</h4>
                <div className="glass rounded-lg overflow-hidden mb-4">
                  <table className="w-full text-xs">
                    <thead><tr className="border-b border-white/5 text-white/30">
                      <th className="text-left p-2">Component</th><th className="text-left p-2">Replicas</th><th className="text-left p-2">CPU</th><th className="text-left p-2">Memory</th><th className="text-left p-2">Status</th>
                    </tr></thead>
                    <tbody>
                      {((c.components as D[]) || []).map((comp, i) => (
                        <tr key={i} className="border-b border-white/5 last:border-0">
                          <td className="p-2 font-mono text-white/80">{comp.name as string}</td>
                          <td className="p-2 text-white/60">{comp.replicas as number}</td>
                          <td className="p-2 text-white/60">{comp.cpu as string}</td>
                          <td className="p-2 text-white/60">{comp.memory as string}</td>
                          <td className="p-2"><span className={`px-1.5 py-0.5 rounded-full text-[10px] ${STATUS_COLORS[(comp.status as string)] ?? ''}`}>{comp.status as string}</span></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                {scaleTarget?.cluster === c.id && scaleTarget && (
                  <div className="glass-heavy rounded-lg p-3 mb-3 flex gap-3 items-end">
                    <div><label className="text-[10px] text-white/40 block mb-1">Component</label>
                      <select value={scaleTarget.component} onChange={e => setScaleTarget({ ...scaleTarget, component: e.target.value })} className="bg-white/5 border border-white/10 rounded px-2 py-1 text-xs">
                        {((c.components as D[]) || []).map((comp) => <option key={comp.name as string} value={comp.name as string}>{comp.name as string}</option>)}
                      </select>
                    </div>
                    <div><label className="text-[10px] text-white/40 block mb-1">Replicas</label>
                      <input type="number" value={scaleTarget.replicas} onChange={e => setScaleTarget({ ...scaleTarget, replicas: +e.target.value })} className="w-20 bg-white/5 border border-white/10 rounded px-2 py-1 text-xs" />
                    </div>
                    <button onClick={() => setScaleTarget(null)} className="glass px-3 py-1.5 rounded text-xs text-emerald-400">Apply</button>
                    <button onClick={() => setScaleTarget(null)} className="text-xs text-white/40">Cancel</button>
                  </div>
                )}

                <div className="flex gap-2">
                  <button onClick={() => setScaleTarget({ cluster: c.id as string, component: ((c.components as D[])?.[0]?.name as string) || 'api', replicas: 3 })} className="glass px-3 py-1.5 rounded-lg text-xs text-cyan-400 flex items-center gap-1"><Play className="w-3 h-3" /> Scale</button>
                  <button className="glass px-3 py-1.5 rounded-lg text-xs text-purple-400 flex items-center gap-1"><ArrowUpCircle className="w-3 h-3" /> Rolling Upgrade</button>
                  <button className="glass px-3 py-1.5 rounded-lg text-xs text-amber-400 flex items-center gap-1"><Database className="w-3 h-3" /> Create Backup</button>
                  <button className="glass px-3 py-1.5 rounded-lg text-xs text-red-400 flex items-center gap-1"><RotateCcw className="w-3 h-3" /> Restart</button>
                </div>

                {((c.operations as D[]) || []).length > 0 && (
                  <div className="mt-4">
                    <h4 className="text-xs font-semibold text-white/60 mb-2">Recent Operations</h4>
                    {((c.operations as D[]) || []).map((op, i) => (
                      <div key={i} className="flex items-center gap-3 text-xs py-1 text-white/50">
                        <span className={`px-1.5 py-0.5 rounded text-[10px] ${STATUS_COLORS[(op.status as string)] ?? ''}`}>{op.type as string}</span>
                        <span>{op.component as string}: {op.detail as string}</span>
                        <span className="text-white/30">{op.duration as string}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-8">
        {clusters.map(c => (
          <div key={c.id as string} className="glass rounded-xl p-3">
            <div className="text-xs font-semibold mb-2">{c.name as string} Resources</div>
            {['CPU', 'Memory'].map(r => {
              const pct = r === 'CPU' ? 45 + Math.random() * 30 : 55 + Math.random() * 25;
              return (
                <div key={r} className="mb-2">
                  <div className="flex justify-between text-[10px] text-white/40"><span>{r}</span><span>{Math.round(pct)}%</span></div>
                  <div className="w-full bg-white/10 rounded-full h-2"><div className={`h-2 rounded-full ${pct > 80 ? 'bg-red-400' : pct > 60 ? 'bg-amber-400' : 'bg-emerald-400'}`} style={{ width: `${pct}%` }} /></div>
                </div>
              );
            })}
          </div>
        ))}
      </div>

      <h2 className="text-lg font-semibold mb-3">Operations Log</h2>
      <div className="glass rounded-xl overflow-hidden">
        <table className="w-full text-xs">
          <thead><tr className="border-b border-white/5 text-white/40">
            <th className="text-left p-3">Cluster</th><th className="text-left p-3">Operation</th><th className="text-left p-3">Status</th><th className="text-left p-3">Duration</th><th className="text-left p-3">Timestamp</th>
          </tr></thead>
          <tbody>
            {opsLog.map((op, i) => (
              <tr key={i} className="border-b border-white/5 last:border-0">
                <td className="p-3 text-white/80">{op.cluster as string}</td>
                <td className="p-3 text-white/60">{op.operation as string}</td>
                <td className="p-3"><span className={`px-2 py-0.5 rounded-full text-[10px] ${STATUS_COLORS[(op.status as string)] ?? ''}`}>{op.status as string}</span></td>
                <td className="p-3 text-white/50">{op.duration as string}</td>
                <td className="p-3 text-white/30">{new Date(op.timestamp as string).toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
