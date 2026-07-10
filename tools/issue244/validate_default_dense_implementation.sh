#!/usr/bin/env bash
set -uo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd)"
CONTAINER_NAME="${PDFSCORE_PIPELINE_CONTAINER:-pdfscore_pipeline_pytest_dev}"
CONTAINER_WORKDIR="${PDFSCORE_PIPELINE_WORKDIR:-/workspace}"

cd "$REPO_ROOT"

lint_status=0
validation_status=0

printf '%s\n' '## Host lint'
make lint || lint_status=$?
if ((lint_status != 0)); then
  printf 'Lint failed with status %s; continuing to focused tests.\n' "$lint_status"
fi

printf '%s\n' '## Container validation'
if ! docker start "$CONTAINER_NAME" >/dev/null; then
  exit 1
fi

docker exec \
  -w "$CONTAINER_WORKDIR" \
  -e PYTHONPATH="$CONTAINER_WORKDIR" \
  "$CONTAINER_NAME" \
  bash -lc '
set -euo pipefail

python3 -m pytest \
  tests/test_issue244_default_dense_detector_route.py \
  tests/test_issue244_dense_input_profile.py \
  tests/test_apply_corrections.py \
  tests/test_apply_corrections_mmr_suppressions.py \
  tests/test_apply_corrections_existing_overrides.py \
  tests/test_corrected_final_output.py \
  tests/test_apply_corrections_final_output.py

python3 tools/issue244/run_default_dense_page001_smoke.py --force
' || validation_status=$?

if ((validation_status != 0)); then
  printf 'Focused validation failed with status %s.\n' "$validation_status"
  if ((lint_status != 0)); then
    printf 'Lint also failed with status %s.\n' "$lint_status"
  fi
  exit "$validation_status"
fi

if ((lint_status != 0)); then
  printf 'Focused validation passed, but lint failed with status %s.\n' "$lint_status"
  exit "$lint_status"
fi

printf '%s\n' '## Focused validation passed'
