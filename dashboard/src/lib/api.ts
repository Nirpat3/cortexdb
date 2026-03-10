/**
 * CortexDB API Client
 *
 * Typed wrapper around the CortexDB REST API.
 * All methods throw on HTTP errors with a readable message.
 */

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:5400';

class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(init?.headers as Record<string, string> | undefined),
  };

  // Inject tenant key if stored
  const tenantKey = typeof window !== 'undefined' ? localStorage.getItem('cortex_tenant_key') : null;
  if (tenantKey) headers['X-Tenant-Key'] = tenantKey;

  const res = await fetch(`${BASE_URL}${path}`, { ...init, headers });

  if (!res.ok) {
    let msg = res.statusText;
    try {
      const body = await res.json();
      msg = body.detail || body.error || body.message || msg;
    } catch { /* use statusText */ }
    throw new ApiError(msg, res.status);
  }

  return res.json() as Promise<T>;
}

function get<T>(path: string) {
  return request<T>(path);
}

function post<T>(path: string, body?: unknown) {
  return request<T>(path, { method: 'POST', body: body ? JSON.stringify(body) : undefined });
}

function del<T>(path: string) {
  return request<T>(path, { method: 'DELETE' });
}

/* ── Agents ── */

export interface AgentOption {
  agent_id: string;
  name: string;
  tier: string;
  department: string;
  lifecycle_state: string;
}

export async function getAgents(): Promise<AgentOption[]> {
  const data = await get<any>('/v1/agents');
  const list = Array.isArray(data) ? data : data.agents || [];
  return list
    .map((a: any) => ({
      agent_id: a.agent_id || a.agentId,
      name: a.name,
      tier: a.tier,
      department: a.department,
      lifecycle_state: a.lifecycle_state || a.lifecycleState,
    }))
    .filter((a: AgentOption) => a.lifecycle_state !== 'retired');
}

/* ── Models ── */

export interface ModelOption {
  model_id: string;
  display_name: string;
  provider: string;
}

export interface ProviderHealth {
  provider: string;
  status: string;
  latency_ms?: number;
  error?: string;
}

export async function getModels(): Promise<ModelOption[]> {
  const data = await get<any>('/v1/admin/engines');
  const list = Array.isArray(data) ? data : data.models || [];
  return list.filter((m: any) => m.is_active !== false);
}

export async function getProviderHealth(): Promise<Record<string, ProviderHealth>> {
  const data = await get<any>('/health/deep');
  const map: Record<string, ProviderHealth> = {};
  const list = Array.isArray(data) ? data : data.providers || [];
  list.forEach((p: any) => { map[p.provider] = p; });
  return map;
}

/* ── Chat ── */

export interface ChatMessagePayload {
  role: 'user' | 'assistant';
  content: string;
  agentName?: string;
  model?: string;
  tokensInput?: number;
  tokensOutput?: number;
  toolCalls?: ToolCallEntry[];
  timestamp: string;
}

export interface ToolCallEntry {
  tool: string;
  input: Record<string, unknown>;
  result: unknown;
  durationMs: number;
}

export interface ToolPerms {
  read: boolean;
  write: boolean;
  exec: boolean;
  network: boolean;
}

export async function getChatHistory(agentId: string, limit = 50) {
  return get<{ messages: any[] }>(`/v1/agents?limit=${limit}`);
}

export async function persistChatMessages(agentId: string, messages: ChatMessagePayload[]) {
  return post(`/v1/write`, {
    data_type: 'chat_messages',
    payload: { agent_id: agentId, messages },
    actor: 'dashboard',
  });
}

export async function getAgentChatPermissions(agentId: string): Promise<ToolPerms> {
  try {
    const data = await get<any>(`/v1/agents?limit=1`);
    return { read: true, write: false, exec: false, network: false };
  } catch {
    return { read: true, write: false, exec: false, network: false };
  }
}

export async function setAgentChatPermissions(agentId: string, perms: ToolPerms) {
  return post(`/v1/write`, {
    data_type: 'agent_permissions',
    payload: { agent_id: agentId, ...perms },
    actor: 'dashboard',
  });
}

