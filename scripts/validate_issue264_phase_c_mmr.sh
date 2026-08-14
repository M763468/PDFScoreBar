#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

python_bin="${PYTHON:-$repo_root/.venv_pdf/bin/python}"
container="${CONTAINER:-issue264_phase_c_gpu}"
image="${PIPELINE_IMAGE:-pdfscore_pipeline_gpu}"
run_id="${RUN_ID:-issue264_phase_c_current_production_full68}"

expected_base="acdda23a7ff1f0bc74f702a03f24f6a2985e8d1a"
merge_base="$(git merge-base HEAD origin/develop 2>/dev/null || true)"
echo "=== repository ==="
echo "head:       $(git rev-parse HEAD)"
echo "branch:     $(git branch --show-current)"
echo "merge-base: ${merge_base:-<unavailable>}"
echo "Phase C baseline develop commit: $expected_base"

echo
echo "=== focused validation ==="
bash scripts/check_pr_slice.sh \
  issue264-phase-c-mmr-regression \
  --python "$python_bin"

echo
echo "=== pipeline image/container ==="
if ! docker image inspect "$image" >/dev/null 2>&1; then
  echo "Required pipeline image is missing: $image" >&2
  echo "Build the maintained image first (make docker-build)." >&2
  false
fi

if docker inspect "$container" >/dev/null 2>&1; then
  if [ "$(docker inspect --format '{{.State.Running}}' "$container")" != "true" ]; then
    docker start "$container" >/dev/null
  fi
else
  docker run -dit \
    --gpus all \
    --name "$container" \
    -v "$repo_root:/workspace" \
    -w /workspace \
    -e PYTHONPATH=/workspace \
    "$image" \
    bash >/dev/null
fi

image_id="$(docker inspect --format '{{.Image}}' "$container")"
echo "container: $container"
echo "image:     $image"
echo "image id:  $image_id"

docker exec "$container" nvidia-smi >/dev/null

echo
echo "=== current-production full-68 MMR regression ==="
docker exec \
  -w /workspace \
  -e PYTHONPATH=/workspace \
  -e ISSUE264_CONTAINER_NAME="$container" \
  -e ISSUE264_CONTAINER_IMAGE_ID="$image_id" \
  "$container" \
  /opt/venv_pipeline/bin/python \
  tools/issue264/run_phase_c_mmr_regression.py \
  --run-id "$run_id" \
  "$@"

echo
echo "report: logs/issue264_phase_c_mmr_regression/$run_id/phase_c_mmr_regression_report.json"
