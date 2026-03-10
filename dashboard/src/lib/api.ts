/**
 * CortexDB API Client
 *
 * AI Agent Data Infrastructure — typed wrapper around the CortexDB REST API.
 */

const BASE_URL = '/api';

class APIError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = 'APIError';
  }
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    ...options,
  });

  if (!res.ok) {
    const text = await res.text().catch(() => 'Unknown error');
    throw new APIError(res.status, text);
  }

  return res.json();
}

export const api = {
  // Health
  healthLive: () => request<{ status: string; timestamp: number }>('/health/live'),
  healthReady: () => request<{ status: string; engines: Record<string, string> }>('/health/ready'),
  healthDeep: () => request<Record<string, unknown>>('/health/deep'),

  // Engines
  getEngines: () => request<Record<string, unknown>>('/admin/engines'),

  // CortexGraph
  cortexGraphStats: () => request<Record<string, unknown>>('/v1/cortexgraph/stats'),
  customer360: (id: string) => request<Record<string, unknown>>(`/v1/cortexgraph/customer/${id}/360`),
  customerProfile: (id: string) => request<Record<string, unknown>>(`/v1/cortexgraph/customer/${id}/profile`),
  churnRisk: (threshold?: number) => request<unknown[]>(`/v1/cortexgraph/churn-risk${threshold ? `?threshold=${threshold}` : ''}`),
  similarCustomers: (id: string) => request<unknown[]>(`/v1/cortexgraph/similar/${id}`),

  // Compliance
  complianceAudit: (framework?: string) => request<Record<string, unknown>>(`/v1/compliance/audit${framework ? `/${framework}` : ''}`),
  complianceSummary: () => request<Record<string, unknown>>('/v1/compliance/summary'),
  auditLog: (params?: Record<string, string>) => {
    const qs = params ? '?' + new URLSearchParams(params).toString() : '';
    return request<unknown[]>(`/v1/compliance/audit-log${qs}`);
  },
  encryptionStats: () => request<Record<string, unknown>>('/v1/compliance/encryption/stats'),
  rotateKeys: () => request<Record<string, unknown>>('/v1/compliance/encryption/rotate-keys', { method: 'POST' }),

  // Scale
  shardingStats: () => request<Record<string, unknown>>('/v1/admin/sharding/stats'),
  rebalanceShards: () => request<Record<string, unknown>>('/v1/admin/sharding/rebalance', { method: 'POST' }),
  replicaStats: () => request<Record<string, unknown>>('/v1/admin/replicas/stats'),
  replicaLag: () => request<Record<string, unknown>>('/v1/admin/replicas/lag'),
  indexRecommendations: () => request<unknown[]>('/v1/admin/indexes/recommend'),

  // Grid
  gridNodes: (state?: string) => request<unknown[]>(`/v1/grid/nodes${state ? `?state=${state}` : ''}`),
  gridHealthScores: () => request<Record<string, unknown>>('/v1/grid/health-scores'),
  gridCemetery: () => request<unknown[]>('/v1/grid/cemetery'),
  gridResurrections: () => request<unknown[]>('/v1/grid/resurrections'),

  // Heartbeat
  heartbeatStatus: () => request<Record<string, unknown>>('/v1/heartbeat/status'),
  circuitBreakers: () => request<Record<string, unknown>>('/v1/heartbeat/circuit-breakers'),
  healthHistory: () => request<unknown[]>('/v1/heartbeat/health-history'),

  // MCP
  mcpTools: () => request<unknown[]>('/v1/mcp/tools'),
  mcpCall: (tool: string, input: Record<string, unknown>) =>
    request<Record<string, unknown>>('/v1/mcp/call', {
      method: 'POST',
      body: JSON.stringify({ tool, input }),
    }),

  // Query
  query: (cortexql: string, params?: Record<string, unknown>) =>
    request<Record<string, unknown>>('/v1/query', {
      method: 'POST',
      body: JSON.stringify({ cortexql, params }),
    }),

  // Write
  write: (data_type: string, payload: Record<string, unknown>, actor: string) =>
    request<Record<string, unknown>>('/v1/write', {
      method: 'POST',
      body: JSON.stringify({ data_type, payload, actor }),
    }),

  // Benchmark
  runBenchmark: (suite: string, concurrency: number, iterations: number) =>
    request<Record<string, unknown>>('/v1/admin/benchmark/run', {
      method: 'POST',
      body: JSON.stringify({ suite, concurrency, iterations }),
    }),
  runStress: (pattern: string, duration: number, rps: number) =>
    request<Record<string, unknown>>('/v1/admin/benchmark/stress', {
      method: 'POST',
      body: JSON.stringify({ pattern, duration_seconds: duration, requests_per_second: rps }),
    }),

  // Cache
  cacheStats: () => request<Record<string, unknown>>('/v1/admin/cache/stats'),

  // Budget
  budgetSummary: () => request<Record<string, unknown>>('/v1/budget/summary'),
  budgetResources: () => request<Record<string, unknown>>('/v1/budget/resources'),
  budgetTenants: () => request<Record<string, unknown>>('/v1/budget/tenants'),
  budgetMonthly: () => request<Record<string, unknown>>('/v1/budget/monthly'),
  budgetHistory: (resource?: string, days?: number) => {
    const params = new URLSearchParams();
    if (resource) params.set('resource', resource);
    if (days) params.set('days', String(days));
    const qs = params.toString();
    return request<Record<string, unknown>>(`/v1/budget/history${qs ? `?${qs}` : ''}`);
  },
  setBudget: (resource: string, allocated: number) =>
    request<Record<string, unknown>>(`/v1/budget/resources/${resource}`, {
      method: 'POST',
      body: JSON.stringify({ allocated }),
    }),

  // Forecasting
  runForecast: () => request<Record<string, unknown>>('/v1/forecast/run', { method: 'POST' }),
  latestForecast: () => request<Record<string, unknown>>('/v1/forecast/latest'),
  resourceForecast: (resource: string) => request<Record<string, unknown>>(`/v1/forecast/resource/${resource}`),

  // Tenants (real API)
  getTenants: () => request<Record<string, unknown>>('/v1/admin/tenants'),
  getTenant: (id: string) => request<Record<string, unknown>>(`/v1/admin/tenants/${id}`),

  // ASA / Standards
  getStandards: () => request<Record<string, unknown>>('/v1/asa/standards'),
  getViolations: () => request<Record<string, unknown>>('/v1/asa/violations'),

  // Audit trail
  auditLogStats: () => request<Record<string, unknown>>('/v1/compliance/audit-log/stats'),
  complianceEvidence: (framework: string) => request<Record<string, unknown>>(`/v1/compliance/evidence/${framework}`),

  // Agent Registry
  getAgentRegistry: () => request<Record<string, unknown>>('/v1/agents/registry'),
  getAgentDetail: (id: string) => request<Record<string, unknown>>(`/v1/agents/registry/${id}`),
  getAgentsSummary: () => request<Record<string, unknown>>('/v1/agents/summary'),

  // System Metrics Agent
  systemMetrics: () => request<Record<string, unknown>>('/v1/metrics/system'),
  systemMetricsHistory: (minutes?: number) => request<Record<string, unknown>>(`/v1/metrics/system/history${minutes ? `?minutes=${minutes}` : ''}`),
  hardwareSummary: () => request<Record<string, unknown>>('/v1/metrics/hardware'),

  // Database Monitor Agent
  dbMonitor: () => request<Record<string, unknown>>('/v1/monitor/db'),
  dbMonitorSummary: () => request<Record<string, unknown>>('/v1/monitor/db/summary'),
  dbSlowQueries: () => request<Record<string, unknown>>('/v1/monitor/db/slow-queries'),
  dbLocks: () => request<Record<string, unknown>>('/v1/monitor/db/locks'),
  dbMonitorHistory: (minutes?: number) => request<Record<string, unknown>>(`/v1/monitor/db/history${minutes ? `?minutes=${minutes}` : ''}`),
  dbPool: () => request<Record<string, unknown>>('/v1/monitor/db/pool'),

  // Service Monitor Agent
  serviceMonitor: () => request<Record<string, unknown>>('/v1/monitor/services'),
  serviceMonitorSummary: () => request<Record<string, unknown>>('/v1/monitor/services/summary'),
  serviceDetail: (name: string) => request<Record<string, unknown>>(`/v1/monitor/services/${name}`),

  // Security Agent
  securityOverview: () => request<Record<string, unknown>>('/v1/security/overview'),
  securityThreats: (severity?: string) => request<Record<string, unknown>>(`/v1/security/threats${severity ? `?severity=${severity}` : ''}`),
  securityThreatStats: () => request<Record<string, unknown>>('/v1/security/threats/stats'),
  securityAudit: () => request<Record<string, unknown>>('/v1/security/audit'),

  // Error Tracking Agent
  getErrors: (level?: string) => request<Record<string, unknown>>(`/v1/errors${level ? `?level=${level}` : ''}`),
  errorSummary: () => request<Record<string, unknown>>('/v1/errors/summary'),
  getError: (id: string) => request<Record<string, unknown>>(`/v1/errors/${id}`),
  resolveError: (id: string, resolution: string) =>
    request<Record<string, unknown>>(`/v1/errors/${id}/resolve`, {
      method: 'POST', body: JSON.stringify({ resolution }),
    }),
  errorsByService: () => request<Record<string, unknown>>('/v1/errors/by-service'),

  // Notification Agent
  getNotifications: (params?: { severity?: string; category?: string; unread_only?: boolean; limit?: number }) => {
    const qs = new URLSearchParams();
    if (params?.severity) qs.set('severity', params.severity);
    if (params?.category) qs.set('category', params.category);
    if (params?.unread_only) qs.set('unread_only', 'true');
    if (params?.limit) qs.set('limit', String(params.limit));
    const q = qs.toString();
    return request<Record<string, unknown>>(`/v1/notifications${q ? `?${q}` : ''}`);
  },
  notificationSummary: () => request<Record<string, unknown>>('/v1/notifications/summary'),
  markNotificationRead: (id: string) => request<Record<string, unknown>>(`/v1/notifications/${id}/read`, { method: 'POST' }),
  markAllNotificationsRead: () => request<Record<string, unknown>>('/v1/notifications/read-all', { method: 'POST' }),
  dismissNotification: (id: string) => request<Record<string, unknown>>(`/v1/notifications/${id}/dismiss`, { method: 'POST' }),
};

