#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(git rev-parse --show-toplevel)"
cd "$PROJECT_ROOT"

EXECUTION_IMAGE_REF="${ISSUE294_EXECUTION_IMAGE:-pdfscore_pipeline_gpu:latest}"
ACCEPTED_REBASE_HOST="/home/masaki_muramatsu/issue264_phase_c_rescore/phase_c_mmr_geometry_rebased_score_report.json"
ACCEPTED_REBASE_CONTAINER="/tmp/issue264_phase_c_mmr_geometry_rebased_score_report.json"
TRACE_TAG="$(date +%Y%m%d_%H%M%S)"
HEAD="$(git rev-parse HEAD)"
CONTAINER="pdfscore_issue294_mmr_cf_${HEAD:0:12}_${TRACE_TAG}"

cleanup() {
  docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
}
trap cleanup EXIT

if [[ ! -f "$ACCEPTED_REBASE_HOST" ]]; then
  echo "ERROR: accepted Issue #264 report not found: $ACCEPTED_REBASE_HOST" >&2
  exit 2
fi
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

printf 'execution_head=%s\nexecution_image_id=%s\ncontainer=%s\n' "$HEAD" "$EXECUTION_IMAGE_ID" "$CONTAINER"
docker run -dit --gpus all \
  --name "$CONTAINER" \
  "${MOUNT_ARGS[@]}" \
  -w /workspace \
  -e PYTHONPATH=/workspace \
  "$EXECUTION_IMAGE_ID" bash >/dev/null

docker cp "$ACCEPTED_REBASE_HOST" "$CONTAINER:$ACCEPTED_REBASE_CONTAINER"

docker exec -w /workspace "$CONTAINER" /opt/venv_pipeline/bin/python \
  tools/issue294/run_post277_mmr_horizontal_counterfactual.py \
  --accepted-rebase-report "$ACCEPTED_REBASE_CONTAINER"
