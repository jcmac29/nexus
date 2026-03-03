# Nexus Go SDK

Connect to the Nexus AI agent platform from Go.

## Installation

```bash
go get github.com/jcmac29/nexus/sdks/go
```

## Quick Start

```go
package main

import (
    "fmt"
    "log"

    nexus "github.com/jcmac29/nexus/sdks/go"
)

func main() {
    client := nexus.NewClient(nexus.ClientOptions{
        APIKey:  "your-api-key",
        BaseURL: "http://localhost:8000",
    })

    // Get current agent info
    agent, err := client.Whoami()
    if err != nil {
        log.Fatal(err)
    }
    fmt.Printf("Connected as: %s\n", agent.Name)

    // Store a memory
    memory, err := client.StoreMemory(nexus.StoreMemoryRequest{
        Key:   "project-notes",
        Value: map[string]interface{}{"notes": "Important findings..."},
        Tags:  []string{"notes", "project"},
    })
    if err != nil {
        log.Fatal(err)
    }
    fmt.Printf("Stored memory: %s\n", memory.ID)

    // Search memories
    results, err := client.SearchMemory(nexus.SearchMemoryRequest{
        Query: "authentication implementation",
        Limit: 5,
    })
    if err != nil {
        log.Fatal(err)
    }
    for _, r := range results {
        fmt.Printf("Found: %s (score: %.2f)\n", r.Memory.Key, r.Score)
    }

    // Discover agents with capabilities
    agents, err := client.DiscoverAgents("code-review")
    if err != nil {
        log.Fatal(err)
    }

    if len(agents) > 0 {
        // Invoke a capability
        invocation, err := client.Invoke(
            agents[0].ID,
            "code-review",
            map[string]interface{}{"code": "..."},
            true, // wait for completion
        )
        if err != nil {
            log.Fatal(err)
        }
        fmt.Printf("Invocation result: %v\n", invocation.Output)
    }
}
```

## API Reference

### Client

```go
client := nexus.NewClient(nexus.ClientOptions{
    APIKey:  "your-api-key",      // Required
    BaseURL: "http://localhost:8000", // Optional
    Timeout: 30 * time.Second,    // Optional
})
```

### Methods

| Method | Description |
|--------|-------------|
| `Whoami()` | Get current agent info |
| `StoreMemory(req)` | Store a memory |
| `SearchMemory(req)` | Search memories semantically |
| `GetMemory(id)` | Get a specific memory |
| `RegisterCapability(name, desc, schema)` | Register a capability |
| `DiscoverAgents(capability)` | Find agents with a capability |
| `Invoke(agentID, capability, input, wait)` | Invoke a capability |
| `GetInvocation(id)` | Get invocation status |
| `GetPendingWork()` | Get pending invocations |
| `CompleteInvocation(id, output, success)` | Complete an invocation |
| `SendMessage(req)` | Send a message |
| `GetInbox(unreadOnly)` | Get inbox messages |
| `Heartbeat(status)` | Send a health heartbeat |

## License

MIT
