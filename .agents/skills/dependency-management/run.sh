#!/bin/bash
set -euo pipefail
mkdir -p artifacts
echo "Checking dependencies..."
(
  echo "--- uv lock status ---"
  uv lock --check 2>/dev/null || echo "uv lock is out of sync or uv not found"
  echo ""
  echo "--- installed packages ---"
  uv pip list 2>/dev/null || pip list
) > artifacts/dependency_status.txt
echo "Artifact generated: artifacts/dependency_status.txt"
