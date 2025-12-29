#!/usr/bin/env bash
set -euo pipefail

RUN_ID="$(date +%Y%m%dT%H%M%S)"
OUT_ROOT="logs/gt_rebuild_hybrid_eval/${RUN_ID}_hybrid_row_notehead"
UNION_ROOT="logs/phase5b_confirmed_union_eval"

.venv_pdf/bin/python tools/run_gt_rebuild_hybrid_eval.py \
  --union-root "${UNION_ROOT}" \
  --output-root "${OUT_ROOT}"

echo "Output: ${OUT_ROOT}"
