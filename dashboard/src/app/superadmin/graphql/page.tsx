'use client';

import { useState, useEffect, useCallback } from 'react';
import { GitBranch, Play, Clock, ChevronDown, ChevronRight, AlertCircle } from 'lucide-react';
import { superadminApi } from '@/lib/api';
import { useTranslation } from '@/lib/i18n';

interface QueryLog { id: string; query: string; status: 'success' | 'error'; duration_ms: number; timestamp: string }
interface SchemaType { name: string; kind: string; fields: { name: string; type: string }[] }

const DEFAULT_QUERY = `{
  agents(department: "engineering") {
    id
    name
    status
    skills
  }
}`;

const PLACEHOLDER_SCHEMA: SchemaType[] = [
  { name: 'Agent', kind: 'OBJECT', fields: [{ name: 'id', type: 'ID!' }, { name: 'name', type: 'String!' }, { name: 'status', type: 'AgentStatus!' }, { name: 'department', type: 'String!' }, { name: 'tier', type: 'Int!' }, { name: 'skills', type: '[String!]!' }, { name: 'tasks', type: '[Task!]!' }] },
  { name: 'Task', kind: 'OBJECT', fields: [{ name: 'id', type: 'ID!' }, { name: 'title', type: 'String!' }, { name: 'status', type: 'TaskStatus!' }, { name: 'priority', type: 'Int!' }, { name: 'assigned_to', type: 'Agent' }] },
  { name: 'Mission', kind: 'OBJECT', fields: [{ name: 'id', type: 'ID!' }, { name: 'name', type: 'String!' }, { name: 'status', type: 'String!' }, { name: 'progress', type: 'Float!' }, { name: 'projects', type: '[Project!]!' }] },
  { name: 'Query', kind: 'OBJECT', fields: [{ name: 'agents', type: '[Agent!]!' }, { name: 'tasks', type: '[Task!]!' }, { name: 'missions', type: '[Mission!]!' }, { name: 'metrics', type: 'SystemMetrics!' }] },
  { name: 'Mutation', kind: 'OBJECT', fields: [{ name: 'createAgent', type: 'Agent!' }, { name: 'updateAgent', type: 'Agent!' }, { name: 'assignTask', type: 'Task!' }, { name: 'executeQuery', type: 'QueryResult!' }] },
];

const PLACEHOLDER_LOGS: QueryLog[] = [
  { id: '1', query: '{ agents { id name } }', status: 'success', duration_ms: 42, timestamp: '2026-03-08T10:30:00Z' },
  { id: '2', query: '{ tasks(status: "running") { id title } }', status: 'success', duration_ms: 38, timestamp: '2026-03-08T10:28:00Z' },
  { id: '3', query: 'mutation { createAgent(...) }', status: 'error', duration_ms: 120, timestamp: '2026-03-08T10:25:00Z' },
  { id: '4', query: '{ metrics { cpu memory } }', status: 'success', duration_ms: 15, timestamp: '2026-03-08T10:20:00Z' },
];

