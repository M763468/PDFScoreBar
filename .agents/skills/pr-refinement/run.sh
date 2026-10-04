#!/bin/bash
set -euo pipefail
PR_NUMBER=$1
mkdir -p "artifacts/pr${PR_NUMBER}"
echo "Fetching PR #$PR_NUMBER for refinement (standard fields only)..."
gh pr view "$PR_NUMBER" --json number,title,body,comments,reviews,state,mergeable,url > "artifacts/pr${PR_NUMBER}/pr.json"
gh pr diff "$PR_NUMBER" > "artifacts/pr${PR_NUMBER}/diff.patch"
echo "Artifacts generated: artifacts/pr${PR_NUMBER}/pr.json, artifacts/pr${PR_NUMBER}/diff.patch"
