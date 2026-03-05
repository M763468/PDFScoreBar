#!/bin/bash
set -euo pipefail
PR_NUMBER=$1
mkdir -p artifacts
echo "Fetching PR #$PR_NUMBER for refinement..."
gh pr view "$PR_NUMBER" --json title,body,comments,reviews > artifacts/pr_refinement_data.json
echo "Artifact generated: artifacts/pr_refinement_data.json"
