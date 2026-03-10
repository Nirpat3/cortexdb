/**
 * Session management: create, delete, pin, group, condense, export.
 */
import { useCallback } from 'react';
import { useChatStore } from './useChatStore';
import { useSidebarLoader } from './useChatInit';
import * as api from '@/lib/api';
import { toast } from '@/lib/toast';

export function useChatSessions() {
  const store = useChatStore();
  const loadSidebar = useSidebarLoader();

  const startNewChat = useCallback(async () => {
    const { selectedAgent } = useChatStore.getState();
    if (!selectedAgent) return;

    try {
      const session = await api.createChatSession(selectedAgent.agent_id, `Chat with ${selectedAgent.name}`);
      store.setActiveSessionId(session.id);
      store.clearMessages();
      loadSidebar();
    } catch (err) {
      toast.apiError('Create session', err);
      store.clearMessages();
    }
  }, []);

  const selectSession = useCallback((session: api.ChatSession) => {
    const { agents } = useChatStore.getState();
    const agent = agents.find((a) => a.agent_id === session.agent_id);
    if (agent) store.setSelectedAgent(agent);
    store.setActiveSessionId(session.id);
  }, []);

  const deleteSession = useCallback(async (sessionId: string) => {
    try {
      await api.deleteChatSession(sessionId);
      const { activeSessionId } = useChatStore.getState();
      if (activeSessionId === sessionId) {
        store.setActiveSessionId(null);
        store.clearMessages();
      }
      loadSidebar();
      toast.success('Session deleted');
    } catch (err) {
      toast.apiError('Delete session', err);
    }
  }, []);

  const togglePin = useCallback(async (session: api.ChatSession) => {
    try {
      await api.pinSession(session.id, !session.pinned);
      loadSidebar();
    } catch (err) {
      toast.apiError('Pin session', err);
    }
  }, []);

  const condense = useCallback(async () => {
    const { activeSessionId, selectedAgent } = useChatStore.getState();
    if (!activeSessionId) return;

    try {
      const result = (await api.condenseSession(activeSessionId)) as any;
      store.setCondensedSummary(result.summary);

      if (selectedAgent) {
        const data = await api.getChatHistory(selectedAgent.agent_id, 50);
        const msgs = (data.messages || []).map((m: any) => ({
          id: m.id || `h-${crypto.randomUUID()}`,
          role: m.role as 'user' | 'assistant',
          content: m.content,
          agentName: m.role === 'assistant' ? selectedAgent.name : undefined,
          timestamp: new Date(m.created_at),
        }));
        store.setMessages(msgs);
      }

      store.addSystemMessage(`Conversation condensed: ${result.condensedCount} messages summarized.`);
    } catch (err: any) {
      if (!err.message?.includes('Not enough')) {
        toast.apiError('Condense', err);
      }
    }
  }, []);

  const moveToGroup = useCallback(async (sessionId: string, groupId: string | null) => {
    try {
      await api.moveSessionToGroup(sessionId, groupId);
      loadSidebar();
    } catch (err) {
      toast.apiError('Move session', err);
    }
  }, []);

  const createGroup = useCallback(async (name: string, color: string) => {
    try {
      await api.createChatGroup(name, color);
      loadSidebar();
    } catch (err) {
      toast.apiError('Create group', err);
    }
  }, []);

  const exportChat = useCallback(async () => {
    const { selectedAgent } = useChatStore.getState();
    if (!selectedAgent) return;

    try {
      const md = await api.exportChat(selectedAgent.agent_id);
      const blob = new Blob([md], { type: 'text/markdown' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `chat-${selectedAgent.agent_id}-${Date.now()}.md`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      toast.apiError('Export chat', err);
    }
  }, []);

  return {
    startNewChat,
    selectSession,
    deleteSession,
    togglePin,
    condense,
    moveToGroup,
    createGroup,
    exportChat,
    loadSidebar,
  };
}
