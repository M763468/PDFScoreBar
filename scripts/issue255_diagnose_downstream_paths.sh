#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE="${PDFSCORE_PIPELINE_IMAGE:-pdfscore_pipeline_gpu}"
OUTPUT="logs/verification/issue255_downstream_path_diagnostic.json"

cd "$ROOT"
rm -f "$OUTPUT"

docker run --rm \
  -v "$ROOT:/workspace" \
  -w /workspace \
  -e PYTHONPATH=/workspace \
  "$IMAGE" \
  /opt/venv_pipeline/bin/python \
  tools/verification/diagnose_issue255_downstream_paths.py \
  --output "/workspace/$OUTPUT" \
  >/dev/null

printf '%s\n' "$OUTPUT"
