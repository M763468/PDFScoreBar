#!/bin/bash
set -euo pipefail
PR_NUMBER=$1
mkdir -p artifacts
echo "Fetching PR #$PR_NUMBER diff and comments..."
gh pr view "$PR_NUMBER" --json title,body,comments,reviews,reviewThreads,state,mergeable > artifacts/pr_review_data.json
gh pr diff "$PR_NUMBER" > artifacts/pr_diff.patch
echo "Artifacts generated: artifacts/pr_review_data.json, artifacts/pr_diff.patch"
