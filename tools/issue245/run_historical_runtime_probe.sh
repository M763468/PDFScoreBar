#!/usr/bin/env bash
set -euo pipefail

CONTAINER_NAME="${ISSUE245_HISTORICAL_CONTAINER:-sr_eval_gpu}"
EXPLICIT_IMAGE="${ISSUE245_HISTORICAL_IMAGE:-}"
MAIN_REPO_ROOT="${ISSUE245_MAIN_REPO_ROOT:-/home/masaki_muramatsu/ws_PDFScoreBar}"
OUTPUT_REL="logs/issue245_focused_homr_probe/canonical_va_prokofiev_symphony1_page001/historical_runtime_probe"
OUTPUT_HOST="$MAIN_REPO_ROOT/$OUTPUT_REL"
RUN_OUTPUT_REL="$OUTPUT_REL/run"
KEEP_SNAPSHOT="${ISSUE245_KEEP_HISTORICAL_SNAPSHOT:-0}"

WORKTREE_ROOT="$(git rev-parse --show-toplevel)"
HOST_COMMIT="$(git -C "$WORKTREE_ROOT" rev-parse HEAD)"
HOST_BRANCH="$(git -C "$WORKTREE_ROOT" branch --show-current)"

mkdir -p "$OUTPUT_HOST/image_candidates"
docker container ls -a --no-trunc >"$OUTPUT_HOST/docker_containers.txt"
docker image ls -a --no-trunc >"$OUTPUT_HOST/docker_images.txt"

probe_image() {
    local image_ref="$1"
    docker run --rm --entrypoint /bin/sh "$image_ref" -lc '
        test -x /opt/venv_sr/bin/python
        /opt/venv_sr/bin/python -c '\''
import importlib.metadata as metadata
import homr
import sys

ort_version = metadata.version("onnxruntime-gpu")
if ort_version != "1.22.0":
    raise SystemExit(f"unexpected onnxruntime-gpu version: {ort_version}")
print(f"python={sys.version.split()[0]}")
print(f"homr_file={homr.__file__}")
print(f"homr_version={metadata.version(\"homr\")}")
print(f"onnxruntime_gpu_version={ort_version}")
'\''
    '
}

record_candidate() {
    local image_id="$1"
    local short_id="${image_id#sha256:}"
    short_id="${short_id:0:16}"
    local detail_path="$OUTPUT_HOST/image_candidates/${short_id}.txt"
    local tags
    local created

    tags="$(docker image inspect -f '{{json .RepoTags}}' "$image_id")"
    created="$(docker image inspect -f '{{.Created}}' "$image_id")"
    probe_image "$image_id" >"$detail_path" 2>&1
    printf '%s\t%s\t%s\t%s\n' "$image_id" "$created" "$tags" "$detail_path"
}

SOURCE_KIND=""
SOURCE_REF=""
SOURCE_IMAGE_ID=""
RUN_IMAGE_ID=""
SNAPSHOT_TAG=""
SNAPSHOT_IMAGE_ID=""

if [[ -n "$EXPLICIT_IMAGE" ]]; then
    if ! docker image inspect "$EXPLICIT_IMAGE" >/dev/null 2>&1; then
        echo "Explicit historical image was not found: $EXPLICIT_IMAGE" >&2
        exit 2
    fi
    if ! probe_image "$EXPLICIT_IMAGE" >"$OUTPUT_HOST/explicit_image_probe.txt" 2>&1; then
        cat "$OUTPUT_HOST/explicit_image_probe.txt" >&2
        echo "Explicit image does not satisfy the historical runtime contract." >&2
        exit 2
    fi
    SOURCE_KIND="explicit_image"
    SOURCE_REF="$EXPLICIT_IMAGE"
    SOURCE_IMAGE_ID="$(docker image inspect -f '{{.Id}}' "$EXPLICIT_IMAGE")"
    RUN_IMAGE_ID="$SOURCE_IMAGE_ID"
elif docker container inspect "$CONTAINER_NAME" >/dev/null 2>&1; then
    SOURCE_KIND="container_snapshot"
    SOURCE_REF="$CONTAINER_NAME"
    docker container inspect "$CONTAINER_NAME" >"$OUTPUT_HOST/source_container_inspect.json"
    SOURCE_IMAGE_ID="$(docker container inspect -f '{{.Image}}' "$CONTAINER_NAME")"

    SNAPSHOT_TAG="pdfscorebar-issue245-sr-eval-snapshot:$(date +%Y%m%d-%H%M%S)"
    SNAPSHOT_IMAGE_ID="$(docker commit --pause=true "$CONTAINER_NAME" "$SNAPSHOT_TAG")"
    RUN_IMAGE_ID="$SNAPSHOT_IMAGE_ID"
