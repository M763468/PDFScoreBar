#!/usr/bin/env bash
set -u -o pipefail

PROJECT_ROOT="$(git rev-parse --show-toplevel)"
cd "$PROJECT_ROOT"

EXECUTION_IMAGE_REF="${ISSUE294_EXECUTION_IMAGE:-pdfscore_pipeline_gpu:latest}"
TRACE_TAG="$(date +%Y%m%d_%H%M%S)"
HEAD="$(git rev-parse HEAD)"
CONTAINER="pdfscore_issue294_geomprobe_${HEAD:0:12}_${TRACE_TAG}"
OUTPUT_DIR="$PROJECT_ROOT/logs/issue294"
STABILITY_OUTPUT="$OUTPUT_DIR/issue294_maintained_family_detector_stability_${TRACE_TAG}.json"
JITTER_OUTPUT="$OUTPUT_DIR/issue294_post277_edge_jitter_${TRACE_TAG}.json"
mkdir -p "$OUTPUT_DIR"

cleanup() {
  docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
}
trap cleanup EXIT

if ! docker image inspect "$EXECUTION_IMAGE_REF" >/dev/null 2>&1; then
  echo "ERROR: execution image unavailable: $EXECUTION_IMAGE_REF" >&2
  exit 2
fi
EXECUTION_IMAGE_ID="$(docker image inspect --format '{{.Id}}' "$EXECUTION_IMAGE_REF")"

declare -A SEEN_TARGETS=()
MOUNT_ARGS=( -v "$PROJECT_ROOT:/workspace" )
while IFS= read -r -d '' link; do
  target="$(readlink -f "$link" 2>/dev/null || true)"
  [[ -n "$target" && -e "$target" ]] || continue
  case "$target" in
    "$PROJECT_ROOT"|"$PROJECT_ROOT"/*) continue ;;
  esac
  [[ -z "${SEEN_TARGETS[$target]:-}" ]] || continue
  SEEN_TARGETS[$target]=1
  rel="${link#"$PROJECT_ROOT"/}"
  mode=":ro"
  case "$rel" in
    logs|logs/*|artifacts|artifacts/*|cache|cache/*) mode="" ;;
  esac
  MOUNT_ARGS+=( -v "$target:$target$mode" )
done < <(find "$PROJECT_ROOT" -maxdepth 3 -type l -print0)

printf 'execution_head=%s\nexecution_image_id=%s\ncontainer=%s\nstability_output=%s\njitter_output=%s\n' \
  "$HEAD" "$EXECUTION_IMAGE_ID" "$CONTAINER" "$STABILITY_OUTPUT" "$JITTER_OUTPUT"

docker run -dit --gpus all \
  --name "$CONTAINER" \
  "${MOUNT_ARGS[@]}" \
  -w /workspace \
  -e PYTHONPATH=/workspace \
  "$EXECUTION_IMAGE_ID" bash >/dev/null

set +e
docker exec -w /workspace "$CONTAINER" /opt/venv_pipeline/bin/python \
  tools/issue294/summarize_maintained_family_detector_stability.py >"$STABILITY_OUTPUT"
stability_status=$?
if [[ $stability_status -eq 0 ]]; then
  python3 -m json.tool "$STABILITY_OUTPUT" >/dev/null || stability_status=$?
fi

docker exec -w /workspace "$CONTAINER" /opt/venv_pipeline/bin/python \
  tools/issue294/diagnose_post277_edge_jitter.py >"$JITTER_OUTPUT"
jitter_status=$?
if [[ $jitter_status -eq 0 ]]; then
  python3 -m json.tool "$JITTER_OUTPUT" >/dev/null || jitter_status=$?
fi
set -e

printf '\nstability_status=%s\njitter_status=%s\n' "$stability_status" "$jitter_status"

if [[ $stability_status -eq 0 && $jitter_status -eq 0 ]]; then
  python3 tools/issue294/summarize_post277_geometry_robustness.py
  exit 0
fi

echo "One or more diagnostics failed; inspect the JSON outputs above." >&2
exit 1
