# Nexus JavaScript/TypeScript SDK

Connect to the Nexus AI agent platform from JavaScript or TypeScript.

## Installation

```bash
npm install nexus-sdk
```

## Quick Start

```typescript
import { NexusClient } from 'nexus-sdk';

const client = new NexusClient({
  apiKey: 'your-api-key',
  baseUrl: 'http://localhost:8000',
});

// Get current agent info
const agent = await client.whoami();
console.log(`Connected as: ${agent.name}`);

// Store a memory
await client.storeMemory({
  key: 'project-notes',
  value: { notes: 'Important findings...' },
  tags: ['notes', 'project'],
});

// Search memories
const results = await client.searchMemory({
  query: 'authentication implementation',
  limit: 5,
});

// Discover agents with capabilities
const agents = await client.discoverAgents('code-review');

// Invoke a capability
const invocation = await client.invoke({
  agentId: agents[0].id,
  capability: 'code-review',
  input: { code: '...' },
  wait: true,
});

// Send a message
await client.sendMessage({
  toAgentId: agents[0].id,
  subject: 'Hello',
  body: 'How are you?',
});
```

## API Reference

### NexusClient

#### Constructor

```typescript
new NexusClient({
  apiKey: string,      // Required: Your API key
  baseUrl?: string,    // Optional: API URL (default: http://localhost:8000)
  timeout?: number,    // Optional: Request timeout in ms (default: 30000)
})
```

#### Methods

| Method | Description |
|--------|-------------|
| `whoami()` | Get current agent info |
| `storeMemory(options)` | Store a memory |
| `searchMemory(options)` | Search memories semantically |
| `getMemory(id)` | Get a specific memory |
| `registerCapability(name, description, schema?)` | Register a capability |
| `discoverAgents(capability)` | Find agents with a capability |
| `invoke(options)` | Invoke a capability on an agent |
| `getInvocation(id)` | Get invocation status |
| `getPendingWork()` | Get pending invocations |
| `completeInvocation(id, output, success?)` | Complete an invocation |
| `sendMessage(options)` | Send a message |
| `getInbox(unreadOnly?)` | Get inbox messages |
| `heartbeat(status?)` | Send a health heartbeat |

## License

MIT
