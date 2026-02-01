#!/usr/bin/env bash
set -euo pipefail

ROOT="logs/gt_rebuild_hybrid_eval/20251229T_phase5b_srcheck"
UNION_V1="${ROOT}/union_v1_sr_artifacts"
UNION_V2="${ROOT}/union_v2_current_plus_sr"
OUT_V1="${ROOT}/v1_sr_artifacts"
OUT_V2="${ROOT}/v2_current_plus_sr"

mkdir -p "${UNION_V1}" "${UNION_V2}" "${OUT_V1}" "${OUT_V2}"

pages=(page_10 page_15 page_001 page_004)

declare -A BASELINE_SR
BASELINE_SR[page_10]="logs/hybrid_generalization/sr_eval_page10_check2/baseline/page_10/page_10/page_10_detections.json"
BASELINE_SR[page_15]="logs/hybrid_generalization/sr_eval_page15_check2/baseline/page_15/page_15/page_15_detections.json"
BASELINE_SR[page_001]="logs/hybrid_generalization/phase4b_cv_prokofiev_va_page_001/baseline/page_001/page_001/page_001_detections.json"
BASELINE_SR[page_004]="logs/hybrid_generalization/phase4b_cv_prokofiev_va_page_004/baseline/page_004/page_004/page_004_detections.json"

declare -A SR_MAP
SR_MAP[page_10]="logs/hybrid_generalization/sr_eval_page10_check2/sr/page_10/page_10/page_10_detections.json"
SR_MAP[page_15]="logs/hybrid_generalization/sr_eval_page15_check2/sr/page_15/page_15/page_15_detections.json"
SR_MAP[page_001]="logs/hybrid_generalization/phase4b_cv_prokofiev_va_page_001/sr/page_001/page_001/page_001_detections.json"
SR_MAP[page_004]="logs/hybrid_generalization/phase4b_cv_prokofiev_va_page_004/sr/page_004/page_004/page_004_detections.json"

declare -A OMR_MAP
OMR_MAP[page_10]="logs/hybrid_generalization/sr_eval_page10_check2/omr_sr/predictions.json"
OMR_MAP[page_15]="logs/hybrid_generalization/sr_eval_page15_check2/omr_sr/predictions.json"
OMR_MAP[page_001]="logs/hybrid_generalization/phase4b_cv_prokofiev_va_page_001/omr_sr/predictions.json"
OMR_MAP[page_004]="logs/hybrid_generalization/phase4b_cv_prokofiev_va_page_004/omr_sr/predictions.json"

for page in "${pages[@]}"; do
  ./.venv_pdf/bin/python tools/generate_hybrid_results.py \
    --baseline "${BASELINE_SR[$page]}" \
    --sr "${SR_MAP[$page]}" \
    --omr "${OMR_MAP[$page]}" \
    --output "${UNION_V1}/${page}_hybrid_preds.json" \
    --merge-strategy promiscuous_union

  ./.venv_pdf/bin/python tools/generate_hybrid_results.py \
    --baseline "logs/homr_eval/20251229T_gt_rebuild_eval/${page}/${page}_detections.json" \
    --sr "${SR_MAP[$page]}" \
    --omr "${OMR_MAP[$page]}" \
    --output "${UNION_V2}/${page}_hybrid_preds.json" \
    --merge-strategy promiscuous_union

done

.venv_pdf/bin/python tools/run_gt_rebuild_hybrid_eval.py \
  --union-root "${UNION_V1}" \
  --output-root "${OUT_V1}"

.venv_pdf/bin/python tools/run_gt_rebuild_hybrid_eval.py \
  --union-root "${UNION_V2}" \
  --output-root "${OUT_V2}"

echo "Done."
