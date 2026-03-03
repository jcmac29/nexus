#!/bin/bash
# Install Nexus Git Hooks

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GIT_DIR="$(git rev-parse --git-dir 2>/dev/null)"

if [ -z "$GIT_DIR" ]; then
    echo "Error: Not in a git repository"
    exit 1
fi

HOOKS_DIR="${GIT_DIR}/hooks"

echo "Installing Nexus git hooks..."

cp "${SCRIPT_DIR}/post-commit" "${HOOKS_DIR}/post-commit"
cp "${SCRIPT_DIR}/pre-push" "${HOOKS_DIR}/pre-push"

chmod +x "${HOOKS_DIR}/post-commit"
chmod +x "${HOOKS_DIR}/pre-push"

echo "Done! Set these environment variables:"
echo "  export NEXUS_URL=http://localhost:8000"
echo "  export NEXUS_API_KEY=your_api_key"
