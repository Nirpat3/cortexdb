# CortexDB Installation Guide

## Quick Start

```bash
# 1. Clone the repository
git clone https://github.com/nirlab/cortexdb.git
cd cortexdb

# 2. Run the installer
chmod +x install.sh
./install.sh

# 3. Open the dashboard
# http://localhost:3400
```

The installer handles everything: environment setup, secret generation, Docker services, health checks, and the dashboard build.

---

## Prerequisites

| Dependency       | Minimum Version | Required | Notes                                    |
|------------------|-----------------|----------|------------------------------------------|
| Docker           | 20.10+          | Yes      | Docker Desktop or Docker Engine          |
| Docker Compose   | 2.0+            | Yes      | V2 plugin preferred; standalone works    |
| Node.js          | 18.0+           | Yes      | For the dashboard (LTS recommended)      |
| Python           | 3.12+           | No       | Only for local CortexDB development      |

**Hardware Requirements:**

| Tier         | CPU   | RAM    | Storage   |
|--------------|-------|--------|-----------|
| Minimum      | 2     | 4 GB   | 50 GB SSD |
| Recommended  | 4     | 16 GB  | 200 GB NVMe |
| Enterprise   | 8+    | 32+ GB | 500+ GB NVMe |

---

## Installer Options

```bash
./install.sh              # Full install: Docker + dashboard build
./install.sh --dev        # Full install + start dashboard in dev mode
./install.sh --no-docker  # Dashboard only (assumes CortexDB is running elsewhere)
```

The script is idempotent. Running it again will not overwrite your `.env` or regenerate secrets.

---

## Configuration

The installer creates `.env` from `.env.example` and auto-generates secrets. Key variables:

### Security (auto-generated)

| Variable                | Description                                      |
|-------------------------|--------------------------------------------------|
| `CORTEX_SECRET_KEY`     | 64-char hex key for signing tokens and encryption |
| `CORTEX_ADMIN_TOKEN`    | Admin API authentication token                   |
| `CORTEXDB_MASTER_SECRET`| SuperAdmin passphrase                            |

### Database and Cache

| Variable            | Default                | Description              |
|---------------------|------------------------|--------------------------|
| `POSTGRES_PASSWORD` | `cortex_secret`        | PostgreSQL password      |
| `REDIS_PASSWORD`    | `cortex_redis_secret`  | Redis cache password     |
| `STREAM_PASSWORD`   | `cortex_stream_secret` | Redis Streams password   |

### LLM Providers (optional)

| Variable           | Description                              |
|--------------------|------------------------------------------|
| `ANTHROPIC_API_KEY`| Anthropic Claude API key                 |
| `OPENAI_API_KEY`   | OpenAI API key                           |
| `OLLAMA_BASE_URL`  | Local Ollama endpoint (default: `http://localhost:11434`) |

At least one LLM provider is needed for AI-powered features. Ollama works out of the box if installed locally.

### Ports

| Service          | Default Port | Variable         |
|------------------|-------------|------------------|
| CortexDB API     | 5400        | `CORTEX_PORT`    |
| Health endpoint  | 5401        | -                |
| Admin API        | 5402        | -                |
| Dashboard        | 3400        | `DASHBOARD_PORT` |
| PostgreSQL       | 5432        | -                |
| Redis (cache)    | 6379        | -                |
| Redis (streams)  | 6380        | -                |
| Qdrant (vectors) | 6333        | -                |

---

## Platform Support

CortexDB exposes a standard REST API. Any application that can make HTTP requests can use it, regardless of language or framework.

### REST API

Every query goes through a single endpoint:

```bash
curl http://localhost:5400/v1/query \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  -d '{"cortexql": "SELECT * FROM users WHERE id = $1", "params": [42]}'
```

Response:

```json
{
  "rows": [{"id": 42, "name": "Alice"}],
  "rowCount": 1,
  "duration_ms": 3.2
}
```

### WebSocket (Real-Time Events)

Connect to `ws://localhost:5400/ws` for real-time streaming of events, query subscriptions, and change notifications.

### Docker Compose (Drop Into Any Stack)

Add CortexDB to an existing project by including it as a service:

