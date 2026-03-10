'use client';

import { useState, useEffect, useCallback } from 'react';
import { Code, Copy, Check, ExternalLink, ChevronDown, ChevronRight, Terminal } from 'lucide-react';
import { superadminApi } from '@/lib/api';
import { useTranslation } from '@/lib/i18n';

interface SDK {
  id: string; name: string; language: string; install: string;
  version: string; status: 'available' | 'coming_soon' | 'beta';
  color: string; icon: string;
  quickstart: string;
}

const SDKS: SDK[] = [
  {
    id: 'python', name: 'Python SDK', language: 'Python', install: 'pip install cortexdb',
    version: '2.4.1', status: 'available', color: 'text-yellow-400', icon: 'Py',
    quickstart: `from cortexdb import CortexClient

client = CortexClient(
    url="http://localhost:9090",
    api_key="your-api-key"
)

# Query agents
agents = client.query("SELECT * FROM agents WHERE department = 'engineering'")
print(f"Found {len(agents)} agents")

# Execute a task
result = client.execute_task(agent_id="T1-OPS-LEAD-001", instruction="Analyze system health")
print(result.status)`,
  },
  {
    id: 'node', name: 'Node.js SDK', language: 'TypeScript', install: 'npm install @cortexdb/client',
    version: '2.3.0', status: 'available', color: 'text-green-400', icon: 'JS',
    quickstart: `import { CortexDB } from '@cortexdb/client';

const db = new CortexDB({
  url: 'http://localhost:9090',
  apiKey: 'your-api-key',
});

// Query with CortexQL
const agents = await db.query('SELECT * FROM agents WHERE tier = 1');
console.log(\`Found \${agents.length} tier-1 agents\`);

// Stream real-time events
db.subscribe('agent.status', (event) => {
  console.log(\`Agent \${event.agentId}: \${event.status}\`);
});`,
  },
  {
    id: 'go', name: 'Go SDK', language: 'Go', install: 'go get github.com/cortexdb/cortexdb-go',
    version: '1.8.0', status: 'available', color: 'text-cyan-400', icon: 'Go',
    quickstart: `package main

import (
    "fmt"
    cortex "github.com/cortexdb/cortexdb-go"
)

func main() {
    client, _ := cortex.NewClient(cortex.Config{
        URL:    "http://localhost:9090",
        APIKey: "your-api-key",
    })

    agents, _ := client.Query("SELECT id, name FROM agents LIMIT 10")
    fmt.Printf("Found %d agents\\n", len(agents))
}`,
  },
  {
    id: 'rust', name: 'Rust SDK', language: 'Rust', install: 'cargo add cortexdb',
    version: '0.9.0', status: 'beta', color: 'text-orange-400', icon: 'Rs',
    quickstart: `use cortexdb::Client;

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let client = Client::builder()
        .url("http://localhost:9090")
        .api_key("your-api-key")
        .build()?;

    let agents = client.query("SELECT * FROM agents").await?;
    println!("Found {} agents", agents.len());
    Ok(())
}`,
  },
  {
    id: 'rest', name: 'REST API', language: 'HTTP', install: 'curl https://api.cortexdb.io/v1/health',
    version: 'v1', status: 'available', color: 'text-blue-400', icon: 'API',
    quickstart: `# Health check
curl http://localhost:9090/v1/health

# Query agents
curl -H "Authorization: Bearer <token>" \\
     http://localhost:9090/v1/query \\
     -d '{"cortexql": "SELECT * FROM agents WHERE department = \\'engineering\\'"}'

# Execute task
curl -X POST -H "Authorization: Bearer <token>" \\
     http://localhost:9090/v1/agents/T1-OPS-LEAD-001/tasks \\
     -d '{"instruction": "Analyze system health"}'`,
  },
  {
    id: 'graphql', name: 'GraphQL', language: 'GraphQL', install: 'Endpoint: /v1/graphql',
    version: 'v1', status: 'available', color: 'text-pink-400', icon: 'GQL',
    quickstart: `# Query agents with GraphQL
query {
  agents(department: "engineering", tier: 1) {
    id
    name
    status
    skills
    tasks(status: "running") {
      id
      title
      progress
    }
  }
}`,
  },
];

const STATUS_COLORS: Record<string, string> = {
  available: 'bg-green-500/20 text-green-400',
  beta: 'bg-amber-500/20 text-amber-400',
  coming_soon: 'bg-white/10 text-white/40',
};

const API_ENDPOINTS = [
  { method: 'GET', path: '/v1/health', description: 'Health check' },
  { method: 'POST', path: '/v1/query', description: 'Execute CortexQL query' },
  { method: 'GET', path: '/v1/agents', description: 'List all agents' },
  { method: 'GET', path: '/v1/agents/:id', description: 'Get agent details' },
  { method: 'POST', path: '/v1/agents/:id/tasks', description: 'Assign task to agent' },
  { method: 'GET', path: '/v1/tasks', description: 'List tasks' },
  { method: 'GET', path: '/v1/missions', description: 'List missions' },
  { method: 'GET', path: '/v1/metrics', description: 'System metrics' },
];

