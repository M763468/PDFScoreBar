#!/bin/bash
set -euo pipefail
ISSUE_NUMBER=$1
mkdir -p artifacts
echo "Fetching Issue #$ISSUE_NUMBER data..."
gh issue view "$ISSUE_NUMBER" --json title,body,labels,assignees,state,comments > artifacts/issue_data.json
echo "Artifact generated: artifacts/issue_data.json"
