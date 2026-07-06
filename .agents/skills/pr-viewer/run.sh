#!/bin/bash
set -euo pipefail

if [ -z "${1:-}" ]; then
  echo "Usage: bash .agents/skills/pr-viewer/run.sh <pr_number>"
  exit 1
fi

PR_NUMBER=$1
mkdir -p artifacts

echo "Fetching PR #$PR_NUMBER data..."
gh pr view "$PR_NUMBER" --json title,body,state,comments,reviews,mergeable > "artifacts/pr_data_${PR_NUMBER}.json"

echo "Fetching PR #$PR_NUMBER diff..."
gh pr diff "$PR_NUMBER" > "artifacts/pr_diff_${PR_NUMBER}.patch"

echo "Artifacts generated: artifacts/pr_data_${PR_NUMBER}.json, artifacts/pr_diff_${PR_NUMBER}.patch"
