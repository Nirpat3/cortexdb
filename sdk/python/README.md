# cortexdb-client

Python client for [CortexDB](https://cortexdb.io) — the AI-native database.

## Installation

```bash
pip install cortexdb-client
```

## Quick Start

### Query & Write

```python
from cortexdb_client import CortexDBClient

client = CortexDBClient("http://localhost:5400")

# Read
result = client.query("SELECT * FROM users WHERE age > $1", [30])
for row in result:
    print(row["name"], row["email"])

# Write
client.write(
    "INSERT INTO users (name, email) VALUES ($1, $2)",
    ["Alice", "alice@example.com"],
)

# Health check
status = client.health()
print(status)
```

### Context Manager

```python
with CortexDBClient("http://localhost:5400", api_key="sk-...") as db:
    result = db.query("SELECT count(*) AS total FROM events")
    print(result.rows[0]["total"])
```

### SuperAdmin Operations

```python
from cortexdb_client import SuperAdminClient

admin = SuperAdminClient("http://localhost:5400")
admin.login("my-superadmin-passphrase")

# List agents
agents = admin.list_agents()
for a in agents:
    print(a["id"], a["name"])

# Create a task
task = admin.create_task(
    agent_id="T1-OPS-POS-001",
    instruction="Analyze server logs for the last 24 hours",
    priority=8,
)

# Chat with an agent
response = admin.chat("T1-OPS-POS-001", "What is the current system status?")
print(response)

# Marketplace
items = admin.marketplace_list()
admin.marketplace_enable(items[0]["id"])
```

## Error Handling

```python
from cortexdb_client import CortexDBClient, CortexDBError, QueryError, ConnectionError

try:
    client = CortexDBClient("http://localhost:5400")
    result = client.query("SELECT * FROM nonexistent_table")
except ConnectionError:
    print("Cannot reach CortexDB")
except QueryError as e:
    print(f"Query failed ({e.status_code}): {e}")
except CortexDBError as e:
    print(f"Unexpected error: {e}")
```

## API Reference

### CortexDBClient

| Method | Description |
|--------|-------------|
| `query(cortexql, params=None)` | Execute a read query |
| `write(cortexql, params=None)` | Execute a write operation |
| `health()` | Basic readiness check |
| `deep_health()` | Deep health check (all engines) |
| `close()` | Close connection pool |

### SuperAdminClient

| Method | Description |
|--------|-------------|
| `login(passphrase)` | Authenticate and store JWT |
| `list_agents(**filters)` | List agents |
| `get_agent(agent_id)` | Get single agent |
| `create_task(agent_id, instruction, ...)` | Create a task |
| `list_tasks(**filters)` | List tasks |
| `chat(agent_id, message)` | Chat with an agent |
| `marketplace_list()` | List marketplace items |
| `marketplace_enable(item_id)` | Enable a marketplace item |
| `marketplace_disable(item_id)` | Disable a marketplace item |

## License

MIT
