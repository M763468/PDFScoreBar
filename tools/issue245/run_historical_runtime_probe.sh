#!/usr/bin/env bash
set -euo pipefail

CONTAINER_NAME="${ISSUE245_HISTORICAL_CONTAINER:-sr_eval_gpu}"
MAIN_REPO_ROOT="${ISSUE245_MAIN_REPO_ROOT:-/home/masaki_muramatsu/ws_PDFScoreBar}"
OUTPUT_REL="logs/issue245_focused_homr_probe/canonical_va_prokofiev_symphony1_page001/historical_runtime_probe"
OUTPUT_HOST="$MAIN_REPO_ROOT/$OUTPUT_REL"
RUN_OUTPUT_REL="$OUTPUT_REL/run"
KEEP_SNAPSHOT="${ISSUE245_KEEP_HISTORICAL_SNAPSHOT:-0}"

WORKTREE_ROOT="$(git rev-parse --show-toplevel)"
HOST_COMMIT="$(git -C "$WORKTREE_ROOT" rev-parse HEAD)"
HOST_BRANCH="$(git -C "$WORKTREE_ROOT" branch --show-current)"

if ! docker inspect "$CONTAINER_NAME" >/dev/null 2>&1; then
    cat >&2 <<EOF
Historical container '$CONTAINER_NAME' was not found.
Do not rebuild Dockerfile.sr_eval yet: the historical external/homr checkout was
ignored by Git, so rebuilding from the current checkout would destroy the variable
this experiment is intended to preserve.
EOF
    exit 2
fi

mkdir -p "$OUTPUT_HOST"
docker inspect "$CONTAINER_NAME" >"$OUTPUT_HOST/source_container_inspect.json"
SOURCE_IMAGE_ID="$(docker inspect -f '{{.Image}}' "$CONTAINER_NAME")"
docker image inspect "$SOURCE_IMAGE_ID" >"$OUTPUT_HOST/source_image_inspect.json"

SNAPSHOT_TAG="pdfscorebar-issue245-sr-eval-snapshot:$(date +%Y%m%d-%H%M%S)"
SNAPSHOT_IMAGE_ID="$(docker commit --pause=true "$CONTAINER_NAME" "$SNAPSHOT_TAG")"
docker image inspect "$SNAPSHOT_IMAGE_ID" >"$OUTPUT_HOST/snapshot_image_inspect.json"

cleanup() {
    if [[ "$KEEP_SNAPSHOT" != "1" ]]; then
        docker image rm "$SNAPSHOT_TAG" >/dev/null 2>&1 || true
    fi
}
trap cleanup EXIT

printf '%s\n' \
    "container_name=$CONTAINER_NAME" \
    "source_image_id=$SOURCE_IMAGE_ID" \
    "snapshot_tag=$SNAPSHOT_TAG" \
    "snapshot_image_id=$SNAPSHOT_IMAGE_ID" \
    "host_commit=$HOST_COMMIT" \
    "host_branch=$HOST_BRANCH" \
    "keep_snapshot=$KEEP_SNAPSHOT" \
    >"$OUTPUT_HOST/host_snapshot_context.txt"

docker run --rm --gpus all \
    -v "$WORKTREE_ROOT":/workspace \
    -v "$MAIN_REPO_ROOT/logs":/workspace/logs \
    -v "$MAIN_REPO_ROOT/data/evaluation2":/workspace/data/evaluation2:ro \
    -w /workspace \
    -e PYTHONPATH=/workspace \
    -e ISSUE245_SOURCE_CONTAINER="$CONTAINER_NAME" \
    -e ISSUE245_SOURCE_IMAGE_ID="$SOURCE_IMAGE_ID" \
    -e ISSUE245_SNAPSHOT_IMAGE_ID="$SNAPSHOT_IMAGE_ID" \
    -e ISSUE245_HOST_COMMIT="$HOST_COMMIT" \
    -e ISSUE245_HOST_BRANCH="$HOST_BRANCH" \
    "$SNAPSHOT_IMAGE_ID" \
    /opt/venv_sr/bin/python \
    tools/issue245/run_historical_runtime_probe.py \
    --output-root "$RUN_OUTPUT_REL" \
    --force

cat <<EOF
Historical runtime probe completed.
Report:
  $OUTPUT_HOST/run/historical_runtime_probe_report.json
Provenance:
  $OUTPUT_HOST/run/historical_runtime_provenance.json
Model inventory:
  $OUTPUT_HOST/run/historical_runtime_model_artifacts.json
Container metadata:
  $OUTPUT_HOST/source_container_inspect.json
  $OUTPUT_HOST/source_image_inspect.json
  $OUTPUT_HOST/snapshot_image_inspect.json
EOF
