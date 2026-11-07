#!/usr/bin/env bash
# Usage: run_variant.sh <control|no_omr>   (run from the manager checkout host)
# Runs as root because the image's CNN cache is root-only (0600); outputs are chowned back.
set -uo pipefail
variant=$1
manager=/home/masaki_muramatsu/ws_PDFScoreBar
commit=$(git -C "$manager/.worktrees/issue519" rev-parse HEAD)
image=pdfscore_issue409_staff_mask104
image_id=$(docker inspect "$image" --format '{{.Id}}')
docker run --rm --gpus all \
  -v "$manager":/workspace -w /workspace \
  -e PYTHONPATH=/workspace/.worktrees/issue519 \
  -e PYTHONDONTWRITEBYTECODE=1 \
  -e PDFSCORE_DOCKER_IMAGE_ID="$image_id" \
  -e PDFSCORE_HOST_SOURCE_COMMIT="$commit" \
  --entrypoint /opt/venv_pipeline/bin/python "$image" \
  /workspace/.worktrees/issue519/tools/issue519/replay_omr_ablation.py \
  --variant "$variant" --out "/workspace/logs/issue519/ablation/$variant"
rc=$?
docker run --rm -v "$manager/logs/issue519":/out --entrypoint chown "$image" -R 1000:1001 /out
exit $rc
