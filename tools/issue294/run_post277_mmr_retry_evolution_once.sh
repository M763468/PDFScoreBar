#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(git rev-parse --show-toplevel)"
cd "$PROJECT_ROOT"

EXECUTION_IMAGE_REF="${ISSUE294_EXECUTION_IMAGE:-pdfscore_pipeline_gpu:latest}"
TRACE_TAG="$(date +%Y%m%d_%H%M%S)"
HEAD="$(git rev-parse HEAD)"
CONTAINER="pdfscore_issue294_retry_evo_${HEAD:0:12}_${TRACE_TAG}"
OUTPUT_DIR="$PROJECT_ROOT/logs/issue294"
OUTPUT="$OUTPUT_DIR/issue294_post277_mmr_retry_evolution_${TRACE_TAG}.json"
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

printf 'execution_head=%s\nexecution_image_id=%s\ncontainer=%s\noutput=%s\n' \
  "$HEAD" "$EXECUTION_IMAGE_ID" "$CONTAINER" "$OUTPUT"

docker run -dit --gpus all \
  --name "$CONTAINER" \
  "${MOUNT_ARGS[@]}" \
  -w /workspace \
  -e PYTHONPATH=/workspace \
  "$EXECUTION_IMAGE_ID" bash >/dev/null

docker exec -w /workspace "$CONTAINER" /opt/venv_pipeline/bin/python \
  tools/issue294/diagnose_post277_mmr_retry_evolution.py >"$OUTPUT"
python3 -m json.tool "$OUTPUT" >/dev/null
cat "$OUTPUT"