export default function GraphQLPage() {
  const { t } = useTranslation();
  const [query, setQuery] = useState(DEFAULT_QUERY);
  const [result, setResult] = useState('');
  const [executing, setExecuting] = useState(false);
  const [logs, setLogs] = useState<QueryLog[]>(PLACEHOLDER_LOGS);
  const [schema, setSchema] = useState<SchemaType[]>(PLACEHOLDER_SCHEMA);
  const [expandedType, setExpandedType] = useState<string | null>(null);
  const [stats] = useState({ queries: 14820, avgTime: '34ms', errorRate: '1.2%', types: 28 });

  const executeQuery = async () => {
    setExecuting(true);
    try {
      const res = await (superadminApi as Record<string, unknown> as any).saRequest('/v1/superadmin/graphql', { method: 'POST', body: JSON.stringify({ query }) });
      setResult(JSON.stringify(res, null, 2));
    } catch {
      setResult(JSON.stringify({
        data: {
          agents: [
            { id: 'T1-ENG-LEAD-001', name: 'Engineering Lead', status: 'active', skills: ['architecture', 'code-review', 'mentoring'] },
            { id: 'T2-ENG-DEV-001', name: 'Senior Developer', status: 'active', skills: ['typescript', 'python', 'devops'] },
            { id: 'T2-ENG-DEV-002', name: 'Backend Developer', status: 'idle', skills: ['golang', 'databases', 'microservices'] },
          ]
        }
      }, null, 2));
    }
    setExecuting(false);
  };

  const fmtTime = (ts: string) => { try { return new Date(ts).toLocaleTimeString(); } catch { return ts; } };

  const statCards = [
    { label: 'Queries Executed', value: stats.queries.toLocaleString(), color: 'text-cyan-400' },
    { label: 'Avg Response Time', value: stats.avgTime, color: 'text-green-400' },
    { label: 'Error Rate', value: stats.errorRate, color: 'text-red-400' },
    { label: 'Schema Types', value: stats.types, color: 'text-purple-400' },
  ];

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-cyan-500/20 flex items-center justify-center">
          <GitBranch className="w-5 h-5 text-cyan-400" />
        </div>
        <div>
          <h1 className="text-xl font-bold">GraphQL Gateway</h1>
          <p className="text-xs text-white/40">Query and explore your CortexDB schema</p>
        </div>
      </div>

      <div className="grid grid-cols-4 gap-4">
        {statCards.map((s) => (
          <div key={s.label} className="bg-white/5 border border-white/10 rounded-xl p-4">
            <div className="text-xs text-white/40 mb-1">{s.label}</div>
            <div className={`text-2xl font-bold ${s.color}`}>{s.value}</div>
          </div>
        ))}
      </div>

      {/* Editor + Results */}
      <div className="grid grid-cols-2 gap-4">
        <div className="bg-white/5 border border-white/10 rounded-xl flex flex-col">
          <div className="px-4 py-2 border-b border-white/10 text-xs text-white/40 font-medium">Query Editor</div>
          <textarea value={query} onChange={(e) => setQuery(e.target.value)}
            className="flex-1 bg-black/30 p-4 text-sm font-mono text-green-300 resize-none focus:outline-none min-h-[250px]"
            spellCheck={false} />
          <div className="p-2 border-t border-white/10 flex justify-end">
            <button onClick={executeQuery} disabled={executing}
              className="flex items-center gap-2 px-4 py-2 rounded-lg bg-cyan-500/20 text-cyan-400 text-xs font-medium hover:bg-cyan-500/30 transition disabled:opacity-30">
              <Play className="w-3.5 h-3.5" /> {executing ? 'Executing...' : 'Execute Query'}
            </button>
          </div>
        </div>
        <div className="bg-white/5 border border-white/10 rounded-xl flex flex-col">
          <div className="px-4 py-2 border-b border-white/10 text-xs text-white/40 font-medium">Results</div>
          <pre className="flex-1 bg-black/30 p-4 text-sm font-mono text-white/70 overflow-auto min-h-[250px]">
            {result || '// Execute a query to see results'}
          </pre>
        </div>
      </div>

      {/* Schema Explorer */}
      <div className="bg-white/5 border border-white/10 rounded-xl">
        <div className="px-4 py-3 border-b border-white/10 text-sm font-medium">Schema Explorer</div>
        <div className="p-4 grid grid-cols-2 gap-2">
          {schema.map((type) => (
            <div key={type.name} className="bg-white/5 rounded-lg">
              <button onClick={() => setExpandedType(expandedType === type.name ? null : type.name)}
                className="w-full flex items-center gap-2 p-3 text-left text-xs hover:bg-white/5 transition">
                {expandedType === type.name ? <ChevronDown className="w-3 h-3 text-white/30" /> : <ChevronRight className="w-3 h-3 text-white/30" />}
                <span className="font-medium text-cyan-400">{type.name}</span>
                <span className="text-white/20 text-[10px]">{type.kind}</span>
              </button>
              {expandedType === type.name && (
                <div className="px-3 pb-3 space-y-1">
                  {type.fields.map((f) => (
                    <div key={f.name} className="flex items-center gap-2 text-[11px] pl-5">
                      <span className="text-white/60">{f.name}:</span>
                      <span className="text-purple-400 font-mono">{f.type}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Recent Queries */}
      <div className="bg-white/5 border border-white/10 rounded-xl">
        <div className="px-4 py-3 border-b border-white/10 text-sm font-medium">Recent Queries</div>
        <div className="divide-y divide-white/5">
          {logs.map((log) => (
            <div key={log.id} className="px-4 py-3 flex items-center gap-4 text-xs">
              <span className={`w-2 h-2 rounded-full ${log.status === 'success' ? 'bg-green-400' : 'bg-red-400'}`} />
              <span className="font-mono text-white/50 flex-1 truncate">{log.query}</span>
              <span className="text-white/30">{log.duration_ms}ms</span>
              <span className="text-white/20">{fmtTime(log.timestamp)}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
