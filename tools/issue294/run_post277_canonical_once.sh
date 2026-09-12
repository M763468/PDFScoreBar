#!/usr/bin/env bash
set -euo pipefail

# Temporary Issue #294 execution wrapper. It does not add acceptance gates; it only
# creates a worktree-correct container, makes failures observable, and refreshes
# the run record after all output has been flushed. Remove before the production PR.

PROJECT_ROOT="$(git rev-parse --show-toplevel)"
cd "$PROJECT_ROOT"

RUNNER="tools/issue294/run_post277_resume_local.sh"
RECORDER="tools/issue294/record_post277_attempt.sh"
TRACE_DIR="$PROJECT_ROOT/logs/issue294"
TRACE_TAG="$(date +%Y%m%d_%H%M%S)"
TRACE_LOG="$TRACE_DIR/issue294_post277_driver_${TRACE_TAG}.trace.log"
EXPECTED_IMAGE_ID="sha256:5e1265263a5ba014814002c02fcfaf7f07a61e7000c13697db6c3087c7d2acdc"
HEAD="$(git rev-parse HEAD)"
CONTAINER="pdfscore_issue294_post277_${HEAD:0:12}_${TRACE_TAG}"
mkdir -p "$TRACE_DIR"

cleanup() {
  docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
}
trap cleanup EXIT

# The issue worktree intentionally contains host-local symlinks for retained data,
# logs, models and third-party assets. A plain /workspace bind does not expose an
# absolute symlink target inside the container, so bind each existing target at the
# same absolute path. Output/cache roots stay writable; other local assets are read-only.
declare -A SEEN_TARGETS=()
MOUNT_ARGS=( -v "$PROJECT_ROOT:/workspace" )
while IFS= read -r -d '' link; do
  target="$(readlink -f "$link" 2>/dev/null || true)"
  [[ -n "$target" && -e "$target" ]] || continue
  case "$target" in
    "$PROJECT_ROOT"|"$PROJECT_ROOT"/*)
      continue
      ;;
  esac
  [[ -z "${SEEN_TARGETS[$target]:-}" ]] || continue
  SEEN_TARGETS[$target]=1

  rel="${link#"$PROJECT_ROOT"/}"
  mode=":ro"
  case "$rel" in
    logs|logs/*|artifacts|artifacts/*|cache|cache/*)
      mode=""
      ;;
  esac
  MOUNT_ARGS+=( -v "$target:$target$mode" )
done < <(find "$PROJECT_ROOT" -maxdepth 3 -type l -print0)

printf 'Creating Issue #294 dedicated container: %s\n' "$CONTAINER"
docker run -dit --gpus all \
  --name "$CONTAINER" \
  "${MOUNT_ARGS[@]}" \
  -w /workspace \
  -e PYTHONPATH=/workspace \
  "$EXPECTED_IMAGE_ID" bash >/dev/null

actual_image="$(docker inspect --format '{{.Image}}' "$CONTAINER")"
workspace_source="$(docker inspect --format '{{range .Mounts}}{{if eq .Destination "/workspace"}}{{.Source}}{{end}}{{end}}' "$CONTAINER")"
if [[ "$actual_image" != "$EXPECTED_IMAGE_ID" ]]; then
  echo "ERROR: dedicated container image mismatch: $actual_image" >&2
  exit 2
fi
if [[ "$(readlink -f "$workspace_source")" != "$(readlink -f "$PROJECT_ROOT")" ]]; then
  echo "ERROR: dedicated container /workspace mismatch: $workspace_source" >&2
  exit 2
fi

# Preserve the previous dedicated-container behavior: targeted pytest is part of
# the existing validation sequence, so make it available if the base image lacks it.
if ! docker exec "$CONTAINER" /opt/venv_pipeline/bin/python -c 'import pytest' >/dev/null 2>&1; then
  docker exec "$CONTAINER" /opt/venv_pipeline/bin/python -m pip install pytest
fi

export ISSUE294_CONTAINER="$CONTAINER"
printf 'container=%s\ncontainer_workspace_source=%s\ncontainer_image_id=%s\n' \
  "$CONTAINER" "$workspace_source" "$actual_image"

# Keep xtrace out of the terminal, but persist it so a silent `set -e` exit always
# has a concrete command/line to diagnose. The existing runner still writes its
# normal human-readable run log and artifacts.
exec 3>>"$TRACE_LOG"
export BASH_XTRACEFD=3
export PS4='+ ${BASH_SOURCE}:${LINENO}: ${FUNCNAME[0]:-main}: '

set +e
bash -x "$RUNNER"
runner_status=$?
set -e
exec 3>&-
unset BASH_XTRACEFD PS4

latest_run_log="$(find "$TRACE_DIR" -maxdepth 1 -type f -name 'issue294_post277_full68_*_resume_local.log' -printf '%T@ %p\n' | sort -nr | head -1 | cut -d' ' -f2-)"
if [[ -z "$latest_run_log" || ! -f "$latest_run_log" ]]; then
  echo "ERROR: no Issue #294 post-#277 runner log found" >&2
  exit 2
fi

if [[ "$runner_status" -ne 0 ]]; then
  {
    printf '\n=== canonical driver failure diagnostics ===\n'
    printf 'runner_exit_code=%s\n' "$runner_status"
    printf 'trace_log=%s\n' "$TRACE_LOG"
    printf '%s\n' '--- trace tail ---'
    tail -n 80 "$TRACE_LOG"
  } >>"$latest_run_log"
fi

# This runs only after the child runner and its output pipe have closed, so the
# Issue record is generated from the fully-written log/artifacts rather than the
# runner EXIT trap's potentially stale snapshot.
bash "$RECORDER"

if [[ "$runner_status" -ne 0 ]]; then
  exit "$runner_status"
fi

printf 'Issue #294 canonical post-#277 runner completed.\n'
printf 'trace_log=%s\n' "$TRACE_LOG"
