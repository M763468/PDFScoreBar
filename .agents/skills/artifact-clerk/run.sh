#!/bin/bash
set -euo pipefail
mkdir -p artifacts
echo "Clerking artifacts..."
shopt -s nullglob
(
  echo "--- Artifact Evidence Sheet ---"
  echo "Generated at: $(date)"
  echo ""
  for file in artifacts/*; do
    # Skip the summary file itself and common hidden files
    if [[ "$file" == *"evidence_summary.txt" ]] || [[ "$file" == *".gitkeep" ]]; then
      continue
    fi
    if [ -f "$file" ]; then
      echo "File: $file"
      echo "Last Modified: $(date -r "$file")"
      echo "Preview (First 5 lines):"
      if [[ "$file" == *.txt ]] || [[ "$file" == *.json ]] || [[ "$file" == *.md ]]; then
        head -n 5 "$file" | sed "s/^/  /"
      else
        echo "  [Binary or Image]"
      fi
      echo "---"
      echo ""
    fi
  done
) > artifacts/evidence_summary.txt
echo "Artifact generated: artifacts/evidence_summary.txt"
