#!/usr/bin/env bash
set -uo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd)"
CONTAINER_NAME="${PDFSCORE_PIPELINE_CONTAINER:-pdfscore_pipeline_pytest_dev}"
CONTAINER_WORKDIR="${PDFSCORE_PIPELINE_WORKDIR:-/workspace}"

cd "$REPO_ROOT"

lint_status=0
pytest_status=0

printf '%s\n' '## Host lint'
make lint || lint_status=$?
if ((lint_status != 0)); then
  printf 'Lint failed with status %s; continuing to the full pytest suite.\n' "$lint_status"
fi

printf '%s\n' '## Start execution container'
if ! docker start "$CONTAINER_NAME" >/dev/null; then
  printf '%s\n' 'Failed to start execution container.'
  exit 1
fi

printf '%s\n' '## Full pytest suite'
docker exec \
  -w "$CONTAINER_WORKDIR" \
  -e PYTHONPATH="$CONTAINER_WORKDIR" \
  "$CONTAINER_NAME" \
  python3 -m pytest tests/ || pytest_status=$?

if ((pytest_status != 0)); then
  printf 'Full pytest suite failed with status %s.\n' "$pytest_status"
  if ((lint_status != 0)); then
    printf 'Lint also failed with status %s.\n' "$lint_status"
  fi
  printf '%s\n' 'Skipping the expensive full-68 regression because pytest did not pass.'
  exit "$pytest_status"
fi

printf '%s\n' '## Production-default full-68 pipeline'
if ! docker exec \
  -w "$CONTAINER_WORKDIR" \
  -e PYTHONPATH="$CONTAINER_WORKDIR" \
  "$CONTAINER_NAME" \
  bash -lc '
set -euo pipefail
python3 tools/issue244/run_production_default_full68.py --force \
  2>&1 | tee logs/issue244_full_regression/full68_pipeline.log
'; then
  exit 1
fi

printf '%s\n' '## Re-evaluate retained historical Stage E artifact'
if ! docker exec \
  -w "$CONTAINER_WORKDIR" \
  -e PYTHONPATH="$CONTAINER_WORKDIR" \
  "$CONTAINER_NAME" \
  python3 tools/issue120/eval_stage_e_contract.py \
    --run-root logs/issue120_e2e_recovery/stage_e_full_pipeline \
    --eval-inputs-dir logs/issue120_e2e_recovery/stage_e_full_pipeline/eval_inputs \
    --eval-output-dir logs/issue120_e2e_recovery/stage_e_full_pipeline/eval_detector; then
  exit 1
fi

printf '%s\n' '## Evaluate current full-68 detector artifact'
if ! docker exec \
  -w "$CONTAINER_WORKDIR" \
  -e PYTHONPATH="$CONTAINER_WORKDIR" \
  "$CONTAINER_NAME" \
  python3 tools/issue120/eval_stage_e_contract.py \
    --run-root logs/issue244_full_regression/runs/production_default_full68 \
    --eval-inputs-dir logs/issue244_full_regression/detector_eval_inputs \
    --eval-output-dir logs/issue244_full_regression/detector_eval; then
  exit 1
fi

printf '%s\n' '## Evaluate current full-68 MMR artifact'
if ! docker exec \
  -w "$CONTAINER_WORKDIR" \
  -e PYTHONPATH="$CONTAINER_WORKDIR" \
  "$CONTAINER_NAME" \
  bash -lc '
set -euo pipefail
python3 tools/issue94/eval_all_mmr.py \
  --page-inputs logs/issue244_full_regression/mmr_page_inputs.json \
  --output-root logs/issue244_full_regression/mmr_eval \
  2>&1 | tee logs/issue244_full_regression/mmr_eval.log
'; then
  exit 1
fi

printf '%s\n' '## Compare against historical detector, numbering, and MMR baselines'
if ! docker exec \
  -w "$CONTAINER_WORKDIR" \
  -e PYTHONPATH="$CONTAINER_WORKDIR" \
  "$CONTAINER_NAME" \
  python3 tools/issue244/check_full68_regression.py; then
  exit 1
fi

if ((lint_status != 0)); then
  printf 'Full pytest and regression passed, but lint failed with status %s.\n' "$lint_status"
  exit "$lint_status"
fi

printf '%s\n' '## Full regression passed'
printf '%s\n' 'Report: logs/issue244_full_regression/full68_regression_report.json'
