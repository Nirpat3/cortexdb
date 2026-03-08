# CortexDB Platform Integration Guide

**How to integrate CortexDB into any application stack.**

CortexDB exposes a standard REST API. Any language, framework, or platform that can make HTTP requests can use CortexDB as its data layer. This guide covers integration patterns, code examples, and migration paths.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Integration Patterns](#2-integration-patterns)
3. [Supported Use Cases](#3-supported-use-cases)
4. [Migration from Existing Databases](#4-migration-from-existing-databases)
5. [API Quick Reference](#5-api-quick-reference)

---

## 1. Architecture Overview

```
Your Application (any language/framework)
        |
        | HTTP / WebSocket
        v
  +-----------------+
  | cortex-router   |  <-- Port 5400 (REST API + WebSocket)
  | (FastAPI)       |
  +-----------------+
        |
        +--- relational-core (Citus/PostgreSQL, port 5432)
        +--- memory-core (Redis, port 6379)
        +--- stream-core (Redis Streams, port 6380)
        +--- vector-core (Qdrant, port 6333)
```

Key points:

- **REST API on port 5400** -- the single entry point for all data operations. Accepts CortexQL (a SQL superset) via `POST /v1/query`.
- **SuperAdmin Dashboard on port 3400** -- optional web UI for monitoring, tenant management, and configuration. Not required for application integration.
- **WebSocket on `/ws/events`** -- real-time event streaming for applications that need push notifications or live data feeds.
- **Multi-engine routing** -- the router automatically directs queries to the appropriate backend engine (relational, cache, vector, graph, time-series, stream, ledger) based on query analysis.

Your application never connects to the underlying engines directly. All access goes through the router.

---

## 2. Integration Patterns

### 2.1 Direct REST API

Every integration starts with a single HTTP call. Here is the same query in six languages.

**Query:**
```
POST /v1/query
Content-Type: application/json
Authorization: Bearer YOUR_API_KEY

{ "cortexql": "SELECT * FROM users WHERE age > 25" }
```

**Python**
```python
import httpx

resp = httpx.post("http://localhost:5400/v1/query",
    headers={"Authorization": "Bearer YOUR_API_KEY"},
    json={"cortexql": "SELECT * FROM users WHERE age > 25"})

data = resp.json()["data"]
```

**Node.js**
```javascript
const resp = await fetch("http://localhost:5400/v1/query", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "Authorization": "Bearer YOUR_API_KEY",
  },
  body: JSON.stringify({ cortexql: "SELECT * FROM users WHERE age > 25" }),
});

const { data } = await resp.json();
```

**Go**
```go
package main

import (
    "bytes"
    "encoding/json"
    "net/http"
)

func query() ([]map[string]interface{}, error) {
    body, _ := json.Marshal(map[string]string{
        "cortexql": "SELECT * FROM users WHERE age > 25",
    })
    req, _ := http.NewRequest("POST", "http://localhost:5400/v1/query",
        bytes.NewBuffer(body))
    req.Header.Set("Content-Type", "application/json")
    req.Header.Set("Authorization", "Bearer YOUR_API_KEY")

    resp, err := http.DefaultClient.Do(req)
    if err != nil {
        return nil, err
    }
    defer resp.Body.Close()

    var result struct {
        Data []map[string]interface{} `json:"data"`
    }
    json.NewDecoder(resp.Body).Decode(&result)
    return result.Data, nil
}
```

**Java**
```java
import java.net.http.*;
import java.net.URI;

HttpClient client = HttpClient.newHttpClient();
HttpRequest request = HttpRequest.newBuilder()
    .uri(URI.create("http://localhost:5400/v1/query"))
    .header("Content-Type", "application/json")
    .header("Authorization", "Bearer YOUR_API_KEY")
    .POST(HttpRequest.BodyPublishers.ofString(
        "{\"cortexql\": \"SELECT * FROM users WHERE age > 25\"}"))
    .build();

HttpResponse<String> response = client.send(request,
    HttpResponse.BodyHandlers.ofString());
// Parse response.body() with your preferred JSON library
```

**Ruby**
```ruby
require "net/http"
require "json"

uri = URI("http://localhost:5400/v1/query")
req = Net::HTTP::Post.new(uri)
req["Content-Type"] = "application/json"
req["Authorization"] = "Bearer YOUR_API_KEY"
req.body = { cortexql: "SELECT * FROM users WHERE age > 25" }.to_json

resp = Net::HTTP.start(uri.hostname, uri.port) { |http| http.request(req) }
data = JSON.parse(resp.body)["data"]
```

**C#**
```csharp
using System.Net.Http;
using System.Text;
using System.Text.Json;

var client = new HttpClient();
client.DefaultRequestHeaders.Add("Authorization", "Bearer YOUR_API_KEY");

var content = new StringContent(
    JsonSerializer.Serialize(new { cortexql = "SELECT * FROM users WHERE age > 25" }),
    Encoding.UTF8, "application/json");

var response = await client.PostAsync("http://localhost:5400/v1/query", content);
var json = await response.Content.ReadAsStringAsync();
```

All six produce the same response:
```json
{
  "data": [{"id": 1, "name": "Alice", "age": 30}, ...],
  "tier_served": "R3",
  "engines_hit": ["relational_core"],
  "latency_ms": 3.2,
  "cache_hit": false
}
```

---

### 2.2 As a Docker Sidecar

Add CortexDB alongside your existing application with no infrastructure changes. Append this to your existing `docker-compose.yml`:

```yaml
services:
  # Your existing app
  my-app:
    build: .
    ports:
      - "8080:8080"
    environment:
      - DATABASE_URL=http://cortex-router:5400
    depends_on:
      cortex-router:
        condition: service_healthy

  # CortexDB stack
  cortex-router:
    image: nirlab/cortexdb-router:latest
    ports:
      - "5400:5400"
    environment:
      - RELATIONAL_HOST=relational-core
      - MEMORY_HOST=memory-core
      - VECTOR_HOST=vector-core
      - STREAM_HOST=stream-core
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:5400/health/live"]
      interval: 10s
      timeout: 5s
      retries: 3
    depends_on:
      - relational-core
      - memory-core
      - vector-core
      - stream-core

  relational-core:
    image: citusdata/citus:12.1
    environment:
      - POSTGRES_PASSWORD=cortex
      - POSTGRES_DB=cortexdb
    volumes:
      - cortex-relational:/var/lib/postgresql/data

  memory-core:
    image: redis:7-alpine
    command: redis-server --maxmemory 512mb --maxmemory-policy allkeys-lru

  vector-core:
    image: qdrant/qdrant:latest
    volumes:
      - cortex-vector:/qdrant/storage

  stream-core:
    image: redis:7-alpine
    command: redis-server --port 6380

volumes:
  cortex-relational:
  cortex-vector:
```

Your app connects to `http://cortex-router:5400` on the Docker network. No ports are exposed to the host except those you choose.

---

### 2.3 As a Microservice

In a microservice architecture, CortexDB serves as the shared data platform. Each service talks to CortexDB over HTTP, isolated by tenant or namespace.

```
                 +-----------+
                 | API       |
                 | Gateway   |
                 +-----+-----+
                       |
          +------------+------------+
          |            |            |
     +----v---+  +----v---+  +----v---+
     | User   |  | Order  |  | Search |
     | Service|  | Service|  | Service|
     +----+---+  +----+---+  +----+---+
          |            |            |
          +------------+------------+
                       |
                 +-----v-----+
                 | CortexDB  |
                 | Router    |
                 | :5400     |
                 +-----------+
```

Each microservice queries CortexDB using its own API key (or shared tenant key). CortexDB handles:

- **Relational queries** -- User Service reads/writes user records.
- **Cache** -- Order Service caches hot order lookups via `hint: "cache_first"`.
- **Vector search** -- Search Service runs `FIND SIMILAR TO '...' IN products LIMIT 20`.
- **Event streaming** -- All services publish events via `POST /v1/write` with `data_type: "event"`.

No service-to-service database coupling. No shared connection pools. Each service treats CortexDB as a stateless HTTP endpoint.

---

### 2.4 With AI/LLM Applications

CortexDB is built for AI agent workflows. Agents use it for persistent memory, knowledge retrieval, and tool execution.

**Agent Memory (store and recall)**
```python
# Store a memory
await cortex.write("experience", {
    "agent_id": "agent-001",
    "content": "User prefers dark mode and metric units",
    "memory_type": "long_term",
    "embedding": embedding_vector  # 1536-dim float array
})

# Recall by semantic similarity
result = await cortex.query(
    "FIND SIMILAR TO 'user display preferences' IN agent_memories LIMIT 5",
    hint="cache_first"
)
```

**RAG (Retrieval-Augmented Generation)**
```python
# 1. Embed the user question
embedding = await openai.embeddings.create(input=question, model="text-embedding-3-small")

# 2. Search CortexDB for relevant documents
results = await cortex.query(
    "FIND SIMILAR TO $1 IN documents LIMIT 10",
    params={"$1": embedding.data[0].embedding}
)

# 3. Pass context to LLM
context = "\n".join([r["content"] for r in results["data"]])
answer = await llm.complete(f"Context:\n{context}\n\nQuestion: {question}")
```

**MCP Tool Integration**

CortexDB exposes an MCP (Model Context Protocol) endpoint that AI agents can call as a tool:

```json
{
  "tool": "cortexdb_query",
  "arguments": {
    "cortexql": "SELECT name, email FROM customers WHERE region = 'APAC' LIMIT 10"
  }
}
```

This allows frameworks like LangChain, LangGraph, and CrewAI to use CortexDB directly as an agent tool without custom adapters.

---

### 2.5 With Web Frameworks

Each example shows the minimal setup to wire CortexDB into a popular framework.

**Express.js (Node.js)**
```javascript
const express = require("express");
const app = express();

async function dbQuery(sql, params) {
  const res = await fetch("http://localhost:5400/v1/query", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ cortexql: sql, params }),
  });
  return (await res.json()).data;
}

app.get("/users", async (req, res) => {
  const users = await dbQuery("SELECT * FROM users LIMIT 50");
  res.json(users);
});

app.listen(3000);
```

**FastAPI (Python)**
```python
from fastapi import FastAPI
import httpx

app = FastAPI()
CORTEX_URL = "http://localhost:5400/v1/query"

async def db_query(sql: str, params: dict = None):
    async with httpx.AsyncClient() as client:
        resp = await client.post(CORTEX_URL, json={"cortexql": sql, "params": params})
        return resp.json()["data"]

@app.get("/users")
async def get_users():
    return await db_query("SELECT * FROM users LIMIT 50")
```

**Django (Python)**
```python
# views.py
import requests
from django.http import JsonResponse

CORTEX_URL = "http://localhost:5400/v1/query"

def user_list(request):
    resp = requests.post(CORTEX_URL, json={
        "cortexql": "SELECT * FROM users LIMIT 50"
    })
    return JsonResponse(resp.json()["data"], safe=False)
```

**Ruby on Rails**
```ruby
# app/controllers/users_controller.rb
class UsersController < ApplicationController
  CORTEX_URL = "http://localhost:5400/v1/query"

  def index
    resp = Net::HTTP.post(
      URI(CORTEX_URL),
      { cortexql: "SELECT * FROM users LIMIT 50" }.to_json,
      "Content-Type" => "application/json"
    )
    render json: JSON.parse(resp.body)["data"]
  end
end
```

**Spring Boot (Java)**
```java
@RestController
public class UserController {
    private final RestTemplate rest = new RestTemplate();
    private static final String CORTEX_URL = "http://localhost:5400/v1/query";

    @GetMapping("/users")
    public Object getUsers() {
        var body = Map.of("cortexql", "SELECT * FROM users LIMIT 50");
        var resp = rest.postForObject(CORTEX_URL, body, Map.class);
        return resp.get("data");
    }
}
```

**ASP.NET (C#)**
```csharp
[ApiController]
[Route("[controller]")]
public class UsersController : ControllerBase
{
    private static readonly HttpClient _http = new();
    private const string CortexUrl = "http://localhost:5400/v1/query";

    [HttpGet]
    public async Task<IActionResult> GetUsers()
    {
        var content = new StringContent(
            JsonSerializer.Serialize(new { cortexql = "SELECT * FROM users LIMIT 50" }),
            Encoding.UTF8, "application/json");
        var resp = await _http.PostAsync(CortexUrl, content);
        var json = await resp.Content.ReadAsStringAsync();
        return Content(json, "application/json");
    }
}
```

---

### 2.6 With Mobile Apps

CortexDB's REST API works from any HTTP client. No special SDK is required.

**iOS (Swift / URLSession)**
```swift
let url = URL(string: "https://your-cortexdb-host.com/v1/query")!
var request = URLRequest(url: url)
request.httpMethod = "POST"
request.setValue("application/json", forHTTPHeaderField: "Content-Type")
request.setValue("Bearer \(apiKey)", forHTTPHeaderField: "Authorization")
request.httpBody = try JSONEncoder().encode(["cortexql": "SELECT * FROM products LIMIT 20"])

let (data, _) = try await URLSession.shared.data(for: request)
let result = try JSONDecoder().decode(CortexResponse.self, from: data)
```

**Android (Kotlin / Retrofit)**
```kotlin
interface CortexApi {
    @POST("v1/query")
    suspend fun query(@Body body: Map<String, String>): CortexResponse
}

// Usage
val result = cortexApi.query(mapOf("cortexql" to "SELECT * FROM products LIMIT 20"))
```

**Flutter (Dart / http)**
```dart
final response = await http.post(
  Uri.parse('https://your-cortexdb-host.com/v1/query'),
  headers: {'Content-Type': 'application/json', 'Authorization': 'Bearer $apiKey'},
  body: jsonEncode({'cortexql': 'SELECT * FROM products LIMIT 20'}),
);
final data = jsonDecode(response.body)['data'];
```

For mobile, always route through your backend or API gateway in production. Direct mobile-to-CortexDB connections should only be used for prototyping.

---

### 2.7 Real-Time via WebSocket

Connect to `/ws/events` for live event streaming:

```javascript
const ws = new WebSocket("ws://localhost:5400/ws/events");

ws.onopen = () => {
  // Subscribe to specific event types
  ws.send(JSON.stringify({
    action: "subscribe",
    channels: ["events:purchase_completed", "events:user_signup"]
  }));
};

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log("Event received:", data);
};
```

---

## 3. Supported Use Cases

CortexDB replaces seven specialized databases with one system. Each use case maps to an internal engine.

| Use Case | Engine | How to Use |
|----------|--------|------------|
| Relational queries (CRUD, joins, transactions) | RelationalCore (Citus/PostgreSQL) | Standard SQL via `POST /v1/query` |
| Cache layer (sessions, hot data) | MemoryCore (Redis) | Use `hint: "cache_first"` or write with `data_type` that targets memory |
| Vector search (embeddings, RAG, similarity) | VectorCore (Qdrant) | `FIND SIMILAR TO '...' IN collection LIMIT N` |
| Graph queries (relationships, traversals) | GraphCore (Apache AGE) | `TRAVERSE Node->EDGE->Node DEPTH N` |
| Time-series data (metrics, IoT, heartbeats) | TemporalCore (TimescaleDB) | `time_bucket()` functions, automatic hypertable routing |
| Event streaming (pub/sub, event sourcing) | StreamCore (Redis Streams) | `SUBSCRIBE TO channel` or `POST /v1/write` with event data |
| Blockchain/audit trail (immutable records) | ImmutableCore | `COMMIT TO LEDGER {...}` -- SHA-256 hash chain, append-only |

All seven engines are accessed through the same `POST /v1/query` endpoint. The router analyzes your CortexQL statement and directs it to the right engine automatically.

### Combined Queries

A single application can use all engines without managing separate connections:

```python
# Relational
users = await db.query("SELECT * FROM users WHERE region = 'EU'")

# Vector search
similar = await db.query("FIND SIMILAR TO 'data engineer with Python' IN resumes LIMIT 5")

# Graph traversal
network = await db.query("TRAVERSE User->FOLLOWS->User DEPTH 3")

# Time-series
metrics = await db.query("""
    SELECT time_bucket('1 hour', ts) AS hour, AVG(value) AS avg_val
    FROM sensor_readings WHERE ts > NOW() - INTERVAL '24 hours'
    GROUP BY hour ORDER BY hour
""")

# Immutable audit
await db.query("COMMIT TO LEDGER { type: 'ACCESS', actor: 'admin', resource: 'users' }")
```

---

## 4. Migration from Existing Databases

CortexDB accepts standard SQL, so migrations from existing systems are straightforward.

### From PostgreSQL

Lowest friction. CortexDB's relational engine is PostgreSQL (via Citus).

1. Export your schema: `pg_dump --schema-only > schema.sql`
2. Run the schema through CortexDB: `POST /v1/query` with each `CREATE TABLE` statement.
3. Export data: `pg_dump --data-only --format=csv`
4. Import via `POST /v1/write` in batches or use the bulk import endpoint.

Most PostgreSQL extensions (PostGIS, pg_trgm, hstore) work out of the box since the relational engine is PostgreSQL.

### From MongoDB

Map collections to tables. CortexDB supports JSONB columns for document-style storage.

```sql
CREATE TABLE products (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    data JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Query documents with JSON operators
SELECT data->>'name' AS name, data->'price' AS price
FROM products
WHERE data @> '{"category": "electronics"}';
```

Export from MongoDB with `mongoexport --jsonArray`, then insert via `POST /v1/write`.

### From Redis

CortexDB's MemoryCore is Redis. For cache workloads, no migration is needed -- just point your cache reads to CortexDB with `hint: "cache_first"`. For persistent Redis data, export with `redis-cli --rdb` and reimport, or replay writes through the CortexDB API.

### From Pinecone / Weaviate (Vector DBs)

Export your vectors and metadata. Insert into CortexDB:

```python
await cortex.write("block", {
    "content": "document text here",
    "embedding": [0.1, 0.2, ...],  # your existing vector
    "metadata": {"source": "pinecone_migration"}
})
```

Then query with `FIND SIMILAR TO ... IN collection LIMIT N`.

### From Neo4j (Graph DB)

Export nodes and edges as CSV. Create them in CortexDB's GraphCore:

```sql
-- Create nodes
TRAVERSE CREATE (u:User {id: 'U-1', name: 'Alice'})

-- Create edges
TRAVERSE MATCH (a:User {id: 'U-1'}), (b:User {id: 'U-2'})
         CREATE (a)-[:FOLLOWS]->(b)
```

CortexDB uses Apache AGE, which supports Cypher syntax within the `TRAVERSE` directive.

---

## 5. API Quick Reference

All endpoints are served from `http://localhost:5400`.

### Core Data Operations

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/v1/query` | Execute a CortexQL query (SELECT, FIND SIMILAR, TRAVERSE, etc.) |
| POST | `/v1/write` | Write data with automatic fan-out to relevant engines |
| POST | `/v1/query` + `SUBSCRIBE` | Start a real-time subscription to a stream channel |
| POST | `/v1/query` + `COMMIT TO LEDGER` | Append an immutable record to the audit chain |

### CortexGraph (Customer Intelligence)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/v1/cortexgraph/identify` | Resolve identifiers to a unified customer profile |
| POST | `/v1/cortexgraph/track` | Record a customer event |
| POST | `/v1/cortexgraph/track/batch` | Record multiple events in one call |
| GET | `/v1/cortexgraph/customer/{id}/360` | Full customer 360 view (identity, events, relationships, scores) |
| POST | `/v1/cortexgraph/segment/query` | Query a customer segment by criteria |

### Tenant Administration

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/v1/admin/tenants` | Create a new tenant |
| POST | `/v1/admin/tenants/{id}/activate` | Activate a tenant |
| POST | `/v1/admin/tenants/{id}/suspend` | Suspend a tenant |
| POST | `/v1/admin/tenants/{id}/export` | Export all tenant data (GDPR compliance) |
| POST | `/v1/admin/tenants/{id}/purge` | Permanently delete a tenant |

### Health and Monitoring

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health/live` | Liveness probe (is the router running?) |
| GET | `/health/ready` | Readiness probe (are all engines connected?) |
| GET | `/metrics` | Prometheus-format metrics |

### WebSocket

| Endpoint | Description |
|----------|-------------|
| `ws://host:5400/ws/events` | Real-time event stream; send `subscribe`/`unsubscribe` messages |

### Query Hints

Pass `"hint"` in the query body to control routing behavior:

| Hint | Effect |
|------|--------|
| `cache_first` | Check MemoryCore before hitting RelationalCore |
| `skip_semantic` | Bypass the R2 semantic cache layer |
| `force_refresh` | Skip all caches, query the source engine directly |

---

## Summary

CortexDB works with any platform that can make HTTP requests. There is no proprietary protocol, no mandatory SDK, and no language lock-in. Start with `POST /v1/query`, add a Docker sidecar to your existing stack, and progressively adopt vector search, graph queries, and event streaming as your application needs grow.

For detailed query syntax, see the [Developer Guide](./developer-guide.md). For deployment options, see the [Docker Guide](./docker-guide.md).
