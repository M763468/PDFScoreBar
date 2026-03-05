#!/bin/bash
set -euo pipefail
# Usage: ./run.sh [search_dir] [file_pattern]
SEARCH_DIR=${1:-debug_outputs/}
PATTERN=${2:-*.png}
mkdir -p artifacts/visual_evidence

echo "Scanning for visual evidence in $SEARCH_DIR..."
(
  echo "--- Visual Evidence Manifest ---"
  echo "Generated at: $(date)"
  echo "Search Dir: $SEARCH_DIR"
  echo ""
  find "$SEARCH_DIR" -maxdepth 2 -name "$PATTERN" -printf "%T+ | %p\n" 2>/dev/null | sort -r | head -n 20
) > artifacts/visual_manifest.txt

# Copy the top 5 most recent images to artifacts for easier multi-modal access
find "$SEARCH_DIR" -maxdepth 2 -name "$PATTERN" -printf "%T+ %p\n" 2>/dev/null | sort -r | head -n 5 | cut -d' ' -f2- | while IFS= read -r img; do
  if [ -n "$img" ]; then
    cp "$img" artifacts/visual_evidence/ 2>/dev/null || true
  fi
done

echo "Artifact generated: artifacts/visual_manifest.txt"
echo "Top 5 recent images copied to artifacts/visual_evidence/"
