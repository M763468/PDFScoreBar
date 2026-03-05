#!/bin/bash
set -euo pipefail
PR_NUMBER=$1
mkdir -p artifacts
echo "Generating PR explanation data for #$PR_NUMBER..."
gh pr view "$PR_NUMBER" --json title,body,comments,reviews > artifacts/pr_explanation_data.json
gh pr diff "$PR_NUMBER" > artifacts/pr_diff.patch
echo "Artifacts generated: artifacts/pr_explanation_data.json, artifacts/pr_diff.patch"