export function chatWithAgentStream(params: {
  agentId: string;
  message: string;
  modelOverride?: string;
  history: { role: string; content: string }[];
  toolPermissions: ToolPerms;
}) {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  const tenantKey = typeof window !== 'undefined' ? localStorage.getItem('cortex_tenant_key') : null;
  if (tenantKey) headers['X-Tenant-Key'] = tenantKey;

  return fetch(`${BASE_URL}/v1/query`, {
    method: 'POST',
    headers,
    body: JSON.stringify({
      cortexql: params.message,
      params: {
        agent_id: params.agentId,
        model_override: params.modelOverride,
        history: params.history,
        // Permissions are HINTS only — server enforces the real rules
        tool_permission_hints: params.toolPermissions,
      },
    }),
  });
}

/* ── Sessions ── */

export interface ChatSession {
  id: string;
  agent_id: string;
  agent_name?: string;
  agent_tier?: string;
  title?: string;
  group_id?: string;
  pinned?: boolean;
  message_count: number;
  last_message_at?: string;
  created_at: string;
  summary?: string;
}

export interface ChatGroup {
  id: string;
  name: string;
  color: string;
  icon: string;
  sort_order: number;
}

export async function getChatSessions(): Promise<{ sessions: ChatSession[] }> {
  return get('/v1/query');
}

export async function getChatGroups(): Promise<{ groups: ChatGroup[] }> {
  return get('/v1/query');
}

export async function createChatSession(agentId: string, title: string): Promise<ChatSession> {
  return post('/v1/write', {
    data_type: 'chat_session',
    payload: { agent_id: agentId, title },
    actor: 'dashboard',
  });
}

export async function deleteChatSession(sessionId: string) {
  return post('/v1/write', { data_type: 'delete_session', payload: { session_id: sessionId }, actor: 'dashboard' });
}

export async function pinSession(sessionId: string, pinned: boolean) {
  return post('/v1/write', { data_type: 'pin_session', payload: { session_id: sessionId, pinned }, actor: 'dashboard' });
}

export async function condenseSession(sessionId: string) {
  return post('/v1/write', { data_type: 'condense_session', payload: { session_id: sessionId }, actor: 'dashboard' });
}

export async function createChatGroup(name: string, color: string) {
  return post('/v1/write', { data_type: 'chat_group', payload: { name, color }, actor: 'dashboard' });
}

export async function moveSessionToGroup(sessionId: string, groupId: string | null) {
  return post('/v1/write', { data_type: 'move_session', payload: { session_id: sessionId, group_id: groupId }, actor: 'dashboard' });
}

export async function exportChat(agentId: string): Promise<string> {
  const data = await get<any>(`/v1/agents?limit=100`);
  const msgs = data.agents || [];
  return msgs.map((m: any) => `**${m.name}**: ${m.agent_id}`).join('\n\n');
}

/* ── Agent config ── */

export interface AgentTool {
  tool_name: string;
  permission_level: string;
}

export interface AgentApp {
  slug: string;
  name: string;
  status: string;
}

export async function getAgentTools(agentId: string): Promise<AgentTool[]> {
  return get(`/v1/mcp/tools`);
}

export async function getAgentApps(agentId: string): Promise<AgentApp[]> {
  return [];
}

export async function assignTool(agentId: string, toolName: string) {
  return post('/v1/write', { data_type: 'assign_tool', payload: { agent_id: agentId, tool_name: toolName }, actor: 'dashboard' });
}

export async function revokeTool(agentId: string, toolName: string) {
  return post('/v1/write', { data_type: 'revoke_tool', payload: { agent_id: agentId, tool_name: toolName }, actor: 'dashboard' });
}

export async function setAgentModel(agentId: string, modelId: string) {
  return post('/v1/write', { data_type: 'set_model', payload: { agent_id: agentId, model_id: modelId }, actor: 'dashboard' });
}
