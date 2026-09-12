#!/usr/bin/env bash
set -euo pipefail

# One-shot local execution driver for Issue #294 after merging develop/#277.
# Repository changes are experiment-only. Production source/config/dispatch are not edited.

PROJECT_ROOT="$(git rev-parse --show-toplevel)"
cd "$PROJECT_ROOT"

REQUESTED_CONTAINER="${ISSUE294_CONTAINER:-pdfscore_issue294_profile_worktree}"
CONTAINER="$REQUESTED_CONTAINER"
WORKTREE_CONTAINER_BASE="${ISSUE294_WORKTREE_CONTAINER:-pdfscore_issue294_post277_worktree}"
EXPECTED_IMAGE_ID="sha256:5e1265263a5ba014814002c02fcfaf7f07a61e7000c13697db6c3087c7d2acdc"
CONTAINER_IMAGE="${ISSUE294_CONTAINER_IMAGE:-$EXPECTED_IMAGE_ID}"
REQUIRED_DEVELOP="edc17ee08de6694827c67d4ab8b30c2adc1f05e3"
LATEST_HOMR="${ISSUE294_LATEST_HOMR_COMMIT:-457e7c6518a10ba755db2e60883419e56c4d7369}"
ACCEPTED_REBASE="${ISSUE294_ACCEPTED_REBASE_REPORT:-/home/masaki_muramatsu/issue264_phase_c_rescore/phase_c_mmr_geometry_rebased_score_report.json}"
OLD_MANIFEST="${ISSUE294_RETAINED_MANIFEST:-$PROJECT_ROOT/logs/issue294/issue294_full68_refresh_02/full68_host.json}"
WEIGHT_REL="external/realesrgan/weights/RealESRGAN_x4plus.pth"
WEIGHT_SHA="4fa0d38905f75ac06eb49a7951b426670021be3018265fd191d2125df9d682f1"
WEIGHT_SIZE="67040989"
STAMP="${ISSUE294_RUN_SUFFIX:-$(date +%Y%m%d_%H%M%S)}"
RUN_TAG="${ISSUE294_RUN_TAG:-issue294_post277_full68_${STAMP}}"
FOCUSED_OUT="$PROJECT_ROOT/logs/issue294/issue294_post277_focused_${STAMP}.json"
FULL_MMR_OUT="$PROJECT_ROOT/logs/issue294/${RUN_TAG}/post277_mapping_guarded_mmr.json"
LOCAL_LOG="$PROJECT_ROOT/logs/issue294/${RUN_TAG}_resume_local.log"
CONTAINER_ACCEPTED="/tmp/issue294_phase_c_mmr_geometry_rebased_score_report.json"

mkdir -p "$PROJECT_ROOT/logs/issue294"
exec > >(tee -a "$LOCAL_LOG") 2>&1

record_attempt_on_exit() {
  local status=$?
  trap - EXIT
  if [[ -f "$PROJECT_ROOT/tools/issue294/record_post277_acceptance.py" ]]; then
    python3 "$PROJECT_ROOT/tools/issue294/record_post277_acceptance.py" || true
  fi
  exit "$status"
}
trap record_attempt_on_exit EXIT

printf 'Issue #294 post-#277 local runner\n'
printf 'repo=%s\nrun_tag=%s\nrequested_container=%s\n' \
  "$PROJECT_ROOT" "$RUN_TAG" "$REQUESTED_CONTAINER"

HEAD="$(git rev-parse HEAD)"
if ! git merge-base --is-ancestor "$REQUIRED_DEVELOP" "$HEAD"; then
  echo "ERROR: HEAD=$HEAD does not contain required develop commit $REQUIRED_DEVELOP"
  echo "Merge origin/develop into perf/issue294-homr-baseline-refresh first."
  exit 2
fi
printf 'execution_head=%s\nrequired_develop=%s\n' "$HEAD" "$REQUIRED_DEVELOP"

container_exists() {
  docker inspect "$1" >/dev/null 2>&1
}

container_workspace_source() {
  docker inspect --format '{{range .Mounts}}{{if eq .Destination "/workspace"}}{{.Source}}{{end}}{{end}}' "$1"
}

start_if_stopped() {
  local name="$1"
  if [[ "$(docker inspect --format '{{.State.Running}}' "$name")" != "true" ]]; then
    docker start "$name" >/dev/null
  fi
}

