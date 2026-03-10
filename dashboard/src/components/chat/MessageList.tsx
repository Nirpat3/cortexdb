'use client';
import { useRef, useEffect, useMemo, useState } from 'react';
import { ArrowDown, Clock, Loader2, BookOpen } from 'lucide-react';
import { formatDate } from '@/lib/utils';
import { useChatStore } from '@/hooks/useChatStore';
import { MessageBubble } from './MessageBubble';
import { ToolCallBlock } from './ToolCallBlock';

export function MessageList() {
  const {
    messages, sending, streamingText, streamingToolCalls,
    selectedAgent, perms, condensedSummary,
  } = useChatStore();

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const [showScrollBtn, setShowScrollBtn] = useState(false);

  const anyTools = perms.read || perms.write || perms.exec || perms.network;

  // Auto-scroll on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages.length, streamingText]);

  // Show/hide "scroll to bottom" button
  useEffect(() => {
    const c = scrollContainerRef.current;
    if (!c) return;
    const onScroll = () =>
      setShowScrollBtn(c.scrollHeight - c.scrollTop - c.clientHeight > 200);
    c.addEventListener('scroll', onScroll);
    return () => c.removeEventListener('scroll', onScroll);
  }, []);

  const scrollToBottom = () =>
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });

  // Date separators
  const dateSeps = useMemo(() => {
    const map: Record<number, string> = {};
    let last = '';
    messages.forEach((m, i) => {
      const f = formatDate(m.timestamp);
      if (f !== last) { map[i] = f; last = f; }
    });
    return map;
  }, [messages]);

  return (
    <div
      ref={scrollContainerRef}
      className="relative flex-1 overflow-auto rounded-xl border border-[var(--border-default)] bg-[#0a0a0a] font-mono text-sm"
    >
      <div className="p-4 space-y-3">
        {/* Condensed summary */}
        {condensedSummary && (
          <div className="rounded-lg border border-purple-500/30 bg-purple-500/5 p-3 text-xs">
            <div className="flex items-center gap-2 mb-2 text-purple-400 font-medium">
              <BookOpen className="h-3.5 w-3.5" /> Previous Conversation Summary
            </div>
            <pre className="text-[var(--text-secondary)] whitespace-pre-wrap break-words text-[11px] max-h-32 overflow-auto">
              {condensedSummary}
            </pre>
          </div>
        )}

        {/* Empty state */}
        {messages.length === 0 && !streamingText && !condensedSummary && (
          <div className="text-[var(--text-muted)]">
            <p className="text-amber-400 mb-2">CortexDB Agent Chat v4.0</p>
            <p>
              Type <span className="text-green-400">/help</span> for commands. Use{' '}
              <span className="text-green-400">@AgentName</span> to delegate.
            </p>
            <p className="mt-1">
              Conversations auto-save and persist. Use{' '}
              <span className="text-green-400">/condense</span> to summarize long chats.
            </p>
            <p className="text-xs mt-2 text-[var(--text-muted)]">
              Read = files | Write = edit | Exec = commands | Network = HTTP
            </p>
          </div>
        )}

        {/* Messages */}
        {messages.map((msg, idx) => (
          <div key={msg.id}>
            {dateSeps[idx] && (
              <div className="flex items-center gap-3 my-4">
                <div className="flex-1 h-px bg-[var(--border-default)]" />
                <span className="text-[10px] text-[var(--text-muted)] uppercase tracking-wider flex items-center gap-1">
                  <Clock className="h-2.5 w-2.5" />
                  {dateSeps[idx]}
                </span>
                <div className="flex-1 h-px bg-[var(--border-default)]" />
              </div>
            )}
            <MessageBubble msg={msg} />
          </div>
        ))}

        {/* Streaming indicator */}
        {sending && (streamingText || streamingToolCalls.length > 0) && (
          <div className="pl-2 border-l-2 border-amber-500/30">
            <div className="flex items-center gap-2 text-xs text-[var(--text-muted)] mb-1">
              <span className="text-amber-400">[{selectedAgent?.name}]</span>
              <span className="animate-pulse text-amber-400/60">streaming...</span>
            </div>
            {streamingToolCalls.length > 0 && (
              <div className="my-2">
                {streamingToolCalls.map((tc, i) => (
                  <ToolCallBlock key={i} tc={tc} />
                ))}
              </div>
            )}
            {streamingText && (
              <pre className="text-[var(--text-secondary)] whitespace-pre-wrap break-words">
                {streamingText}
                <span className="animate-pulse">|</span>
              </pre>
            )}
          </div>
        )}

        {/* Thinking indicator */}
        {sending && !streamingText && streamingToolCalls.length === 0 && (
          <div className="flex items-center gap-2 text-amber-400/60">
            <Loader2 className="h-3 w-3 animate-spin" />
            <span className="text-xs">
              {selectedAgent?.name} is {anyTools ? 'working' : 'thinking'}...
            </span>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Scroll to bottom */}
      {showScrollBtn && (
        <button
          onClick={scrollToBottom}
          className="absolute bottom-4 right-4 flex items-center gap-1.5 rounded-full bg-amber-500/90 px-3 py-1.5 text-xs font-medium text-black shadow-lg hover:bg-amber-400 z-10"
        >
          <ArrowDown className="h-3 w-3" /> Latest
        </button>
      )}
    </div>
  );
}
