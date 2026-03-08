# CortexDB Go Client

Official Go client library for [CortexDB](https://github.com/nirlab/cortexdb).

## Installation

```bash
go get github.com/nirlab/cortexdb-client-go/cortexdb
```

## Quick Start

### Basic Query

```go
package main

import (
    "context"
    "fmt"
    "log"
    "time"

    "github.com/nirlab/cortexdb-client-go/cortexdb"
)

func main() {
    client := cortexdb.NewClient("http://localhost:3001",
        cortexdb.WithAPIKey("your-api-key"),
        cortexdb.WithTimeout(10*time.Second),
    )
    defer client.Close()

    ctx := context.Background()

    // Health check
    health, err := client.Health(ctx)
    if err != nil {
        log.Fatal(err)
    }
    fmt.Printf("CortexDB status: %s (v%s)\n", health.Status, health.Version)

    // Query
    result, err := client.Query(ctx, "SELECT * FROM agents WHERE tier = $1", map[string]any{
        "$1": "T1",
    })
    if err != nil {
        log.Fatal(err)
    }
    fmt.Printf("Found %d agents\n", result.Count)
    for _, row := range result.Rows {
        fmt.Printf("  %s — %s\n", row["id"], row["name"])
    }

    // Write
    wr, err := client.Write(ctx, "INSERT INTO metrics (agent_id, value) VALUES ($1, $2)", map[string]any{
        "$1": "T1-OPS-POS-001",
        "$2": 42,
    })
    if err != nil {
        log.Fatal(err)
    }
    fmt.Printf("Rows affected: %d\n", wr.RowsAffected)
}
```

### Super Admin Operations

```go
package main

import (
    "context"
    "fmt"
    "log"

    "github.com/nirlab/cortexdb-client-go/cortexdb"
)

func main() {
    admin := cortexdb.NewSuperAdminClient("http://localhost:3001",
        cortexdb.WithAPIKey("your-api-key"),
    )
    defer admin.Close()

    ctx := context.Background()

    // Authenticate
    if err := admin.Login(ctx, "your-passphrase"); err != nil {
        log.Fatal(err)
    }

    // List agents
    agents, err := admin.ListAgents(ctx)
    if err != nil {
        log.Fatal(err)
    }
    for _, a := range agents {
        fmt.Printf("[%s] %s — %s\n", a.Tier, a.ID, a.Name)
    }

    // Create a task
    task, err := admin.CreateTask(ctx, cortexdb.CreateTaskInput{
        AgentID:     "T1-OPS-POS-001",
        Type:        "analysis",
        Priority:    "high",
        Instruction: "Analyze system performance for the last 24 hours",
    })
    if err != nil {
        log.Fatal(err)
    }
    fmt.Printf("Task created: %s (status: %s)\n", task.ID, task.Status)

    // Chat with an agent
    chat, err := admin.Chat(ctx, "T1-OPS-POS-001", "What is the current system status?")
    if err != nil {
        log.Fatal(err)
    }
    fmt.Printf("Agent response: %s\n", chat.Response)

    // Marketplace
    caps, err := admin.MarketplaceList(ctx)
    if err != nil {
        log.Fatal(err)
    }
    for _, c := range caps {
        status := "disabled"
        if c.Enabled {
            status = "enabled"
        }
        fmt.Printf("  [%s] %s — %s\n", status, c.Name, c.Description)
    }
}
```

### Error Handling

```go
result, err := client.Query(ctx, "SELECT * FROM nonexistent", nil)
if err != nil {
    switch e := err.(type) {
    case *cortexdb.AuthError:
        fmt.Printf("Authentication failed (HTTP %d): %s\n", e.StatusCode, e.Body)
    case *cortexdb.QueryError:
        fmt.Printf("Query failed (HTTP %d): %s\n", e.StatusCode, e.Body)
    case *cortexdb.CortexDBError:
        fmt.Printf("Client error: %s\n", e.Message)
    default:
        fmt.Printf("Unexpected error: %v\n", err)
    }
}
```

## API Reference

### Client Methods

| Method | Description |
|--------|-------------|
| `Query(ctx, cortexql, params)` | Execute a read query |
| `Write(ctx, cortexql, params)` | Execute a write operation |
| `Health(ctx)` | Check instance readiness |
| `DeepHealth(ctx)` | Detailed health from all cores |
| `Close()` | Release resources |

### SuperAdminClient Methods

All `Client` methods plus:

| Method | Description |
|--------|-------------|
| `Login(ctx, passphrase)` | Authenticate as super admin |
| `ListAgents(ctx)` | List all agents |
| `GetAgent(ctx, id)` | Get agent by ID |
| `CreateTask(ctx, input)` | Create a new task |
| `ListTasks(ctx)` | List all tasks |
| `Chat(ctx, agentID, message)` | Chat with an agent |
| `MarketplaceList(ctx)` | List marketplace capabilities |
| `MarketplaceEnable(ctx, id)` | Enable a capability |
| `MarketplaceDisable(ctx, id)` | Disable a capability |

## License

MIT
