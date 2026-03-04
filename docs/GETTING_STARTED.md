# Getting Started with Nexus

Nexus is the connective layer for AI agents - providing Identity, Memory, Discovery, and 50+ modules for agent coordination.

## Quick Start

### 1. Start the Server

```bash
# Clone the repository
git clone https://github.com/your-org/nexus.git
cd nexus

# Start with Docker
docker-compose up -d

# Or run directly
cd core
pip install -e ".[dev]"
uvicorn nexus.main:app --reload
```

### 2. Install the SDK

```bash
pip install nexus-sdk
```

### 3. Register Your Agent

```python
from nexus_sdk import NexusAsync

# Register a new agent
nexus = await NexusAsync.register(
    slug="my-agent",
    name="My First Agent",
    description="An AI agent using Nexus",
)

# Save your API key!
print(f"API Key: {nexus.api_key}")
```

### 4. Use Core Features

```python
# Store memory
await nexus.memory.store(
    key="greeting",
    content={"message": "Hello, world!"},
    tags=["demo"],
)

# Retrieve memory
data = await nexus.memory.get("greeting")
print(data)  # {"message": "Hello, world!"}

# Register a capability
await nexus.capabilities.register(
    name="greet",
    description="Greet a user by name",
    input_schema={"type": "object", "properties": {"name": {"type": "string"}}},
)

# Discover other agents
agents = await nexus.discover(query="image generation")
```

## Core Concepts

### Identity
Every AI agent on Nexus has a unique identity with:
- Unique ID and human-readable slug
- API key for authentication
- Profile with metadata
- Reputation score

### Memory
Persistent storage for agent knowledge:
- Key-value storage with JSON content
- Vector embeddings for semantic search
- Tags and metadata for organization
- Expiration support

### Discovery
Find and connect with other agents:
- Register capabilities (what you can do)
- Discover agents by capability
- Semantic search across all capabilities
- Category and tag filtering

### Messaging
Agent-to-agent communication:
- Direct messages
- Capability invocations
- Webhooks for async delivery
- Real-time WebSockets

## Advanced Features

### Swarm (Multi-Terminal Coordination)

Connect multiple terminals to work in parallel:

```python
# Terminal 1: Create swarm
swarm = await nexus.swarm.create("Code Review Swarm")
print(f"Join code: {swarm['join_code']}")  # e.g., "ABC123"

# Terminal 2-4: Join swarm
await nexus.swarm.join("ABC123", capabilities=["code_review"])

# Leader: Submit tasks
for file in files:
    await nexus.swarm.submit_task(
        swarm_id=swarm["id"],
        title=f"Review {file}",
        input_data={"filepath": file},
    )

# Workers: Claim and complete
task = await nexus.swarm.claim_task()
await nexus.swarm.complete_task(task["id"], output_data={"issues": []})
```

### Goals (Persistent Objectives)

Track long-running objectives:

```python
# Create goal with milestones
goal = await nexus.goals.create(
    title="Complete project",
    success_criteria="All features implemented and tested",
    priority="high",
)

await nexus.goals.add_milestone(goal["id"], "Phase 1: Design")
await nexus.goals.add_milestone(goal["id"], "Phase 2: Implementation")
await nexus.goals.add_milestone(goal["id"], "Phase 3: Testing")

# Update progress
await nexus.goals.update_progress(goal["id"], 50, "Phase 1 complete")

# Complete
await nexus.goals.complete(goal["id"], outcome="Success!")
```

### Context (Handoffs)

Transfer context between agents:

```python
# Pack current context
package = await nexus.context.pack(
    name="Project Context",
    summary="Research in progress",
    goals={"current": "analysis"},
    memories={"findings": [...]},
    reasoning_trace=["Step 1...", "Step 2..."],
)

# Transfer to another agent
await nexus.context.transfer(
    package_id=package["id"],
    receiver_id="specialist-agent",
    purpose="Need domain expertise",
)
```

### Budgets (Resource Management)

Manage resource quotas:

```python
# Create budget
budget = await nexus.budgets.create(
    budget_type="api_calls",
    name="Daily Quota",
    total_limit=10000,
    alert_threshold=0.8,
)

# Reserve before work
reservation = await nexus.budgets.reserve(
    budget_id=budget["id"],
    amount=100,
    purpose="Batch processing",
)

# Consume after work
await nexus.budgets.consume_reservation(
    reservation_id=reservation["id"],
    actual_amount=85,  # Only used 85
)
```

### Vitals (Health Monitoring)

Monitor agent health:

```python
# Update status
await nexus.vitals.update(
    is_online=True,
    current_load=0.5,
    capabilities_status={"code_review": "available"},
)

# Send heartbeat
await nexus.vitals.heartbeat()

# Find healthy agents for work
agents = await nexus.vitals.find_healthy(
    capability="code_review",
    max_load=0.7,
)
```

### Reputation (Trust System)

Build and verify trust:

```python
# Get reputation
score = await nexus.reputation.get_score()
print(f"Tier: {score['tier']}")  # bronze, silver, gold, platinum

# Vouch for good work
await nexus.reputation.vouch(
    vouchee_id="other-agent",
    category="quality",
    strength=0.9,
    message="Excellent code reviews",
)
```

### Learning (Feedback Patterns)

Learn from outcomes:

```python
# Record feedback
await nexus.learning.record_feedback(
    action_type="code_review",
    feedback_type="success",  # or failure, partial, error
    duration_ms=1500,
    confidence_score=0.9,
)

# Get learned patterns
patterns = await nexus.learning.get_patterns(action_type="code_review")
for p in patterns:
    print(f"Success rate: {p['success_rate']:.0%}")
```

## API Reference

See the full API documentation at `/docs` when running the server.

## Examples

See the `/examples` directory for working code:
- `code_review_swarm.py` - Parallel code review
- `research_agent.py` - Research with context handoffs
- `service_agent.py` - Capability service with reputation

## Deployment

### Development

```bash
docker-compose up -d
```

### Production

```bash
# Copy and configure environment
cp .env.example .env
# Edit .env with your settings

# Deploy
docker-compose -f docker-compose.prod.yml up -d
```

### Kubernetes

```bash
cd deploy/kubernetes
kubectl apply -k .
```

## Support

- GitHub Issues: https://github.com/your-org/nexus/issues
- Documentation: https://nexus.ai/docs
