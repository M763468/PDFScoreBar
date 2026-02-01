#!/bin/bash
set -ex

# Phase 5b Evaluation of Strategy 2: Promiscuous Union
# - Generates hybrid predictions using the new merge strategy.
# - Applies Phase 4 row-only filter.
# - Uses existing detector artifacts.

PAGES=("page_10" "page_15" "page_001" "page_004")
declare -A GT_MAP
GT_MAP["page_10"]="data/training/annotations/page_010/fn_only.json"
GT_MAP["page_15"]="data/training/annotations/page_015/fn_only.json"
GT_MAP["page_001"]="data/evaluation2/annotations/Va_Prokofiev_Symphony1/page_001/fn_only.json"
GT_MAP["page_004"]="data/evaluation2/annotations/Va_Prokofiev_Symphony1/page_004/fn_only.json"

declare -A IMG_MAP
IMG_MAP["page_10"]="data/training/images/page_10.png"
IMG_MAP["page_15"]="data/training/images/page_15.png"
IMG_MAP["page_001"]="data/evaluation2/images/Va_Prokofiev_Symphony1/page_001.png"
IMG_MAP["page_004"]="data/evaluation2/images/Va_Prokofiev_Symphony1/page_004.png"

# Corrected artifact paths based on 'sr_eval_*_check2' directories
declare -A BASELINE_MAP
BASELINE_MAP["page_10"]="logs/hybrid_generalization/sr_eval_page10_check2/baseline/page_10/page_10/page_10_detections.json"
BASELINE_MAP["page_15"]="logs/hybrid_generalization/sr_eval_page15_check2/baseline/page_15/page_15/page_15_detections.json"
BASELINE_MAP["page_001"]="logs/hybrid_generalization/phase4b_cv_prokofiev_va_page_001/baseline/page_001/page_001/page_001_detections.json"
BASELINE_MAP["page_004"]="logs/hybrid_generalization/phase4b_cv_prokofiev_va_page_004/baseline/page_004/page_004/page_004_detections.json"

declare -A SR_MAP
SR_MAP["page_10"]="logs/hybrid_generalization/sr_eval_page10_check2/sr/page_10/page_10/page_10_detections.json"
SR_MAP["page_15"]="logs/hybrid_generalization/sr_eval_page15_check2/sr/page_15/page_15/page_15_detections.json"
SR_MAP["page_001"]="logs/hybrid_generalization/phase4b_cv_prokofiev_va_page_001/sr/page_001/page_001/page_001_detections.json"
SR_MAP["page_004"]="logs/hybrid_generalization/phase4b_cv_prokofiev_va_page_004/sr/page_004/page_004/page_004_detections.json"

declare -A OMR_MAP
OMR_MAP["page_10"]="logs/hybrid_generalization/sr_eval_page10_check2/omr_sr/predictions.json"
OMR_MAP["page_15"]="logs/hybrid_generalization/sr_eval_page15_check2/omr_sr/predictions.json"
OMR_MAP["page_001"]="logs/hybrid_generalization/phase4b_cv_prokofiev_va_page_001/omr_sr/predictions.json"
OMR_MAP["page_004"]="logs/hybrid_generalization/phase4b_cv_prokofiev_va_page_004/omr_sr/predictions.json"


OUTPUT_DIR="logs/phase5b_promiscuous_union_eval"
mkdir -p "$OUTPUT_DIR"

for PAGE in "${PAGES[@]}"; do
    echo "--- Processing $PAGE ---"
    
    HYBRID_PREDS="$OUTPUT_DIR/${PAGE}_hybrid_preds.json"
    FILTER_OUTPUT_DIR="$OUTPUT_DIR/${PAGE}_filtered_output"

    # Check if all source files exist before proceeding
    if [ ! -f "${BASELINE_MAP[$PAGE]}" ] || [ ! -f "${SR_MAP[$PAGE]}" ] || [ ! -f "${OMR_MAP[$PAGE]}" ]; then
        echo "Error: Missing artifact for page $PAGE. Skipping."
        echo "Searched for:"
        echo "  ${BASELINE_MAP[$PAGE]}"
        echo "  ${SR_MAP[$PAGE]}"
        echo "  ${OMR_MAP[$PAGE]}"
        continue
    fi

    # 1. Generate Hybrid Predictions using Promiscuous Union
    ./.venv_pdf/bin/python tools/generate_hybrid_results.py \
        --baseline "${BASELINE_MAP[$PAGE]}" \
        --sr "${SR_MAP[$PAGE]}" \
        --omr "${OMR_MAP[$PAGE]}" \
        --output "$HYBRID_PREDS" \
        --gt "${GT_MAP[$PAGE]}" \
        --merge-strategy promiscuous_union

    # 2. Apply Phase 4 Row-only Filter
    ./.venv_pdf/bin/python experiments/fp_reduction/analyze_staff_consistency.py \
        --json "$HYBRID_PREDS" \
        --image "${IMG_MAP[$PAGE]}" \
        --gt "${GT_MAP[$PAGE]}" \
        --output "$FILTER_OUTPUT_DIR" \
        --no-use-ratio-tolerance --tol-top-px 5 --tol-bottom-px 5

done

echo "--- FN-only page evaluation complete ---"
