'use client';
import { useRef, useEffect, useCallback, useState } from 'react';
import { Send, Paperclip, Smile, X, Terminal, FileText, Image as ImageIcon, AtSign } from 'lucide-react';
import { cn, formatFileSize, validateFile } from '@/lib/utils';
import { toast } from '@/lib/toast';
import { useChatStore } from '@/hooks/useChatStore';
import { useMentions } from '@/hooks/useMentions';
import type { FileAttachment } from '@/hooks/useChatStore';

const EMOJI_CATEGORIES: Record<string, string[]> = {
  Smileys: ['😀','😂','🤣','😊','😍','🥰','😎','🤔','😏','🙄','😤','😡','🥺','😢','😭','🤯','🥳','😴','🤖','👽','💀','👻','🎃','😈'],
  Gestures: ['👍','👎','👏','🙌','🤝','✌️','🤞','💪','👋','🫡','🫶','❤️','🔥','⭐','✨','💯','🎯','🚀','💡','⚡'],
  Objects: ['📎','📁','📂','💻','🖥️','⌨️','🔧','🔨','🛡️','🔒','🔑','📊','📈','🗂️','📋','✅','❌','⚠️','🔔','💬'],
};

interface ChatInputProps {
  onSend: (text: string, files?: FileAttachment[]) => void;
  onCommand: (cmd: string) => boolean;
}

