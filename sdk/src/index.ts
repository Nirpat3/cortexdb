// Main client
export { CortexClient } from './client.js';

// Direct database access
export { DirectPostgres } from './direct/postgres.js';
export type { PostgresConfig } from './direct/postgres.js';
export { DirectRedis } from './direct/redis.js';
export type { RedisConfig } from './direct/redis.js';

// CortexDB service client
export { CortexService, CortexError } from './cortex/service.js';

// Types
export type {
  CortexConfig,
  WriteResult,
  HealthResult,
  QueryResult,
  AgentCard,
  SemanticSearchOptions,
} from './types.js';
