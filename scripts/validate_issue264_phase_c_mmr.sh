#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

python_bin="${PYTHON:-$repo_root/.venv_pdf/bin/python}"
container="${CONTAINER:-issue264_phase_c_gpu}"
image="${PIPELINE_IMAGE:-pdfscore_pipeline_gpu}"
run_id="${RUN_ID:-issue264_phase_c_current_production_full68}"

# This wrapper owns the report location it validates. Forwarding the runner's own
# run/output selectors would let the expensive replay write somewhere different
# from the path checked below, so reject those overrides before doing any work.
for arg in "$@"; do
  case "$arg" in
    --run-id | --run-id=* | --output-root | --output-root=*)
      echo "Do not pass --run-id or --output-root through this validation wrapper." >&2
      echo "Use RUN_ID to select the Phase C run id; the acceptance output root is fixed." >&2
      false
      ;;
  esac
done

# The container imports the live bind-mounted repository. A dirty worktree would
# execute bytes that are not represented by git rev-parse HEAD while the report
# attributes the result to that commit, so acceptance requires an exact clean tree.
worktree_status="$(git status --porcelain=v1 --untracked-files=all)"
if [ -n "$worktree_status" ]; then
  echo "Phase C acceptance requires a clean worktree, including untracked files." >&2
  printf '%s\n' "$worktree_status" >&2
  false
fi

expected_base="acdda23a7ff1f0bc74f702a03f24f6a2985e8d1a"
host_head="$(git rev-parse HEAD)"
merge_base="$(git merge-base HEAD origin/develop 2>/dev/null || true)"
invocation_id="${ISSUE264_INVOCATION_ID:-${host_head}-$$-$(date +%s%N)}"
echo "=== repository ==="
echo "head:       $host_head"
echo "branch:     $(git branch --show-current)"
echo "merge-base: ${merge_base:-<unavailable>}"
echo "Phase C baseline develop commit: $expected_base"
echo "invocation: $invocation_id"

echo
echo "=== focused behavior validation ==="
# Run behavior tests before the long real-artifact replay. The final PR lint/format
# gate is intentionally run after artifact validation so formatter-only churn cannot
# prevent collection of the expensive Phase C result.
bash scripts/check_pr_slice.sh \
  issue264-phase-c-mmr-regression \
  --pytest-only \
  --python "$python_bin"

echo
echo "=== pipeline image/container ==="
if ! docker image inspect "$image" >/dev/null 2>&1; then
  echo "Required pipeline image is missing: $image" >&2
  echo "Build the maintained image first (make docker-build)." >&2
  false
fi

requested_image_id="$(docker image inspect --format '{{.Id}}' "$image")"
if docker inspect "$container" >/dev/null 2>&1; then
  existing_image_id="$(docker inspect --format '{{.Image}}' "$container")"
  if [ "$existing_image_id" != "$requested_image_id" ]; then
    echo "Container image mismatch; recreating dedicated Phase C container." >&2
    echo "container image:  $existing_image_id" >&2
    echo "requested image:  $requested_image_id" >&2
    docker rm -f "$container" >/dev/null
  fi
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
if [ "$image_id" != "$requested_image_id" ]; then
  echo "Phase C container image does not match requested image after setup." >&2
  false
fi

echo "container: $container"
echo "image:     $image"
echo "image id:  $image_id"

docker exec "$container" nvidia-smi >/dev/null

echo
echo "=== current-production full-68 MMR regression ==="
# The runner retains direct historical-index scoring as diagnostic evidence. Only
# those explicitly classified direct-index score gates may be superseded by the
# geometry-rebased acceptance below. All other source gates remain mandatory.
raw_status=0
if docker exec \
  -w /workspace \
  -e PYTHONPATH=/workspace \
  -e ISSUE264_CONTAINER_NAME="$container" \
  -e ISSUE264_CONTAINER_IMAGE_ID="$image_id" \
  -e ISSUE264_HOST_GIT_HEAD="$host_head" \
  -e ISSUE264_INVOCATION_ID="$invocation_id" \
  "$container" \
  /opt/venv_pipeline/bin/python \
  tools/issue264/run_phase_c_mmr_regression_container.py \
  --run-id "$run_id" \
  "$@"; then
  raw_status=0
else
  raw_status=$?
fi

report="logs/issue264_phase_c_mmr_regression/$run_id/phase_c_mmr_regression_report.json"
if [ ! -f "$report" ]; then
  echo "Phase C source report was not produced: $report" >&2
  false
fi

echo "direct-index runner exit: $raw_status (canonical source-integrity gate follows)"
echo "source report: $report"

echo
echo "=== source report integrity / non-index production gates ==="
# This rejects stale reports from an earlier invocation and carries every source
# gate forward except the three historical-index score gates handled by the spatial
# rebase. It also requires the report to be bound to the current HEAD.
PYTHONPATH=. "$python_bin" \
  tools/issue264/phase_c_acceptance_integrity.py \
  --report "$report" \
  --expected-invocation-id "$invocation_id" \
  --expected-git-head "$host_head"

echo
echo "=== geometry-rebased MMR acceptance ==="
rebased_report="logs/issue264_phase_c_mmr_regression/$run_id/phase_c_mmr_geometry_rebased_score_report.json"
PYTHONPATH=. "$python_bin" \
  tools/issue264/rescore_phase_c_mmr_geometry_rebased.py \
  --report "$report" \
  --output "$rebased_report"

echo
echo "=== final lint/format gate ==="
make lint

echo
echo "source report:  $report"
echo "rebased report: $rebased_report"
