#!/bin/bash
set -euo pipefail
PR_NUMBER=$1
mkdir -p artifacts
echo "Fetching PR #$PR_NUMBER for refinement (standard fields only)..."
gh pr view "$PR_NUMBER" --json title,body,comments,reviews,state,mergeable > artifacts/pr_refinement_data.json
echo "Artifact generated: artifacts/pr_refinement_data.json"
