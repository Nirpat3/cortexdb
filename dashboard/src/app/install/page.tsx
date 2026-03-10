'use client';

import { BookOpen, Terminal, CheckCircle2, Server, Container, Database, Shield, Rocket, Copy, Check } from 'lucide-react';
import { AppShell } from '@/components/shell/AppShell';
import { GlassCard } from '@/components/shared/GlassCard';
import { useState } from 'react';

function CodeBlock({ code, language }: { code: string; language: string }) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };
  return (
    <div className="relative group">
      <pre className="bg-black/40 rounded-xl p-4 text-sm font-mono text-white/70 overflow-x-auto leading-relaxed">
        <code>{code}</code>
      </pre>
      <button onClick={copy} className="absolute top-2 right-2 text-white/20 hover:text-white/60 transition-colors opacity-0 group-hover:opacity-100">
        {copied ? <Check className="w-4 h-4 text-emerald-400" /> : <Copy className="w-4 h-4" />}
      </button>
    </div>
  );
}

const STEPS = [
  {
    icon: Terminal,
    title: '1. Prerequisites',
    description: 'Ensure you have the following installed:',
    content: (
      <div className="space-y-2 text-sm text-white/60">
        <div className="flex items-center gap-2"><CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" /> Docker &amp; Docker Compose (v2.20+)</div>
        <div className="flex items-center gap-2"><CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" /> 4+ GB RAM (8 GB recommended)</div>
        <div className="flex items-center gap-2"><CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" /> 10 GB free disk space</div>
        <div className="flex items-center gap-2"><CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" /> Python 3.12+ (for local development)</div>
      </div>
    ),
  },
  {
    icon: Rocket,
    title: '2. Clone & Setup',
    description: 'Clone the repository and run the setup script:',
    code: `git clone https://github.com/nirlab/cortexdb.git
cd cortexdb
chmod +x setup.sh && ./setup.sh`,
  },
  {
    icon: Container,
    title: '3. Start with Docker',
    description: 'Launch all 12 containers with Docker Compose:',
    code: `docker compose up -d

# View logs
docker compose logs -f cortexdb-server

# Check status
docker compose ps`,
  },
  {
    icon: Server,
    title: '4. Verify Health',
    description: 'Confirm all engines are online:',
    code: `# Liveness check
curl http://localhost:5400/health/live

# Full readiness check
curl http://localhost:5400/health/ready

# Deep health with all subsystems
curl http://localhost:5400/health/deep`,
  },
  {
    icon: Database,
    title: '5. Initialize Sharding (Optional)',
    description: 'Enable Citus distributed sharding for petabyte scale:',
    code: `# Initialize Citus extension
curl -X POST http://localhost:5400/v1/admin/sharding/initialize

# Distribute tables across workers
curl -X POST http://localhost:5400/v1/admin/sharding/distribute`,
  },
  {
    icon: Terminal,
    title: '6. Run Your First Query',
    description: 'Test CortexQL with a simple query:',
    code: `# CortexQL query
curl -X POST http://localhost:5400/v1/query \\
  -H "Content-Type: application/json" \\
  -d '{"cortexql": "SELECT * FROM blocks LIMIT 5"}'

# Write data
curl -X POST http://localhost:5400/v1/write \\
  -H "Content-Type: application/json" \\
  -d '{"data_type": "block", "payload": {"name": "test"}, "actor": "dev"}'

# Vector search
curl -X POST http://localhost:5400/v1/query \\
  -H "Content-Type: application/json" \\
  -d '{"cortexql": "FIND SIMILAR TO \\'hello world\\' IN embeddings LIMIT 5"}'`,
  },
  {
    icon: Shield,
    title: '7. Compliance Verification',
    description: 'Verify all compliance frameworks are passing:',
    code: `# Full audit
curl http://localhost:5400/v1/compliance/audit

# Specific framework
curl http://localhost:5400/v1/compliance/audit/fedramp
curl http://localhost:5400/v1/compliance/audit/hipaa`,
  },
];

