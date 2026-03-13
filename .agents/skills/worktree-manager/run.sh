#!/bin/bash
set -euo pipefail
# Worktree management script
# Usage:
#   ./run.sh add <issue_number> <branch_name>
#   ./run.sh remove <issue_number>
#   ./run.sh list

COMMAND=$1

case "$COMMAND" in
  add)
    ISSUE=$2
    BRANCH=$3
    DIR="../ws_PDFScoreBar_issue${ISSUE}"
    echo "Adding worktree for Issue ${ISSUE} at ${DIR}..."
    git worktree add "${DIR}" "${BRANCH}"
    ;;
  remove)
    ISSUE=$2
    DIR="../ws_PDFScoreBar_issue${ISSUE}"
    echo "Removing worktree for Issue ${ISSUE}..."
    git worktree remove "${DIR}"
    ;;
  list)
    git worktree list
    ;;
  *)
    echo "Usage: $0 {add|remove|list}"
    exit 1
    ;;
esac