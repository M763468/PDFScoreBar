#!/bin/bash
set -ex

# Phase 5b Evaluation of Strategy 2 on page_3 (Regression Guard)
# - Generates hybrid predictions using promiscuous_union.
# - Applies FULL Phase 4 filter chain (row + geom note-context).

PAGE="page_3"
GT="data/evaluation/annotations/page_003/boxes_sorted.json"
IMG="data/evaluation/images/page_3.png"

BASELINE="logs/hybrid_generalization/sr_eval_smoke_page3/baseline/page_3/page_3/page_3_detections.json"
SR="logs/hybrid_generalization/sr_eval_smoke_page3/sr/page_3/page_3/page_3_detections.json"
OMR="logs/hybrid_generalization/sr_eval_smoke_page3/omr_sr/predictions.json"
HOMR_CONTEXT_DIR="logs/hybrid_generalization/sr_eval_smoke_page3/homr_debug_600dpi"

OUTPUT_DIR="logs/phase5b_promiscuous_union_eval"
mkdir -p "$OUTPUT_DIR"

HYBRID_PREDS="$OUTPUT_DIR/${PAGE}_hybrid_preds.json"
FILTER_OUTPUT_DIR="$OUTPUT_DIR/${PAGE}_filtered_output"

# 1. Generate Hybrid Predictions
./.venv_pdf/bin/python tools/generate_hybrid_results.py \
    --baseline "$BASELINE" \
    --sr "$SR" \
    --omr "$OMR" \
    --output "$HYBRID_PREDS" \
    --gt "$GT" \
    --merge-strategy promiscuous_union

# 2. Apply Full Phase 4 Filters
./.venv_pdf/bin/python experiments/fp_reduction/analyze_staff_consistency.py \
    --json "$HYBRID_PREDS" \
    --image "$IMG" \
    --gt "$GT" \
    --output "$FILTER_OUTPUT_DIR" \
    --no-use-ratio-tolerance --tol-top-px 5 --tol-bottom-px 5 \
    --enable-geom-notehead-filter \
    --geom-notehead-mode page3_known_fp \
    --homr-context-dir "$HOMR_CONTEXT_DIR"

echo "--- page_3 regression check complete ---"
