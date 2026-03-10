/**
 * @-mention autocomplete hook.
 *
 * Tracks the mention query from input text, filters agents,
 * and provides navigation + insertion helpers.
 */
import { useState, useMemo, useCallback } from 'react';
import { useChatStore } from './useChatStore';

export function useMentions() {
  const { agents, input, setInput } = useChatStore();
  const [mentionQuery, setMentionQuery] = useState<string | null>(null);
  const [mentionIdx, setMentionIdx] = useState(0);
  const [mentionStart, setMentionStart] = useState(-1);

  const results = useMemo(() => {
    if (mentionQuery === null) return [];
    const q = mentionQuery.toLowerCase();
    return agents
      .filter((a) => a.name.toLowerCase().includes(q) || a.agent_id.toLowerCase().includes(q))
      .slice(0, 8);
  }, [mentionQuery, agents]);

  /** Call on every input change to detect @-trigger */
  const updateFromInput = useCallback((value: string, cursorPos: number) => {
    const before = value.slice(0, cursorPos);
    const match = before.match(/@(\w*)$/);
    if (match) {
      setMentionQuery(match[1]);
      setMentionStart(match.index!);
      setMentionIdx(0);
    } else {
      setMentionQuery(null);
    }
  }, []);

  /** Insert selected mention into input */
  const insertMention = useCallback(
    (agentName: string) => {
      const before = input.slice(0, mentionStart);
      const after = input.slice(mentionStart + 1 + (mentionQuery?.length || 0));
      setInput(`${before}@${agentName} ${after}`);
      setMentionQuery(null);
    },
    [input, mentionStart, mentionQuery, setInput],
  );

  const dismiss = useCallback(() => setMentionQuery(null), []);

  return {
    mentionQuery,
    mentionIdx,
    setMentionIdx,
    results,
    isActive: mentionQuery !== null && results.length > 0,
    updateFromInput,
    insertMention,
    dismiss,
  };
}