export function ChatInput({ onSend, onCommand }: ChatInputProps) {
  const {
    input, setInput, attachments, setAttachments,
    sending, agentsLoaded, selectedAgent, cliMode,
  } = useChatStore();

  const mentions = useMentions();
  const inputRef = useRef<HTMLInputElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const emojiRef = useRef<HTMLDivElement>(null);
  const [showEmojiPicker, setShowEmojiPicker] = useState(false);

  // Close emoji picker on outside click
  useEffect(() => {
    if (!showEmojiPicker) return;
    const handler = (e: MouseEvent) => {
      if (emojiRef.current && !emojiRef.current.contains(e.target as Node)) {
        setShowEmojiPicker(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [showEmojiPicker]);

  // Close mentions on outside click
  useEffect(() => {
    if (!mentions.isActive) return;
    const handler = (e: MouseEvent) => mentions.dismiss();
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [mentions.isActive]);

  const handleFileSelect = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files) return;

    Array.from(files).forEach((file) => {
      // Validate file size before reading
      const error = validateFile(file);
      if (error) {
        toast.error(error);
        return;
      }

      const att: FileAttachment = { name: file.name, size: file.size, type: file.type };
      const reader = new FileReader();
      if (file.type.startsWith('image/')) {
        reader.onload = () => {
          att.dataUrl = reader.result as string;
          setAttachments((prev) => [...prev, att]);
        };
        reader.readAsDataURL(file);
      } else {
        reader.onload = () => {
          att.content = reader.result as string;
          setAttachments((prev) => [...prev, att]);
        };
        reader.readAsText(file);
      }
    });
    e.target.value = '';
  }, [setAttachments]);

  const removeAttachment = useCallback(
    (i: number) => setAttachments((prev) => prev.filter((_, j) => j !== i)),
    [setAttachments],
  );

  const insertEmoji = useCallback(
    (emoji: string) => {
      setInput(input + emoji);
      setShowEmojiPicker(false);
      inputRef.current?.focus();
    },
    [input, setInput],
  );

  const handleInputChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const val = e.target.value;
      setInput(val);
      const pos = e.target.selectionStart || val.length;
      mentions.updateFromInput(val, pos);
    },
    [setInput, mentions],
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLInputElement>) => {
      // Mention navigation
      if (mentions.isActive) {
        if (e.key === 'ArrowDown') {
          e.preventDefault();
          mentions.setMentionIdx((i) => Math.min(i + 1, mentions.results.length - 1));
          return;
        }
        if (e.key === 'ArrowUp') {
          e.preventDefault();
          mentions.setMentionIdx((i) => Math.max(i - 1, 0));
          return;
        }
        if (e.key === 'Tab' || e.key === 'Enter') {
          e.preventDefault();
          mentions.insertMention(mentions.results[mentions.mentionIdx].name);
          return;
        }
        if (e.key === 'Escape') {
          e.preventDefault();
          mentions.dismiss();
          return;
        }
      }
      if (e.key === 'Enter') handleSend();
    },
    [mentions],
  );

  const handleSend = useCallback(() => {
    const text = input.trim();
    if (!text && attachments.length === 0) return;
    if (sending) return;

    // Check commands
    if (text.startsWith('/') || text.startsWith('!')) {
      setInput('');
      if (onCommand(text)) return;
    }

    if (!selectedAgent) {
      useChatStore.getState().addSystemMessage('No agent selected.');
      return;
    }

    let msg = cliMode && !text.startsWith('/')
      ? `Run this command and show the full output. Do not explain, just run it:\n\`\`\`\n${text}\n\`\`\``
      : text;

    if (attachments.length > 0) {
      const descs = attachments.map((a) =>
        a.content
          ? `[File: ${a.name}]\n\`\`\`\n${a.content.slice(0, 4000)}\n\`\`\``
          : `[File: ${a.name} (${formatFileSize(a.size)})]`,
      );
      msg = msg ? `${msg}\n\n${descs.join('\n\n')}` : descs.join('\n\n');
    }

    const currentAttachments = [...attachments];
    setInput('');
    setAttachments([]);
    mentions.dismiss();
    onSend(msg, currentAttachments);
  }, [input, attachments, sending, selectedAgent, cliMode, onSend, onCommand, setInput, setAttachments, mentions]);

  return (
    <>
      {/* Attachments preview */}
      {attachments.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-2 px-1">
          {attachments.map((a, i) => (
            <div
              key={i}
              className="flex items-center gap-1.5 rounded-lg border border-[var(--border-default)] bg-[var(--bg-elevated)] px-2.5 py-1.5 text-xs"
            >
              {a.type.startsWith('image/') ? (
                a.dataUrl ? (
                  <img src={a.dataUrl} alt={a.name} className="h-6 w-6 rounded object-cover" />
                ) : (
                  <ImageIcon className="h-3.5 w-3.5 text-purple-400" />
                )
              ) : (
                <FileText className="h-3.5 w-3.5 text-blue-400" />
              )}
              <span className="text-[var(--text-secondary)] max-w-[120px] truncate">{a.name}</span>
              <button
                onClick={() => removeAttachment(i)}
                className="ml-0.5 rounded p-0.5 text-[var(--text-muted)] hover:text-red-400"
              >
                <X className="h-3 w-3" />
              </button>
            </div>
          ))}
        </div>
      )}

      {/* CLI mode banner */}
      {cliMode && (
        <div className="mt-2 flex items-center gap-2 rounded-lg bg-cyan-500/10 border border-cyan-500/30 px-3 py-1.5 text-xs">
          <Terminal className="h-3.5 w-3.5 text-cyan-400" />
          <span className="text-cyan-400 font-medium">CLI Mode</span>
          <span className="text-[var(--text-muted)]">-- Type /cli to exit.</span>
        </div>
      )}

      {/* Input bar */}
      <div className="relative">
        {/* Mention dropdown */}
        {mentions.isActive && (
          <div className="absolute bottom-full left-0 mb-1 w-80 rounded-lg border border-[var(--border-default)] bg-[var(--bg-surface)] shadow-xl z-50 overflow-hidden">
            <div className="px-3 py-1.5 text-[10px] font-semibold text-[var(--text-muted)] uppercase bg-[var(--bg-elevated)] flex items-center gap-1.5">
              <AtSign className="h-3 w-3" /> Mention agent
            </div>
            {mentions.results.map((a, i) => (
              <button
                key={a.agent_id}
                onClick={() => mentions.insertMention(a.name)}
                className={cn(
                  'w-full text-left px-3 py-2 text-sm flex justify-between hover:bg-[var(--bg-hover)]',
                  i === mentions.mentionIdx && 'bg-amber-500/10',
                )}
              >
                <div>
                  <div className="font-medium">{a.name}</div>
                  <div className="text-xs text-[var(--text-muted)]">{a.agent_id}</div>
                </div>
                <span className="text-[10px] text-[var(--text-muted)] capitalize">{a.tier}</span>
              </button>
            ))}
          </div>
        )}

        <div
          className={cn(
            'mt-2 flex items-center gap-2 rounded-lg border px-3 py-2.5 font-mono',
            cliMode ? 'border-cyan-500/40 bg-[#0a0f0a]' : 'border-[var(--border-default)] bg-[#0a0a0a]',
          )}
        >
          <input ref={fileInputRef} type="file" multiple className="hidden" onChange={handleFileSelect}
            accept=".txt,.md,.json,.csv,.js,.ts,.py,.html,.css,.log,.xml,.yaml,.yml,.toml,.sh,.sql,.png,.jpg,.jpeg,.gif,.svg,.webp,.pdf"
          />
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={sending}
            className="rounded p-1 text-[var(--text-muted)] hover:text-blue-400 disabled:opacity-30"
          >
            <Paperclip className="h-4 w-4" />
          </button>

          <span className={cn('shrink-0', cliMode ? 'text-cyan-400' : 'text-green-400')}>
            {cliMode ? '$' : '>'}
          </span>

          <input
            ref={inputRef}
            type="text"
            value={input}
            onChange={handleInputChange}
            onKeyDown={handleKeyDown}
            placeholder={
              !agentsLoaded
                ? 'Loading...'
                : cliMode
                  ? 'Enter command...'
                  : selectedAgent
                    ? `Message ${selectedAgent.name}... (@ to mention)`
                    : '/help'
            }
            className="flex-1 bg-transparent text-sm text-[var(--text-primary)] outline-none placeholder:text-[var(--text-muted)]"
            disabled={sending || !agentsLoaded}
            autoFocus
          />

          {/* Emoji picker */}
          <div className="relative" ref={emojiRef}>
            <button
              onClick={() => setShowEmojiPicker(!showEmojiPicker)}
              disabled={sending}
              className="rounded p-1 text-[var(--text-muted)] hover:text-yellow-400 disabled:opacity-30"
            >
              <Smile className="h-4 w-4" />
            </button>
            {showEmojiPicker && (
              <div className="absolute bottom-full right-0 mb-2 w-72 max-h-64 overflow-auto rounded-lg border border-[var(--border-default)] bg-[var(--bg-surface)] shadow-xl p-2 z-50">
                {Object.entries(EMOJI_CATEGORIES).map(([cat, emojis]) => (
                  <div key={cat}>
                    <div className="text-[10px] font-semibold text-[var(--text-muted)] uppercase px-1 py-1">{cat}</div>
                    <div className="flex flex-wrap gap-0.5 mb-1">
                      {emojis.map((e) => (
                        <button
                          key={e}
                          onClick={() => insertEmoji(e)}
                          className="rounded p-1 text-base hover:bg-[var(--bg-hover)]"
                        >
                          {e}
                        </button>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          <button
            onClick={handleSend}
            disabled={(!input.trim() && attachments.length === 0) || sending}
            className="rounded p-1.5 text-amber-400 hover:bg-amber-500/20 disabled:opacity-30"
          >
            <Send className="h-4 w-4" />
          </button>
        </div>
      </div>
    </>
  );
}
