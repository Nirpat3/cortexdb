'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { MessageSquare, Send, Bot, Trash2, RefreshCw, Loader2 } from 'lucide-react';
import { superadminApi } from '@/lib/api';
import { useTranslation } from '@/lib/i18n';

interface Message {
  role: 'user' | 'assistant';
  content: string;
  timestamp?: number;
}

export default function AgentChatPage() {
  const { t } = useTranslation();
  const [agents, setAgents] = useState<any[]>([]);
  const [selectedAgent, setSelectedAgent] = useState<any>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [loading, setLoading] = useState(true);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    superadminApi.getTeam().then((res: any) => {
      setAgents(res.agents || []);
      setLoading(false);
    }).catch(() => setLoading(false));
  }, []);

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, []);

  useEffect(() => { scrollToBottom(); }, [messages, scrollToBottom]);

  const selectAgent = async (agent: any) => {
    setSelectedAgent(agent);
    setMessages([]);
    // Load recent conversation from memory
    try {
      const mem = await superadminApi.getAgentMemory(agent.agent_id) as any;
      if (mem?.short_term_turns > 0) {
        const ctx = await superadminApi.getAgentContext(agent.agent_id) as any;
        // We'll start fresh but show turn count
      }
    } catch { /* silent */ }
  };

  const sendMessage = async () => {
    if (!input.trim() || !selectedAgent || sending) return;
    const userMsg = input.trim();
    setInput('');
    setMessages(prev => [...prev, { role: 'user', content: userMsg }]);
    setSending(true);

    try {
      const result = await superadminApi.chatWithAgent(
        selectedAgent.agent_id, userMsg
      ) as any;
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: result.response || result.error || t('chat.noResponse'),
      }]);
    } catch (err: any) {
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: `Error: ${err.message || t('chat.failedToSend')}`,
      }]);
    }
    setSending(false);
  };

  const clearChat = async () => {
    if (!selectedAgent) return;
    try {
      await superadminApi.clearChat(selectedAgent.agent_id);
      setMessages([]);
    } catch { /* silent */ }
  };

  const deptColors: Record<string, string> = {
    engineering: 'bg-blue-500/10 text-blue-400',
    qa: 'bg-green-500/10 text-green-400',
    operations: 'bg-amber-500/10 text-amber-400',
    security: 'bg-red-500/10 text-red-400',
    documentation: 'bg-purple-500/10 text-purple-400',
    executive: 'bg-cyan-500/10 text-cyan-400',
  };

  return (
    <div className="flex h-[calc(100vh-3rem)] gap-4">
      {/* Agent List */}
      <div className="w-64 glass rounded-xl border border-white/5 flex flex-col shrink-0">
        <div className="p-3 border-b border-white/5">
          <h3 className="text-sm font-medium flex items-center gap-2">
            <MessageSquare className="w-4 h-4 text-cyan-400" /> {t('chat.title')}
          </h3>
          <p className="text-[10px] text-white/30 mt-1">{t('chat.selectAgent')}</p>
        </div>
        <div className="flex-1 overflow-y-auto p-2 space-y-1">
          {loading ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="w-4 h-4 animate-spin text-white/30" />
            </div>
          ) : agents.map((agent: any) => (
            <button key={agent.agent_id} onClick={() => selectAgent(agent)}
              className={`w-full text-left px-3 py-2 rounded-lg text-xs transition ${
                selectedAgent?.agent_id === agent.agent_id
                  ? 'bg-white/10 text-white'
                  : 'text-white/50 hover:text-white/80 hover:bg-white/5'
              }`}>
              <div className="font-medium truncate">{agent.name}</div>
              <div className="text-[10px] text-white/30 truncate">{agent.title}</div>
            </button>
          ))}
        </div>
      </div>

      {/* Chat Area */}
      <div className="flex-1 glass rounded-xl border border-white/5 flex flex-col">
        {selectedAgent ? (
          <>
            {/* Chat Header */}
            <div className="p-4 border-b border-white/5 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 rounded-lg bg-cyan-500/10 flex items-center justify-center">
                  <Bot className="w-4.5 h-4.5 text-cyan-400" />
                </div>
                <div>
                  <div className="text-sm font-medium">{selectedAgent.name}</div>
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] text-white/40">{selectedAgent.title}</span>
                    <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${
                      deptColors[selectedAgent.department] || 'bg-white/5 text-white/40'
                    }`}>{selectedAgent.department}</span>
                  </div>
                </div>
              </div>
              <button onClick={clearChat} className="p-2 rounded-lg hover:bg-white/5 text-white/30 hover:text-white/60 transition"
                title={t('chat.clearConversation')}>
                <Trash2 className="w-4 h-4" />
              </button>
            </div>

            {/* Messages */}
            <div className="flex-1 overflow-y-auto p-4 space-y-4">
              {messages.length === 0 && (
                <div className="text-center text-white/20 text-sm py-12">
                  <Bot className="w-8 h-8 mx-auto mb-3 opacity-30" />
                  <p>{t('chat.startConversation', { name: selectedAgent.name })}</p>
                  <p className="text-[10px] mt-1">{t('chat.messagesStored')}</p>
                </div>
              )}
              {messages.map((msg, i) => (
                <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                  <div className={`max-w-[75%] rounded-xl px-4 py-2.5 text-sm ${
                    msg.role === 'user'
                      ? 'bg-cyan-500/15 text-cyan-100'
                      : 'glass border border-white/5 text-white/80'
                  }`}>
                    <div className="whitespace-pre-wrap">{msg.content}</div>
                  </div>
                </div>
              ))}
              {sending && (
                <div className="flex justify-start">
                  <div className="glass border border-white/5 rounded-xl px-4 py-2.5">
                    <Loader2 className="w-4 h-4 animate-spin text-white/30" />
                  </div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>

            {/* Input */}
            <div className="p-4 border-t border-white/5">
              <div className="flex gap-2">
                <input
                  type="text"
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && sendMessage()}
                  placeholder={t('chat.messagePlaceholder', { name: selectedAgent.name })}
                  className="flex-1 glass rounded-xl px-4 py-2.5 text-sm bg-white/5 border border-white/10 focus:border-cyan-500/50 focus:outline-none transition"
                  disabled={sending}
                />
                <button onClick={sendMessage} disabled={sending || !input.trim()}
                  className="px-4 py-2.5 rounded-xl bg-cyan-500/20 text-cyan-300 hover:bg-cyan-500/30 transition disabled:opacity-30">
                  <Send className="w-4 h-4" />
                </button>
              </div>
            </div>
          </>
        ) : (
          <div className="flex-1 flex items-center justify-center text-white/20">
            <div className="text-center">
              <MessageSquare className="w-10 h-10 mx-auto mb-3 opacity-30" />
              <p className="text-sm">{t('chat.selectToStart')}</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
