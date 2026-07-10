#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd)"
CONTAINER_NAME="${PDFSCORE_PIPELINE_CONTAINER:-pdfscore_pipeline_pytest_dev}"
CONTAINER_WORKDIR="${PDFSCORE_PIPELINE_WORKDIR:-/workspace}"

cd "$REPO_ROOT"

printf '%s\n' '## Host lint'
make lint

printf '%s\n' '## Start execution container'
docker start "$CONTAINER_NAME" >/dev/null

printf '%s\n' '## Full pytest suite'
docker exec \
  -w "$CONTAINER_WORKDIR" \
  -e PYTHONPATH="$CONTAINER_WORKDIR" \
  "$CONTAINER_NAME" \
  python3 -m pytest tests/

printf '%s\n' '## Production-default full-68 pipeline'
docker exec \
  -w "$CONTAINER_WORKDIR" \
  -e PYTHONPATH="$CONTAINER_WORKDIR" \
  "$CONTAINER_NAME" \
  bash -lc '
set -euo pipefail
python3 tools/issue244/run_production_default_full68.py --force \
  2>&1 | tee logs/issue244_full_regression/full68_pipeline.log
'

printf '%s\n' '## Re-evaluate retained historical Stage E artifact'
docker exec \
  -w "$CONTAINER_WORKDIR" \
  -e PYTHONPATH="$CONTAINER_WORKDIR" \
  "$CONTAINER_NAME" \
  python3 tools/issue120/eval_stage_e_contract.py \
    --run-root logs/issue120_e2e_recovery/stage_e_full_pipeline \
    --eval-inputs-dir logs/issue120_e2e_recovery/stage_e_full_pipeline/eval_inputs \
    --eval-output-dir logs/issue120_e2e_recovery/stage_e_full_pipeline/eval_detector

printf '%s\n' '## Evaluate current full-68 detector artifact'
docker exec \
  -w "$CONTAINER_WORKDIR" \
  -e PYTHONPATH="$CONTAINER_WORKDIR" \
  "$CONTAINER_NAME" \
  python3 tools/issue120/eval_stage_e_contract.py \
    --run-root logs/issue244_full_regression/runs/production_default_full68 \
    --eval-inputs-dir logs/issue244_full_regression/detector_eval_inputs \
    --eval-output-dir logs/issue244_full_regression/detector_eval

printf '%s\n' '## Evaluate current full-68 MMR artifact'
docker exec \
  -w "$CONTAINER_WORKDIR" \
  -e PYTHONPATH="$CONTAINER_WORKDIR" \
  "$CONTAINER_NAME" \
  bash -lc '
set -euo pipefail
python3 tools/issue94/eval_all_mmr.py \
  --page-inputs logs/issue244_full_regression/mmr_page_inputs.json \
  --output-root logs/issue244_full_regression/mmr_eval \
  2>&1 | tee logs/issue244_full_regression/mmr_eval.log
'

printf '%s\n' '## Compare against historical detector, numbering, and MMR baselines'
docker exec \
  -w "$CONTAINER_WORKDIR" \
  -e PYTHONPATH="$CONTAINER_WORKDIR" \
  "$CONTAINER_NAME" \
  python3 tools/issue244/check_full68_regression.py

printf '%s\n' '## Full regression passed'
printf '%s\n' 'Report: logs/issue244_full_regression/full68_regression_report.json'
