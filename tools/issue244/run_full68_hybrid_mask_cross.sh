#!/usr/bin/env bash
set -uo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd)"
CONTAINER_NAME="${PDFSCORE_PIPELINE_CONTAINER:-pdfscore_pipeline_pytest_dev}"
CONTAINER_WORKDIR="${PDFSCORE_PIPELINE_WORKDIR:-/workspace}"

cd "$REPO_ROOT"

lint_status=0
make lint || lint_status=$?
if (( lint_status != 0 )); then
  printf 'Lint failed with status %s; continuing to the cross experiment.\n' "$lint_status"
fi

if ! docker start "$CONTAINER_NAME" >/dev/null; then
  printf '%s\n' 'Failed to start execution container.'
  exit 1
fi

docker exec \
  -w "$CONTAINER_WORKDIR" \
  -e PYTHONPATH="$CONTAINER_WORKDIR" \
  "$CONTAINER_NAME" \
  python3 tools/issue244/run_full68_hybrid_mask_cross.py
experiment_status=$?

if (( experiment_status != 0 )); then
  exit "$experiment_status"
fi
exit "$lint_status"