export default function SDKsPage() {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState<string | null>(null);
  const [copied, setCopied] = useState<string | null>(null);

  const handleCopy = (text: string, id: string) => {
    navigator.clipboard.writeText(text).catch(() => {});
    setCopied(id);
    setTimeout(() => setCopied(null), 2000);
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-blue-500/20 flex items-center justify-center">
          <Code className="w-5 h-5 text-blue-400" />
        </div>
        <div>
          <h1 className="text-xl font-bold">SDK &amp; Developer Tools</h1>
          <p className="text-xs text-white/40">Client libraries, APIs, and quick start guides</p>
        </div>
      </div>

      <div className="grid grid-cols-4 gap-4">
        {[
          { label: 'SDKs Available', value: SDKS.filter((s) => s.status === 'available').length, color: 'text-green-400' },
          { label: 'In Beta', value: SDKS.filter((s) => s.status === 'beta').length, color: 'text-amber-400' },
          { label: 'API Version', value: 'v1', color: 'text-blue-400' },
          { label: 'Endpoints', value: API_ENDPOINTS.length, color: 'text-purple-400' },
        ].map((s) => (
          <div key={s.label} className="bg-white/5 border border-white/10 rounded-xl p-4">
            <div className="text-xs text-white/40 mb-1">{s.label}</div>
            <div className={`text-2xl font-bold ${s.color}`}>{s.value}</div>
          </div>
        ))}
      </div>

      {/* SDK Cards */}
      <div className="grid grid-cols-3 gap-4">
        {SDKS.map((sdk) => (
          <div key={sdk.id} className="bg-white/5 border border-white/10 rounded-xl hover:border-white/20 transition">
            <div className="p-4">
              <div className="flex items-start justify-between mb-3">
                <div className="flex items-center gap-3">
                  <div className={`w-10 h-10 rounded-lg bg-white/5 flex items-center justify-center font-bold text-sm ${sdk.color}`}>
                    {sdk.icon}
                  </div>
                  <div>
                    <div className="font-medium text-sm">{sdk.name}</div>
                    <div className="text-[10px] text-white/30">{sdk.language}</div>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-[10px] text-white/30">v{sdk.version}</span>
                  <span className={`px-2 py-0.5 rounded-full text-[10px] ${STATUS_COLORS[sdk.status]}`}>
                    {sdk.status === 'coming_soon' ? 'Coming Soon' : sdk.status === 'beta' ? 'Beta' : 'Available'}
                  </span>
                </div>
              </div>

              {/* Install command */}
              <div className="flex items-center gap-2 bg-black/30 rounded-lg px-3 py-2 mb-3">
                <Terminal className="w-3 h-3 text-white/30 shrink-0" />
                <code className="text-[11px] text-white/60 font-mono flex-1 truncate">{sdk.install}</code>
                <button onClick={() => handleCopy(sdk.install, `install-${sdk.id}`)}
                  className="shrink-0 text-white/30 hover:text-white/60 transition">
                  {copied === `install-${sdk.id}` ? <Check className="w-3 h-3 text-green-400" /> : <Copy className="w-3 h-3" />}
                </button>
              </div>

              <button onClick={() => setExpanded(expanded === sdk.id ? null : sdk.id)}
                className="w-full flex items-center justify-center gap-1 px-3 py-1.5 rounded-lg bg-white/5 text-white/40 text-xs hover:bg-white/10 transition">
                {expanded === sdk.id ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
                {expanded === sdk.id ? 'Hide' : 'Quick Start'}
              </button>
            </div>

            {expanded === sdk.id && (
              <div className="border-t border-white/10 p-4">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-[10px] text-white/30">Quick Start Example</span>
                  <button onClick={() => handleCopy(sdk.quickstart, `code-${sdk.id}`)}
                    className="flex items-center gap-1 text-[10px] text-white/30 hover:text-white/60 transition">
                    {copied === `code-${sdk.id}` ? <Check className="w-3 h-3 text-green-400" /> : <Copy className="w-3 h-3" />} Copy
                  </button>
                </div>
                <pre className="bg-black/30 rounded-lg p-3 text-[11px] text-white/60 font-mono overflow-x-auto whitespace-pre">
                  {sdk.quickstart}
                </pre>
              </div>
            )}
          </div>
        ))}
      </div>

      {/* API Reference */}
      <div className="bg-white/5 border border-white/10 rounded-xl">
        <div className="px-4 py-3 border-b border-white/10 text-sm font-medium">API Reference</div>
        <div className="p-4 space-y-3">
          <div className="grid grid-cols-2 gap-4 text-xs">
            <div>
              <span className="text-white/30">Base URL:</span>
              <code className="ml-2 text-blue-400 font-mono">http://localhost:9090/v1</code>
            </div>
            <div>
              <span className="text-white/30">Authentication:</span>
              <code className="ml-2 text-white/60 font-mono">Authorization: Bearer &lt;token&gt;</code>
            </div>
          </div>
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-white/10 text-white/40">
                <th className="text-left py-2 font-medium w-20">Method</th>
                <th className="text-left py-2 font-medium">Endpoint</th>
                <th className="text-left py-2 font-medium">Description</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {API_ENDPOINTS.map((ep) => (
                <tr key={ep.path} className="hover:bg-white/5 transition">
                  <td className="py-2">
                    <span className={`px-1.5 py-0.5 rounded text-[10px] font-mono font-bold ${ep.method === 'GET' ? 'bg-green-500/20 text-green-400' : 'bg-blue-500/20 text-blue-400'}`}>
                      {ep.method}
                    </span>
                  </td>
                  <td className="py-2 font-mono text-white/60">{ep.path}</td>
                  <td className="py-2 text-white/40">{ep.description}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
