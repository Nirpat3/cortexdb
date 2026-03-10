'use client';

import { Code2, ChevronRight, Copy, Check, Search } from 'lucide-react';
import { AppShell } from '@/components/shell/AppShell';
import { GlassCard } from '@/components/shared/GlassCard';
import { useState } from 'react';

interface Endpoint {
  method: 'GET' | 'POST' | 'PUT' | 'DELETE';
  path: string;
  description: string;
  body?: string;
  response?: string;
}

interface EndpointGroup {
  name: string;
  color: string;
  endpoints: Endpoint[];
}

const API_GROUPS: EndpointGroup[] = [
  {
    name: 'Health',
    color: '#34D399',
    endpoints: [
      { method: 'GET', path: '/health/live', description: 'Liveness probe', response: '{"status": "alive", "timestamp": 1709712000.0}' },
      { method: 'GET', path: '/health/ready', description: 'Readiness probe with engine status', response: '{"status": "healthy", "engines": {"relational": "ok", ...}}' },
      { method: 'GET', path: '/health/deep', description: 'Deep health check with all subsystems' },
    ],
  },
  {
    name: 'Query & Write',
    color: '#6366F1',
    endpoints: [
      { method: 'POST', path: '/v1/query', description: 'Execute CortexQL query', body: '{"cortexql": "SELECT * FROM blocks LIMIT 5"}', response: '{"data": [...], "row_count": 5, "execution_time_ms": 4.2, "engine_used": "relational", "cached": true}' },
      { method: 'POST', path: '/v1/write', description: 'Write with fan-out to all engines', body: '{"data_type": "block", "payload": {...}, "actor": "dev"}' },
    ],
  },
  {
    name: 'CortexGraph',
    color: '#8B5CF6',
    endpoints: [
      { method: 'POST', path: '/v1/cortexgraph/identify', description: 'Identity resolution across 9 identifier types' },
      { method: 'POST', path: '/v1/cortexgraph/track', description: 'Track customer event' },
      { method: 'GET', path: '/v1/cortexgraph/customer/{id}/360', description: 'Complete customer 360 view' },
      { method: 'GET', path: '/v1/cortexgraph/customer/{id}/profile', description: 'Behavioral profile (RFM, churn, health)' },
      { method: 'GET', path: '/v1/cortexgraph/similar/{id}', description: 'Lookalike customers' },
      { method: 'GET', path: '/v1/cortexgraph/churn-risk', description: 'High churn risk customer list' },
      { method: 'POST', path: '/v1/cortexgraph/recommend/{id}', description: 'Product recommendations' },
      { method: 'GET', path: '/v1/cortexgraph/attribution/{campaign}', description: 'Campaign attribution analysis' },
    ],
  },
  {
    name: 'Compliance',
    color: '#10B981',
    endpoints: [
      { method: 'GET', path: '/v1/compliance/audit', description: 'Full compliance audit across all frameworks' },
      { method: 'GET', path: '/v1/compliance/audit/{framework}', description: 'Framework-specific audit (fedramp, soc2, hipaa, pci_dss, pa_dss)' },
      { method: 'GET', path: '/v1/compliance/summary', description: 'Compliance summary scores' },
      { method: 'GET', path: '/v1/compliance/audit-log', description: 'Query tamper-evident audit trail' },
      { method: 'GET', path: '/v1/compliance/evidence/{framework}', description: 'Evidence report for auditors' },
      { method: 'POST', path: '/v1/compliance/encryption/rotate-keys', description: 'Rotate per-tenant encryption keys' },
      { method: 'GET', path: '/v1/compliance/encryption/stats', description: 'Encryption status and key stats' },
    ],
  },
  {
    name: 'Scale & Admin',
    color: '#F59E0B',
    endpoints: [
      { method: 'POST', path: '/v1/admin/sharding/initialize', description: 'Initialize Citus sharding' },
      { method: 'POST', path: '/v1/admin/sharding/distribute', description: 'Distribute tables across workers' },
      { method: 'POST', path: '/v1/admin/sharding/add-worker', description: 'Add new worker node' },
      { method: 'POST', path: '/v1/admin/sharding/rebalance', description: 'Rebalance shard distribution' },
      { method: 'GET', path: '/v1/admin/sharding/stats', description: 'Shard distribution statistics' },
      { method: 'GET', path: '/v1/admin/indexes/recommend', description: 'AI-powered index recommendations' },
      { method: 'POST', path: '/v1/admin/indexes/create', description: 'Create recommended indexes' },
      { method: 'GET', path: '/v1/admin/cache/stats', description: 'Read cascade cache statistics' },
    ],
  },
  {
    name: 'Grid & Heartbeat',
    color: '#EC4899',
    endpoints: [
      { method: 'GET', path: '/v1/grid/nodes', description: 'List grid nodes with health' },
      { method: 'GET', path: '/v1/grid/health-scores', description: 'Node health scores' },
      { method: 'GET', path: '/v1/grid/cemetery', description: 'Dead node cemetery' },
      { method: 'GET', path: '/v1/heartbeat/status', description: 'Component health status' },
      { method: 'GET', path: '/v1/heartbeat/circuit-breakers', description: 'Circuit breaker states' },
    ],
  },
  {
    name: 'MCP (AI Tools)',
    color: '#06B6D4',
    endpoints: [
      { method: 'GET', path: '/v1/mcp/tools', description: 'List available MCP tools' },
      { method: 'POST', path: '/v1/mcp/call', description: 'Invoke an MCP tool', body: '{"tool": "query_database", "input": {...}}' },
    ],
  },
  {
    name: 'Benchmark',
    color: '#F97316',
    endpoints: [
      { method: 'POST', path: '/v1/admin/benchmark/run', description: 'Run performance benchmark', body: '{"suite": "full", "concurrency": 10, "iterations": 100}' },
      { method: 'POST', path: '/v1/admin/benchmark/stress', description: 'Run stress test', body: '{"pattern": "mixed", "duration_seconds": 60, "requests_per_second": 100}' },
    ],
  },
];

