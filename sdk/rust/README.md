# CortexDB Rust Client

Official Rust client library for [CortexDB](https://github.com/nirlab/cortexdb).

## Installation

Add to your `Cargo.toml`:

```toml
[dependencies]
cortexdb-client = "0.1"
tokio = { version = "1", features = ["full"] }
```

## Quick Start

### Basic Query

```rust
use cortexdb_client::CortexDBClient;
use serde_json::json;

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let client = CortexDBClient::with_api_key("http://localhost:3001", "your-api-key");

    // Health check
    let health = client.health().await?;
    println!("CortexDB status: {} (v{})",
        health.status,
        health.version.unwrap_or_default()
    );

    // Query
    let result = client.query(
        "SELECT * FROM agents WHERE tier = $1",
        Some(json!({"$1": "T1"})),
    ).await?;
    println!("Found {} agents", result.count);
    for row in &result.rows {
        println!("  {} - {}", row["id"], row["name"]);
    }

    // Write
    let wr = client.write(
        "INSERT INTO metrics (agent_id, value) VALUES ($1, $2)",
        Some(json!({"$1": "T1-OPS-POS-001", "$2": 42})),
    ).await?;
    println!("Rows affected: {}", wr.rows_affected);

    Ok(())
}
```

### Super Admin Operations

```rust
use cortexdb_client::{SuperAdminClient, CreateTask};

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut admin = SuperAdminClient::new("http://localhost:3001", Some("your-api-key"));

    // Authenticate
    admin.login("your-passphrase").await?;

    // List agents
    let agents = admin.list_agents().await?;
    for a in &agents {
        println!("[{}] {} - {}", a.tier, a.id, a.name);
    }

    // Create a task
    let task = admin.create_task(&CreateTask {
        agent_id: "T1-OPS-POS-001".to_string(),
        task_type: "analysis".to_string(),
        priority: Some("high".to_string()),
        instruction: "Analyze system performance for the last 24 hours".to_string(),
        input: None,
        parent_id: None,
    }).await?;
    println!("Task created: {} (status: {})", task.id, task.status);

    // Chat with an agent
    let chat = admin.chat("T1-OPS-POS-001", "What is the current system status?").await?;
    println!("Agent response: {}", chat.response);

    // Marketplace
    let caps = admin.marketplace_list().await?;
    for c in &caps {
        let status = if c.enabled { "enabled" } else { "disabled" };
        println!("  [{}] {} - {}", status, c.name, c.description);
    }

    // Enable/disable capabilities
    admin.marketplace_enable("some-capability-id").await?;
    admin.marketplace_disable("some-capability-id").await?;

    Ok(())
}
```

### Error Handling

```rust
use cortexdb_client::{CortexDBClient, CortexDBError};

#[tokio::main]
async fn main() {
    let client = CortexDBClient::new("http://localhost:3001");

    match client.query("SELECT * FROM nonexistent", None).await {
        Ok(result) => println!("Got {} rows", result.count),
        Err(CortexDBError::Auth { status, body }) => {
            eprintln!("Authentication failed (HTTP {}): {}", status, body);
        }
        Err(CortexDBError::Query { status, body }) => {
            eprintln!("Query failed (HTTP {}): {}", status, body);
        }
        Err(CortexDBError::Connection(e)) => {
            eprintln!("Connection error: {}", e);
        }
        Err(e) => {
            eprintln!("Unexpected error: {}", e);
        }
    }
}
```

### Deep Health Check

```rust
use cortexdb_client::CortexDBClient;

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let client = CortexDBClient::new("http://localhost:3001");

    let deep = client.deep_health().await?;
    println!("Deep health: {}", serde_json::to_string_pretty(&deep)?);

    Ok(())
}
```

## API Reference

### CortexDBClient Methods

| Method | Description |
|--------|-------------|
| `new(base_url)` | Create client without API key |
| `with_api_key(base_url, key)` | Create client with API key |
| `with_client(base_url, key, client)` | Create with custom reqwest::Client |
| `query(cortexql, params)` | Execute a read query |
| `write(cortexql, params)` | Execute a write operation |
| `health()` | Check instance readiness |
| `deep_health()` | Detailed health from all cores |

### SuperAdminClient Methods

| Method | Description |
|--------|-------------|
| `new(base_url, api_key)` | Create super-admin client |
| `core()` | Access underlying CortexDBClient |
| `login(passphrase)` | Authenticate as super admin |
| `list_agents()` | List all agents |
| `get_agent(id)` | Get agent by ID |
| `create_task(task)` | Create a new task |
| `list_tasks()` | List all tasks |
| `chat(agent_id, message)` | Chat with an agent |
| `marketplace_list()` | List marketplace capabilities |
| `marketplace_enable(id)` | Enable a capability |
| `marketplace_disable(id)` | Disable a capability |

### Error Variants

| Variant | Description |
|---------|-------------|
| `Connection` | Network or connection failure |
| `Auth { status, body }` | HTTP 401/403 |
| `Query { status, body }` | Query rejected by server |
| `Api(status, body)` | General API error |
| `Serialization` | JSON encoding/decoding failure |

## License

MIT
