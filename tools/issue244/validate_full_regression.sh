#!/usr/bin/env bash
set -uo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd)"
CONTAINER_NAME="${PDFSCORE_PIPELINE_CONTAINER:-pdfscore_pipeline_pytest_dev}"
CONTAINER_WORKDIR="${PDFSCORE_PIPELINE_WORKDIR:-/workspace}"
REUSE_FULL68="${PDFSCORE_REUSE_FULL68:-0}"
SKIP_TESTS="${PDFSCORE_SKIP_TESTS:-0}"
REGRESSION_ROOT="logs/issue244_full_regression"

cd "$REPO_ROOT"
mkdir -p "$REGRESSION_ROOT"

lint_status=0
pytest_status=0

printf '%s\n' '## Host lint'
make lint || lint_status=$?
if ((lint_status != 0)); then
  printf 'Lint failed with status %s; continuing to later validation stages.\n' "$lint_status"
fi

printf '%s\n' '## Start execution container'
if ! docker start "$CONTAINER_NAME" >/dev/null; then
  printf '%s\n' 'Failed to start execution container.'
  exit 1
fi

if [[ "$SKIP_TESTS" == "1" ]]; then
  printf '%s\n' '## Full pytest suite skipped by PDFSCORE_SKIP_TESTS=1'
else
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
fi

if [[ "$REUSE_FULL68" == "1" ]]; then
  printf '%s\n' '## Validate and reuse completed production-default full-68 pipeline'
  if ! docker exec \
    -w "$CONTAINER_WORKDIR" \
    -e PYTHONPATH="$CONTAINER_WORKDIR" \
    "$CONTAINER_NAME" \
    python3 -c '
import json
from pathlib import Path

root = Path("logs/issue244_full_regression")
summary_path = root / "run_summary.json"
manifest_path = root / "runs" / "production_default_full68" / "manifest.json"
page_inputs_path = root / "mmr_page_inputs.json"
for path in (summary_path, manifest_path, page_inputs_path):
    if not path.exists():
        raise SystemExit(f"Required completed-run artifact is missing: {path}")
summary = json.loads(summary_path.read_text(encoding="utf-8"))
route = summary.get("resolved_route", {})
page_count = summary.get("page_count")
if page_count != 68:
    raise SystemExit(f"Expected 68 completed pages, got {page_count}")
if route.get("profile") != "production_dense_v1" or route.get("selection") != "default":
    raise SystemExit(f"Unexpected completed route metadata: {route}")
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
if len(manifest.get("pages", [])) != 68:
    raise SystemExit("Completed manifest does not contain 68 pages")
print("Reusing completed full-68 run:", summary.get("run_dir"))
print("Route profile:", route.get("profile"))
print("Route selection:", route.get("selection"))
'
  then
    exit 1
  fi
else
  printf '%s\n' '## Production-default full-68 pipeline'
  if ! docker exec \
    -w "$CONTAINER_WORKDIR" \
    -e PYTHONPATH="$CONTAINER_WORKDIR" \
    "$CONTAINER_NAME" \
    bash -lc '
set -euo pipefail
mkdir -p logs/issue244_full_regression
python3 tools/issue244/run_production_default_full68.py --force \
  2>&1 | tee logs/issue244_full_regression/full68_pipeline.log
'; then
    exit 1
  fi
fi

printf '%s\n' '## Re-evaluate retained historical Stage E artifact against current GT'
if ! docker exec \
  -w "$CONTAINER_WORKDIR" \
  -e PYTHONPATH="$CONTAINER_WORKDIR" \
  "$CONTAINER_NAME" \
  python3 tools/issue120/eval_stage_e_contract.py \
    --run-root logs/issue120_e2e_recovery/stage_e_full_pipeline \
    --eval-inputs-dir logs/issue120_e2e_recovery/stage_e_full_pipeline/eval_inputs \
    --eval-output-dir logs/issue120_e2e_recovery/stage_e_full_pipeline/eval_detector \
    --allow-target-mismatch; then
  exit 1
fi

printf '%s\n' '## Evaluate current full-68 detector artifact against current GT'
if ! docker exec \
  -w "$CONTAINER_WORKDIR" \
  -e PYTHONPATH="$CONTAINER_WORKDIR" \
  "$CONTAINER_NAME" \
  python3 tools/issue120/eval_stage_e_contract.py \
    --run-root logs/issue244_full_regression/runs/production_default_full68 \
    --eval-inputs-dir logs/issue244_full_regression/detector_eval_inputs \
    --eval-output-dir logs/issue244_full_regression/detector_eval \
    --allow-target-mismatch; then
  exit 1
fi

printf '%s\n' '## Evaluate current full-68 MMR artifact'
if ! docker exec \
  -w "$CONTAINER_WORKDIR" \
  -e PYTHONPATH="$CONTAINER_WORKDIR" \
  "$CONTAINER_NAME" \
  bash -lc '
set -euo pipefail
mkdir -p logs/issue244_full_regression
python3 tools/issue94/eval_all_mmr.py \
  --page-inputs logs/issue244_full_regression/mmr_page_inputs.json \
  --output-root logs/issue244_full_regression/mmr_eval \
  2>&1 | tee logs/issue244_full_regression/mmr_eval.log
'; then
  exit 1
fi

printf '%s\n' '## Compare against current-GT historical detector, numbering, and MMR baselines'
if ! docker exec \
  -w "$CONTAINER_WORKDIR" \
  -e PYTHONPATH="$CONTAINER_WORKDIR" \
  "$CONTAINER_NAME" \
  python3 tools/issue244/check_full68_regression.py; then
  printf '%s\n' 'Regression checks failed; the report was still written.'
  printf '%s\n' 'Report: logs/issue244_full_regression/full68_regression_report.json'
  exit 1
fi

if ((lint_status != 0)); then
  printf 'Full pytest and regression passed, but lint failed with status %s.\n' "$lint_status"
  exit "$lint_status"
fi

printf '%s\n' '## Full regression passed'
printf '%s\n' 'Report: logs/issue244_full_regression/full68_regression_report.json'
