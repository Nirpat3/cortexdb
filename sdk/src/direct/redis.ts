import Redis from 'ioredis';

export interface RedisConfig {
  url?: string;
  host?: string;
  port?: number;
  password?: string;
  db?: number;
}

export class DirectRedis {
  private client: Redis;

  constructor(config: RedisConfig) {
    if (config.url) {
      this.client = new Redis(config.url);
    } else {
      this.client = new Redis({
        host: config.host ?? 'localhost',
        port: config.port ?? 6379,
        password: config.password,
        db: config.db ?? 0,
      });
    }
  }

  /** Get a value by key. Automatically parses JSON if possible. */
  async get<T = unknown>(key: string): Promise<T | null> {
    const value = await this.client.get(key);
    if (value === null) return null;
    try {
      return JSON.parse(value) as T;
    } catch {
      return value as unknown as T;
    }
  }

  /** Set a value by key. Objects are JSON-serialized. Optional TTL in seconds. */
  async set(key: string, value: unknown, ttlSeconds?: number): Promise<void> {
    const serialized = typeof value === 'string' ? value : JSON.stringify(value);
    if (ttlSeconds) {
      await this.client.set(key, serialized, 'EX', ttlSeconds);
    } else {
      await this.client.set(key, serialized);
    }
  }

  /** Delete a key. */
  async del(key: string): Promise<void> {
    await this.client.del(key);
  }

  /** Check if a key exists. */
  async exists(key: string): Promise<boolean> {
    return (await this.client.exists(key)) === 1;
  }

  /** Find keys matching a glob pattern. Use with caution in production. */
  async keys(pattern: string): Promise<string[]> {
    return this.client.keys(pattern);
  }

  /** Close the Redis connection. */
  async close(): Promise<void> {
    this.client.disconnect();
  }
}
