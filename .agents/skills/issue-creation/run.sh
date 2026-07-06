#!/bin/bash
set -euo pipefail
# This script wraps gh issue creation to ensure artifact-based result logging.
# Usage: bash .agents/skills/issue-creation/run.sh template_file title body_file
TEMPLATE=$1
TITLE=$2
BODY_FILE=$3
mkdir -p artifacts

echo "Drafting/Creating GitHub Issue..."
gh issue create --title "$TITLE" --body-file "$BODY_FILE" > artifacts/issue_creation_result.txt

echo "Artifact generated: artifacts/issue_creation_result.txt"
