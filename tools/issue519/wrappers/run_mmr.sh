#!/usr/bin/env bash
# Usage: run_mmr.sh <control|no_omr>
set -uo pipefail
variant=$1
manager=/home/masaki_muramatsu/ws_PDFScoreBar
image=pdfscore_issue409_staff_mask104
docker run --rm --gpus all -v "$manager":/workspace -w /workspace \
  -e PYTHONPATH=/workspace/.worktrees/issue519 -e PYTHONDONTWRITEBYTECODE=1 \
  --entrypoint /opt/venv_pipeline/bin/python "$image" \
  /workspace/.worktrees/issue519/tools/issue519/replay_mmr.py \
  --variant-root "/workspace/logs/issue519/ablation/$variant" \
  --out "/workspace/logs/issue519/ablation/mmr_$variant"
rc=$?
docker run --rm -v "$manager/logs/issue519":/out --entrypoint chown "$image" -R 1000:1001 /out
exit $rc