else
    SOURCE_KIND="discovered_image"
    SOURCE_REF="local-image-scan"
    CANDIDATE_TSV="$OUTPUT_HOST/historical_image_candidates.tsv"
    : >"$CANDIDATE_TSV"
    mapfile -t ALL_IMAGE_IDS < <(docker image ls -a --no-trunc --format '{{.ID}}' | sort -u)
    CANDIDATE_IDS=()

    for image_id in "${ALL_IMAGE_IDS[@]}"; do
        if probe_image "$image_id" >/dev/null 2>&1; then
            record_candidate "$image_id" >>"$CANDIDATE_TSV"
            CANDIDATE_IDS+=("$image_id")
        fi
    done

    if [[ "${#CANDIDATE_IDS[@]}" -eq 0 ]]; then
        cat >&2 <<EOF
The historical container '$CONTAINER_NAME' is absent, and no local Docker image
satisfies all historical runtime markers:

- /opt/venv_sr/bin/python exists
- homr imports successfully
- onnxruntime-gpu == 1.22.0

Do not rebuild Dockerfile.sr_eval yet. The historical external/homr checkout was
ignored by Git, so a current rebuild would not reproduce the missing runtime.
Docker inventories were written to:
  $OUTPUT_HOST/docker_containers.txt
  $OUTPUT_HOST/docker_images.txt
EOF
        exit 2
    fi

    if [[ "${#CANDIDATE_IDS[@]}" -gt 1 ]]; then
        cat >&2 <<EOF
Multiple historical-runtime image candidates were found. No image was selected
implicitly. Review:
  $CANDIDATE_TSV
  $OUTPUT_HOST/image_candidates/

Then rerun with an exact image ID or tag, for example:
  ISSUE245_HISTORICAL_IMAGE=sha256:<id> \\
    bash tools/issue245/run_historical_runtime_probe.sh
EOF
        exit 3
    fi

    SOURCE_IMAGE_ID="${CANDIDATE_IDS[0]}"
    RUN_IMAGE_ID="$SOURCE_IMAGE_ID"
fi

docker image inspect "$SOURCE_IMAGE_ID" >"$OUTPUT_HOST/source_image_inspect.json"
if [[ -n "$SNAPSHOT_IMAGE_ID" ]]; then
    docker image inspect "$SNAPSHOT_IMAGE_ID" >"$OUTPUT_HOST/snapshot_image_inspect.json"
fi

cleanup() {
    if [[ -n "$SNAPSHOT_TAG" && "$KEEP_SNAPSHOT" != "1" ]]; then
        docker image rm "$SNAPSHOT_TAG" >/dev/null 2>&1 || true
    fi
}
trap cleanup EXIT

printf '%s\n' \
    "source_kind=$SOURCE_KIND" \
    "source_ref=$SOURCE_REF" \
    "container_name=$CONTAINER_NAME" \
    "source_image_id=$SOURCE_IMAGE_ID" \
    "run_image_id=$RUN_IMAGE_ID" \
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
    -e ISSUE245_SNAPSHOT_IMAGE_ID="$RUN_IMAGE_ID" \
    -e ISSUE245_HOST_COMMIT="$HOST_COMMIT" \
    -e ISSUE245_HOST_BRANCH="$HOST_BRANCH" \
    "$RUN_IMAGE_ID" \
    /opt/venv_sr/bin/python \
    tools/issue245/run_historical_runtime_probe.py \
    --output-root "$RUN_OUTPUT_REL" \
    --force

cat <<EOF
Historical runtime probe completed.
Source kind: $SOURCE_KIND
Source image: $SOURCE_IMAGE_ID
Run image: $RUN_IMAGE_ID
Report:
  $OUTPUT_HOST/run/historical_runtime_probe_report.json
Provenance:
  $OUTPUT_HOST/run/historical_runtime_provenance.json
Model inventory:
  $OUTPUT_HOST/run/historical_runtime_model_artifacts.json
Docker metadata:
  $OUTPUT_HOST/docker_containers.txt
  $OUTPUT_HOST/docker_images.txt
  $OUTPUT_HOST/source_image_inspect.json
  $OUTPUT_HOST/host_snapshot_context.txt
EOF