// ── SuperAdmin API (requires auth token) ──

function saRequest<T>(path: string, options?: RequestInit): Promise<T> {
  const token = typeof window !== 'undefined' ? sessionStorage.getItem('sa_token') ?? '' : '';
  return request<T>(path, {
    ...options,
    headers: { 'X-SuperAdmin-Token': token, ...options?.headers },
  });
}

export const superadminApi = {
  // Auth
  login: (passphrase: string) =>
    request<{ token: string; expires_in: number }>('/v1/superadmin/login', {
      method: 'POST', body: JSON.stringify({ passphrase }),
    }),
  logout: () => saRequest<Record<string, unknown>>('/v1/superadmin/logout', { method: 'POST' }),
  session: () => saRequest<Record<string, unknown>>('/v1/superadmin/session'),

  // Team
  getTeam: () => saRequest<Record<string, unknown>>('/v1/superadmin/team'),
  getOrgChart: () => saRequest<Record<string, unknown>>('/v1/superadmin/team/org-chart'),
  getTeamAgent: (id: string) => saRequest<Record<string, unknown>>(`/v1/superadmin/team/${id}`),
  updateTeamAgent: (id: string, data: Record<string, unknown>) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/team/${id}`, {
      method: 'PUT', body: JSON.stringify(data),
    }),
  getDepartment: (dept: string) => saRequest<Record<string, unknown>>(`/v1/superadmin/team/department/${dept}`),

  // Tasks
  createTask: (data: Record<string, unknown>) =>
    saRequest<Record<string, unknown>>('/v1/superadmin/tasks', {
      method: 'POST', body: JSON.stringify(data),
    }),
  getTasks: (status?: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/tasks${status ? `?status=${status}` : ''}`),
  getTask: (id: string) => saRequest<Record<string, unknown>>(`/v1/superadmin/tasks/${id}`),
  updateTask: (id: string, data: Record<string, unknown>) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/tasks/${id}`, {
      method: 'PUT', body: JSON.stringify(data),
    }),

  // Instructions
  sendInstruction: (data: { content: string; agent_id?: string; provider?: string; model?: string }) =>
    saRequest<Record<string, unknown>>('/v1/superadmin/instructions', {
      method: 'POST', body: JSON.stringify(data),
    }),
  getInstructions: (agentId?: string, limit?: number) => {
    const qs = new URLSearchParams();
    if (agentId) qs.set('agent_id', agentId);
    if (limit) qs.set('limit', String(limit));
    const q = qs.toString();
    return saRequest<Record<string, unknown>>(`/v1/superadmin/instructions${q ? `?${q}` : ''}`);
  },

  // LLM Providers
  getLLMProviders: () => saRequest<Record<string, unknown>>('/v1/superadmin/llm/providers'),
  configureLLM: (data: Record<string, unknown>) =>
    saRequest<Record<string, unknown>>('/v1/superadmin/llm/configure', {
      method: 'POST', body: JSON.stringify(data),
    }),
  ollamaHealth: () => saRequest<Record<string, unknown>>('/v1/superadmin/llm/ollama/health'),
  ollamaModels: () => saRequest<Record<string, unknown>>('/v1/superadmin/llm/ollama/models'),

  // Task Executor
  executeTask: (taskId: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/tasks/${taskId}/execute`, { method: 'POST' }),
  executePending: () =>
    saRequest<Record<string, unknown>>('/v1/superadmin/tasks/execute-pending', { method: 'POST' }),
  executorStatus: () => saRequest<Record<string, unknown>>('/v1/superadmin/executor/status'),

  // Agent Communication Bus
  busSend: (data: Record<string, unknown>) =>
    saRequest<Record<string, unknown>>('/v1/superadmin/bus/send', {
      method: 'POST', body: JSON.stringify(data),
    }),
  busDelegate: (data: { from_agent: string; to_agent: string; task_id: string; instructions?: string }) =>
    saRequest<Record<string, unknown>>('/v1/superadmin/bus/delegate', {
      method: 'POST', body: JSON.stringify(data),
    }),
  busEscalate: (data: { from_agent: string; to_agent: string; task_id: string; reason?: string }) =>
    saRequest<Record<string, unknown>>('/v1/superadmin/bus/escalate', {
      method: 'POST', body: JSON.stringify(data),
    }),
  busBroadcast: (data: { from_agent?: string; subject: string; content: string; department?: string }) =>
    saRequest<Record<string, unknown>>('/v1/superadmin/bus/broadcast', {
      method: 'POST', body: JSON.stringify(data),
    }),
  busInbox: (agentId: string, unread?: boolean) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/bus/inbox/${agentId}${unread ? '?unread=true' : ''}`),
  busSent: (agentId: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/bus/sent/${agentId}`),
  busThread: (messageId: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/bus/thread/${messageId}`),
  busMarkRead: (messageId: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/bus/read/${messageId}`, { method: 'POST' }),
  busStats: () => saRequest<Record<string, unknown>>('/v1/superadmin/bus/stats'),
  busMessages: (msgType?: string, limit?: number) => {
    const qs = new URLSearchParams();
    if (msgType) qs.set('msg_type', msgType);
    if (limit) qs.set('limit', String(limit));
    const q = qs.toString();
    return saRequest<Record<string, unknown>>(`/v1/superadmin/bus/messages${q ? `?${q}` : ''}`);
  },

  // Audit Log
  getAuditLog: (entityType?: string, limit?: number) => {
    const qs = new URLSearchParams();
    if (entityType) qs.set('entity_type', entityType);
    if (limit) qs.set('limit', String(limit));
    const q = qs.toString();
    return saRequest<Record<string, unknown>>(`/v1/superadmin/audit${q ? `?${q}` : ''}`);
  },

  // Unified Registry
  getUnifiedRegistry: () => saRequest<Record<string, unknown>>('/v1/superadmin/registry/all'),

  // Performance Dashboard
  getPerformance: () => saRequest<Record<string, unknown>>('/v1/superadmin/performance'),

  // Agent Memory
  getAgentMemory: (agentId: string) => saRequest<Record<string, unknown>>(`/v1/superadmin/agents/${agentId}/memory`),
  getAgentContext: (agentId: string) => saRequest<Record<string, unknown>>(`/v1/superadmin/agents/${agentId}/memory/context`),

  // Task Approval
  submitForApproval: (taskId: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/tasks/${taskId}/submit-for-approval`, { method: 'POST' }),
  approveTask: (taskId: string, autoExecute = false) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/tasks/${taskId}/approve`, {
      method: 'POST', body: JSON.stringify({ auto_execute: autoExecute }),
    }),
  rejectTask: (taskId: string, reason = '') =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/tasks/${taskId}/reject`, {
      method: 'POST', body: JSON.stringify({ reason }),
    }),

  // Pipelines
  createPipeline: (name: string, steps: Record<string, unknown>[], autoExecute = false) =>
    saRequest<Record<string, unknown>>('/v1/superadmin/pipelines', {
      method: 'POST', body: JSON.stringify({ name, steps, auto_execute: autoExecute }),
    }),

  // Migrations
  getMigrations: () => saRequest<Record<string, unknown>>('/v1/superadmin/migrations'),
  runMigrations: () => saRequest<Record<string, unknown>>('/v1/superadmin/migrations/run', { method: 'POST' }),

  // SSE Streaming Chat
  chatStream: (provider: string, messages: Array<{role: string; content: string}>,
               opts?: { system?: string; model?: string; temperature?: number }) => {
    const token = typeof window !== 'undefined' ? localStorage.getItem('sa_token') : null;
    return fetch(`${BASE_URL}/v1/superadmin/llm/chat/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ provider, messages, ...opts }),
    });
  },

  // Version Management
  getVersion: () => saRequest<Record<string, unknown>>('/v1/superadmin/version'),
  bumpVersion: (bump: string, reason: string, changes: string[]) =>
    saRequest<Record<string, unknown>>('/v1/superadmin/version/bump', {
      method: 'POST', body: JSON.stringify({ bump, reason, changes }),
    }),
  getChangelog: (limit = 10) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/version/changelog?limit=${limit}`),
  syncVersion: () =>
    saRequest<Record<string, unknown>>('/v1/superadmin/version/sync', { method: 'POST' }),

  // Learning: Outcome Analyzer
  getLearningInsights: () => saRequest<Record<string, unknown>>('/v1/superadmin/learning/insights'),
  getLearningAnalyses: (limit = 20) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/learning/analyses?limit=${limit}`),
  getLearningScores: () => saRequest<Record<string, unknown>>('/v1/superadmin/learning/scores'),
  getAgentScores: (agentId: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/learning/agents/${agentId}/scores`),
  analyzeTask: (taskId: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/learning/analyze/${taskId}`, { method: 'POST' }),

  // Learning: Model Tracker
  getModelPerformance: () => saRequest<Record<string, unknown>>('/v1/superadmin/learning/models'),
  getModelRecommendation: (category: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/learning/models/recommend/${category}`),
  getAllModelRecommendations: () =>
    saRequest<Record<string, unknown>>('/v1/superadmin/learning/models/recommendations'),

  // Learning: Prompt Evolution
  getPromptPerformance: (agentId?: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/learning/prompts/performance${agentId ? `?agent_id=${agentId}` : ''}`),
  getPromptEvolutions: (agentId?: string, limit = 20) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/learning/prompts/evolutions?limit=${limit}${agentId ? `&agent_id=${agentId}` : ''}`),
  evolvePrompt: (agentId: string, provider?: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/learning/prompts/evolve/${agentId}`, {
      method: 'POST', body: JSON.stringify(provider ? { provider } : {}),
    }),
  applyEvolution: (agentId: string, newPrompt: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/learning/prompts/apply/${agentId}`, {
      method: 'POST', body: JSON.stringify({ new_prompt: newPrompt }),
    }),
  getWeakCategories: (agentId: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/learning/prompts/weak/${agentId}`),

  // Learning: Sleep Cycle
  getSleepCycleStatus: () =>
    saRequest<Record<string, unknown>>('/v1/superadmin/learning/sleep-cycle/status'),
  triggerSleepCycle: () =>
    saRequest<Record<string, unknown>>('/v1/superadmin/learning/sleep-cycle/run', { method: 'POST' }),

  // Engine Bridge
  getBridgeStatus: () => saRequest<Record<string, unknown>>('/v1/superadmin/bridge/status'),
  bridgeRecall: (agentId: string, query: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/bridge/memory/recall/${agentId}?query=${encodeURIComponent(query)}`),
  bridgeGlobalSearch: (query: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/bridge/memory/search?query=${encodeURIComponent(query)}`),
  bridgeEvents: (lastId = '0') =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/bridge/events?last_id=${lastId}`),
  bridgeVerifyAudit: () => saRequest<Record<string, unknown>>('/v1/superadmin/bridge/audit/verify'),

  // Cost Tracking
  getCosts: () => saRequest<Record<string, unknown>>('/v1/superadmin/costs'),
  getRecentCosts: (limit = 50) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/costs/recent?limit=${limit}`),
  getAgentCosts: (agentId: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/costs/agent/${agentId}`),
  getDepartmentCosts: () => saRequest<Record<string, unknown>>('/v1/superadmin/costs/departments'),
  getPricingTable: () => saRequest<Record<string, unknown>>('/v1/superadmin/costs/pricing'),

  // Agent Chat
  chatWithAgent: (agentId: string, message: string, sessionId?: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/chat/${agentId}`, {
      method: 'POST', body: JSON.stringify({ message, session_id: sessionId }),
    }),
  streamChat: (agentId: string, message: string) =>
    fetch(`${BASE_URL}/v1/superadmin/chat/${agentId}/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${localStorage.getItem('sa_token') || ''}` },
      body: JSON.stringify({ message }),
    }),
  getChatSessions: () => saRequest<Record<string, unknown>>('/v1/superadmin/chat/sessions'),
  clearChat: (agentId: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/chat/${agentId}/clear`, { method: 'DELETE' }),

  // Multi-Agent Collaboration
  createCollabSession: (goal: string, agentIds: string[], coordinatorId?: string) =>
    saRequest<Record<string, unknown>>('/v1/superadmin/collab/sessions', {
      method: 'POST', body: JSON.stringify({ goal, agent_ids: agentIds, coordinator_id: coordinatorId }),
    }),
  runCollabRound: (sessionId: string, rounds = 1) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/collab/${sessionId}/run`, {
      method: 'POST', body: JSON.stringify({ rounds }),
    }),
  synthesizeCollab: (sessionId: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/collab/${sessionId}/synthesize`, { method: 'POST' }),
  addCollabMessage: (sessionId: string, agentId: string, message: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/collab/${sessionId}/message`, {
      method: 'POST', body: JSON.stringify({ agent_id: agentId, message }),
    }),
  listCollabSessions: (status?: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/collab/sessions${status ? `?status=${status}` : ''}`),
  getCollabSession: (sessionId: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/collab/${sessionId}`),
  closeCollabSession: (sessionId: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/collab/${sessionId}/close`, { method: 'POST' }),

  // Rate Limiting
  getRateLimits: () => saRequest<Record<string, unknown>>('/v1/superadmin/rate-limits'),
  setRateLimitBudget: (key: string, tokens: number) =>
    saRequest<Record<string, unknown>>('/v1/superadmin/rate-limits/budget', {
      method: 'POST', body: JSON.stringify({ key, tokens }),
    }),

  // Agent Tools
  getTools: () => saRequest<Record<string, unknown>>('/v1/superadmin/tools'),
  getToolLog: (agentId?: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/tools/log${agentId ? `?agent_id=${agentId}` : ''}`),

  // Workflows
  createWorkflow: (name: string, description: string, steps: any[]) =>
    saRequest<Record<string, unknown>>('/v1/superadmin/workflows', {
      method: 'POST', body: JSON.stringify({ name, description, steps }),
    }),
  executeWorkflow: (workflowId: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/workflows/${workflowId}/execute`, { method: 'POST' }),
  listWorkflows: () => saRequest<Record<string, unknown>>('/v1/superadmin/workflows'),
  getWorkflow: (workflowId: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/workflows/${workflowId}`),

  // RAG
  ragIngest: (title: string, content: string) =>
    saRequest<Record<string, unknown>>('/v1/superadmin/rag/ingest', {
      method: 'POST', body: JSON.stringify({ title, content }),
    }),
  ragRetrieve: (query: string, limit = 5) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/rag/retrieve?query=${encodeURIComponent(query)}&limit=${limit}`),
  ragDocuments: () => saRequest<Record<string, unknown>>('/v1/superadmin/rag/documents'),
  ragDelete: (docId: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/rag/documents/${docId}`, { method: 'DELETE' }),
  ragStats: () => saRequest<Record<string, unknown>>('/v1/superadmin/rag/stats'),

  // Templates
  getTemplates: () => saRequest<Record<string, unknown>>('/v1/superadmin/templates'),
  createTemplate: (data: any) =>
    saRequest<Record<string, unknown>>('/v1/superadmin/templates', {
      method: 'POST', body: JSON.stringify(data),
    }),
  spawnFromTemplate: (templateId: string, name?: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/templates/${templateId}/spawn`, {
      method: 'POST', body: JSON.stringify(name ? { name } : {}),
    }),
  cloneAgent: (agentId: string, name?: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/agents/${agentId}/clone`, {
      method: 'POST', body: JSON.stringify(name ? { name } : {}),
    }),

  // Scheduler
  getSchedulerStatus: () => saRequest<Record<string, unknown>>('/v1/superadmin/scheduler/status'),
  getScheduledJobs: (agentId?: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/scheduler/jobs${agentId ? `?agent_id=${agentId}` : ''}`),
  createScheduledJob: (agentId: string, title: string, prompt: string, interval: string, category?: string) =>
    saRequest<Record<string, unknown>>('/v1/superadmin/scheduler/jobs', {
      method: 'POST', body: JSON.stringify({ agent_id: agentId, title, prompt, interval, category }),
    }),
  updateScheduledJob: (jobId: string, updates: any) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/scheduler/jobs/${jobId}`, {
      method: 'PUT', body: JSON.stringify(updates),
    }),
  deleteScheduledJob: (jobId: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/scheduler/jobs/${jobId}`, { method: 'DELETE' }),

  // Unified Health
  getUnifiedHealth: () => saRequest<Record<string, unknown>>('/v1/superadmin/health/unified'),

  // Agent Skills
  getSkillProfile: (agentId: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/skills/${agentId}`),
  getAllSkillProfiles: () =>
    saRequest<Record<string, unknown>>('/v1/superadmin/skills'),
  getSkillCatalog: () =>
    saRequest<Record<string, unknown>>('/v1/superadmin/skills/catalog'),
  getSkillLeaderboard: (skill?: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/skills/leaderboard${skill ? `?skill=${encodeURIComponent(skill)}` : ''}`),
  getSkillHistory: (agentId: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/skills/${agentId}/history`),
  addSkill: (agentId: string, skillName: string, category?: string, level?: number) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/skills/${agentId}`, {
      method: 'POST', body: JSON.stringify({ skill_name: skillName, category, level }),
    }),
  removeSkill: (agentId: string, skillName: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/skills/${agentId}/${encodeURIComponent(skillName)}`, {
      method: 'DELETE',
    }),
  enhanceSkills: (agentId: string, category: string, grade: number, keywords?: string[]) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/skills/${agentId}/enhance`, {
      method: 'POST', body: JSON.stringify({ category, grade, keywords }),
    }),

  // Agent Reputation
  getReputation: (agentId: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/reputation/${agentId}`),
  getAllReputations: () =>
    saRequest<Record<string, unknown>>('/v1/superadmin/reputation'),
  updateReputation: (agentId: string, data: { grade?: number; delegation_success?: boolean }) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/reputation/${agentId}/update`, {
      method: 'POST', body: JSON.stringify(data),
    }),
  canDelegate: (agentId: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/reputation/${agentId}/can-delegate`),

  // Agent Delegation
  getDelegationCandidates: (taskId: string, limit?: number) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/delegation/candidates/${taskId}${limit ? `?limit=${limit}` : ''}`),
  delegateTask: (taskId: string, fromAgent: string, toAgent?: string) =>
    saRequest<Record<string, unknown>>('/v1/superadmin/delegation/delegate', {
      method: 'POST', body: JSON.stringify({ task_id: taskId, from_agent: fromAgent, to_agent: toAgent }),
    }),
  autoDelegateTask: (taskId: string, fromAgent: string) =>
    saRequest<Record<string, unknown>>('/v1/superadmin/delegation/auto', {
      method: 'POST', body: JSON.stringify({ task_id: taskId, from_agent: fromAgent }),
    }),
  getDelegationLog: (limit?: number) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/delegation/log${limit ? `?limit=${limit}` : ''}`),
  getDelegationStats: () =>
    saRequest<Record<string, unknown>>('/v1/superadmin/delegation/stats'),

  // Goal Decomposition
  decomposeGoal: (goal: string, context?: string, owner?: string) =>
    saRequest<Record<string, unknown>>('/v1/superadmin/goals/decompose', {
      method: 'POST', body: JSON.stringify({ goal, context, owner }),
    }),
  suggestGoalPlan: (goal: string, context?: string) =>
    saRequest<Record<string, unknown>>('/v1/superadmin/goals/suggest', {
      method: 'POST', body: JSON.stringify({ goal, context }),
    }),
  getGoalHistory: () =>
    saRequest<Record<string, unknown>>('/v1/superadmin/goals/history'),
  getGoalDetail: (goalId: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/goals/${goalId}`),

  // Auto-Hiring
  getHiringGaps: () =>
    saRequest<Record<string, unknown>>('/v1/superadmin/hiring/gaps'),
  getHiringRecommendations: () =>
    saRequest<Record<string, unknown>>('/v1/superadmin/hiring/recommendations'),
  autoHire: (templateId: string, overrides?: Record<string, unknown>) =>
    saRequest<Record<string, unknown>>('/v1/superadmin/hiring/hire', {
      method: 'POST', body: JSON.stringify({ template_id: templateId, overrides }),
    }),
  getHiringHistory: () =>
    saRequest<Record<string, unknown>>('/v1/superadmin/hiring/history'),
  getHiringTemplates: () =>
    saRequest<Record<string, unknown>>('/v1/superadmin/hiring/templates'),

  // Sprint Planning
  createSprint: (goal: string, durationDays?: number) =>
    saRequest<Record<string, unknown>>('/v1/superadmin/sprints', {
      method: 'POST', body: JSON.stringify({ goal, duration_days: durationDays ?? 7 }),
    }),
  listSprints: () =>
    saRequest<Record<string, unknown>>('/v1/superadmin/sprints'),
  getSprint: (sprintId: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/sprints/${sprintId}`),
  activateSprint: (sprintId: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/sprints/${sprintId}/activate`, { method: 'POST' }),
  sprintStandup: (sprintId: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/sprints/${sprintId}/standup`),
  completeSprint: (sprintId: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/sprints/${sprintId}/complete`, { method: 'POST' }),

  // Self-Improvement
  generateImprovement: (agentId: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/improvement/${agentId}`, { method: 'POST' }),
  generateAllImprovements: () =>
    saRequest<Record<string, unknown>>('/v1/superadmin/improvement/all', { method: 'POST' }),
  getImprovementProposals: () =>
    saRequest<Record<string, unknown>>('/v1/superadmin/improvement/proposals'),
  approveImprovement: (proposalId: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/improvement/${proposalId}/approve`, { method: 'POST' }),
  rejectImprovement: (proposalId: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/improvement/${proposalId}/reject`, { method: 'POST' }),

  // Alert System
  getAlerts: (severity?: string, unacked?: boolean) => {
    const qs = new URLSearchParams();
    if (severity) qs.set('severity', severity);
    if (unacked) qs.set('unacked', 'true');
    const q = qs.toString();
    return saRequest<Record<string, unknown>>(`/v1/superadmin/alerts${q ? `?${q}` : ''}`);
  },
  createAlert: (type: string, severity: string, title: string, details?: Record<string, unknown>) =>
    saRequest<Record<string, unknown>>('/v1/superadmin/alerts', {
      method: 'POST', body: JSON.stringify({ type, severity, title, details }),
    }),
  acknowledgeAlert: (alertId: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/alerts/${alertId}/ack`, { method: 'POST' }),
  acknowledgeAllAlerts: () =>
    saRequest<Record<string, unknown>>('/v1/superadmin/alerts/ack-all', { method: 'POST' }),
  getAlertSummary: () =>
    saRequest<Record<string, unknown>>('/v1/superadmin/alerts/summary'),

  // Agent Metrics
  getAgentMetrics: (agentId: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/metrics/agent/${agentId}`),
  getTeamMetrics: () =>
    saRequest<Record<string, unknown>>('/v1/superadmin/metrics/team'),
  getDepartmentMetrics: (dept: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/metrics/department/${dept}`),
  getMetricsSummary: () =>
    saRequest<Record<string, unknown>>('/v1/superadmin/metrics/summary'),
  getAllDepartmentMetrics: () =>
    saRequest<Record<string, unknown>>('/v1/superadmin/metrics/departments'),

  // Execution Replay
  getRecentTraces: (limit?: number) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/replay/recent${limit ? `?limit=${limit}` : ''}`),
  getExecutionTrace: (taskId: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/replay/${taskId}`),
  getReplayStats: () =>
    saRequest<Record<string, unknown>>('/v1/superadmin/replay/stats'),
  getActiveTraces: () =>
    saRequest<Record<string, unknown>>('/v1/superadmin/replay/active'),

  // Cost Optimizer
  getCostOptimizationReport: () =>
    saRequest<Record<string, unknown>>('/v1/superadmin/cost-optimizer/report'),
  getCostRecommendation: (category: string, threshold?: number) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/cost-optimizer/recommend/${category}${threshold ? `?threshold=${threshold}` : ''}`),
  applyCostOptimizations: (dryRun = true) =>
    saRequest<Record<string, unknown>>('/v1/superadmin/cost-optimizer/apply', {
      method: 'POST', body: JSON.stringify({ dry_run: dryRun }),
    }),
  getProviderCosts: () =>
    saRequest<Record<string, unknown>>('/v1/superadmin/cost-optimizer/providers'),
  getPotentialSavings: () =>
    saRequest<Record<string, unknown>>('/v1/superadmin/cost-optimizer/savings'),

  // Compliance Reports
  getReportTypes: () =>
    saRequest<Record<string, unknown>>('/v1/superadmin/reports/types'),
  generateReport: (reportType: string, fromDate?: number, toDate?: number) =>
    saRequest<Record<string, unknown>>('/v1/superadmin/reports/generate', {
      method: 'POST', body: JSON.stringify({ report_type: reportType, from_date: fromDate, to_date: toDate }),
    }),
  listReports: () =>
    saRequest<Record<string, unknown>>('/v1/superadmin/reports'),
  getReport: (reportId: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/reports/${reportId}`),

  // Live Feed
  getLiveFeed: (limit?: number) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/live-feed${limit ? `?limit=${limit}` : ''}`),

  // ── Phase 10: Knowledge Network ──

  // Knowledge Graph
  addKnowledgeNode: (data: { topic: string; content: string; node_type?: string; source_agent?: string; department?: string; confidence?: number; metadata?: Record<string, unknown> }) =>
    saRequest<Record<string, unknown>>('/v1/superadmin/knowledge/nodes', {
      method: 'POST', body: JSON.stringify(data),
    }),
  getKnowledgeNodes: (params?: { topic?: string; node_type?: string; department?: string; source_agent?: string; limit?: number }) => {
    const qs = new URLSearchParams();
    if (params?.topic) qs.set('topic', params.topic);
    if (params?.node_type) qs.set('node_type', params.node_type);
    if (params?.department) qs.set('department', params.department);
    if (params?.source_agent) qs.set('source_agent', params.source_agent);
    if (params?.limit) qs.set('limit', String(params.limit));
    const q = qs.toString();
    return saRequest<Record<string, unknown>>(`/v1/superadmin/knowledge/nodes${q ? `?${q}` : ''}`);
  },
  getKnowledgeNode: (nodeId: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/knowledge/nodes/${nodeId}`),
  addKnowledgeEdge: (data: { from_node: string; to_node: string; relation: string; weight?: number; metadata?: Record<string, unknown> }) =>
    saRequest<Record<string, unknown>>('/v1/superadmin/knowledge/edges', {
      method: 'POST', body: JSON.stringify(data),
    }),
  getKnowledgeNeighbors: (nodeId: string, depth?: number) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/knowledge/nodes/${nodeId}/neighbors${depth ? `?depth=${depth}` : ''}`),
  searchKnowledge: (query: string, limit?: number) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/knowledge/search?query=${encodeURIComponent(query)}${limit ? `&limit=${limit}` : ''}`),
  getKnowledgeStats: () =>
    saRequest<Record<string, unknown>>('/v1/superadmin/knowledge/stats'),
  getKnowledgeEdges: (params?: { from_node?: string; to_node?: string; relation?: string }) => {
    const qs = new URLSearchParams();
    if (params?.from_node) qs.set('from_node', params.from_node);
    if (params?.to_node) qs.set('to_node', params.to_node);
    if (params?.relation) qs.set('relation', params.relation);
    const q = qs.toString();
    return saRequest<Record<string, unknown>>(`/v1/superadmin/knowledge/edges${q ? `?${q}` : ''}`);
  },
  deleteKnowledgeNode: (nodeId: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/knowledge/nodes/${nodeId}`, { method: 'DELETE' }),
  getKnowledgeTopics: () =>
    saRequest<Record<string, unknown>>('/v1/superadmin/knowledge/topics'),

  // Knowledge Propagation
  propagateInsight: (nodeId: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/knowledge/propagate/${nodeId}`, { method: 'POST' }),
  getPendingPropagations: (agentId: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/knowledge/propagations/${agentId}`),
  acceptPropagation: (propagationId: string, agentId: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/knowledge/propagations/${propagationId}/accept`, {
      method: 'POST', body: JSON.stringify({ agent_id: agentId }),
    }),
  dismissPropagation: (propagationId: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/knowledge/propagations/${propagationId}/dismiss`, { method: 'POST' }),
  autoPropagateHighGrade: (minConfidence?: number) =>
    saRequest<Record<string, unknown>>('/v1/superadmin/knowledge/propagate/auto', {
      method: 'POST', body: JSON.stringify({ min_confidence: minConfidence }),
    }),
  getPropagationStats: () =>
    saRequest<Record<string, unknown>>('/v1/superadmin/knowledge/propagations/stats'),

  // Context Pools
  contributeToPool: (department: string, agentId: string, content: string) =>
    saRequest<Record<string, unknown>>('/v1/superadmin/knowledge/pools/contribute', {
      method: 'POST', body: JSON.stringify({ department, agent_id: agentId, content }),
    }),
  getContextPool: (department: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/knowledge/pools/${department}`),
  getRelevantContext: (department: string, query: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/knowledge/pools/${department}/relevant?query=${encodeURIComponent(query)}`),
  listContextPools: () =>
    saRequest<Record<string, unknown>>('/v1/superadmin/knowledge/pools'),
  pruneContextPools: () =>
    saRequest<Record<string, unknown>>('/v1/superadmin/knowledge/pools/prune', { method: 'POST' }),

  // Expert Discovery
  findExpert: (query: string, domain?: string, topK?: number) => {
    const qs = new URLSearchParams({ query });
    if (domain) qs.set('domain', domain);
    if (topK) qs.set('top_k', String(topK));
    return saRequest<Record<string, unknown>>(`/v1/superadmin/knowledge/experts/find?${qs}`);
  },
  getDomainMap: () =>
    saRequest<Record<string, unknown>>('/v1/superadmin/knowledge/experts/domains'),
  recommendExpertForTask: (taskDescription: string) =>
    saRequest<Record<string, unknown>>('/v1/superadmin/knowledge/experts/recommend', {
      method: 'POST', body: JSON.stringify({ task_description: taskDescription }),
    }),
  getExpertiseMatrix: (department?: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/knowledge/experts/matrix${department ? `?department=${department}` : ''}`),

  // ── Phase 10: Simulation Sandbox ──

  // Simulations
  createSimulation: (name: string, simType: string, config?: Record<string, unknown>, agentIds?: string[]) =>
    saRequest<Record<string, unknown>>('/v1/superadmin/simulations', {
      method: 'POST', body: JSON.stringify({ name, sim_type: simType, config, agent_ids: agentIds }),
    }),
  listSimulations: (status?: string, simType?: string) => {
    const qs = new URLSearchParams();
    if (status) qs.set('status', status);
    if (simType) qs.set('sim_type', simType);
    const q = qs.toString();
    return saRequest<Record<string, unknown>>(`/v1/superadmin/simulations${q ? `?${q}` : ''}`);
  },
  getSimulation: (simId: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/simulations/${simId}`),
  updateSimulation: (simId: string, updates: Record<string, unknown>) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/simulations/${simId}`, {
      method: 'PUT', body: JSON.stringify(updates),
    }),
  runSandboxTask: (simId: string, agentId: string, taskPrompt: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/simulations/${simId}/run`, {
      method: 'POST', body: JSON.stringify({ agent_id: agentId, task_prompt: taskPrompt }),
    }),
  cleanupSimulation: (simId: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/simulations/${simId}/cleanup`, { method: 'POST' }),
  getSimulationStats: () =>
    saRequest<Record<string, unknown>>('/v1/superadmin/simulations/stats'),

  // Behavior Tests
  createTestSuite: (name: string, description: string, testCases: Record<string, unknown>[]) =>
    saRequest<Record<string, unknown>>('/v1/superadmin/simulations/tests/suites', {
      method: 'POST', body: JSON.stringify({ name, description, test_cases: testCases }),
    }),
  listTestSuites: () =>
    saRequest<Record<string, unknown>>('/v1/superadmin/simulations/tests/suites'),
  getTestSuite: (suiteId: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/simulations/tests/suites/${suiteId}`),
  updateTestSuite: (suiteId: string, updates: Record<string, unknown>) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/simulations/tests/suites/${suiteId}`, {
      method: 'PUT', body: JSON.stringify(updates),
    }),
  runTestSuite: (suiteId: string, agentIds?: string[]) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/simulations/tests/suites/${suiteId}/run`, {
      method: 'POST', body: JSON.stringify({ agent_ids: agentIds }),
    }),
  getTestRunResults: (runId: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/simulations/tests/runs/${runId}`),
  getTestSuiteHistory: (suiteId: string, limit?: number) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/simulations/tests/suites/${suiteId}/history${limit ? `?limit=${limit}` : ''}`),

  // A/B Testing
  createABExperiment: (data: { name: string; variant_a: string; variant_b: string; agent_ids: string[]; task_prompts: string[]; config?: Record<string, unknown> }) =>
    saRequest<Record<string, unknown>>('/v1/superadmin/simulations/ab', {
      method: 'POST', body: JSON.stringify(data),
    }),
  listABExperiments: (status?: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/simulations/ab${status ? `?status=${status}` : ''}`),
  getABExperiment: (experimentId: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/simulations/ab/${experimentId}`),
  runABExperiment: (experimentId: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/simulations/ab/${experimentId}/run`, { method: 'POST' }),
  applyABWinner: (experimentId: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/simulations/ab/${experimentId}/apply`, { method: 'POST' }),
  getABStats: () =>
    saRequest<Record<string, unknown>>('/v1/superadmin/simulations/ab/stats'),

  // Chaos Injection
  injectChaos: (simId: string, eventType: string, target: string, config?: Record<string, unknown>) =>
    saRequest<Record<string, unknown>>('/v1/superadmin/simulations/chaos/inject', {
      method: 'POST', body: JSON.stringify({ sim_id: simId, event_type: eventType, target, config }),
    }),
  getChaosEvents: (simId: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/simulations/chaos/${simId}`),
  evaluateChaosRecovery: (eventId: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/simulations/chaos/${eventId}/evaluate`),
  runChaosScenario: (data: { name: string; agent_ids: string[]; events_sequence: Record<string, unknown>[] }) =>
    saRequest<Record<string, unknown>>('/v1/superadmin/simulations/chaos/scenario', {
      method: 'POST', body: JSON.stringify(data),
    }),
  getChaosCatalog: () =>
    saRequest<Record<string, unknown>>('/v1/superadmin/simulations/chaos/catalog'),
  getChaosStats: () =>
    saRequest<Record<string, unknown>>('/v1/superadmin/simulations/chaos/stats'),

  // ── Autonomy Loop ──

  getAutonomyStatus: () =>
    saRequest<Record<string, unknown>>('/v1/superadmin/autonomy/status'),
  getAutonomyAgents: () =>
    saRequest<Record<string, unknown>>('/v1/superadmin/autonomy/agents'),
  getAutonomyAgentStatus: (agentId: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/autonomy/agents/${agentId}`),
  configureAutonomy: (agentId: string, config: Record<string, unknown>) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/autonomy/agents/${agentId}/configure`, {
      method: 'POST', body: JSON.stringify(config),
    }),
  startAutonomy: (agentId: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/autonomy/agents/${agentId}/start`, { method: 'POST' }),
  stopAutonomy: (agentId: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/autonomy/agents/${agentId}/stop`, { method: 'POST' }),
  runAutonomyCycle: (agentId: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/autonomy/agents/${agentId}/cycle`, { method: 'POST' }),
  getAutonomyHistory: (agentId?: string, limit?: number) => {
    const qs = new URLSearchParams();
    if (agentId) qs.set('agent_id', agentId);
    if (limit) qs.set('limit', String(limit));
    const q = qs.toString();
    return saRequest<Record<string, unknown>>(`/v1/superadmin/autonomy/history${q ? `?${q}` : ''}`);
  },
  getEventCounts: () =>
    saRequest<Record<string, unknown>>('/v1/superadmin/events/counts'),

  // ── Marketplace ──
  getMarketplaceCapabilities: (category?: string, enabledOnly?: boolean) => {
    const qs = new URLSearchParams();
    if (category) qs.set('category', category);
    if (enabledOnly) qs.set('enabled_only', 'true');
    const q = qs.toString();
    return saRequest<Record<string, unknown>>(`/v1/superadmin/marketplace/capabilities${q ? `?${q}` : ''}`);
  },
  getMarketplaceStats: () =>
    saRequest<Record<string, unknown>>('/v1/superadmin/marketplace/stats'),
  searchMarketplace: (query: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/marketplace/search?q=${encodeURIComponent(query)}`),
  getMarketplaceCapability: (id: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/marketplace/capabilities/${id}`),
  enableCapability: (id: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/marketplace/capabilities/${id}/enable`, { method: 'POST' }),
  disableCapability: (id: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/marketplace/capabilities/${id}/disable`, { method: 'POST' }),
  updateCapabilityConfig: (id: string, config: Record<string, unknown>) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/marketplace/capabilities/${id}/config`, {
      method: 'PUT', body: JSON.stringify({ config }),
    }),
  getCapabilityDependencies: (id: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/marketplace/capabilities/${id}/dependencies`),
  getCapabilityDependents: (id: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/marketplace/capabilities/${id}/dependents`),

  // ── Plugins ──
  listPlugins: (enabledOnly?: boolean) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/plugins${enabledOnly ? '?enabled_only=true' : ''}`),
  getPluginStats: () =>
    saRequest<Record<string, unknown>>('/v1/superadmin/plugins/stats'),
  getPlugin: (id: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/plugins/${id}`),
  registerPlugin: (manifest: Record<string, unknown>) =>
    saRequest<Record<string, unknown>>('/v1/superadmin/plugins', {
      method: 'POST', body: JSON.stringify(manifest),
    }),
  unregisterPlugin: (id: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/plugins/${id}`, { method: 'DELETE' }),
  enablePlugin: (id: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/plugins/${id}/enable`, { method: 'POST' }),
  disablePlugin: (id: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/plugins/${id}/disable`, { method: 'POST' }),

  // ── AI Copilot ──
  copilotListSessions: () =>
    saRequest<Record<string, unknown>>('/v1/superadmin/copilot/sessions'),
  copilotCreateSession: (title?: string) =>
    saRequest<Record<string, unknown>>('/v1/superadmin/copilot/sessions', {
      method: 'POST', body: JSON.stringify({ title }),
    }),
  copilotGetSession: (id: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/copilot/sessions/${id}`),
  copilotDeleteSession: (id: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/copilot/sessions/${id}`, { method: 'DELETE' }),
  copilotChat: (sessionId: string, message: string, context?: Record<string, unknown>) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/copilot/chat`, {
      method: 'POST', body: JSON.stringify({ session_id: sessionId, message, context }),
    }),
  copilotGenerateQuery: (description: string) =>
    saRequest<Record<string, unknown>>('/v1/superadmin/copilot/generate-query', {
      method: 'POST', body: JSON.stringify({ description }),
    }),
  copilotExplainAgent: (agentId: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/copilot/explain-agent/${agentId}`),
  copilotSuggestOptimizations: () =>
    saRequest<Record<string, unknown>>('/v1/superadmin/copilot/suggest-optimizations'),
  copilotGetStats: () =>
    saRequest<Record<string, unknown>>('/v1/superadmin/copilot/stats'),

  // ── Template Marketplace ──
  templateMarketList: (category?: string, search?: string, sort?: string) => {
    const qs = new URLSearchParams();
    if (category) qs.set('category', category);
    if (search) qs.set('search', search);
    if (sort) qs.set('sort_by', sort);
    const q = qs.toString();
    return saRequest<Record<string, unknown>>(`/v1/superadmin/template-market/templates${q ? `?${q}` : ''}`);
  },
  templateMarketGet: (id: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/template-market/templates/${id}`),
  templateMarketInstall: (id: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/template-market/templates/${id}/install`, { method: 'POST' }),
  templateMarketRate: (id: string, rating: number) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/template-market/templates/${id}/rate`, {
      method: 'POST', body: JSON.stringify({ rating }),
    }),
  templateMarketPublish: (data: Record<string, unknown>) =>
    saRequest<Record<string, unknown>>('/v1/superadmin/template-market/templates', {
      method: 'POST', body: JSON.stringify(data),
    }),
  templateMarketCategories: () =>
    saRequest<Record<string, unknown>>('/v1/superadmin/template-market/categories'),
  templateMarketStats: () =>
    saRequest<Record<string, unknown>>('/v1/superadmin/template-market/stats'),

  // ── GraphQL Gateway ──
  graphqlExecute: (query: string, variables?: Record<string, unknown>) =>
    saRequest<Record<string, unknown>>('/v1/superadmin/graphql/execute', {
      method: 'POST', body: JSON.stringify({ query, variables }),
    }),
  graphqlGetSchema: () =>
    saRequest<Record<string, unknown>>('/v1/superadmin/graphql/schema'),
  graphqlGenerateSchema: () =>
    saRequest<Record<string, unknown>>('/v1/superadmin/graphql/generate', { method: 'POST' }),
  graphqlQueryLog: (limit?: number) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/graphql/log${limit ? `?limit=${limit}` : ''}`),
  graphqlStats: () =>
    saRequest<Record<string, unknown>>('/v1/superadmin/graphql/stats'),

  // ── Teams Integration ──
  teamsConfigure: (config: Record<string, unknown>) =>
    saRequest<Record<string, unknown>>('/v1/superadmin/integrations/teams/configure', {
      method: 'POST', body: JSON.stringify(config),
    }),
  teamsGetConfig: () =>
    saRequest<Record<string, unknown>>('/v1/superadmin/integrations/teams/config'),
  teamsTestConnection: () =>
    saRequest<Record<string, unknown>>('/v1/superadmin/integrations/teams/test', { method: 'POST' }),
  teamsListMessages: (limit?: number) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/integrations/teams/messages${limit ? `?limit=${limit}` : ''}`),
  teamsGetStats: () =>
    saRequest<Record<string, unknown>>('/v1/superadmin/integrations/teams/stats'),

  // ── Discord Integration ──
  discordConfigure: (config: Record<string, unknown>) =>
    saRequest<Record<string, unknown>>('/v1/superadmin/integrations/discord/configure', {
      method: 'POST', body: JSON.stringify(config),
    }),
  discordGetConfig: () =>
    saRequest<Record<string, unknown>>('/v1/superadmin/integrations/discord/config'),
  discordTestConnection: () =>
    saRequest<Record<string, unknown>>('/v1/superadmin/integrations/discord/test', { method: 'POST' }),
  discordListMessages: (limit?: number) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/integrations/discord/messages${limit ? `?limit=${limit}` : ''}`),
  discordGetStats: () =>
    saRequest<Record<string, unknown>>('/v1/superadmin/integrations/discord/stats'),

  // ── Zapier / n8n Connector ──
  zapierCreateEndpoint: (data: Record<string, unknown>) =>
    saRequest<Record<string, unknown>>('/v1/superadmin/integrations/zapier/endpoints', {
      method: 'POST', body: JSON.stringify(data),
    }),
  zapierListEndpoints: () =>
    saRequest<Record<string, unknown>>('/v1/superadmin/integrations/zapier/endpoints'),
  zapierGetEndpoint: (id: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/integrations/zapier/endpoints/${id}`),
  zapierDeleteEndpoint: (id: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/integrations/zapier/endpoints/${id}`, { method: 'DELETE' }),
  zapierGetDeliveries: (endpointId?: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/integrations/zapier/deliveries${endpointId ? `?endpoint_id=${endpointId}` : ''}`),
  zapierRetryDelivery: (id: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/integrations/zapier/deliveries/${id}/retry`, { method: 'POST' }),
  zapierSupportedEvents: () =>
    saRequest<Record<string, unknown>>('/v1/superadmin/integrations/zapier/events'),
  zapierGetStats: () =>
    saRequest<Record<string, unknown>>('/v1/superadmin/integrations/zapier/stats'),

  // ── Voice Interface ──
  voiceCreateSession: (config?: Record<string, unknown>) =>
    saRequest<Record<string, unknown>>('/v1/superadmin/voice/sessions', {
      method: 'POST', body: JSON.stringify({ config }),
    }),
  voiceProcessCommand: (sessionId: string, transcript: string) =>
    saRequest<Record<string, unknown>>('/v1/superadmin/voice/process', {
      method: 'POST', body: JSON.stringify({ session_id: sessionId, transcript }),
    }),
  voiceGetCommands: () =>
    saRequest<Record<string, unknown>>('/v1/superadmin/voice/commands'),
  voiceGetHistory: (sessionId?: string, limit?: number) => {
    const qs = new URLSearchParams();
    if (sessionId) qs.set('session_id', sessionId);
    if (limit) qs.set('limit', String(limit));
    const q = qs.toString();
    return saRequest<Record<string, unknown>>(`/v1/superadmin/voice/history${q ? `?${q}` : ''}`);
  },
  voiceGetConfig: () =>
    saRequest<Record<string, unknown>>('/v1/superadmin/voice/config'),
  voiceUpdateConfig: (config: Record<string, unknown>) =>
    saRequest<Record<string, unknown>>('/v1/superadmin/voice/config', {
      method: 'PUT', body: JSON.stringify(config),
    }),
  voiceGetStats: () =>
    saRequest<Record<string, unknown>>('/v1/superadmin/voice/stats'),

  // ── Secrets Vault ──
  vaultListSecrets: (prefix?: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/vault/secrets${prefix ? `?prefix=${prefix}` : ''}`),
  vaultGetSecret: (path: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/vault/secrets/${encodeURIComponent(path)}`),
  vaultPutSecret: (path: string, value: string, metadata?: Record<string, unknown>) =>
    saRequest<Record<string, unknown>>('/v1/superadmin/vault/secrets', {
      method: 'POST', body: JSON.stringify({ path, value, metadata }),
    }),
  vaultDeleteSecret: (path: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/vault/secrets/${encodeURIComponent(path)}`, { method: 'DELETE' }),
  vaultRotateSecret: (path: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/vault/secrets/${encodeURIComponent(path)}/rotate`, { method: 'POST' }),
  vaultGetRotationSchedule: () =>
    saRequest<Record<string, unknown>>('/v1/superadmin/vault/rotation-schedule'),
  vaultGetStatus: () =>
    saRequest<Record<string, unknown>>('/v1/superadmin/vault/status'),
  vaultGetStats: () =>
    saRequest<Record<string, unknown>>('/v1/superadmin/vault/stats'),

  // ── Zero-Trust ──
  ztListPolicies: () =>
    saRequest<Record<string, unknown>>('/v1/superadmin/zero-trust/policies'),
  ztGetPolicy: (id: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/zero-trust/policies/${id}`),
  ztCreatePolicy: (data: Record<string, unknown>) =>
    saRequest<Record<string, unknown>>('/v1/superadmin/zero-trust/policies', {
      method: 'POST', body: JSON.stringify(data),
    }),
  ztUpdatePolicy: (id: string, data: Record<string, unknown>) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/zero-trust/policies/${id}`, {
      method: 'PUT', body: JSON.stringify(data),
    }),
  ztDeletePolicy: (id: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/zero-trust/policies/${id}`, { method: 'DELETE' }),
  ztListCertificates: () =>
    saRequest<Record<string, unknown>>('/v1/superadmin/zero-trust/certificates'),
  ztIssueCertificate: (subject: string) =>
    saRequest<Record<string, unknown>>('/v1/superadmin/zero-trust/certificates', {
      method: 'POST', body: JSON.stringify({ subject }),
    }),
  ztRevokeCertificate: (id: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/zero-trust/certificates/${id}/revoke`, { method: 'POST' }),
  ztGetAuditLog: (limit?: number) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/zero-trust/audit${limit ? `?limit=${limit}` : ''}`),
  ztGetStats: () =>
    saRequest<Record<string, unknown>>('/v1/superadmin/zero-trust/stats'),

  // ── Data Pipelines ──
  pipelineCreate: (data: Record<string, unknown>) =>
    saRequest<Record<string, unknown>>('/v1/superadmin/data-pipelines', {
      method: 'POST', body: JSON.stringify(data),
    }),
  pipelineList: (status?: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/data-pipelines${status ? `?status=${status}` : ''}`),
  pipelineGet: (id: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/data-pipelines/${id}`),
  pipelineUpdate: (id: string, data: Record<string, unknown>) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/data-pipelines/${id}`, {
      method: 'PUT', body: JSON.stringify(data),
    }),
  pipelineDelete: (id: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/data-pipelines/${id}`, { method: 'DELETE' }),
  pipelineExecute: (id: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/data-pipelines/${id}/execute`, { method: 'POST' }),
  pipelineListRuns: (pipelineId?: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/data-pipelines/runs${pipelineId ? `?pipeline_id=${pipelineId}` : ''}`),
  pipelineGetStageTypes: () =>
    saRequest<Record<string, unknown>>('/v1/superadmin/data-pipelines/stage-types'),
  pipelineGetStats: () =>
    saRequest<Record<string, unknown>>('/v1/superadmin/data-pipelines/stats'),

  // ── Custom Dashboards ──
  customDashboardCreate: (data: Record<string, unknown>) =>
    saRequest<Record<string, unknown>>('/v1/superadmin/custom-dashboards', {
      method: 'POST', body: JSON.stringify(data),
    }),
  customDashboardList: () =>
    saRequest<Record<string, unknown>>('/v1/superadmin/custom-dashboards'),
  customDashboardGet: (id: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/custom-dashboards/${id}`),
  customDashboardUpdate: (id: string, data: Record<string, unknown>) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/custom-dashboards/${id}`, {
      method: 'PUT', body: JSON.stringify(data),
    }),
  customDashboardDelete: (id: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/custom-dashboards/${id}`, { method: 'DELETE' }),
  customDashboardDuplicate: (id: string, newName: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/custom-dashboards/${id}/duplicate`, {
      method: 'POST', body: JSON.stringify({ new_name: newName }),
    }),
  customDashboardAddWidget: (dashboardId: string, widget: Record<string, unknown>) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/custom-dashboards/${dashboardId}/widgets`, {
      method: 'POST', body: JSON.stringify(widget),
    }),
  customDashboardRemoveWidget: (widgetId: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/custom-dashboards/widgets/${widgetId}`, { method: 'DELETE' }),
  customDashboardGetWidgetTypes: () =>
    saRequest<Record<string, unknown>>('/v1/superadmin/custom-dashboards/widget-types'),
  customDashboardGetStats: () =>
    saRequest<Record<string, unknown>>('/v1/superadmin/custom-dashboards/stats'),

  // ── Edge Deployment ──
  edgeListNodes: (region?: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/edge/nodes${region ? `?region=${region}` : ''}`),
  edgeGetNode: (id: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/edge/nodes/${id}`),
  edgeRegisterNode: (data: Record<string, unknown>) =>
    saRequest<Record<string, unknown>>('/v1/superadmin/edge/nodes', {
      method: 'POST', body: JSON.stringify(data),
    }),
  edgeRemoveNode: (id: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/edge/nodes/${id}`, { method: 'DELETE' }),
  edgeSyncData: (nodeId: string, direction?: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/edge/nodes/${nodeId}/sync`, {
      method: 'POST', body: JSON.stringify({ direction }),
    }),
  edgeGetSyncLog: (nodeId?: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/edge/sync-log${nodeId ? `?node_id=${nodeId}` : ''}`),
  edgeGetStats: () =>
    saRequest<Record<string, unknown>>('/v1/superadmin/edge/stats'),

  // ── Kubernetes Operator ──
  k8sListClusters: () =>
    saRequest<Record<string, unknown>>('/v1/superadmin/kubernetes/clusters'),
  k8sGetCluster: (id: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/kubernetes/clusters/${id}`),
  k8sRegisterCluster: (data: Record<string, unknown>) =>
    saRequest<Record<string, unknown>>('/v1/superadmin/kubernetes/clusters', {
      method: 'POST', body: JSON.stringify(data),
    }),
  k8sScale: (clusterId: string, component: string, replicas: number) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/kubernetes/clusters/${clusterId}/scale`, {
      method: 'POST', body: JSON.stringify({ component, replicas }),
    }),
  k8sUpgrade: (clusterId: string, image: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/kubernetes/clusters/${clusterId}/upgrade`, {
      method: 'POST', body: JSON.stringify({ image }),
    }),
  k8sGenerateManifests: (config?: Record<string, unknown>) =>
    saRequest<Record<string, unknown>>('/v1/superadmin/kubernetes/manifests', {
      method: 'POST', body: JSON.stringify(config || {}),
    }),
  k8sGetOperations: (clusterId?: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/kubernetes/operations${clusterId ? `?cluster_id=${clusterId}` : ''}`),
  k8sGetStats: () =>
    saRequest<Record<string, unknown>>('/v1/superadmin/kubernetes/stats'),

  // ── White-Label & Theming ──
  themeList: () =>
    saRequest<Record<string, unknown>>('/v1/superadmin/theming/themes'),
  themeGet: (id: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/theming/themes/${id}`),
  themeCreate: (data: Record<string, unknown>) =>
    saRequest<Record<string, unknown>>('/v1/superadmin/theming/themes', {
      method: 'POST', body: JSON.stringify(data),
    }),
  themeActivate: (id: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/theming/themes/${id}/activate`, { method: 'POST' }),
  themeDelete: (id: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/theming/themes/${id}`, { method: 'DELETE' }),
  themeGetActive: () =>
    saRequest<Record<string, unknown>>('/v1/superadmin/theming/active'),
  brandingGet: () =>
    saRequest<Record<string, unknown>>('/v1/superadmin/theming/branding'),
  brandingUpdate: (data: Record<string, unknown>) =>
    saRequest<Record<string, unknown>>('/v1/superadmin/theming/branding', {
      method: 'PUT', body: JSON.stringify(data),
    }),
  themeGetStats: () =>
    saRequest<Record<string, unknown>>('/v1/superadmin/theming/stats'),

  // ── Multi-Region ──
  regionList: () =>
    saRequest<Record<string, unknown>>('/v1/superadmin/regions'),
  regionGet: (id: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/regions/${id}`),
  regionAdd: (data: Record<string, unknown>) =>
    saRequest<Record<string, unknown>>('/v1/superadmin/regions', {
      method: 'POST', body: JSON.stringify(data),
    }),
  regionRemove: (id: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/regions/${id}`, { method: 'DELETE' }),
  regionSetPrimary: (id: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/regions/${id}/set-primary`, { method: 'POST' }),
  regionListStreams: () =>
    saRequest<Record<string, unknown>>('/v1/superadmin/regions/streams'),
  regionCreateStream: (data: Record<string, unknown>) =>
    saRequest<Record<string, unknown>>('/v1/superadmin/regions/streams', {
      method: 'POST', body: JSON.stringify(data),
    }),
  regionListConflicts: () =>
    saRequest<Record<string, unknown>>('/v1/superadmin/regions/conflicts'),
  regionResolveConflict: (id: string, resolution: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/regions/conflicts/${id}/resolve`, {
      method: 'POST', body: JSON.stringify({ resolution }),
    }),
  regionTriggerFailover: (from: string, to: string, reason?: string) =>
    saRequest<Record<string, unknown>>('/v1/superadmin/regions/failover', {
      method: 'POST', body: JSON.stringify({ from_region: from, to_region: to, reason }),
    }),
  regionGetHealth: () =>
    saRequest<Record<string, unknown>>('/v1/superadmin/regions/health'),
  regionGetStats: () =>
    saRequest<Record<string, unknown>>('/v1/superadmin/regions/stats'),

  // ── Sentinel (Security Testing) ──
  sentinelStats: () =>
    saRequest<Record<string, unknown>>('/v1/superadmin/sentinel/stats'),
  sentinelQuickScan: () =>
    saRequest<Record<string, unknown>>('/v1/superadmin/sentinel/quick-scan', { method: 'POST' }),
  sentinelKnowledge: (category?: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/sentinel/knowledge${category ? `?category=${category}` : ''}`),
  sentinelKnowledgeDetail: (id: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/sentinel/knowledge/${id}`),
  sentinelAddVector: (data: Record<string, unknown>) =>
    saRequest<Record<string, unknown>>('/v1/superadmin/sentinel/knowledge', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data),
    }),
  sentinelCampaigns: (status?: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/sentinel/campaigns${status ? `?status=${status}` : ''}`),
  sentinelCreateCampaign: (data: Record<string, unknown>) =>
    saRequest<Record<string, unknown>>('/v1/superadmin/sentinel/campaigns', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data),
    }),
  sentinelCampaign: (id: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/sentinel/campaigns/${id}`),
  sentinelUpdateCampaign: (id: string, data: Record<string, unknown>) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/sentinel/campaigns/${id}`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data),
    }),
  sentinelDeleteCampaign: (id: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/sentinel/campaigns/${id}`, { method: 'DELETE' }),
  sentinelExecuteCampaign: (id: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/sentinel/campaigns/${id}/execute`, { method: 'POST' }),
  sentinelRuns: (campaignId?: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/sentinel/runs${campaignId ? `?campaign_id=${campaignId}` : ''}`),
  sentinelRun: (id: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/sentinel/runs/${id}`),
  sentinelAbortRun: (id: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/sentinel/runs/${id}/abort`, { method: 'POST' }),
  sentinelFindings: (params?: Record<string, string>) => {
    const q = params ? '?' + new URLSearchParams(params).toString() : '';
    return saRequest<Record<string, unknown>>(`/v1/superadmin/sentinel/findings${q}`);
  },
  sentinelUpdateFinding: (id: string, data: Record<string, unknown>) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/sentinel/findings/${id}`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data),
    }),
  sentinelPosture: () =>
    saRequest<Record<string, unknown>>('/v1/superadmin/sentinel/posture'),
  sentinelPostureHistory: () =>
    saRequest<Record<string, unknown>>('/v1/superadmin/sentinel/posture/history'),
  sentinelRisks: () =>
    saRequest<Record<string, unknown>>('/v1/superadmin/sentinel/posture/risks'),
  sentinelRemediation: (status?: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/sentinel/remediation${status ? `?status=${status}` : ''}`),
  sentinelGenerateRemediation: (findingId: string) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/sentinel/remediation/${findingId}/generate`, { method: 'POST' }),
  sentinelUpdateRemediation: (id: string, data: Record<string, unknown>) =>
    saRequest<Record<string, unknown>>(`/v1/superadmin/sentinel/remediation/${id}`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data),
    }),
  sentinelThreatIntel: () =>
    saRequest<Record<string, unknown>>('/v1/superadmin/sentinel/threat-intel'),
  sentinelAddThreatIntel: (data: Record<string, unknown>) =>
    saRequest<Record<string, unknown>>('/v1/superadmin/sentinel/threat-intel', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data),
    }),
};
