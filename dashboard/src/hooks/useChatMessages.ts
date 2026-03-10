/**
 * Message loading, streaming, and persistence logic.
 *
 * Extracted from the god component to keep message concerns isolated.
 */
import { useCallback, useEffect, useRef } from 'react';
import { useChatStore } from './useChatStore';
import type { FileAttachment, ChatMessage } from './useChatStore';
import * as api from '@/lib/api';
import { toast } from '@/lib/toast';

/** Load chat history when agent or session changes */
export function useMessageLoader() {
  const {
    selectedAgent, activeSessionId, sessions,
    setMessages, setCondensedSummary, setPerms,
  } = useChatStore();

  useEffect(() => {
    if (!selectedAgent) return;

    api.getChatHistory(selectedAgent.agent_id, 50)
      .then((data) => {
        const msgs: ChatMessage[] = (data.messages || []).map((m: any) => ({
          id: m.id || `h-${crypto.randomUUID()}`,
          role: m.role as 'user' | 'assistant',
          content: m.content,
          agentName: m.role === 'assistant' ? selectedAgent.name : undefined,
          tokens:
            m.tokens_input || m.tokens_output
              ? { input: m.tokens_input || 0, output: m.tokens_output || 0 }
              : undefined,
          toolCalls: m.tool_calls
            ? typeof m.tool_calls === 'string'
              ? JSON.parse(m.tool_calls)
              : m.tool_calls
            : undefined,
          timestamp: new Date(m.created_at),
        }));
        setMessages(msgs);

        // Restore condensed summary from session
        if (activeSessionId) {
          const session = sessions.find((s) => s.id === activeSessionId);
          setCondensedSummary(session?.summary || null);
        }
      })
      .catch((err) => toast.apiError('Load chat history', err));

    api.getAgentChatPermissions(selectedAgent.agent_id)
      .then((data) => setPerms(data))
      .catch(() => {}); // fallback defaults are fine
  }, [selectedAgent?.agent_id, activeSessionId]);
}

/** Debounced persistence of recent messages */
export function useMessagePersistence() {
  const { selectedAgent, messages } = useChatStore();
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!selectedAgent || messages.length === 0) return;

    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => {
      const persistable = messages.filter((m) => !m.isSystem);
      if (persistable.length === 0) return;

      // Persist all messages, not just last 10
      api.persistChatMessages(
        selectedAgent.agent_id,
        persistable.map((m) => ({
          role: m.role,
          content: m.content,
          agentName: m.agentName,
          model: m.model,
          tokensInput: m.tokens?.input,
          tokensOutput: m.tokens?.output,
          toolCalls: m.toolCalls,
          timestamp: m.timestamp.toISOString(),
        })),
      ).catch((err) => toast.apiError('Save messages', err));
    }, 3000);

    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [messages, selectedAgent?.agent_id]);
}

/** Streaming send handler */
export function useSendMessage() {
  const store = useChatStore();

  const sendStreaming = useCallback(
    async (text: string, files?: FileAttachment[]) => {
      const { selectedAgent, agents, perms, selectedModel, condensedSummary, messages } =
        useChatStore.getState();

      if (!selectedAgent) {
        store.addSystemMessage('No agent selected.');
        return;
      }

      // Detect @mentions and build delegation hint
      const mentions = [...text.matchAll(/@([\w\s-]+?)(?=\s|$|,)/g)].map((m) => m[1].trim());
      const mentionedAgents = mentions
        .map((n) => agents.find((a) => a.name.toLowerCase() === n.toLowerCase()))
        .filter(Boolean) as api.AgentOption[];

      let augmented = text;
      if (mentionedAgents.length > 0) {
        augmented += `\n\n[SYSTEM: Delegate to these agents using delegate_task:\n${mentionedAgents.map((a) => `- ${a.name} (${a.agent_id})`).join('\n')}]`;
      }

      // Add user message
      store.addMessage({
        id: `u-${Date.now()}`,
        role: 'user',
        content: text,
        attachments: files?.length ? files : undefined,
        timestamp: new Date(),
      });
      store.setSending(true);
      store.setStreamingText('');
      store.setStreamingToolCalls([]);

      try {
        // Build history with condensed summary
        const history = messages
          .filter((m) => m.role === 'user' || (m.role === 'assistant' && !m.isSystem))
          .slice(-10)
          .map((m) => ({ role: m.role, content: m.content }));

        if (condensedSummary) {
          history.unshift({ role: 'user', content: `[Previous conversation summary]:\n${condensedSummary}` });
          history.unshift({ role: 'assistant', content: 'I remember our previous conversation. How can I continue helping you?' });
        }

        const response = await api.chatWithAgentStream({
          agentId: selectedAgent.agent_id,
          message: augmented,
          ...(selectedModel ? { modelOverride: selectedModel } : {}),
          history,
          toolPermissions: perms,
        });

        if (!response.ok) {
          const errBody = await response.json().catch(() => ({ error: response.statusText }));
          store.addSystemMessage(`Error: ${errBody.error || errBody.message || response.statusText}`);
          store.setSending(false);
          return;
        }

        const reader = response.body?.getReader();
        if (!reader) {
          store.addSystemMessage('No response stream');
          store.setSending(false);
          return;
        }

        const decoder = new TextDecoder();
        let buffer = '';
        let agentName = '';
        let model = '';
        let tokens = { input: 0, output: 0 };
        let accText = '';
        const accToolCalls: api.ToolCallEntry[] = [];
        const pendingCalls: Record<string, { tool: string; input: Record<string, unknown> }> = {};

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() || '';

          for (const line of lines) {
            if (!line.startsWith('data: ')) continue;
            let d: any;
            try { d = JSON.parse(line.slice(6)); } catch { continue; }

            if (d.agentName !== undefined && d.model !== undefined) {
              agentName = d.agentName;
              model = d.model;
            } else if (d.content !== undefined && d.tokens === undefined) {
              accText += d.content;
              store.setStreamingText(accText);
            } else if (d.tool !== undefined && d.id !== undefined && d.result === undefined) {
              pendingCalls[d.id] = { tool: d.tool, input: d.input };
              store.setStreamingToolCalls((prev) => [
                ...prev,
                { tool: d.tool, input: d.input, result: { status: 'running...' }, durationMs: 0 },
              ]);
            } else if (d.tool !== undefined && d.result !== undefined) {
              accToolCalls.push({
                tool: d.tool,
                input: pendingCalls[d.id]?.input ?? {},
                result: d.result,
                durationMs: d.durationMs ?? 0,
              });
              store.setStreamingToolCalls([...accToolCalls]);
            } else if (d.tokens !== undefined) {
              tokens = d.tokens;
            } else if (d.message !== undefined && d.tokens === undefined) {
              accText += `\n[Error: ${d.message}]`;
              store.setStreamingText(accText);
            }
          }
        }

        // Finalize assistant message
        store.addMessage({
          id: `a-${Date.now()}`,
          role: 'assistant',
          content: accText,
          agentName,
          model,
          tokens,
          toolCalls: accToolCalls.length > 0 ? accToolCalls : undefined,
          timestamp: new Date(),
        });
        store.setStreamingText('');
        store.setStreamingToolCalls([]);
      } catch (err: any) {
        store.addSystemMessage(`Error: ${err.message || 'Stream failed'}`);
      } finally {
        store.setSending(false);
      }
    },
    [],
  );

  return sendStreaming;
}
