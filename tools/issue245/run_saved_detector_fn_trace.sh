#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKTREE_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
MAIN_REPO_ROOT="${ISSUE245_MAIN_REPO_ROOT:-/home/masaki_muramatsu/ws_PDFScoreBar}"

exec env PYTHONPATH="$WORKTREE_ROOT${PYTHONPATH:+:$PYTHONPATH}" \
  python3 "$SCRIPT_DIR/analyze_detector_fn_stages.py" \
  --inventory "$MAIN_REPO_ROOT/logs/issue245_accuracy_first_mixed_route/mixed_inventory.json" \
  --stage-e-root "$MAIN_REPO_ROOT/logs/issue245_accuracy_first_stage_e/stage_e_full_pipeline" \
  --historical-root "$WORKTREE_ROOT/data/evaluation2/golden_baseline_eval2_bc23deb" \
  "$@"