export default function InstallPage() {
  return (
    <AppShell title="Installation" icon={BookOpen} color="#4ADE80">
      <div className="mb-6">
        <h2 className="text-xl font-semibold mb-1">Installation Guide</h2>
        <p className="text-sm text-white/40">Get CortexDB v4.0 running in under 5 minutes</p>
      </div>

      {/* Architecture quick view */}
      <GlassCard className="mb-6">
        <h3 className="text-sm font-semibold mb-3">Docker Compose Stack (12 Containers)</h3>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
          {[
            'cortexdb-server (FastAPI)',
            'postgres-primary (PostgreSQL 16)',
            'redis-cache (Redis 7)',
            'qdrant-vector (Qdrant 1.12)',
            'citus-coordinator',
            'citus-worker-1',
            'citus-worker-2',
            'prometheus',
            'grafana',
            'otel-collector',
            'nginx-gateway',
            'cortex-dashboard',
          ].map((c) => (
            <div key={c} className="px-2 py-1.5 rounded-lg bg-white/5 text-white/50">{c}</div>
          ))}
        </div>
      </GlassCard>

      {/* Steps */}
      <div className="space-y-4 max-w-3xl">
        {STEPS.map((step) => {
          const Icon = step.icon;
          return (
            <GlassCard key={step.title}>
              <div className="flex items-start gap-3 mb-3">
                <div className="w-8 h-8 rounded-lg bg-emerald-500/15 flex items-center justify-center shrink-0">
                  <Icon className="w-4 h-4 text-emerald-400" />
                </div>
                <div>
                  <h3 className="text-base font-semibold">{step.title}</h3>
                  <p className="text-xs text-white/40 mt-0.5">{step.description}</p>
                </div>
              </div>
              {step.code && <CodeBlock code={step.code} language="bash" />}
              {step.content}
            </GlassCard>
          );
        })}
      </div>

      {/* Local Development */}
      <GlassCard className="mt-6 max-w-3xl">
        <h3 className="text-base font-semibold mb-3">Local Development (Without Docker)</h3>
        <CodeBlock
          code={`# Create virtual environment
python3.12 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -e ".[dev,ml,observability]"

# Set environment variables
cp .env.example .env
# Edit .env with your PostgreSQL/Redis/Qdrant connection strings

# Run server
cortexdb
# or: uvicorn cortexdb.server:app --host 0.0.0.0 --port 5400 --reload`}
          language="bash"
        />
      </GlassCard>

      {/* Environment Variables */}
      <GlassCard className="mt-4 max-w-3xl">
        <h3 className="text-base font-semibold mb-3">Environment Variables</h3>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-left text-white/40 border-b border-white/5">
                <th className="pb-2 pr-4">Variable</th>
                <th className="pb-2 pr-4">Default</th>
                <th className="pb-2">Description</th>
              </tr>
            </thead>
            <tbody className="text-white/60">
              {[
                ['DATABASE_URL', 'postgresql://cortex:cortex@localhost:5432/cortexdb', 'PostgreSQL connection'],
                ['REDIS_URL', 'redis://localhost:6379', 'Redis connection'],
                ['QDRANT_URL', 'http://localhost:6333', 'Qdrant vector DB'],
                ['MASTER_KEY', '(generated)', 'Encryption master key'],
                ['LOG_LEVEL', 'INFO', 'Logging verbosity'],
                ['CORS_ORIGINS', '*', 'Allowed CORS origins'],
              ].map(([key, def, desc]) => (
                <tr key={key} className="border-b border-white/3">
                  <td className="py-2 pr-4 font-mono text-emerald-400/80">{key}</td>
                  <td className="py-2 pr-4 font-mono text-white/30">{def}</td>
                  <td className="py-2 text-white/40">{desc}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </GlassCard>
    </AppShell>
  );
}
