#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd)"
CONTAINER_NAME="${PDFSCORE_PIPELINE_CONTAINER:-pdfscore_pipeline_pytest_dev}"
CONTAINER_WORKDIR="${PDFSCORE_PIPELINE_WORKDIR:-/workspace}"

cd "$REPO_ROOT"

printf '%s\n' '## Host lint'
make lint

printf '%s\n' '## Container validation'
docker start "$CONTAINER_NAME" >/dev/null

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
'