```yaml
# your-project/docker-compose.yml
services:
  your-app:
    build: .
    environment:
      - DATABASE_URL=http://cortex-router:5400
    depends_on:
      cortex-router:
        condition: service_healthy

  cortex-router:
    image: ghcr.io/nirlab/cortexdb:latest
    ports:
      - "5400:5400"
    environment:
      - CORTEX_SECRET_KEY=${CORTEX_SECRET_KEY}
      - RELATIONAL_CORE_URL=postgresql://cortex:secret@relational-core:5432/cortexdb
      - MEMORY_CORE_URL=redis://memory-core:6379/0
    depends_on:
      relational-core:
        condition: service_healthy
      memory-core:
        condition: service_healthy

  relational-core:
    image: citusdata/citus:12.1
    environment:
      - POSTGRES_USER=cortex
      - POSTGRES_PASSWORD=secret
      - POSTGRES_DB=cortexdb
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U cortex -d cortexdb"]
      interval: 5s
      timeout: 3s
      retries: 5

  memory-core:
    image: redis:7-alpine
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 3
```

### SDK Patterns

CortexDB does not require a proprietary SDK. Use your language's HTTP client to call the REST API.

**Python:**

```python
import httpx

client = httpx.Client(base_url="http://localhost:5400")

resp = client.post("/v1/query", json={
    "cortexql": "SELECT * FROM users WHERE email = $1",
    "params": ["alice@example.com"]
})
rows = resp.json()["rows"]
```

**Node.js / TypeScript:**

```typescript
const res = await fetch("http://localhost:5400/v1/query", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    cortexql: "INSERT INTO events (type, payload) VALUES ($1, $2) RETURNING id",
    params: ["signup", JSON.stringify({ user: "bob" })]
  })
});
const { rows } = await res.json();
```

**Go:**

```go
payload := map[string]interface{}{
    "cortexql": "SELECT count(*) FROM orders WHERE status = $1",
    "params":   []interface{}{"shipped"},
}
body, _ := json.Marshal(payload)

resp, err := http.Post("http://localhost:5400/v1/query", "application/json", bytes.NewReader(body))
```

**Java:**

```java
HttpClient client = HttpClient.newHttpClient();
String json = """
    {"cortexql": "SELECT * FROM products WHERE price < $1", "params": [100]}
    """;

HttpRequest request = HttpRequest.newBuilder()
    .uri(URI.create("http://localhost:5400/v1/query"))
    .header("Content-Type", "application/json")
    .POST(HttpRequest.BodyPublishers.ofString(json))
    .build();

HttpResponse<String> response = client.send(request, HttpResponse.BodyHandlers.ofString());
```

**Ruby:**

```ruby
require "net/http"
require "json"

uri = URI("http://localhost:5400/v1/query")
res = Net::HTTP.post(uri,
  { cortexql: "SELECT * FROM users LIMIT $1", params: [10] }.to_json,
  "Content-Type" => "application/json"
)
rows = JSON.parse(res.body)["rows"]
```

### MCP Integration (AI Assistants)

CortexDB can be used as an MCP (Model Context Protocol) tool server, giving AI assistants direct database access:

```json
{
  "mcpServers": {
    "cortexdb": {
      "url": "http://localhost:5400/mcp",
      "env": {
        "CORTEX_ADMIN_TOKEN": "your-admin-token"
      }
    }
  }
}
```

This lets AI agents query, insert, and manage data through structured tool calls.

---

## Deployment Options

### Docker Compose (Recommended)

The default method. Everything runs in containers with health checks, restart policies, and resource limits.

```bash
# Start all services
docker compose up -d

# Include monitoring (Grafana, Prometheus, Loki, Tempo)
docker compose --profile observability up -d

# Stop
docker compose down

# Stop and remove data
docker compose down -v
```

### Docker (Single Container)

For development or testing, run just the CortexDB router (requires external PostgreSQL and Redis):

```bash
docker build -t cortexdb .

docker run -d \
  --name cortexdb \
  -p 5400:5400 \
  -e CORTEX_SECRET_KEY="$(openssl rand -hex 32)" \
  -e RELATIONAL_CORE_URL="postgresql://user:pass@host:5432/cortexdb" \
  -e MEMORY_CORE_URL="redis://host:6379/0" \
  cortexdb
```

### Kubernetes (Basic)

