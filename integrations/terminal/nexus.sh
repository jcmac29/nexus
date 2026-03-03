#!/bin/bash
# Nexus Shell Integration
# Source this file in your .bashrc or .zshrc:
#   source /path/to/nexus.sh

export NEXUS_URL="${NEXUS_URL:-http://localhost:8000}"
export NEXUS_API_KEY="${NEXUS_API_KEY:-}"

# Store a memory
nx-remember() {
    if [ -z "$NEXUS_API_KEY" ]; then
        echo "Error: NEXUS_API_KEY not set"
        return 1
    fi

    local key="$1"
    local content="$2"

    if [ -z "$key" ] || [ -z "$content" ]; then
        echo "Usage: nx-remember <key> <content>"
        return 1
    fi

    curl -s -X POST "${NEXUS_URL}/api/v1/memory" \
        -H "Authorization: Bearer ${NEXUS_API_KEY}" \
        -H "Content-Type: application/json" \
        -d "{
            \"key\": \"shell:${key}\",
            \"value\": {\"content\": \"${content}\", \"cwd\": \"$(pwd)\"},
            \"text_content\": \"${content}\",
            \"tags\": [\"shell\", \"note\"],
            \"scope\": \"shared\"
        }" | jq -r '.key // .detail'
}

# Search memories
nx-search() {
    if [ -z "$NEXUS_API_KEY" ]; then
        echo "Error: NEXUS_API_KEY not set"
        return 1
    fi

    local query="$*"
    if [ -z "$query" ]; then
        echo "Usage: nx-search <query>"
        return 1
    fi

    curl -s -X POST "${NEXUS_URL}/api/v1/memory/search" \
        -H "Authorization: Bearer ${NEXUS_API_KEY}" \
        -H "Content-Type: application/json" \
        -d "{\"query\": \"${query}\", \"limit\": 5, \"include_shared\": true}" \
        | jq -r '.results[] | "[\(.score | tostring | .[0:4])] \(.memory.key)\n    \(.memory.tags | join(", "))"'
}

# Ask AI for help
nx-ask() {
    if [ -z "$NEXUS_API_KEY" ]; then
        echo "Error: NEXUS_API_KEY not set"
        return 1
    fi

    local question="$*"
    if [ -z "$question" ]; then
        echo "Usage: nx-ask <question>"
        return 1
    fi

    # Find an AI agent
    local agent_id=$(curl -s "${NEXUS_URL}/api/v1/discover/capabilities/code-assist" \
        -H "Authorization: Bearer ${NEXUS_API_KEY}" \
        | jq -r '.agents[0].id // empty')

    if [ -z "$agent_id" ]; then
        echo "No AI agent found with 'code-assist' capability"
        return 1
    fi

    # Invoke the agent
    local result=$(curl -s -X POST "${NEXUS_URL}/api/v1/invoke/${agent_id}/code-assist" \
        -H "Authorization: Bearer ${NEXUS_API_KEY}" \
        -H "Content-Type: application/json" \
        -d "{\"input\": {\"question\": \"${question}\", \"cwd\": \"$(pwd)\"}}")

    echo "$result" | jq -r '.invocation_id // .detail'
}

# Get pending work
nx-pending() {
    if [ -z "$NEXUS_API_KEY" ]; then
        echo "Error: NEXUS_API_KEY not set"
        return 1
    fi

    curl -s "${NEXUS_URL}/api/v1/agents/me/pending" \
        -H "Authorization: Bearer ${NEXUS_API_KEY}" \
        | jq -r '.[] | "ID: \(.id)\nCapability: \(.capability)\nInput: \(.input | tostring | .[0:100])...\n"'
}

# Send heartbeat
nx-heartbeat() {
    if [ -z "$NEXUS_API_KEY" ]; then
        return 1
    fi

    curl -s -X POST "${NEXUS_URL}/api/v1/health/heartbeat" \
        -H "Authorization: Bearer ${NEXUS_API_KEY}" \
        -H "Content-Type: application/json" \
        -d '{"status": "healthy"}' > /dev/null
}

# List team members
nx-team() {
    if [ -z "$NEXUS_API_KEY" ]; then
        echo "Error: NEXUS_API_KEY not set"
        return 1
    fi

    curl -s "${NEXUS_URL}/api/v1/teams/me" \
        -H "Authorization: Bearer ${NEXUS_API_KEY}" \
        | jq -r '.[] | "\(.name) (ID: \(.id))"'
}

# Store command output
nx-capture() {
    local cmd="$*"
    if [ -z "$cmd" ]; then
        echo "Usage: nx-capture <command>"
        return 1
    fi

    local output=$(eval "$cmd" 2>&1)
    local exit_code=$?

    nx-remember "cmd:$(date +%s)" "Command: $cmd\nOutput: $output\nExit code: $exit_code"

    echo "$output"
    return $exit_code
}

# Quick status check
nx-status() {
    curl -s "${NEXUS_URL}/health" | jq -r '"Nexus: \(.status) (v\(.version))"'
}

# Auto-complete for bash
if [ -n "$BASH_VERSION" ]; then
    _nx_completions() {
        local cur="${COMP_WORDS[COMP_CWORD]}"
        COMPREPLY=($(compgen -W "remember search ask pending heartbeat team capture status" -- "$cur"))
    }
    complete -F _nx_completions nx-remember nx-search nx-ask nx-pending nx-heartbeat nx-team nx-capture nx-status
fi

echo "Nexus shell integration loaded. Commands: nx-remember, nx-search, nx-ask, nx-pending, nx-team, nx-status"
