#!/bin/bash
set -euo pipefail
ISSUE_NUMBER=$1
mkdir -p "artifacts/issue${ISSUE_NUMBER}"
echo "Fetching Issue #$ISSUE_NUMBER context..."
gh issue view "$ISSUE_NUMBER" --json number,title,body,labels,assignees,state,comments,url > "artifacts/issue${ISSUE_NUMBER}/issue.json"
echo "Artifact generated: artifacts/issue${ISSUE_NUMBER}/issue.json"
