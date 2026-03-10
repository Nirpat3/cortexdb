import { DirectPostgres } from './direct/postgres.js';
import { DirectRedis } from './direct/redis.js';
import { CortexService } from './cortex/service.js';
import type { CortexConfig, WriteResult, HealthResult, SemanticSearchOptions } from './types.js';

export class CortexClient {
  /** Direct PostgreSQL connection — zero overhead for simple queries. */
  readonly pg: DirectPostgres;

  /** Direct Redis connection — zero overhead for cache operations. */
  readonly redis: DirectRedis;

  /** CortexDB service client — for cross-engine and ML operations. */
  readonly cortex: CortexService;

  constructor(config: CortexConfig) {
    // Direct connections — zero overhead for simple queries
    this.pg = new DirectPostgres(config.postgres);
    this.redis = new DirectRedis(config.redis ?? {});

    // CortexDB service — only for cross-engine + ML operations
    this.cortex = new CortexService(config.cortexUrl, {
      apiKey: config.apiKey,
      tenantId: config.tenantId,
    });
  }

  /**
   * Smart query router. Simple SQL goes direct to PG.
   * Vector/graph/cross-engine queries route through CortexDB service.
   */
  async query<T = Record<string, unknown>>(cortexql: string, params?: unknown[]): Promise<T[]> {
    if (this.isSimpleSQL(cortexql)) {
      return this.pg.query<T>(cortexql, params);
    }
    return this.cortex.query<T>(cortexql, params);
  }

  /**
   * Direct PG query — always goes straight to PostgreSQL.
   * Use this when you know you want direct access.
   */
  async sql<T = Record<string, unknown>>(query: string, params?: unknown[]): Promise<T[]> {
    return this.pg.query<T>(query, params);
  }

  /**
   * Semantic search — routes through CortexDB service (needs vector engine + embeddings).
   */
  async search(text: string, options?: SemanticSearchOptions): Promise<unknown[]> {
    return this.cortex.semanticSearch(text, options);
  }

  /**
   * Write fan-out — routes through CortexDB service.
   * Single write propagates to multiple engines (PG + Redis + Qdrant + Stream).
   */
  async write(dataType: string, payload: Record<string, unknown>, actor?: string): Promise<WriteResult> {
    return this.cortex.write(dataType, payload, actor);
  }

  /**
   * Cache get — goes direct to Redis (R1). No Python hop.
   */
  async cacheGet<T = unknown>(key: string): Promise<T | null> {
    return this.redis.get<T>(key);
  }

  /**
   * Cache set — goes direct to Redis (R1). No Python hop.
   */
  async cacheSet(key: string, value: unknown, ttlSeconds?: number): Promise<void> {
    return this.redis.set(key, value, ttlSeconds);
  }

  /** Agent discovery via A2A protocol — routes through CortexDB service. */
  get agents() {
    return {
      discover: (skill: string, limit?: number) => this.cortex.discoverAgents(skill, limit),
      register: (card: Record<string, unknown>) => this.cortex.registerAgent(card),
      list: (options?: { tenant?: string }) => this.cortex.listAgents(options),
    };
  }

  /** Health check for the CortexDB service. */
  async health(): Promise<HealthResult> {
    return this.cortex.health();
  }

  /** Close all connections (PostgreSQL pool + Redis). */
  async close(): Promise<void> {
    await Promise.all([this.pg.close(), this.redis.close()]);
  }

  /**
   * Determines if a query is simple SQL that can go direct to PG,
   * or a CortexQL extension that needs the CortexDB service.
   */
  private isSimpleSQL(query: string): boolean {
    const upper = query.trim().toUpperCase();
    const cortexqlKeywords = [
      'FIND SIMILAR',
      'TRAVERSE',
      'SUBSCRIBE TO',
      'COMMIT TO LEDGER',
      'HINT(',
      'SEARCH_SIMILAR',
      'GRAPH_TRAVERSE',
    ];
    return !cortexqlKeywords.some((kw) => upper.includes(kw));
  }
}
