#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE="${PDFSCORE_PIPELINE_IMAGE:-pdfscore_pipeline_gpu}"
RUN_TAG="${1:-issue255_downstream_focused_scores_04}"
OUTPUT="logs/verification/downstream_full68/${RUN_TAG}/downstream_full68_verification_report.json"
BRANCH="fix/issue255-production-detector-restoration"

cd "$ROOT"

git fetch origin >/dev/null
LOCAL_SHA="$(git rev-parse HEAD)"
REMOTE_SHA="$(git rev-parse "origin/${BRANCH}")"
CURRENT_BRANCH="$(git branch --show-current)"

if [[ "$CURRENT_BRANCH" != "$BRANCH" ]]; then
  printf 'Wrong branch: %s\n' "$CURRENT_BRANCH" >&2
  exit 2
fi
if [[ "$LOCAL_SHA" != "$REMOTE_SHA" ]]; then
  printf 'Local branch is not at remote HEAD. Run:\n' >&2
  printf '  git merge --ff-only origin/%s\n' "$BRANCH" >&2
  exit 2
fi
if [[ -n "$(git status --porcelain)" ]]; then
  printf 'Working tree is not clean.\n' >&2
  exit 2
fi

bash scripts/issue255_diagnose_downstream_paths.sh >/dev/null

python3 - "$ROOT/logs/verification/issue255_downstream_path_diagnostic.json" <<'PY'
import json
import sys
from pathlib import Path
p = Path(sys.argv[1])
r = json.loads(p.read_text(encoding='utf-8'))
if r.get('passed') is not True:
    raise SystemExit(f'downstream path diagnostic failed: {p}')
PY

if [[ -e "$OUTPUT" ]]; then
  printf 'Output already exists: %s\n' "$OUTPUT" >&2
  exit 2
fi

docker run --rm \
  --gpus all \
  -v "$ROOT:/workspace" \
  -w /workspace \
  -e PYTHONPATH=/workspace \
  "$IMAGE" \
  /opt/venv_pipeline/bin/python \
  tools/verification/verify_downstream_full68.py \
  --run-tag "$RUN_TAG" \
  --score Shostakovich-Sym5-Va \
  --score Va_Prokofiev_Symphony1 \
  >/dev/null

printf '%s\n' "$OUTPUT"
