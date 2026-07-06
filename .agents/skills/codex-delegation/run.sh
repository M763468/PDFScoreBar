#!/bin/bash
set -euo pipefail
# This script wraps codex exec to ensure artifact-based result logging.
# Usage: bash .agents/skills/codex-delegation/run.sh "instruction" [--sandbox read-only]
INSTRUCTION=$1
shift
mkdir -p artifacts

echo "Delegating to Codex: $INSTRUCTION"
# Pass all remaining arguments (like --sandbox) to codex exec
codex exec "$INSTRUCTION" "$@" > artifacts/codex_result.txt 2>&1

echo "Artifact generated: artifacts/codex_result.txt"