ensure_issue_worktree_container() {
  local project_real source source_real dedicated image common_git logs_source data_source
  project_real="$(readlink -f "$PROJECT_ROOT")"

  if container_exists "$REQUESTED_CONTAINER"; then
    start_if_stopped "$REQUESTED_CONTAINER"
    source="$(container_workspace_source "$REQUESTED_CONTAINER")"
    source_real=""
    if [[ -n "$source" && -e "$source" ]]; then
      source_real="$(readlink -f "$source")"
    fi
    if [[ "$source_real" == "$project_real" ]]; then
      CONTAINER="$REQUESTED_CONTAINER"
      return
    fi
    printf 'container_mount_mismatch=%s -> %s\n' "${source:-<none>}" "$project_real"
  fi

  image="${CONTAINER_IMAGE:-pdfscore_pipeline_gpu}"
  dedicated="$WORKTREE_CONTAINER_BASE"
  if container_exists "$dedicated"; then
    source="$(container_workspace_source "$dedicated")"
    source_real=""
    if [[ -n "$source" && -e "$source" ]]; then
      source_real="$(readlink -f "$source")"
    fi
    if [[ "$source_real" != "$project_real" ]]; then
      dedicated="${WORKTREE_CONTAINER_BASE}_${HEAD:0:12}_${STAMP}"
    fi
  fi

  if ! container_exists "$dedicated"; then
    common_git="$(readlink -f "$(git rev-parse --git-common-dir)")"
    logs_source="$(readlink -f "$PROJECT_ROOT/logs")"
    data_source=""
    if [[ -e "$PROJECT_ROOT/data" ]]; then
      data_source="$(readlink -f "$PROJECT_ROOT/data")"
    fi

    args=(
      docker run -dit --gpus all
      --name "$dedicated"
      -v "$project_real:/workspace"
      -v "$common_git:$common_git:ro"
      -w /workspace
      -e PYTHONPATH=/workspace
    )
    if [[ "$logs_source" != "$project_real/logs" ]]; then
      args+=( -v "$logs_source:$logs_source" )
    fi
    if [[ -n "$data_source" && -d "$data_source" && "$data_source" != "$project_real/data" ]]; then
      args+=( -v "$data_source:$data_source:ro" )
    fi
    "${args[@]}" "$image" bash >/dev/null
  else
    start_if_stopped "$dedicated"
  fi

  source="$(container_workspace_source "$dedicated")"
  source_real="$(readlink -f "$source")"
  if [[ "$source_real" != "$project_real" ]]; then
    echo "ERROR: dedicated container /workspace mismatch: $source_real != $project_real"
    exit 2
  fi
  CONTAINER="$dedicated"

  if ! docker exec "$CONTAINER" /opt/venv_pipeline/bin/python -c 'import pytest' >/dev/null 2>&1; then
    docker exec "$CONTAINER" /opt/venv_pipeline/bin/python -m pip install pytest
  fi
}

ensure_issue_worktree_container
export ISSUE294_CONTAINER="$CONTAINER"
ACTUAL_IMAGE_ID="$(docker inspect --format '{{.Image}}' "$CONTAINER")"
if [[ "$ACTUAL_IMAGE_ID" != "$EXPECTED_IMAGE_ID" ]]; then
  echo "ERROR: container image mismatch: $ACTUAL_IMAGE_ID != $EXPECTED_IMAGE_ID"
  exit 2
fi
CONTAINER_WORKSPACE_SOURCE="$(container_workspace_source "$CONTAINER")"
printf 'container=%s\ncontainer_workspace_source=%s\ncontainer_image_id=%s\nexecution_head=%s\n' \
  "$CONTAINER" "$CONTAINER_WORKSPACE_SOURCE" "$ACTUAL_IMAGE_ID" "$HEAD"

if [[ ! -f "$ACCEPTED_REBASE" ]]; then
  echo "ERROR: accepted #264 rebase report missing: $ACCEPTED_REBASE"
  exit 2
fi
if [[ ! -f "$OLD_MANIFEST" ]]; then
  echo "ERROR: retained valid full68 manifest missing: $OLD_MANIFEST"
  exit 2
fi

# Keep the accepted physical-GT report outside tracked/bind-mounted repository state.
docker cp "$ACCEPTED_REBASE" "$CONTAINER:$CONTAINER_ACCEPTED"

# Validate the known Real-ESRGAN production support weight before any expensive inference.
WEIGHT_SOURCE=""
WEIGHT_CANDIDATES=()
if [[ -n "${ISSUE294_REALESRGAN_WEIGHT:-}" ]]; then
  WEIGHT_CANDIDATES+=("$ISSUE294_REALESRGAN_WEIGHT")
fi
WEIGHT_CANDIDATES+=(
  "$PROJECT_ROOT/$WEIGHT_REL"
  "$PROJECT_ROOT/../ws_PDFScoreBar/$WEIGHT_REL"
)
for candidate in "${WEIGHT_CANDIDATES[@]}"; do
  if [[ -f "$candidate" ]] \
    && [[ "$(stat -c '%s' "$candidate")" == "$WEIGHT_SIZE" ]] \
    && [[ "$(sha256sum "$candidate" | awk '{print $1}')" == "$WEIGHT_SHA" ]]; then
    WEIGHT_SOURCE="$candidate"
    break
  fi
