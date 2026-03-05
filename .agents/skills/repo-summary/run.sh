#!/bin/bash
set -euo pipefail
mkdir -p artifacts
echo "Generating comprehensive repository summary..."
(
  echo "--- Generated at: $(date) ---"
  echo ""
  echo "--- 1. Repository Tree (L3) ---"
  tree -L 3 -I "artifacts|logs|temp|datasets|.git|__pycache__|.venv*"
  echo ""
  echo "--- 2. Dependency Status ---"
  uv lock --check 2>/dev/null || echo "uv lock is out of sync"
  uv pip list 2>/dev/null || pip list 2>/dev/null || echo "pip not found"
  echo ""
  echo "--- 3. Recent Logs (last 20 lines) ---"
  tail -n 20 logs/*.log 2>/dev/null || echo "No logs found"
  echo ""
  echo "--- 4. Active Branch Status ---"
  git status -sb
) > artifacts/repo_summary.txt
echo "Artifact generated: artifacts/repo_summary.txt"
