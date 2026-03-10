# @cortexdb/sdk

TypeScript SDK for CortexDB. Provides direct database access for simple queries and intelligent routing through the CortexDB service for cross-engine operations.

## Why a SDK?

CortexDB's value is cross-engine intelligence: semantic caching, write fan-out, agent discovery. Simple CRUD doesn't need to go through an HTTP->Python->PostgreSQL chain. This SDK routes queries to the right place:

| Operation | Route | Latency |
|-----------|-------|---------|
| Simple SQL (SELECT, INSERT, etc.) | Direct -> PostgreSQL | ~1ms |
| Cache get/set | Direct -> Redis | ~0.5ms |
| Semantic search | CortexDB service -> Qdrant + PG | ~5-25ms |
| Write fan-out | CortexDB service -> PG + Redis + Stream | ~8ms |
| Agent discovery | CortexDB service -> A2A registry | ~10ms |

## Install

```bash
npm install @cortexdb/sdk
```

## Quick Start

```typescript
import { CortexClient } from '@cortexdb/sdk';

const db = new CortexClient({
  postgres: { connectionString: process.env.DATABASE_URL },
  redis: { url: process.env.REDIS_URL },
  cortexUrl: process.env.CORTEXDB_URL ?? 'http://localhost:8000',
});

// Direct to PostgreSQL (no Python hop)
const users = await db.sql('SELECT * FROM users WHERE id = $1', [userId]);

// Smart routing: simple SQL goes direct, CortexQL goes through service
const results = await db.query('SELECT * FROM orders WHERE user_id = $1', [userId]);

// Semantic search (routes through CortexDB service - needs embeddings)
const similar = await db.search('machine learning frameworks', {
  collection: 'documents',
  limit: 5,
});

// Write fan-out (routes through CortexDB service - multi-engine)
await db.write('user_event', { user_id: userId, action: 'login' });

// Direct Redis cache (no Python hop)
await db.cacheSet('session:abc', { userId: 1 }, 3600);
const session = await db.cacheGet('session:abc');

// Agent discovery (routes through CortexDB service - A2A protocol)
const agents = await db.agents.discover('summarization');

// Clean up
await db.close();
```

## Architecture

```
Simple CRUD:     TS SDK -> pg driver -> PostgreSQL       (1 hop, direct)
Semantic search: TS SDK -> CortexDB service -> Qdrant+PG (justified)
Write fan-out:   TS SDK -> CortexDB service -> PG+Redis  (justified)
Agent ops:       TS SDK -> CortexDB service -> A2A/MCP   (justified)
Cache read:      TS SDK -> Redis (direct)                (1 hop, direct)
```

## Direct Access

When you know the operation is simple, use the direct clients:

```typescript
// Direct PostgreSQL
const rows = await db.pg.query('SELECT * FROM users');
const user = await db.pg.queryOne('SELECT * FROM users WHERE id = $1', [1]);
const count = await db.pg.execute('DELETE FROM sessions WHERE expired_at < NOW()');

// Transactions
await db.pg.transaction(async (query) => {
  await query('UPDATE accounts SET balance = balance - $1 WHERE id = $2', [100, fromId]);
  await query('UPDATE accounts SET balance = balance + $1 WHERE id = $2', [100, toId]);
});

// Direct Redis
await db.redis.set('key', { data: 'value' }, 300);
const val = await db.redis.get('key');
await db.redis.del('key');
```

## License

MIT
