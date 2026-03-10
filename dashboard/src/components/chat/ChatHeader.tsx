'use client';
import { useState, useCallback } from 'react';
import {
  Terminal, Bot, Cpu, ChevronDown, MessageSquarePlus, Download,
  Copy, Check, Settings2, Shrink, Loader2, PanelLeftOpen,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { useChatStore } from '@/hooks/useChatStore';
import { useChatSessions } from '@/hooks/useChatSessions';
import * as api from '@/lib/api';
import { toast } from '@/lib/toast';

export function ChatHeader() {
  const {
    selectedAgent, setSelectedAgent, agents, perms,
    cliMode, setCliMode, messages, selectedModel, setSelectedModel,
    models, providerHealth, sidebarOpen, setSidebarOpen,
    showSettingsPanel, setShowSettingsPanel,
  } = useChatStore();
  const { startNewChat, exportChat, condense } = useChatSessions();

  const [showAgentPicker, setShowAgentPicker] = useState(false);
  const [showModelPicker, setShowModelPicker] = useState(false);
  const [condensing, setCondensing] = useState(false);
  const [copiedAll, setCopiedAll] = useState(false);

  const anyTools = perms.read || perms.write || perms.exec || perms.network;

  const handleCondense = useCallback(async () => {
    setCondensing(true);
    await condense();
    setCondensing(false);
  }, [condense]);

  const copyConversation = useCallback(() => {
    const text = messages
      .filter((m) => !m.isSystem)
      .map((m) => {
        const prefix = m.role === 'user' ? 'You' : m.agentName || 'Assistant';
        const tools = m.toolCalls?.length
          ? `\n  [Used ${m.toolCalls.length} tool${m.toolCalls.length > 1 ? 's' : ''}: ${m.toolCalls.map((tc) => tc.tool).join(', ')}]`
          : '';
        return `${prefix}: ${m.content}${tools}`;
      })
      .join('\n\n');
    navigator.clipboard.writeText(text).then(() => {
      setCopiedAll(true);
      setTimeout(() => setCopiedAll(false), 2000);
    });
  }, [messages]);

  const handleAgentSwitch = useCallback(async (agent: api.AgentOption) => {
    setSelectedAgent(agent);
    setShowAgentPicker(false);
    if (agent.agent_id !== selectedAgent?.agent_id) {
      useChatStore.getState().clearMessages();
      try {
        const session = await api.createChatSession(agent.agent_id, `Chat with ${agent.name}`);
        useChatStore.getState().setActiveSessionId(session.id);
      } catch {
        useChatStore.getState().setActiveSessionId(null);
      }
    }
  }, [selectedAgent, setSelectedAgent]);

  // Group agents by tier
  const tierGroups: Record<string, api.AgentOption[]> = {};
  for (const a of agents) {
    (tierGroups[a.tier || 'other'] = tierGroups[a.tier || 'other'] || []).push(a);
  }

  return (
    <div className="flex items-center justify-between border-b border-[var(--border-default)] pb-3 mb-3">
      <div className="flex items-center gap-2">
        {!sidebarOpen && (
          <button onClick={() => setSidebarOpen(true)} className="rounded p-1.5 text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-hover)] mr-1">
            <PanelLeftOpen className="h-4 w-4" />
          </button>
        )}
        <Terminal className="h-5 w-5 text-amber-400" />
        <h1 className="text-lg font-semibold">Agent Chat</h1>
        {anyTools && (
          <span className="rounded-full bg-green-500/15 px-2 py-0.5 text-xs text-green-400 border border-green-500/30">
            Tools
          </span>
        )}
        <button
          onClick={() => setCliMode(!cliMode)}
          className={cn(
            'rounded-full px-2 py-0.5 text-xs border',
            cliMode
              ? 'bg-cyan-500/15 text-cyan-400 border-cyan-500/30'
              : 'bg-[var(--bg-elevated)] text-[var(--text-muted)] border-[var(--border-default)] hover:text-cyan-400',
          )}
        >
          {cliMode ? '$ CLI ON' : '$ CLI'}
        </button>
        {messages.length > 10 && (
          <button
            onClick={handleCondense}
            disabled={condensing}
            className="flex items-center gap-1 rounded-full px-2 py-0.5 text-xs border border-[var(--border-default)] bg-[var(--bg-elevated)] text-[var(--text-muted)] hover:text-purple-400 hover:border-purple-500/30 disabled:opacity-50"
          >
            {condensing ? <Loader2 className="h-3 w-3 animate-spin" /> : <Shrink className="h-3 w-3" />}
            Condense
          </button>
        )}
      </div>

      <div className="flex items-center gap-2">
        <button onClick={startNewChat} className="flex items-center gap-1.5 rounded-lg border border-[var(--border-default)] bg-[var(--bg-elevated)] px-2.5 py-1.5 text-xs hover:bg-[var(--bg-hover)] text-[var(--text-muted)]" title="New chat">
          <MessageSquarePlus className="h-3.5 w-3.5" /> New
        </button>
        <button onClick={exportChat} className="rounded-lg border border-[var(--border-default)] bg-[var(--bg-elevated)] p-1.5 text-xs hover:bg-[var(--bg-hover)] text-[var(--text-muted)]" title="Export">
          <Download className="h-3.5 w-3.5" />
        </button>
        <button onClick={copyConversation} className="rounded-lg border border-[var(--border-default)] bg-[var(--bg-elevated)] p-1.5 text-xs hover:bg-[var(--bg-hover)] text-[var(--text-muted)]" title="Copy conversation">
          {copiedAll ? <Check className="h-3.5 w-3.5 text-green-400" /> : <Copy className="h-3.5 w-3.5" />}
        </button>
        <button
          onClick={() => setShowSettingsPanel(!showSettingsPanel)}
          className={cn(
            'rounded-lg border border-[var(--border-default)] bg-[var(--bg-elevated)] p-1.5 text-xs hover:bg-[var(--bg-hover)]',
            showSettingsPanel ? 'text-amber-400 border-amber-500/30' : 'text-[var(--text-muted)]',
          )}
          title="Tools & Model Settings"
        >
          <Settings2 className="h-3.5 w-3.5" />
        </button>

        {/* Agent picker */}
        <div className="relative">
          <button onClick={() => setShowAgentPicker(!showAgentPicker)} className="flex items-center gap-2 rounded-lg border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-1.5 text-sm hover:bg-[var(--bg-hover)]">
            <Bot className="h-4 w-4 text-green-400" />
            <span>{selectedAgent ? selectedAgent.name : 'Select Agent'}</span>
            <ChevronDown className="h-3 w-3 text-[var(--text-muted)]" />
          </button>
          {showAgentPicker && (
            <div className="absolute right-0 top-full z-50 mt-1 max-h-80 w-72 overflow-auto rounded-lg border border-[var(--border-default)] bg-[var(--bg-surface)] shadow-xl">
              {Object.entries(tierGroups).sort().map(([tier, list]) => (
                <div key={tier}>
                  <div className="sticky top-0 bg-[var(--bg-elevated)] px-3 py-1.5 text-xs font-semibold text-[var(--text-muted)] uppercase">{tier}</div>
                  {list.map((a) => (
                    <button
                      key={a.agent_id}
                      onClick={() => handleAgentSwitch(a)}
                      className={cn('w-full text-left px-3 py-2 text-sm hover:bg-[var(--bg-hover)] flex justify-between', a.agent_id === selectedAgent?.agent_id && 'bg-amber-500/10')}
                    >
                      <div>
                        <div className="font-medium">{a.name}</div>
                        <div className="text-xs text-[var(--text-muted)]">{a.agent_id}</div>
                      </div>
                      <span className="text-xs text-[var(--text-muted)]">{a.department}</span>
                    </button>
                  ))}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Model picker */}
        <div className="relative">
          <button onClick={() => setShowModelPicker(!showModelPicker)} className="flex items-center gap-2 rounded-lg border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-1.5 text-sm hover:bg-[var(--bg-hover)]">
            <Cpu className="h-4 w-4 text-purple-400" />
            <span className="max-w-[120px] truncate">{selectedModel || 'Default Model'}</span>
            <ChevronDown className="h-3 w-3 text-[var(--text-muted)]" />
          </button>
          {showModelPicker && (
            <div className="absolute right-0 top-full z-50 mt-1 max-h-80 w-72 overflow-auto rounded-lg border border-[var(--border-default)] bg-[var(--bg-surface)] shadow-xl">
              <button
                onClick={() => { setSelectedModel(''); setShowModelPicker(false); }}
                className={cn('w-full text-left px-3 py-2 text-sm hover:bg-[var(--bg-hover)] border-b border-[var(--border-default)]', !selectedModel && 'bg-amber-500/10')}
              >
                <div className="font-medium">Agent Default</div>
              </button>
              {Object.entries(
                models.reduce<Record<string, typeof models>>((acc, m) => {
                  (acc[m.provider || 'unknown'] = acc[m.provider || 'unknown'] || []).push(m);
                  return acc;
                }, {}),
              ).sort().map(([prov, list]) => {
                const ph = providerHealth[prov];
                const isHealthy = ph?.status === 'healthy';
                return (
                  <div key={prov}>
                    <div className="sticky top-0 bg-[var(--bg-elevated)] px-3 py-1.5 flex items-center justify-between">
                      <span className="text-xs font-semibold text-[var(--text-muted)] uppercase">
                        {prov === 'local' ? 'Local (Ollama)' : prov}
                      </span>
                      <span className={cn('text-[10px] font-medium px-1.5 py-0.5 rounded-full', isHealthy ? 'bg-green-500/15 text-green-400' : 'bg-red-500/15 text-red-400')}>
                        {isHealthy ? 'Online' : ph?.error ? 'No API Key' : 'Offline'}
                      </span>
                    </div>
                    {list.map((m) => (
                      <button
                        key={m.model_id}
                        onClick={() => { if (isHealthy) { setSelectedModel(m.model_id); setShowModelPicker(false); } }}
                        className={cn('w-full text-left px-3 py-2 text-sm hover:bg-[var(--bg-hover)]', m.model_id === selectedModel && 'bg-amber-500/10', !isHealthy && 'opacity-40 cursor-not-allowed')}
                      >
                        <div className="flex items-center justify-between">
                          <span className="font-medium">{m.display_name || m.model_id}</span>
                          {!isHealthy && <span className="text-[10px] text-red-400/70">unavailable</span>}
                        </div>
                      </button>
                    ))}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
