#!/bin/bash
set -euo pipefail
COMMAND=${1:-check}
TASK_ID=${2:-}
mkdir -p artifacts

if [[ ! "$TASK_ID" =~ ^[a-zA-Z0-9_-]+$ ]]; then
  echo "Error: TASK_ID must be alphanumeric, hyphens, or underscores."
  exit 1
fi

case "$COMMAND" in
  init)
    ISSUE_NUMBER=${3:-}
    echo "Initializing long-horizon task: $TASK_ID..."
    if [ -n "$ISSUE_NUMBER" ]; then
      python3 tools/ai-workflow-tools/init_long_horizon_task.py "$TASK_ID" --issue "$ISSUE_NUMBER" > artifacts/task_init.txt
    else
      python3 tools/ai-workflow-tools/init_long_horizon_task.py "$TASK_ID" > artifacts/task_init.txt
    fi
    echo "Artifact generated: artifacts/task_init.txt"
    ;;
  check)
    echo "Checking status for task: $TASK_ID..."
    (
      echo "--- Prompt.md ---"
      cat "docs/long-horizon-tasks/$TASK_ID/Prompt.md" 2>/dev/null || echo "Prompt.md not found"
      echo ""
      echo "--- Plan.md ---"
      cat "docs/long-horizon-tasks/$TASK_ID/Plan.md" 2>/dev/null || echo "Plan.md not found"
      echo ""
      echo "--- Latest Log Entries ---"
      tail -n 20 "docs/long-horizon-tasks/$TASK_ID/Log.md" 2>/dev/null || echo "Log.md not found"
    ) > artifacts/task_status.txt
    echo "Artifact generated: artifacts/task_status.txt"
    ;;
  *)
    echo "Usage: ./run.sh {init|check} TASK_ID [ISSUE_NUMBER]"
    exit 1
    ;;
esac