A minimal deployment for Kubernetes clusters:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: cortexdb
spec:
  replicas: 2
  selector:
    matchLabels:
      app: cortexdb
  template:
    metadata:
      labels:
        app: cortexdb
    spec:
      containers:
        - name: cortexdb
          image: ghcr.io/nirlab/cortexdb:latest
          ports:
            - containerPort: 5400
            - containerPort: 5401
          env:
            - name: CORTEX_SECRET_KEY
              valueFrom:
                secretKeyRef:
                  name: cortexdb-secrets
                  key: secret-key
            - name: RELATIONAL_CORE_URL
              valueFrom:
                secretKeyRef:
                  name: cortexdb-secrets
                  key: database-url
            - name: MEMORY_CORE_URL
              valueFrom:
                secretKeyRef:
                  name: cortexdb-secrets
                  key: redis-url
          livenessProbe:
            httpGet:
              path: /health/live
              port: 5401
            initialDelaySeconds: 10
            periodSeconds: 5
          readinessProbe:
            httpGet:
              path: /health/ready
              port: 5401
            initialDelaySeconds: 15
            periodSeconds: 5
          resources:
            requests:
              cpu: "500m"
              memory: "512Mi"
            limits:
              cpu: "2000m"
              memory: "2Gi"
---
apiVersion: v1
kind: Service
metadata:
  name: cortexdb
spec:
  selector:
    app: cortexdb
  ports:
    - name: api
      port: 5400
      targetPort: 5400
    - name: health
      port: 5401
      targetPort: 5401
  type: ClusterIP
```

Store secrets with:

```bash
kubectl create secret generic cortexdb-secrets \
  --from-literal=secret-key="$(openssl rand -hex 32)" \
  --from-literal=database-url="postgresql://cortex:pass@postgres:5432/cortexdb" \
  --from-literal=redis-url="redis://:pass@redis:6379/0"
```

### Bare Metal

Run CortexDB directly without Docker:

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Set environment variables
export CORTEX_SECRET_KEY="$(openssl rand -hex 32)"
export RELATIONAL_CORE_URL="postgresql://cortex:pass@localhost:5432/cortexdb"
export MEMORY_CORE_URL="redis://localhost:6379/0"
export VECTOR_CORE_URL="http://localhost:6333"
export STREAM_CORE_URL="redis://localhost:6380/0"

# 3. Run database migrations
python -m cortexdb.migrations

# 4. Start the server
python -m cortexdb.main
```

You are responsible for running PostgreSQL (with Citus), Redis (two instances), and Qdrant yourself.

---

## Troubleshooting

### Docker containers fail to start

```bash
# Check container logs
docker compose logs cortex-router
docker compose logs relational-core

# Verify Docker has enough resources (4 GB RAM minimum)
docker info | grep "Total Memory"
```

### Port already in use

```bash
# Find what is using the port
lsof -i :5400    # macOS/Linux
netstat -ano | findstr :5400    # Windows

# Change the port in .env or docker-compose.yml
```

### CortexDB health check never passes

The router depends on PostgreSQL, Redis, and Redis Streams all being healthy first. Check each individually:

```bash
docker compose ps                         # See container status
docker compose logs relational-core       # PostgreSQL logs
docker compose logs memory-core           # Redis cache logs
docker compose logs stream-core           # Redis Streams logs
```

Common causes:
- Insufficient memory (Citus needs at least 1 GB)
- Port conflicts with existing PostgreSQL or Redis instances
- Docker volume corruption (fix: `docker compose down -v && docker compose up -d`)

### Dashboard build fails

```bash
# Clear node_modules and reinstall
cd dashboard
rm -rf node_modules .next
npm install
npm run build
```

Requires Node.js 18+. Check with `node -v`.

### Connection refused from application

- Verify CortexDB is running: `curl http://localhost:5400/health/ready`
- If connecting from inside Docker, use `http://cortex-router:5400` (service name, not localhost)
- Check CORS settings in `.env` if calling from a browser

### Secret key errors

If you see `CORTEX_SECRET_KEY` errors, ensure your `.env` has a valid 64-character hex key:

```bash
# Regenerate
echo "CORTEX_SECRET_KEY=$(openssl rand -hex 32)" >> .env
```

---

## Upgrading

### Minor versions (e.g., 4.0 to 4.1)

```bash
git pull
docker compose up -d --build
cd dashboard && npm install && npm run build
```

### Major versions (e.g., 4.x to 5.x)

1. Back up your data:
   ```bash
   docker compose exec relational-core pg_dump -U cortex cortexdb > backup.sql
   ```

2. Check the CHANGELOG.md for breaking changes.

3. Pull and rebuild:
   ```bash
   git pull
   docker compose down
   docker compose up -d --build
   ```

4. Run any required migrations (documented in release notes).

### Rollback

```bash
git checkout v4.0.0    # or your previous version tag
docker compose down
docker compose up -d --build
```

Data volumes are preserved across rebuilds. Only `docker compose down -v` removes data.
