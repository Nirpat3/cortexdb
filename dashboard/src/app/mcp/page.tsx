'use client';

import { useState } from 'react';
import { Cpu, Play, Loader2 } from 'lucide-react';
import { AppShell } from '@/components/shell/AppShell';
import { GlassCard } from '@/components/shared/GlassCard';
import { useApi } from '@/lib/hooks/useApi';
import { api } from '@/lib/api';

export default function MCPPage() {
  const { data: tools } = useApi('mcp-tools', api.mcpTools);
  const [selectedTool, setSelectedTool] = useState<string | null>(null);
  const [input, setInput] = useState('{}');
  const [result, setResult] = useState<string | null>(null);
  const [running, setRunning] = useState(false);

  const toolList = (tools || []) as Record<string, unknown>[];

  const handleRun = async () => {
    if (!selectedTool) return;
    setRunning(true);
    setResult(null);
    try {
      const parsed = JSON.parse(input);
      const res = await api.mcpCall(selectedTool, parsed);
      setResult(JSON.stringify(res, null, 2));
    } catch (e) {
      setResult(String(e));
    } finally {
      setRunning(false);
    }
  };

  return (
    <AppShell title="MCP Tools" icon={Cpu} color="#06B6D4">
      <div className="mb-6">
        <h2 className="text-xl font-semibold mb-1">AI Agent Tools</h2>
        <p className="text-sm text-white/40">Model Context Protocol server — tools available for AI agents</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Tool List */}
        <div>
          <h3 className="text-base font-semibold mb-3 text-white/80">Available Tools ({toolList.length})</h3>
          <div className="space-y-2 max-h-[60vh] overflow-y-auto pr-1">
            {toolList.map((tool, i) => (
              <GlassCard
                key={i}
                hover
                onClick={() => {
                  setSelectedTool(String(tool.name));
                  setResult(null);
                }}
                className={selectedTool === String(tool.name) ? 'ring-1 ring-cyan-400/40' : ''}
              >
                <div className="text-sm font-medium text-cyan-400">{String(tool.name)}</div>
                <div className="text-xs text-white/40 mt-1">{String(tool.description)}</div>
              </GlassCard>
            ))}
            {toolList.length === 0 && (
              <GlassCard className="text-center py-6 text-white/30 text-sm">
                No MCP tools available
              </GlassCard>
            )}
          </div>
        </div>

        {/* Playground */}
        <div>
          <h3 className="text-base font-semibold mb-3 text-white/80">Playground</h3>
          <GlassCard>
            <div className="text-xs text-white/40 mb-2">
              {selectedTool ? `Tool: ${selectedTool}` : 'Select a tool from the list'}
            </div>
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              className="w-full h-32 bg-black/30 rounded-lg p-3 text-sm font-mono text-white/80 resize-none outline-none border border-white/5 focus:border-cyan-400/30 transition-colors"
              placeholder='{"key": "value"}'
            />
            <button
              onClick={handleRun}
              disabled={!selectedTool || running}
              className="mt-3 flex items-center gap-2 px-4 py-2 rounded-lg bg-cyan-500/20 text-cyan-400 text-sm font-medium hover:bg-cyan-500/30 transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
            >
              {running ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
              Run Tool
            </button>
          </GlassCard>

          {result && (
            <GlassCard className="mt-3">
              <div className="text-xs text-white/40 mb-2">Result</div>
              <pre className="text-xs font-mono text-white/70 whitespace-pre-wrap max-h-64 overflow-y-auto">
                {result}
              </pre>
            </GlassCard>
          )}
        </div>
      </div>
    </AppShell>
  );
}
