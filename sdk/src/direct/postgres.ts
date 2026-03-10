import { Pool, type PoolConfig } from 'pg';

export interface PostgresConfig {
  connectionString?: string;
  host?: string;
  port?: number;
  database?: string;
  user?: string;
  password?: string;
  max?: number;
  ssl?: boolean | object;
}

export class DirectPostgres {
  private pool: Pool;

  constructor(config: PostgresConfig) {
    const poolConfig: PoolConfig = config.connectionString
      ? { connectionString: config.connectionString, max: config.max ?? 20 }
      : {
          host: config.host ?? 'localhost',
          port: config.port ?? 5432,
          database: config.database ?? 'cortexdb',
          user: config.user ?? 'cortex',
          password: config.password,
          max: config.max ?? 20,
          ssl: config.ssl,
        };
    this.pool = new Pool(poolConfig);
  }

  /** Execute a query and return all rows. */
  async query<T = Record<string, unknown>>(sql: string, params?: unknown[]): Promise<T[]> {
    const result = await this.pool.query(sql, params);
    return result.rows as T[];
  }

  /** Execute a query and return the first row, or null if no rows. */
  async queryOne<T = Record<string, unknown>>(sql: string, params?: unknown[]): Promise<T | null> {
    const rows = await this.query<T>(sql, params);
    return rows[0] ?? null;
  }

  /** Execute a statement and return the number of affected rows. */
  async execute(sql: string, params?: unknown[]): Promise<number> {
    const result = await this.pool.query(sql, params);
    return result.rowCount ?? 0;
  }

  /** Run a callback within a database transaction. */
  async transaction<T>(
    fn: (query: (sql: string, params?: unknown[]) => Promise<Record<string, unknown>[]>) => Promise<T>,
  ): Promise<T> {
    const client = await this.pool.connect();
    try {
      await client.query('BEGIN');
      const queryFn = async (sql: string, params?: unknown[]): Promise<Record<string, unknown>[]> => {
        const result = await client.query(sql, params);
        return result.rows as Record<string, unknown>[];
      };
      const result = await fn(queryFn);
      await client.query('COMMIT');
      return result;
    } catch (err) {
      await client.query('ROLLBACK');
      throw err;
    } finally {
      client.release();
    }
  }

  /** Close the connection pool. */
  async close(): Promise<void> {
    await this.pool.end();
  }
}
