'use client';
import { useState, useEffect, useCallback } from 'react';
import { Settings2, X, Cpu, Wrench, AppWindow, Plus, Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useChatStore } from '@/hooks/useChatStore';
import * as api from '@/lib/api';
import { toast } from '@/lib/toast';

export function SettingsPanel() {
  const { selectedAgent, showSettingsPanel, setShowSettingsPanel, models, selectedModel, setSelectedModel } = useChatStore();

  const [agentTools, setAgentTools] = useState<api.AgentTool[]>([]);
  const [agentApps, setAgentApps] = useState<api.AgentApp[]>([]);
  const [addToolName, setAddToolName] = useState('');
  const [loading, setLoading] = useState(false);

  const loadData = useCallback(async () => {
    if (!selectedAgent) return;
    setLoading(true);
    try {
      const [tools, apps] = await Promise.all([
        api.getAgentTools(selectedAgent.agent_id).catch(() => []),
        api.getAgentApps(selectedAgent.agent_id).catch(() => []),
      ]);
      setAgentTools(Array.isArray(tools) ? tools : (tools as any).tools || []);
      setAgentApps(Array.isArray(apps) ? apps : []);
    } catch {}
    setLoading(false);
  }, [selectedAgent]);

  useEffect(() => {
    if (showSettingsPanel && selectedAgent) loadData();
  }, [showSettingsPanel, selectedAgent, loadData]);

  const handleAssignTool = async (toolName: string) => {
    if (!selectedAgent || !toolName) return;
    try {
      await api.assignTool(selectedAgent.agent_id, toolName);
      setAddToolName('');
      await loadData();
      toast.success(`Tool "${toolName}" assigned`);
    } catch (err) {
      toast.apiError('Assign tool', err);
    }
  };

  const handleRevokeTool = async (toolName: string) => {
    if (!selectedAgent) return;
    try {
      await api.revokeTool(selectedAgent.agent_id, toolName);
      await loadData();
      toast.success(`Tool "${toolName}" revoked`);
    } catch (err) {
      toast.apiError('Revoke tool', err);
    }
  };

  const handleSetModel = async (modelId: string) => {
    if (!selectedAgent) return;
    try {
      await api.setAgentModel(selectedAgent.agent_id, modelId);
      setSelectedModel(modelId);
      toast.success(`Model changed to ${modelId || 'default'}`);
    } catch (err) {
      toast.apiError('Set model', err);
    }
  };

  if (!showSettingsPanel) return null;

  return (
    <div className="rounded-xl border border-amber-500/20 bg-[var(--bg-surface)] p-4 mb-3 space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-semibold text-amber-400 flex items-center gap-1.5">
          <Settings2 className="h-3.5 w-3.5" /> Agent Configuration
        </h3>
        <button onClick={() => setShowSettingsPanel(false)} className="text-[var(--text-muted)] hover:text-[var(--text-primary)]">
          <X className="h-3.5 w-3.5" />
        </button>
      </div>

      {loading ? (
        <div className="flex items-center gap-2 text-xs text-[var(--text-muted)]">
          <Loader2 className="h-3 w-3 animate-spin" /> Loading...
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {/* Model */}
          <div>
            <div className="text-[10px] text-[var(--text-muted)] uppercase tracking-wider mb-2 flex items-center gap-1">
              <Cpu className="h-3 w-3" /> Model
            </div>
            <select
              value={selectedModel}
              onChange={(e) => handleSetModel(e.target.value)}
              className="w-full rounded-lg border border-[var(--border-default)] bg-[var(--bg-elevated)] px-2 py-1.5 text-xs"
            >
              <option value="">Agent Default</option>
              {models.map((m) => (
                <option key={m.model_id} value={m.model_id}>{m.display_name || m.model_id}</option>
              ))}
            </select>
            {selectedModel && (
              <div className="mt-1 text-[10px] text-[var(--text-muted)]">
                Provider: {models.find((m) => m.model_id === selectedModel)?.provider || 'unknown'}
              </div>
            )}
          </div>

          {/* Tools */}
          <div>
            <div className="text-[10px] text-[var(--text-muted)] uppercase tracking-wider mb-2 flex items-center gap-1">
              <Wrench className="h-3 w-3" /> Tools ({agentTools.length})
            </div>
            <div className="max-h-32 overflow-auto space-y-1">
              {agentTools.map((t) => (
                <div key={t.tool_name} className="flex items-center justify-between rounded px-2 py-1 bg-[var(--bg-elevated)] text-xs group">
                  <span className="font-mono truncate">{t.tool_name}</span>
                  <div className="flex items-center gap-1">
                    <span className={cn('text-[10px] px-1 rounded', t.permission_level === 'auto' ? 'text-green-400' : t.permission_level === 'supervised' ? 'text-amber-400' : 'text-red-400')}>
                      {t.permission_level}
                    </span>
                    <button onClick={() => handleRevokeTool(t.tool_name)} className="opacity-0 group-hover:opacity-100 text-red-400 hover:text-red-300 p-0.5">
                      <X className="h-3 w-3" />
                    </button>
                  </div>
                </div>
              ))}
              {agentTools.length === 0 && (
                <div className="text-[10px] text-[var(--text-muted)] py-1">No tools assigned</div>
              )}
            </div>
            <div className="flex items-center gap-1 mt-2">
              <input
                type="text"
                value={addToolName}
                onChange={(e) => setAddToolName(e.target.value)}
                placeholder="Tool name..."
                className="flex-1 rounded border border-[var(--border-default)] bg-[var(--bg-elevated)] px-2 py-1 text-[10px]"
                onKeyDown={(e) => { if (e.key === 'Enter') handleAssignTool(addToolName); }}
              />
              <button onClick={() => handleAssignTool(addToolName)} disabled={!addToolName} className="rounded bg-green-500/15 text-green-400 px-2 py-1 text-[10px] hover:bg-green-500/25 disabled:opacity-50">
                <Plus className="h-3 w-3" />
              </button>
            </div>
          </div>

          {/* Apps */}
          <div>
            <div className="text-[10px] text-[var(--text-muted)] uppercase tracking-wider mb-2 flex items-center gap-1">
              <AppWindow className="h-3 w-3" /> Apps ({agentApps.length})
            </div>
            <div className="max-h-32 overflow-auto space-y-1">
              {agentApps.map((a) => (
                <div key={a.slug} className="flex items-center justify-between rounded px-2 py-1 bg-[var(--bg-elevated)] text-xs">
                  <span className="truncate">{a.name}</span>
                  <span className={cn('text-[10px] px-1 rounded', a.status === 'active' ? 'text-green-400' : 'text-[var(--text-muted)]')}>
                    {a.status}
                  </span>
                </div>
              ))}
              {agentApps.length === 0 && (
                <div className="text-[10px] text-[var(--text-muted)] py-1">No apps connected</div>
              )}
            </div>
            <a href="/apps" className="text-[10px] text-amber-400 hover:text-amber-300 mt-1 inline-block">
              Manage in App Marketplace &rarr;
            </a>
          </div>
        </div>
      )}
    </div>
  );
}
