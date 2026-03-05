#!/bin/bash
set -euo pipefail
mkdir -p artifacts
echo "Investigating logs and status..."
(
  echo "--- git status ---"
  git status -sb
  echo ""
  echo "--- last 50 lines of logs ---"
  tail -n 50 logs/*.log 2>/dev/null || echo "No logs found in logs/"
) > artifacts/investigation_results.txt
echo "Artifact generated: artifacts/investigation_results.txt"
