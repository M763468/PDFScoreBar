#!/bin/bash
set -euo pipefail
# Usage: bash .agents/skills/pr-creation/run.sh "PR Title" "PR Body File" [base_branch]
TITLE=$1
BODY_FILE=$2
BASE_BRANCH=${3:-main}
TEMPLATE_PATH=".github/pull_request_template.md"
mkdir -p artifacts

echo "Preparing PR creation for: $TITLE"

# If body file doesn't exist, we might want to guide the user/agent to create one first
if [ ! -f "$BODY_FILE" ]; then
  echo "Error: Body file $BODY_FILE not found. Please draft the PR body based on $TEMPLATE_PATH first."
  exit 1
fi

# Create PR using gh CLI
gh pr create --base "$BASE_BRANCH" --title "$TITLE" --body-file "$BODY_FILE" > artifacts/pr_creation_result.txt

echo "Artifact generated: artifacts/pr_creation_result.txt"
cat artifacts/pr_creation_result.txt
