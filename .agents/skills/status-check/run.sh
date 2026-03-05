#!/bin/bash
set -euo pipefail
mkdir -p artifacts
echo "Checking repository status..."
(
  echo "--- git status ---"
  git status -sb
  echo ""
  echo "--- last log ---"
  git log -1 --oneline
) > artifacts/status_check.txt
echo "Artifact generated: artifacts/status_check.txt"
