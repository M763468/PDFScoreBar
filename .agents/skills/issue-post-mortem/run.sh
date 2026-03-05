#!/bin/bash
set -euo pipefail
ISSUE_NUMBER=$1
BASE_BRANCH=${2:-main}
mkdir -p artifacts

echo "Generating issue post-mortem data for #$ISSUE_NUMBER..."
(
  echo "--- Generated at: $(date) ---"
  echo ""
  echo "--- 1. Original Issue Data (#$ISSUE_NUMBER) ---"
  gh issue view "$ISSUE_NUMBER" --json title,body,labels,state,comments
  echo ""
  echo "--- 2. Commits for this issue ---"
  git log --oneline "$BASE_BRANCH..HEAD"
  echo ""
  echo "--- 3. Diff Summary (Stats) ---"
  git diff "$BASE_BRANCH..HEAD" --stat
  echo ""
  echo "--- 4. TODOs remaining in changed files ---"
  git diff "$BASE_BRANCH..HEAD" --name-only | xargs grep -n "TODO" 2>/dev/null || echo "No TODOs found in changed files."
) > artifacts/issue_post_mortem.txt
echo "Artifact generated: artifacts/issue_post_mortem.txt"

# Helper for commenting (optional manual trigger or part of steps)
echo "Tip: Use 'gh issue comment $ISSUE_NUMBER --body-file artifacts/issue_post_mortem_comment.md' after drafting your summary."