const METHOD_COLORS: Record<string, string> = {
  GET: '#34D399',
  POST: '#3B82F6',
  PUT: '#F59E0B',
  DELETE: '#EF4444',
};

export default function ApiDocsPage() {
  const [search, setSearch] = useState('');
  const [expandedGroup, setExpandedGroup] = useState<string | null>('Health');
  const [copied, setCopied] = useState<string | null>(null);

  const filteredGroups = search.trim()
    ? API_GROUPS.map((g) => ({
        ...g,
        endpoints: g.endpoints.filter(
          (e) =>
            e.path.toLowerCase().includes(search.toLowerCase()) ||
            e.description.toLowerCase().includes(search.toLowerCase())
        ),
      })).filter((g) => g.endpoints.length > 0)
    : API_GROUPS;

  const totalEndpoints = API_GROUPS.reduce((sum, g) => sum + g.endpoints.length, 0);

  const copyToClipboard = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopied(id);
    setTimeout(() => setCopied(null), 2000);
  };

  return (
    <AppShell title="API Docs" icon={Code2} color="#818CF8">
      <div className="mb-4 flex items-center justify-between flex-wrap gap-3">
        <div>
          <h2 className="text-xl font-semibold mb-1">API Reference</h2>
          <p className="text-sm text-white/40">{totalEndpoints} endpoints &middot; Base URL: <code className="text-xs bg-white/5 px-1.5 py-0.5 rounded">http://localhost:5400</code></p>
        </div>
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-white/30" />
          <input
            type="text"
            placeholder="Search endpoints..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-9 pr-4 py-2 bg-white/5 rounded-lg text-sm text-white outline-none border border-white/5 focus:border-indigo-400/30 w-64"
          />
        </div>
      </div>

      {/* Endpoint Groups */}
      <div className="space-y-3">
        {filteredGroups.map((group) => (
          <GlassCard key={group.name} className="overflow-hidden">
            <button
              onClick={() => setExpandedGroup(expandedGroup === group.name ? null : group.name)}
              className="w-full flex items-center justify-between py-1"
            >
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 rounded-full" style={{ backgroundColor: group.color }} />
                <span className="text-sm font-semibold">{group.name}</span>
                <span className="text-[10px] text-white/30">{group.endpoints.length} endpoints</span>
              </div>
              <ChevronRight className={`w-4 h-4 text-white/30 transition-transform ${expandedGroup === group.name ? 'rotate-90' : ''}`} />
            </button>

            {expandedGroup === group.name && (
              <div className="mt-3 space-y-2">
                {group.endpoints.map((ep, i) => {
                  const curlCmd = `curl ${ep.method === 'GET' ? '' : `-X ${ep.method} `}http://localhost:5400${ep.path}${ep.body ? ` \\\n  -H "Content-Type: application/json" \\\n  -d '${ep.body}'` : ''}`;
                  return (
                    <div key={i} className="bg-black/20 rounded-lg p-3">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="text-[10px] font-bold px-2 py-0.5 rounded" style={{ backgroundColor: `${METHOD_COLORS[ep.method]}20`, color: METHOD_COLORS[ep.method] }}>
                          {ep.method}
                        </span>
                        <code className="text-sm text-white/80 font-mono">{ep.path}</code>
                        <button
                          onClick={(e) => { e.stopPropagation(); copyToClipboard(curlCmd, `${group.name}-${i}`); }}
                          className="ml-auto text-white/20 hover:text-white/60 transition-colors"
                          title="Copy cURL"
                        >
                          {copied === `${group.name}-${i}` ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                        </button>
                      </div>
                      <div className="text-xs text-white/40">{ep.description}</div>
                      {ep.body && (
                        <div className="mt-2">
                          <div className="text-[10px] text-white/20 mb-0.5">Body</div>
                          <pre className="text-[11px] font-mono text-indigo-300/60">{ep.body}</pre>
                        </div>
                      )}
                      {ep.response && (
                        <div className="mt-2">
                          <div className="text-[10px] text-white/20 mb-0.5">Response</div>
                          <pre className="text-[11px] font-mono text-emerald-300/60">{ep.response}</pre>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </GlassCard>
        ))}
      </div>
    </AppShell>
  );
}
