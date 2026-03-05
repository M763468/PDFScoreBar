#!/bin/bash
set -euo pipefail
BASE_BRANCH=${1:-main}
mkdir -p artifacts
echo "Generating change summary from $BASE_BRANCH to HEAD..."
(
  echo "--- Summary of changes from $BASE_BRANCH to HEAD ---"
  git log --oneline "$BASE_BRANCH..HEAD"
  echo ""
  echo "--- Diff Stats ---"
  git diff "$BASE_BRANCH..HEAD" --stat
) > artifacts/change_summary.txt
echo "Artifact generated: artifacts/change_summary.txt"
