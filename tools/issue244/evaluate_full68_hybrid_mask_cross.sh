#!/usr/bin/env bash
set -uo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd)"
CONTAINER_NAME="${PDFSCORE_PIPELINE_CONTAINER:-pdfscore_pipeline_pytest_dev}"
CONTAINER_WORKDIR="${PDFSCORE_PIPELINE_WORKDIR:-/workspace}"

cd "$REPO_ROOT"

make lint
lint_status=$?
if (( lint_status != 0 )); then
  printf 'Lint failed with status %s; continuing to cross-variant CNN evaluation.\n' \
    "$lint_status"
fi

if ! docker start "$CONTAINER_NAME" >/dev/null; then
  printf 'Failed to start execution container.\n'
  exit 1
fi

docker exec \
  -w "$CONTAINER_WORKDIR" \
  -e PYTHONPATH="$CONTAINER_WORKDIR" \
  "$CONTAINER_NAME" \
  python3 tools/issue244/evaluate_full68_cross_cnn.py
eval_status=$?

printf 'Validation summary: lint=%s cross_cnn_eval=%s\n' "$lint_status" "$eval_status"
if (( lint_status != 0 || eval_status != 0 )); then
  exit 1
fi
