#!/usr/bin/env bash
# Usage: run_downstream.sh <control|no_omr>   (CPU only; no upstream/CNN/MMR inference)
set -uo pipefail
variant=$1
manager=/home/masaki_muramatsu/ws_PDFScoreBar
commit=$(git -C "$manager/.worktrees/issue519" rev-parse HEAD)
image=pdfscore_issue409_staff_mask104
docker run --rm -v "$manager":/workspace -w /workspace \
  -e PYTHONPATH=/workspace/.worktrees/issue519 -e PYTHONDONTWRITEBYTECODE=1 \
  -e PDFSCORE_DOCKER_IMAGE_ID="$(docker inspect "$image" --format '{{.Id}}')" \
  -e PDFSCORE_HOST_SOURCE_COMMIT="$commit" \
  --entrypoint /opt/venv_pipeline/bin/python "$image" \
  /workspace/.worktrees/issue519/tools/issue519/replay_downstream.py \
  --variant "$variant" --out "/workspace/logs/issue519/downstream-20261108/$variant"
rc=$?
docker run --rm -v "$manager/logs/issue519":/out --entrypoint chown "$image" -R 1000:1001 /out
exit $rc
