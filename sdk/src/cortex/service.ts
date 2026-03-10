import type { WriteResult, HealthResult, SemanticSearchOptions } from '../types.js';

export class CortexService {
  private baseUrl: string;
  private headers: Record<string, string>;

  constructor(cortexUrl: string, options?: { apiKey?: string; tenantId?: string }) {
    this.baseUrl = cortexUrl.replace(/\/$/, '');
    this.headers = { 'Content-Type': 'application/json' };
    if (options?.apiKey) this.headers['Authorization'] = `Bearer ${options.apiKey}`;
    if (options?.tenantId) this.headers['X-Tenant-ID'] = options.tenantId;
  }

  /** Execute a CortexQL query through the service. */
  async query<T = unknown>(cortexql: string, params?: unknown[]): Promise<T[]> {
    const res = await this.fetch<{ data?: T[] }>('/v1/query', {
      method: 'POST',
      body: { cortexql, params },
    });
    return res.data ?? [];
  }

  /** Run a semantic search. Builds a FIND SIMILAR CortexQL query. */
  async semanticSearch(text: string, options?: SemanticSearchOptions): Promise<unknown[]> {
    const escapedText = text.replace(/'/g, "''");
    const collection = options?.collection ?? 'default';
    const limit = options?.limit ?? 10;
    const cortexql = `FIND SIMILAR TO '${escapedText}' IN ${collection} LIMIT ${limit}`;

    const res = await this.fetch<{ data?: unknown[] }>('/v1/query', {
      method: 'POST',
      body: { cortexql },
    });
    return res.data ?? [];
  }

  /** Write with fan-out across engines. */
  async write(dataType: string, payload: Record<string, unknown>, actor?: string): Promise<WriteResult> {
    return this.fetch<WriteResult>('/v1/write', {
      method: 'POST',
      body: { data_type: dataType, payload, actor: actor ?? 'sdk' },
    });
  }

  /** Discover agents by skill via the A2A protocol. */
  async discoverAgents(skill: string, limit?: number): Promise<unknown[]> {
    const res = await this.fetch<{ agents?: unknown[] }>('/v1/a2a/discover', {
      method: 'POST',
      body: { skill, limit: limit ?? 5 },
    });
    return res.agents ?? [];
  }

  /** Register an agent card. */
  async registerAgent(card: Record<string, unknown>): Promise<unknown> {
    return this.fetch('/v1/a2a/register', {
      method: 'POST',
      body: card,
    });
  }

  /** List registered agents. Optionally filter by tenant. */
  async listAgents(options?: { tenant?: string }): Promise<unknown[]> {
    const url = options?.tenant
      ? `/v1/a2a/agents?tenant_id=${encodeURIComponent(options.tenant)}`
      : '/v1/a2a/agents';
    const res = await this.fetch<{ agents?: unknown[] }>(url);
    return res.agents ?? [];
  }

  /** Check CortexDB service health. */
  async health(): Promise<HealthResult> {
    return this.fetch<HealthResult>('/health/ready');
  }

  private async fetch<T>(path: string, options?: { method?: string; body?: unknown }): Promise<T> {
    const url = `${this.baseUrl}${path}`;
    const res = await globalThis.fetch(url, {
      method: options?.method ?? 'GET',
      headers: this.headers,
      body: options?.body ? JSON.stringify(options.body) : undefined,
    });

    if (!res.ok) {
      const errorBody = await res.text().catch(() => '');
      throw new CortexError(`CortexDB ${res.status}: ${errorBody}`, res.status);
    }

    return res.json() as Promise<T>;
  }
}

export class CortexError extends Error {
  public readonly statusCode: number;

  constructor(message: string, statusCode: number) {
    super(message);
    this.name = 'CortexError';
    this.statusCode = statusCode;
  }
}
