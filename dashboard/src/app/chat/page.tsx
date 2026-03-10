'use client';

/**
 * Chat Page — Composition Root
 *
 * All logic lives in hooks and sub-components.
 * This file is ~50 lines — layout shell only.
 *
 * Architecture (from CTO critique):
 *   hooks/
 *     useChatStore.ts       — Zustand store (replaces 40+ useState)
 *     useChatInit.ts        — Load agents, models, sidebar on mount
 *     useChatMessages.ts    — History, streaming, persistence
 *     useChatSessions.ts    — Session CRUD, pin, group, condense
 *     useCommands.ts        — Slash command dispatch
 *     useMentions.ts        — @-mention autocomplete
 *   components/chat/
 *     ChatSidebar.tsx        — Session list, groups, pins
 *     ChatHeader.tsx         — Agent picker, model picker, actions
 *     PermissionsBar.tsx     — Tool permission hint toggles
 *     SettingsPanel.tsx      — Tools, model, apps config
 *     MessageList.tsx        — Message rendering + streaming
 *     ChatInput.tsx          — Input bar, attachments, emoji, mentions
 *     MessageBubble.tsx      — Single message (user/assistant)
 *     ToolCallBlock.tsx      — Expandable tool call
 *     PermToggle.tsx         — Permission toggle button
 *
 * Security fixes applied:
 *   - Permissions are HINTS only — labeled as such, no auto-escalation
 *   - File attachments validated before reading (10MB limit)
 *   - All .catch(() => {}) replaced with toast notifications
 *   - Auto-condense removed (was triggering on history load)
 */

import { Toaster } from 'sonner';
import { useChatStore } from '@/hooks/useChatStore';
import { useChatInit } from '@/hooks/useChatInit';
import { useMessageLoader, useMessagePersistence, useSendMessage } from '@/hooks/useChatMessages';
import { useCommands } from '@/hooks/useCommands';
import { ChatSidebar } from '@/components/chat/ChatSidebar';
import { ChatHeader } from '@/components/chat/ChatHeader';
import { PermissionsBar } from '@/components/chat/PermissionsBar';
import { SettingsPanel } from '@/components/chat/SettingsPanel';
import { MessageList } from '@/components/chat/MessageList';
import { ChatInput } from '@/components/chat/ChatInput';

export default function ChatPage() {
  const { sidebarOpen } = useChatStore();

  // Initialize data on mount
  useChatInit();
  useMessageLoader();
  useMessagePersistence();

  // Wire up send + command handlers
  const sendStreaming = useSendMessage();
  const handleCommand = useCommands(sendStreaming);

  return (
    <>
      <Toaster position="top-right" theme="dark" richColors />
      <div className="flex h-[calc(100vh-8rem)]">
        {sidebarOpen && <ChatSidebar />}

        <div className="flex-1 flex flex-col min-w-0">
          <ChatHeader />
          <PermissionsBar />
          <SettingsPanel />
          <MessageList />
          <ChatInput onSend={sendStreaming} onCommand={handleCommand} />
        </div>
      </div>
    </>
  );
}
