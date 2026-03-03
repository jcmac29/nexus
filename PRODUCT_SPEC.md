# Nexus - Product Specification

## Vision

Nexus is the open-source connective layer for AI agents. It provides identity, memory, and discovery in one unified platform—making it trivial for AI agents and MCP servers to authenticate, remember context, and find each other.

## Problem Statement

AI agents today operate in isolation:
- No standard identity/authentication mechanism
- Memory is siloed within individual applications
- No way to discover other agents' capabilities
- No cross-platform context sharing

Existing solutions (Mem0, Zep) focus on single-app memory. MCP Registry handles discovery but not memory or identity. **No one owns the unified layer.**

## Solution

Nexus provides three core primitives:

### 1. Identity
Every agent gets a verifiable identity with scoped permissions.
```python
from nexus import Nexus

agent = Nexus.register("my-agent")
# Returns: agent_id, api_key, public_key
```

### 2. Memory
Persistent, shareable memory scoped by identity.
```python
# Store memory
agent.memory.store("user_preference", {"theme": "dark"})

# Retrieve
prefs = agent.memory.get("user_preference")

# Share with another agent
agent.memory.share("user_preference", with_agent="other-agent-id")
```

### 3. Discovery
Find agents and capabilities across the network.
```python
# Register capabilities
agent.capabilities.register(["text-summarization", "translation"])

# Discover other agents
translators = Nexus.discover(capability="translation")
```

## Target Users

### Primary: MCP Server Developers
- Building tools that AI assistants connect to
- Need persistent memory across sessions
- Want to expose capabilities for discovery

### Secondary: AI Agent Builders
- Building autonomous agents (LangChain, CrewAI, AutoGen)
- Need cross-session memory
- Want agents to collaborate/hand off tasks

### Tertiary: AI Application Developers
- Building apps with AI features
- Need user memory persistence
- Want simple integration

## Core Features (MVP)

### Identity System
- [ ] Agent registration (name, metadata)
- [ ] API key generation and rotation
- [ ] Permission scopes (read, write, share, discover)
- [ ] Agent verification (public key)
- [ ] Revocation and deletion

### Memory System
- [ ] Key-value storage
- [ ] Vector storage for semantic search
- [ ] Memory scopes (agent, user, session, shared)
- [ ] Time-based expiration (optional)
- [ ] Sharing with permission grants
- [ ] Memory namespaces

### Discovery System
- [ ] Capability registration
- [ ] Capability search (keyword, semantic)
- [ ] Agent metadata and status
- [ ] Health/availability signals

### MCP Integration
- [ ] Nexus as MCP server (expose memory/identity tools)
- [ ] MCP client SDK (add Nexus to any MCP server)
- [ ] Tool definitions for Claude/GPT compatibility

## User Stories

### MCP Server Developer
> "I built an MCP server for code review. I want it to remember past reviews and coding preferences for each user. I add Nexus SDK, and now my server has persistent memory with 3 lines of code."

### Agent Builder
> "I'm building a research agent with CrewAI. My agents need to share findings with each other. With Nexus, Agent A stores research, Agent B retrieves it—with proper auth."

### Discovery User
> "I want my agent to find a translation service. I query Nexus for agents with 'translation' capability and get back a list with their endpoints and status."

## Differentiators

| Nexus | Mem0 | MCP Registry |
|-------|------|--------------|
| Open-source core | Partially open | Open |
| Identity-first | No identity | No identity |
| Memory + Discovery | Memory only | Discovery only |
| MCP-native | MCP support | MCP-native |
| Self-hostable | Limited | N/A (metadata only) |

## Success Metrics

### Adoption
- GitHub stars
- Weekly active agents (registered)
- Memory operations/month
- Discovery queries/month

### Developer Experience
- Time to first working integration (<5 min)
- SDK installs (pip, npm)
- Documentation engagement

### Community
- Contributors
- MCP servers using Nexus
- Discord/community size

## Monetization (Post-MVP)

### Cloud Tiers
| Tier | Price | Included |
|------|-------|----------|
| Free | $0 | 10K ops/month, 1K memories |
| Starter | $19/mo | 100K ops/month, 50K memories |
| Pro | $99/mo | 1M ops/month, 500K memories, priority support |
| Enterprise | Custom | Unlimited, SLA, dedicated support |

### Revenue Streams
1. Cloud hosting usage fees
2. Enterprise support contracts
3. Managed self-hosted deployments
4. Premium features (analytics, advanced sharing)

## Roadmap

### Phase 1: Foundation (Weeks 1-4)
- Core identity system
- Basic memory (key-value + vector)
- Python SDK
- Self-hosted deployment (Docker)

### Phase 2: Integration (Weeks 5-8)
- MCP server implementation
- TypeScript SDK
- Discovery system
- Hosted cloud (free tier)

### Phase 3: Growth (Weeks 9-12)
- Graph memory
- Advanced permissions
- Analytics dashboard
- Billing integration

### Phase 4: Scale (Months 4+)
- Federation (multiple Nexus instances)
- Enterprise features
- Marketplace for verified agents
- Payment rails for agent-to-agent transactions

## Open Questions

1. **Naming**: Nexus is working name—final name TBD
2. **License**: MIT vs Apache 2.0 (leaning MIT for max adoption)
3. **Vector DB**: pgvector vs embedded (ChromaDB) vs external (Pinecone)
4. **Federation**: How do multiple Nexus instances discover each other?

---

*Last updated: 2026-03-02*
