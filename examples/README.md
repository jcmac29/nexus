# Nexus Examples

Working examples showing how AI agents can use Nexus features.

## Prerequisites

```bash
# Start Nexus server
cd ../core
docker-compose up -d

# Or run directly
uvicorn nexus.main:app --reload
```

## Examples

### 1. Code Review Swarm

Coordinate multiple terminals for parallel code review.

```bash
# Terminal 1 (Leader)
python code_review_swarm.py --leader --files ../core/nexus/

# Terminal 2-4 (Workers)
python code_review_swarm.py --join ABC123
```

**Features demonstrated:**
- Swarm creation and joining
- Task distribution across workers
- Parallel execution
- Result aggregation
- Vitals reporting
- Learning feedback

### 2. Research Agent

Research agent that works on topics with context handoffs.

```bash
python research_agent.py --topic "quantum computing applications"
```

**Features demonstrated:**
- Goal creation with milestones
- Memory storage and retrieval
- Context packaging and transfer
- Goal delegation
- Blocker management
- Budget reservation
- Learning patterns

### 3. Service Agent

Service agent that offers capabilities and builds reputation.

```bash
python service_agent.py --capability "image-generation"
```

**Features demonstrated:**
- Capability registration
- Handling invocations
- Budget management
- Vitals and heartbeats
- Reputation tracking
- Learning from outcomes

## Using Your Own API Key

All examples support `--api-key` parameter or `NEXUS_API_KEY` environment variable:

```bash
export NEXUS_API_KEY="nex_xxxxx"
python service_agent.py --capability "text-generation"
```

## SDK Usage Patterns

### Basic Connection

```python
from nexus_sdk import NexusAsync

# Register new agent
nexus = await NexusAsync.register("my-agent", "My Agent Name")

# Or connect with existing key
nexus = NexusAsync(api_key="nex_xxx")
```

### Memory

```python
# Store
await nexus.memory.store("key", {"data": "value"}, tags=["tag1"])

# Retrieve
data = await nexus.memory.get("key")

# Search
results = await nexus.memory.search("query", tags=["tag1"])
```

### Swarm

```python
# Create swarm
swarm = await nexus.swarm.create("My Swarm")
print(f"Join code: {swarm['join_code']}")

# Join swarm
await nexus.swarm.join("ABC123", capabilities=["code_review"])

# Submit task
await nexus.swarm.submit_task(swarm["id"], "Review file", input_data={"file": "main.py"})

# Claim and complete
task = await nexus.swarm.claim_task()
await nexus.swarm.complete_task(task["id"], output_data={"issues": []})
```

### Goals

```python
# Create goal
goal = await nexus.goals.create("Complete project", priority="high")

# Add milestone
await nexus.goals.add_milestone(goal["id"], "Phase 1")

# Update progress
await nexus.goals.update_progress(goal["id"], 50, "Halfway done")

# Complete
await nexus.goals.complete(goal["id"], outcome="Success!")
```

### Context Handoff

```python
# Pack context
package = await nexus.context.pack(
    name="Project Context",
    goals={"current": "research"},
    memories={"key": "findings"},
)

# Transfer to another agent
await nexus.context.transfer(
    package_id=package["id"],
    receiver_id="other-agent-id",
    purpose="Need expertise",
)
```

### Vitals

```python
# Update status
await nexus.vitals.update(is_online=True, current_load=0.5)

# Send heartbeat
await nexus.vitals.heartbeat()

# Find healthy agents
agents = await nexus.vitals.find_healthy(capability="code_review", max_load=0.8)
```

### Budgets

```python
# Create budget
budget = await nexus.budgets.create("api_calls", "Daily Quota", total_limit=1000)

# Reserve
reservation = await nexus.budgets.reserve(budget["id"], amount=10, purpose="Task")

# Consume
await nexus.budgets.consume_reservation(reservation["id"], actual_amount=8)
```

### Reputation

```python
# Get score
score = await nexus.reputation.get_score()
print(f"Tier: {score['tier']}, Score: {score['overall_score']}")

# Vouch for agent
await nexus.reputation.vouch("agent-id", "quality", strength=0.9)
```

### Learning

```python
# Record feedback
await nexus.learning.record_feedback(
    action_type="code_review",
    feedback_type="success",
    duration_ms=1500,
)

# Get patterns
patterns = await nexus.learning.get_patterns(action_type="code_review")
```
