export interface CortexConfig {
  /** Direct PostgreSQL connection (for CRUD — no Python hop) */
  postgres: {
    connectionString?: string;
    host?: string;
    port?: number;
    database?: string;
    user?: string;
    password?: string;
    max?: number;
    ssl?: boolean | object;
  };

  /** Direct Redis connection (for caching — no Python hop) */
  redis?: {
    url?: string;
    host?: string;
    port?: number;
    password?: string;
    db?: number;
  };

  /** CortexDB service URL (for cross-engine + ML operations) */
  cortexUrl: string;

  /** API key for CortexDB service */
  apiKey?: string;

  /** Tenant ID for multi-tenant operations */
  tenantId?: string;
}

export interface WriteResult {
  sync: Record<string, { status: string; result?: unknown; error?: string }>;
  async: Record<string, { status: string; task_id?: string; error?: string }>;
  latency_ms: number;
}

export interface HealthResult {
  status: 'healthy' | 'degraded' | 'unhealthy';
  version: string;
  engines: Record<string, { status: string }>;
  cache?: {
    r0_hits: number;
    r1_hits: number;
    r2_hits: number;
    r3_hits: number;
    r0_hit_rate: number;
  };
}

export interface QueryResult<T = unknown> {
  data: T[];
  tier_served: string;
  engines_hit: string[];
  latency_ms: number;
  cache_hit: boolean;
}

export interface AgentCard {
  agent_id: string;
  name: string;
  description: string;
  skills: string[];
  tools?: string[];
  endpoint_url?: string;
  protocol?: 'mcp' | 'rest' | 'grpc';
  model?: string;
  max_concurrent_tasks?: number;
  tenant_id?: string;
}

export interface SemanticSearchOptions {
  collection?: string;
  limit?: number;
  threshold?: number;
  enrichWith?: 'relational';
}
