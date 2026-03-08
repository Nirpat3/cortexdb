'use client';

import { useEffect, useState, useCallback, useRef } from 'react';
import { MessageSquare, Send, Bot, User, RefreshCw } from 'lucide-react';
import { superadminApi } from '@/lib/api';
import { useTranslation } from '@/lib/i18n';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type D = Record<string, any>;

export default function InstructionsPage() {
  const { t } = useTranslation();
  const [instructions, setInstructions] = useState<D[]>([]);
  const [agents, setAgents] = useState<D[]>([]);
  const [ollamaModels, setOllamaModels] = useState<string[]>([]);
  const [content, setContent] = useState('');
  const [agentId, setAgentId] = useState('');
  const [provider, setProvider] = useState('ollama');
  const [model, setModel] = useState('');
  const [sending, setSending] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const refresh = useCallback(async () => {
    try {
      const [iRes, tRes, mRes] = await Promise.all([
        superadminApi.getInstructions(undefined, 100).catch(() => null),
        superadminApi.getTeam().catch(() => null),
        superadminApi.ollamaModels().catch(() => null),
      ]);
      if (iRes) setInstructions(((iRes as D).instructions ?? []).reverse());
      if (tRes) setAgents((tRes as D).agents ?? []);
      if (mRes) setOllamaModels((mRes as D).models ?? []);
    } catch { /* silent */ }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [instructions]);

  const handleSend = async () => {
    if (!content.trim() || sending) return;
    setSending(true);
    try {
      await superadminApi.sendInstruction({
        content: content.trim(),
        agent_id: agentId || undefined,
        provider,
        model: model || undefined,
      });
      setContent('');
      await refresh();
    } catch { /* silent */ }
    setSending(false);
  };

  const selectedAgent = agents.find((a: D) => a.agent_id === agentId);

  return (
    <div className="flex flex-col h-[calc(100vh-3rem)]">
      <div className="mb-4">
        <h1 className="text-2xl font-bold mb-1 flex items-center gap-2">
          <MessageSquare className="w-6 h-6 text-purple-400" /> {t('instructions.title')}
        </h1>
        <p className="text-sm text-white/40">{t('instructions.subtitle')}</p>
      </div>

      {/* Config Bar */}
      <div className="glass rounded-xl p-3 mb-4 flex items-center gap-3 flex-wrap">
        <div className="flex items-center gap-2">
          <span className="text-xs text-white/40">Agent:</span>
          <select value={agentId} onChange={(e) => setAgentId(e.target.value)}
            className="glass rounded-lg px-3 py-1.5 text-xs bg-white/5 border border-white/10 max-w-[200px]">
            <option value="">General (no agent)</option>
            {agents.map((a: D) => <option key={a.agent_id} value={a.agent_id}>{a.name} ({a.department})</option>)}
          </select>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-white/40">Provider:</span>
          <select value={provider} onChange={(e) => setProvider(e.target.value)}
            className="glass rounded-lg px-3 py-1.5 text-xs bg-white/5 border border-white/10">
            <option value="ollama">Ollama (Local)</option>
            <option value="claude">Claude (Anthropic)</option>
            <option value="openai">OpenAI (GPT)</option>
          </select>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-white/40">Model:</span>
          {provider === 'ollama' && ollamaModels.length > 0 ? (
            <select value={model} onChange={(e) => setModel(e.target.value)}
              className="glass rounded-lg px-3 py-1.5 text-xs bg-white/5 border border-white/10">
              <option value="">Default</option>
              {ollamaModels.map((m) => <option key={m} value={m}>{m}</option>)}
            </select>
          ) : (
            <input value={model} onChange={(e) => setModel(e.target.value)}
              placeholder={provider === 'claude' ? 'claude-sonnet-4-20250514' : 'gpt-4o'}
              className="glass rounded-lg px-3 py-1.5 text-xs bg-white/5 border border-white/10 w-48" />
          )}
        </div>
        <button onClick={refresh} className="glass px-2 py-1.5 rounded-lg text-white/40 hover:text-white/70">
          <RefreshCw className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* Agent Context */}
      {selectedAgent && (
        <div className="glass rounded-lg px-3 py-2 mb-3 text-xs text-white/40">
          Talking to <span className="text-white/70 font-medium">{selectedAgent.name}</span> ({selectedAgent.title}) —
          System prompt will be applied based on agent role
        </div>
      )}

      {/* Message History */}
      <div className="flex-1 overflow-y-auto space-y-3 mb-4 pr-1">
        {instructions.length === 0 && (
          <div className="text-center py-12 text-white/20">
            <MessageSquare className="w-10 h-10 mx-auto mb-3 opacity-30" />
            <div>{t('common.noData')}</div>
          </div>
        )}
        {instructions.map((instr: D) => {
          const agent = agents.find((a: D) => a.agent_id === instr.agent_id);
          return (
            <div key={instr.instruction_id} className="space-y-2">
              {/* User message */}
              <div className="flex items-start gap-2 justify-end">
                <div className="glass rounded-xl rounded-tr-sm p-3 max-w-[70%]">
                  <div className="text-sm whitespace-pre-wrap">{instr.content}</div>
                  <div className="text-[10px] text-white/20 mt-1 flex items-center gap-2 justify-end">
                    {instr.agent_id && <span>to: {agent?.name ?? instr.agent_id}</span>}
                    <span>{instr.provider}:{instr.model || 'default'}</span>
                    <span>{instr.created_at ? new Date(instr.created_at * 1000).toLocaleTimeString() : ''}</span>
                  </div>
                </div>
                <div className="w-8 h-8 rounded-lg bg-blue-500/20 flex items-center justify-center shrink-0">
                  <User className="w-4 h-4 text-blue-400" />
                </div>
              </div>

              {/* Response */}
              {instr.response && (
                <div className="flex items-start gap-2">
                  <div className="w-8 h-8 rounded-lg bg-purple-500/20 flex items-center justify-center shrink-0">
                    <Bot className="w-4 h-4 text-purple-400" />
                  </div>
                  <div className={`glass rounded-xl rounded-tl-sm p-3 max-w-[70%] ${
                    instr.status === 'failed' ? 'border border-red-500/30' : ''
                  }`}>
                    <div className="text-sm whitespace-pre-wrap">{instr.response}</div>
                    <div className="text-[10px] text-white/20 mt-1">
                      {instr.status === 'failed' && <span className="text-red-400">Failed · </span>}
                      {instr.completed_at ? new Date(instr.completed_at * 1000).toLocaleTimeString() : ''}
                    </div>
                  </div>
                </div>
              )}

              {instr.status === 'pending' && (
                <div className="flex items-start gap-2">
                  <div className="w-8 h-8 rounded-lg bg-white/5 flex items-center justify-center shrink-0">
                    <Bot className="w-4 h-4 text-white/30 animate-pulse" />
                  </div>
                  <div className="glass rounded-xl p-3 text-sm text-white/30 animate-pulse">Thinking...</div>
                </div>
              )}
            </div>
          );
        })}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="glass rounded-xl p-3 flex items-end gap-2">
        <textarea
          value={content}
          onChange={(e) => setContent(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); } }}
          placeholder="Type your instruction... (Enter to send, Shift+Enter for newline)"
          rows={2}
          className="flex-1 bg-transparent text-sm resize-none focus:outline-none placeholder-white/20"
        />
        <button onClick={handleSend} disabled={sending || !content.trim()}
          className="px-4 py-2 rounded-xl bg-purple-500/20 text-purple-300 hover:bg-purple-500/30 transition disabled:opacity-30 shrink-0">
          {sending ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
        </button>
      </div>
    </div>
  );
}
