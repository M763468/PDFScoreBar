#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE="${PDFSCORE_PIPELINE_IMAGE:-pdfscore_pipeline_gpu}"
OUTPUT="logs/verification/issue255_downstream_path_diagnostic.json"
EXPECTED_BRANCH="fix/issue255-production-detector-restoration"

cd "$ROOT"
rm -f "$OUTPUT"

GIT_BRANCH="$(git branch --show-current)"
GIT_LOCAL_SHA="$(git rev-parse HEAD)"
GIT_REMOTE_SHA="$(git rev-parse "origin/$EXPECTED_BRANCH")"
if [[ -n "$(git status --porcelain)" ]]; then
  GIT_DIRTY=1
else
  GIT_DIRTY=0
fi

docker run --rm \
  -v "$ROOT:/workspace" \
  -w /workspace \
  -e PYTHONPATH=/workspace \
  -e ISSUE255_GIT_BRANCH="$GIT_BRANCH" \
  -e ISSUE255_GIT_LOCAL_SHA="$GIT_LOCAL_SHA" \
  -e ISSUE255_GIT_REMOTE_SHA="$GIT_REMOTE_SHA" \
  -e ISSUE255_GIT_DIRTY="$GIT_DIRTY" \
  "$IMAGE" \
  /opt/venv_pipeline/bin/python \
  tools/verification/diagnose_issue255_downstream_paths.py \
  --output "/workspace/$OUTPUT" \
  >/dev/null

printf '%s\n' "$OUTPUT"
