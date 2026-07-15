#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
MAIN_REPO_ROOT="${ISSUE245_MAIN_REPO_ROOT:-/home/masaki_muramatsu/ws_PDFScoreBar}"
OUTPUT_ROOT="${MAIN_REPO_ROOT}/logs/issue245_local_homr_snapshot_probe"
BASE_IMAGE="${ISSUE245_REVISION_BASE_IMAGE:-pdfscore_pipeline_gpu}"
HOST_UID="$(id -u)"
HOST_GID="$(id -g)"
HOST_PYTHON="${ISSUE245_HOST_PYTHON:-python3}"

normalize_output_ownership() {
  mkdir -p "${OUTPUT_ROOT}"
  docker run --rm \
    --entrypoint /bin/sh \
    -v "${OUTPUT_ROOT}:/issue245-output" \
    "${BASE_IMAGE}" \
    -lc "chown -R ${HOST_UID}:${HOST_GID} /issue245-output"
}

cleanup() {
  status=$?
  trap - EXIT
  normalize_output_ownership || true
  exit "${status}"
}
trap cleanup EXIT

normalize_output_ownership

cd "${REPO_ROOT}"
ISSUE245_MAIN_REPO_ROOT="${MAIN_REPO_ROOT}" \
ISSUE245_REVISION_BASE_IMAGE="${BASE_IMAGE}" \
  "${HOST_PYTHON}" tools/issue245/run_local_homr_snapshot_probe.py "$@"
