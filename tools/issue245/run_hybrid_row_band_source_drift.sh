#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKTREE_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
MAIN_REPO_ROOT="${ISSUE245_MAIN_REPO_ROOT:-/home/masaki_muramatsu/ws_PDFScoreBar}"
OUTPUT="${ISSUE245_ROW_BAND_DRIFT_OUTPUT:-$WORKTREE_ROOT/logs/issue245_accuracy_first_stage_e/hybrid_row_band_source_drift.json}"
PYTHON_BIN="${ISSUE245_PYTHON:-python3}"

cd "$WORKTREE_ROOT"
exec env PYTHONPATH="$WORKTREE_ROOT${PYTHONPATH:+:$PYTHONPATH}" \
  "$PYTHON_BIN" "$SCRIPT_DIR/analyze_hybrid_row_band_source_drift.py" \
  --main-repo-root "$MAIN_REPO_ROOT" \
  --target 'Shostakovich-Sym5-Va|page_013|1679,1202,1683,1296' \
  --target 'Sibelius-Violin_Concerto-Viola|page_004|1514,4015,1518,4195' \
  --target 'Sibelius-Violin_Concerto-Viola|page_004|1924,4015,1928,4195' \
  --output "$OUTPUT" \
  "$@"
