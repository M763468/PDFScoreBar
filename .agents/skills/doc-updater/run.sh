#!/bin/bash
set -euo pipefail
mkdir -p artifacts
echo "Scanning for TODOs and documentation status..."
(
  echo "--- TODOs in src/ and docs/ ---"
  grep -r "TODO" src/ docs/ 2>/dev/null || echo "No TODOs found"
) > artifacts/documentation_status.txt
echo "Artifact generated: artifacts/documentation_status.txt"