done
if [[ -z "$WEIGHT_SOURCE" ]]; then
  echo "ERROR: verified RealESRGAN_x4plus.pth not found."
  echo "Set ISSUE294_REALESRGAN_WEIGHT to the verified weight path or place it at $PROJECT_ROOT/$WEIGHT_REL."
  exit 2
fi
mkdir -p "$PROJECT_ROOT/$(dirname "$WEIGHT_REL")"
if [[ "$WEIGHT_SOURCE" != "$PROJECT_ROOT/$WEIGHT_REL" ]]; then
  cp -p "$WEIGHT_SOURCE" "$PROJECT_ROOT/$WEIGHT_REL"
fi
CONTAINER_WEIGHT_SHA="$(docker exec "$CONTAINER" sha256sum "/workspace/$WEIGHT_REL" | awk '{print $1}')"
if [[ "$CONTAINER_WEIGHT_SHA" != "$WEIGHT_SHA" ]]; then
  echo "ERROR: container does not see verified Real-ESRGAN weight: $CONTAINER_WEIGHT_SHA"
  exit 2
fi

printf '\n=== targeted post-#277 tests ===\n'
docker exec -w /workspace -e PYTHONPATH=/workspace "$CONTAINER" \
  /opt/venv_pipeline/bin/python -m pytest \
  tests/test_issue294_post277_mapping_guarded_mmr.py \
  tests/test_issue294_post277_full68_host.py \
  tests/test_issue294_mapping_guarded_connector_positive_candidate.py \
  tests/test_issue294_full68_host.py \
  tests/test_issue294_downstream_candidate_matrix.py \
  tests/test_mmr_ocr_heuristics.py

printf '\n=== repository fast/lint gates ===\n'
make test-fast
make lint

printf '\n=== focused retained-artifact post-#277 MMR gate ===\n'
docker exec -w /workspace -e PYTHONPATH=/workspace "$CONTAINER" \
  /opt/venv_pipeline/bin/python tools/issue294/run_post277_mapping_guarded_mmr.py \
  --full68-manifest /workspace/logs/issue294/issue294_full68_refresh_02/full68_host.json \
  --accepted-rebase-report "$CONTAINER_ACCEPTED" \
  --output "/workspace/logs/issue294/$(basename "$FOCUSED_OUT")"

printf '\n=== true-x4 fixed-support smoke ===\n'
SMOKE_ROOT="/workspace/temp/${RUN_TAG}_fixed_support_smoke"
docker exec -w /workspace -e PYTHONPATH=/workspace "$CONTAINER" \
  /opt/venv_pipeline/bin/python tools/issue294/run_fixed_support_smoke.py \
  --image /workspace/data/evaluation2/images/Va_Prokofiev_Symphony1/page_004.png \
  --output-root "$SMOKE_ROOT"

printf '\n=== fresh mapping-guarded canonical full68 ===\n'
PYTHON="${ISSUE294_HOST_PYTHON:-$PROJECT_ROOT/.venv_pdf/bin/python}"
if [[ ! -x "$PYTHON" ]]; then
  echo "ERROR: host Python missing/not executable: $PYTHON"
  exit 2
fi
"$PYTHON" tools/issue294/run_post277_mapping_guarded_full68_host.py \
  --run-tag "$RUN_TAG" \
  --latest-homr-commit "$LATEST_HOMR" \
  --chunk-size 6

printf '\n=== fresh full68 post-#277 MMR semantic gate ===\n'
docker exec -w /workspace -e PYTHONPATH=/workspace "$CONTAINER" \
  /opt/venv_pipeline/bin/python tools/issue294/run_post277_mapping_guarded_mmr.py \
  --full68-manifest "/workspace/logs/issue294/${RUN_TAG}/full68_host.json" \
  --accepted-rebase-report "$CONTAINER_ACCEPTED" \
  --full68 \
  --expect-production-reference \
  --require-manifest-head \
  --output "/workspace/logs/issue294/${RUN_TAG}/post277_mapping_guarded_mmr.json"

printf '\n=== completed ===\n'
printf 'head=%s\nrun_tag=%s\nfocused=%s\nmanifest=%s\nmmr=%s\nlog=%s\n' \
  "$HEAD" \
  "$RUN_TAG" \
  "$FOCUSED_OUT" \
  "$PROJECT_ROOT/logs/issue294/$RUN_TAG/full68_host.json" \
  "$FULL_MMR_OUT" \
  "$LOCAL_LOG"
