'use client';

import { useState } from 'react';
import { Gauge, Play, Loader2, Timer, Zap, TrendingUp } from 'lucide-react';
import { AppShell } from '@/components/shell/AppShell';
import { GlassCard } from '@/components/shared/GlassCard';
import { MetricBadge } from '@/components/shared/MetricBadge';
import { api } from '@/lib/api';
import { formatMs, formatNumber } from '@/lib/utils';

const SUITES = ['read_cascade', 'write_fanout', 'vector_search', 'graph_traversal', 'full'];

export default function BenchmarkPage() {
  const [suite, setSuite] = useState('full');
  const [concurrency, setConcurrency] = useState(10);
  const [iterations, setIterations] = useState(100);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [result, setResult] = useState<Record<string, any> | null>(null);
  const [running, setRunning] = useState(false);

  const handleRun = async () => {
    setRunning(true);
    setResult(null);
    try {
      const res = await api.runBenchmark(suite, concurrency, iterations);
      setResult(res);
    } catch (e) {
      setResult({ error: String(e) });
    } finally {
      setRunning(false);
    }
  };

  return (
    <AppShell title="Benchmark" icon={Gauge} color="#F97316">
      <div className="mb-6">
        <h2 className="text-xl font-semibold mb-1">Performance Testing</h2>
        <p className="text-sm text-white/40">Benchmark and stress-test CortexDB</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Config */}
        <GlassCard>
          <h3 className="text-sm font-semibold mb-4 text-white/80">Configuration</h3>

          <div className="space-y-4">
            <div>
              <label className="text-xs text-white/40 mb-1 block">Suite</label>
              <div className="flex flex-wrap gap-2">
                {SUITES.map((s) => (
                  <button
                    key={s}
                    onClick={() => setSuite(s)}
                    className={`text-xs px-3 py-1.5 rounded-lg transition-colors ${
                      suite === s
                        ? 'bg-orange-500/20 text-orange-400'
                        : 'bg-white/5 text-white/40 hover:bg-white/10'
                    }`}
                  >
                    {s.replace(/_/g, ' ')}
                  </button>
                ))}
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs text-white/40 mb-1 block">Concurrency</label>
                <input
                  type="number"
                  value={concurrency}
                  onChange={(e) => setConcurrency(Number(e.target.value))}
                  className="w-full bg-black/30 rounded-lg px-3 py-2 text-sm text-white outline-none border border-white/5 focus:border-orange-400/30"
                />
              </div>
              <div>
                <label className="text-xs text-white/40 mb-1 block">Iterations</label>
                <input
                  type="number"
                  value={iterations}
                  onChange={(e) => setIterations(Number(e.target.value))}
                  className="w-full bg-black/30 rounded-lg px-3 py-2 text-sm text-white outline-none border border-white/5 focus:border-orange-400/30"
                />
              </div>
            </div>

            <button
              onClick={handleRun}
              disabled={running}
              className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-orange-500/20 text-orange-400 text-sm font-medium hover:bg-orange-500/30 transition-colors disabled:opacity-30"
            >
              {running ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
              {running ? 'Running...' : 'Start Benchmark'}
            </button>
          </div>
        </GlassCard>

        {/* Results */}
        <div>
          {result && !result.error && (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-3">
                <GlassCard>
                  <div className="flex items-center gap-2 text-xs text-white/40 mb-1">
                    <Zap className="w-3 h-3" /> Ops/sec
                  </div>
                  <div className="text-2xl font-bold text-orange-400">
                    {formatNumber(Number(result.ops_per_sec) || 0)}
                  </div>
                </GlassCard>
                <GlassCard>
                  <div className="flex items-center gap-2 text-xs text-white/40 mb-1">
                    <Timer className="w-3 h-3" /> Avg Latency
                  </div>
                  <div className="text-2xl font-bold text-blue-400">
                    {formatMs(Number(result.avg_latency_ms) || 0)}
                  </div>
                </GlassCard>
              </div>

              <GlassCard>
                <div className="flex items-center gap-2 text-xs text-white/40 mb-2">
                  <TrendingUp className="w-3 h-3" /> Details
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <MetricBadge label="Total Ops" value={formatNumber(Number(result.total_ops) || 0)} />
                  <MetricBadge label="Duration" value={`${Number(result.duration_sec) || 0}s`} />
                  <MetricBadge label="P99 Latency" value={formatMs(Number(result.p99_latency_ms) || 0)} />
                  <MetricBadge label="Suite" value={String(result.suite || suite)} />
                </div>
              </GlassCard>

              <GlassCard>
                <div className="text-xs text-white/40 mb-2">Raw Output</div>
                <pre className="text-xs font-mono text-white/50 whitespace-pre-wrap max-h-48 overflow-y-auto">
                  {JSON.stringify(result, null, 2)}
                </pre>
              </GlassCard>
            </div>
          )}

          {result && 'error' in result && result.error && (
            <GlassCard className="border-red-500/20">
              <div className="text-xs text-red-400 font-medium mb-1">Error</div>
              <pre className="text-xs font-mono text-red-300/70">{String(result.error)}</pre>
            </GlassCard>
          )}

          {!result && (
            <GlassCard className="text-center py-16 text-white/20 text-sm">
              Configure and run a benchmark to see results
            </GlassCard>
          )}
        </div>
      </div>

      {/* Reference benchmarks */}
      <div className="mt-8">
        <h3 className="text-base font-semibold mb-3 text-white/80">Reference Performance</h3>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {[
            { metric: 'R0 Cache', target: '< 0.1ms', measured: '0.02ms' },
            { metric: 'R1 Redis', target: '< 1ms', measured: '0.4ms' },
            { metric: 'R3 Postgres', target: '< 50ms', measured: '12ms' },
            { metric: 'Write Fanout', target: '< 20ms', measured: '8ms' },
          ].map((b) => (
            <GlassCard key={b.metric}>
              <div className="text-xs text-white/40">{b.metric}</div>
              <div className="text-lg font-bold text-emerald-400 mt-1">{b.measured}</div>
              <div className="text-[10px] text-white/30">Target: {b.target}</div>
            </GlassCard>
          ))}
        </div>
      </div>
    </AppShell>
  );
}
