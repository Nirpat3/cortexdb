'use client';

import { useState } from 'react';
import { Terminal, Play, Loader2, Clock, Zap, Database } from 'lucide-react';
import { AppShell } from '@/components/shell/AppShell';
import { GlassCard } from '@/components/shared/GlassCard';
import { api } from '@/lib/api';
import { formatMs } from '@/lib/utils';

const EXAMPLES = [
  { label: 'List Blocks', query: 'SELECT * FROM blocks LIMIT 10' },
  { label: 'Vector Search', query: "FIND SIMILAR TO 'enterprise analytics' IN embeddings LIMIT 5" },
  { label: 'Graph Traverse', query: 'TRAVERSE Customer->PURCHASED->Product DEPTH 2' },
  { label: 'Stream Subscribe', query: 'SUBSCRIBE TO events:purchase_completed' },
  { label: 'Ledger Commit', query: "COMMIT TO LEDGER { type: 'AUDIT', action: 'query_test' }" },
];

export default function QueryPage() {
  const [query, setQuery] = useState('SELECT * FROM blocks LIMIT 10');
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [history, setHistory] = useState<string[]>([]);

  const handleExecute = async () => {
    if (!query.trim()) return;
    setRunning(true);
    setError(null);
    setResult(null);
    try {
      const res = await api.query(query);
      setResult(res);
      setHistory((h) => [query, ...h.slice(0, 19)]);
    } catch (e) {
      setError(String(e));
    } finally {
      setRunning(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
      e.preventDefault();
      handleExecute();
    }
  };

  return (
    <AppShell title="Query Console" icon={Terminal} color="#6366F1">
      <div className="grid grid-cols-1 lg:grid-cols-[1fr_280px] gap-6">
        <div>
          {/* Editor */}
          <GlassCard className="mb-4">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs text-white/40">CortexQL</span>
              <span className="text-[10px] text-white/20">Ctrl+Enter to execute</span>
            </div>
            <textarea
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={handleKeyDown}
              className="w-full h-40 bg-black/40 rounded-xl p-4 text-sm font-mono text-indigo-200 resize-none outline-none border border-white/5 focus:border-indigo-400/30 transition-colors leading-relaxed"
              spellCheck={false}
            />
            <div className="flex items-center justify-between mt-3">
              <div className="flex gap-2 flex-wrap">
                {EXAMPLES.map((ex) => (
                  <button
                    key={ex.label}
                    onClick={() => setQuery(ex.query)}
                    className="text-[10px] px-2 py-1 rounded-md bg-white/5 text-white/40 hover:text-white/70 hover:bg-white/10 transition-colors"
                  >
                    {ex.label}
                  </button>
                ))}
              </div>
              <button
                onClick={handleExecute}
                disabled={running || !query.trim()}
                className="flex items-center gap-2 px-4 py-2 rounded-lg bg-indigo-500/20 text-indigo-400 text-sm font-medium hover:bg-indigo-500/30 transition-colors disabled:opacity-30"
              >
                {running ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
                Execute
              </button>
            </div>
          </GlassCard>

          {/* Results */}
          {error && (
            <GlassCard className="border-red-500/20">
              <div className="text-xs text-red-400 font-medium mb-1">Error</div>
              <pre className="text-xs font-mono text-red-300/70 whitespace-pre-wrap">{error}</pre>
            </GlassCard>
          )}

          {result && (
            <GlassCard>
              <div className="flex items-center gap-4 mb-3 text-xs text-white/40">
                <span className="flex items-center gap-1">
                  <Clock className="w-3 h-3" />
                  {formatMs(Number(result.execution_time_ms) || 0)}
                </span>
                <span className="flex items-center gap-1">
                  <Database className="w-3 h-3" />
                  {String(result.engine_used || 'unknown')}
                </span>
                <span className="flex items-center gap-1">
                  <Zap className="w-3 h-3" />
                  {result.cached ? 'Cached' : 'Fresh'}
                </span>
                <span>{String(result.row_count || 0)} rows</span>
              </div>

              <div className="overflow-x-auto">
                <pre className="text-xs font-mono text-white/70 whitespace-pre-wrap max-h-96 overflow-y-auto">
                  {JSON.stringify(result.data || result, null, 2)}
                </pre>
              </div>
            </GlassCard>
          )}
        </div>

        {/* History Sidebar */}
        <div className="hidden lg:block">
          <h3 className="text-sm font-semibold mb-3 text-white/60">History</h3>
          <div className="space-y-2 max-h-[70vh] overflow-y-auto pr-1">
            {history.length > 0 ? (
              history.map((q, i) => (
                <button
                  key={i}
                  onClick={() => setQuery(q)}
                  className="w-full text-left glass rounded-lg p-2.5 text-xs font-mono text-white/50 hover:text-white/80 hover:bg-white/5 transition-colors truncate"
                >
                  {q}
                </button>
              ))
            ) : (
              <div className="text-xs text-white/20 text-center py-4">No queries yet</div>
            )}
          </div>
        </div>
      </div>
    </AppShell>
  );
}
