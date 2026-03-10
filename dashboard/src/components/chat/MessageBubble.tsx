'use client';
import { useState, useCallback } from 'react';
import { Copy, Check, FileText, Image as ImageIcon } from 'lucide-react';
import { cn } from '@/lib/utils';
import { formatTime } from '@/lib/utils';
import { ToolCallBlock } from './ToolCallBlock';
import type { ChatMessage } from '@/hooks/useChatStore';

interface MessageBubbleProps {
  msg: ChatMessage;
}

export function MessageBubble({ msg }: MessageBubbleProps) {
  const [copied, setCopied] = useState(false);

  const copy = useCallback(() => {
    navigator.clipboard.writeText(msg.content).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }, [msg.content]);

  if (msg.role === 'user') return <UserBubble msg={msg} copied={copied} onCopy={copy} />;
  return <AssistantBubble msg={msg} copied={copied} onCopy={copy} />;
}

/* ── User message ── */
function UserBubble({ msg, copied, onCopy }: { msg: ChatMessage; copied: boolean; onCopy: () => void }) {
  return (
    <div className="group/msg flex items-start gap-2">
      <span className="text-green-400 shrink-0">&gt;</span>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-[var(--text-primary)] whitespace-pre-wrap break-words">
            {msg.content.split(/(@[\w\s-]+?)(?=\s|$|,)/g).map((part, i) =>
              part.startsWith('@') ? (
                <span key={i} className="text-cyan-400 font-medium">{part}</span>
              ) : (
                <span key={i}>{part}</span>
              ),
            )}
          </span>
          <CopyButton copied={copied} onCopy={onCopy} />
          <span className="text-[10px] text-[var(--text-muted)] shrink-0 ml-auto">
            {formatTime(msg.timestamp)}
          </span>
        </div>
        {msg.attachments && msg.attachments.length > 0 && (
          <div className="mt-1 flex flex-wrap gap-2">
            {msg.attachments.map((a, i) => (
              <div
                key={i}
                className="flex items-center gap-1.5 rounded border border-[var(--border-default)] bg-[var(--bg-elevated)] px-2 py-1 text-xs"
              >
                {a.type.startsWith('image/') ? (
                  <ImageIcon className="h-3 w-3 text-purple-400" />
                ) : (
                  <FileText className="h-3 w-3 text-blue-400" />
                )}
                <span className="text-[var(--text-secondary)] max-w-[150px] truncate">{a.name}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

/* ── Assistant message ── */
function AssistantBubble({ msg, copied, onCopy }: { msg: ChatMessage; copied: boolean; onCopy: () => void }) {
  return (
    <div className="group/msg pl-2 border-l-2 border-amber-500/30">
      <div className="flex items-center gap-2 text-xs text-[var(--text-muted)] mb-1">
        {msg.agentName && (
          <span className={msg.isSystem ? 'text-yellow-500' : 'text-amber-400'}>
            [{msg.agentName}]
          </span>
        )}
        {msg.model && <span className="text-blue-400/60">{msg.model}</span>}
        {msg.tokens && msg.tokens.input + msg.tokens.output > 0 && (
          <span>({msg.tokens.input + msg.tokens.output} tok)</span>
        )}
        {msg.toolCalls?.length ? (
          <span className="text-cyan-400/70">
            {msg.toolCalls.length} tool{msg.toolCalls.length > 1 ? 's' : ''}
          </span>
        ) : null}
        <CopyButton copied={copied} onCopy={onCopy} />
        <span className="text-[10px] ml-auto">{formatTime(msg.timestamp)}</span>
      </div>
      {msg.toolCalls && msg.toolCalls.length > 0 && (
        <div className="my-2">
          {msg.toolCalls.map((tc, i) => (
            <ToolCallBlock key={i} tc={tc} />
          ))}
        </div>
      )}
      <pre className="text-[var(--text-secondary)] whitespace-pre-wrap break-words">{msg.content}</pre>
    </div>
  );
}

/* ── Copy button ── */
function CopyButton({ copied, onCopy }: { copied: boolean; onCopy: () => void }) {
  return (
    <button
      onClick={onCopy}
      className="opacity-0 group-hover/msg:opacity-100 transition-opacity shrink-0 p-0.5 rounded hover:bg-white/10"
      title="Copy message"
    >
      {copied ? (
        <Check className="h-3 w-3 text-green-400" />
      ) : (
        <Copy className="h-3 w-3 text-[var(--text-muted)]" />
      )}
    </button>
  );
}
