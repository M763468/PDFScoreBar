#!/bin/bash
set -euo pipefail
PR_NUMBER=$1
mkdir -p "artifacts/pr${PR_NUMBER}"
echo "Fetching PR #$PR_NUMBER details and diff..."
gh pr view "$PR_NUMBER" --json number,title,body,comments,reviews,state,mergeable,url > "artifacts/pr${PR_NUMBER}/pr.json"
gh pr diff "$PR_NUMBER" > "artifacts/pr${PR_NUMBER}/diff.patch"
REPOSITORY=$(gh repo view --json nameWithOwner --jq .nameWithOwner)
gh api --paginate --jq '.[]' "repos/${REPOSITORY}/pulls/${PR_NUMBER}/comments?per_page=100" \
  | python3 -c 'import json, sys; print(json.dumps([json.loads(line) for line in sys.stdin if line.strip()], indent=2))' \
  > "artifacts/pr${PR_NUMBER}/review_comments.json"
echo "Artifacts generated: artifacts/pr${PR_NUMBER}/pr.json, artifacts/pr${PR_NUMBER}/diff.patch, artifacts/pr${PR_NUMBER}/review_comments.json"
