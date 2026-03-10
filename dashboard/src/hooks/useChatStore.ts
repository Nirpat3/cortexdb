/**
 * Central chat state — Zustand store.
 *
 * Replaces 40+ useState hooks with a single, predictable store.
 * Components subscribe to slices they need, avoiding full re-renders.
 */
import { create } from 'zustand';
import type { AgentOption, ChatSession, ChatGroup, ToolPerms, ToolCallEntry, ModelOption, ProviderHealth } from '@/lib/api';

/* ── Types ── */

export interface FileAttachment {
  name: string;
  size: number;
  type: string;
  dataUrl?: string;
  content?: string;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  agentId?: string;
  agentName?: string;
  model?: string;
  tokens?: { input: number; output: number };
  toolCalls?: ToolCallEntry[];
  attachments?: FileAttachment[];
  timestamp: Date;
  isSystem?: boolean;
}

/* ── Store ── */

interface ChatState {
  // Agents
  agents: AgentOption[];
  selectedAgent: AgentOption | null;
  agentsLoaded: boolean;

  // Messages
  messages: ChatMessage[];
  sending: boolean;
  streamingText: string;
  streamingToolCalls: ToolCallEntry[];

  // Permissions (client-side HINTS — server enforces)
  perms: ToolPerms;

  // Models
  models: ModelOption[];
  providerHealth: Record<string, ProviderHealth>;
  selectedModel: string;

  // Sessions / sidebar
  sessions: ChatSession[];
  groups: ChatGroup[];
  activeSessionId: string | null;
  condensedSummary: string | null;

  // Input
  input: string;
  attachments: FileAttachment[];
  cliMode: boolean;

  // UI
  sidebarOpen: boolean;
  showSettingsPanel: boolean;

  // Actions
  setAgents: (agents: AgentOption[]) => void;
  setSelectedAgent: (agent: AgentOption | null) => void;
  setAgentsLoaded: (v: boolean) => void;
  setMessages: (msgs: ChatMessage[] | ((prev: ChatMessage[]) => ChatMessage[])) => void;
  addMessage: (msg: ChatMessage) => void;
  addSystemMessage: (content: string) => void;
  clearMessages: () => void;
  setSending: (v: boolean) => void;
  setStreamingText: (v: string) => void;
  setStreamingToolCalls: (v: ToolCallEntry[] | ((prev: ToolCallEntry[]) => ToolCallEntry[])) => void;
  setPerms: (perms: ToolPerms | ((prev: ToolPerms) => ToolPerms)) => void;
  setModels: (models: ModelOption[]) => void;
  setProviderHealth: (h: Record<string, ProviderHealth>) => void;
  setSelectedModel: (m: string) => void;
  setSessions: (s: ChatSession[]) => void;
  setGroups: (g: ChatGroup[]) => void;
  setActiveSessionId: (id: string | null) => void;
  setCondensedSummary: (s: string | null) => void;
  setInput: (v: string) => void;
  setAttachments: (a: FileAttachment[] | ((prev: FileAttachment[]) => FileAttachment[])) => void;
  setCliMode: (v: boolean) => void;
  setSidebarOpen: (v: boolean) => void;
  setShowSettingsPanel: (v: boolean) => void;
}

export const useChatStore = create<ChatState>((set) => ({
  agents: [],
  selectedAgent: null,
  agentsLoaded: false,
  messages: [],
  sending: false,
  streamingText: '',
  streamingToolCalls: [],
  perms: { read: true, write: false, exec: false, network: false },
  models: [],
  providerHealth: {},
  selectedModel: '',
  sessions: [],
  groups: [],
  activeSessionId: null,
  condensedSummary: null,
  input: '',
  attachments: [],
  cliMode: false,
  sidebarOpen: true,
  showSettingsPanel: false,

  setAgents: (agents) => set({ agents }),
  setSelectedAgent: (agent) => set({ selectedAgent: agent }),
  setAgentsLoaded: (v) => set({ agentsLoaded: v }),
  setMessages: (msgs) =>
    set((s) => ({ messages: typeof msgs === 'function' ? msgs(s.messages) : msgs })),
  addMessage: (msg) => set((s) => ({ messages: [...s.messages, msg] })),
  addSystemMessage: (content) =>
    set((s) => ({
      messages: [
        ...s.messages,
        { id: `sys-${Date.now()}`, role: 'assistant', content, agentName: 'SYSTEM', timestamp: new Date(), isSystem: true },
      ],
    })),
  clearMessages: () => set({ messages: [], condensedSummary: null }),
  setSending: (v) => set({ sending: v }),
  setStreamingText: (v) => set({ streamingText: v }),
  setStreamingToolCalls: (v) =>
    set((s) => ({ streamingToolCalls: typeof v === 'function' ? v(s.streamingToolCalls) : v })),
  setPerms: (perms) =>
    set((s) => ({ perms: typeof perms === 'function' ? perms(s.perms) : perms })),
  setModels: (models) => set({ models }),
  setProviderHealth: (h) => set({ providerHealth: h }),
  setSelectedModel: (m) => set({ selectedModel: m }),
  setSessions: (s) => set({ sessions: s }),
  setGroups: (g) => set({ groups: g }),
  setActiveSessionId: (id) => set({ activeSessionId: id }),
  setCondensedSummary: (s) => set({ condensedSummary: s }),
  setInput: (v) => set({ input: v }),
  setAttachments: (a) =>
    set((s) => ({ attachments: typeof a === 'function' ? a(s.attachments) : a })),
  setCliMode: (v) => set({ cliMode: v }),
  setSidebarOpen: (v) => set({ sidebarOpen: v }),
  setShowSettingsPanel: (v) => set({ showSettingsPanel: v }),
}));
