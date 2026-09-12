#!/usr/bin/env bash
set -euo pipefail

# Temporary Issue #294 execution wrapper. It does not add acceptance gates; it only
# makes failures in the existing one-shot runner observable and refreshes the run
# record after all output has been flushed. Remove before the production PR.

PROJECT_ROOT="$(git rev-parse --show-toplevel)"
cd "$PROJECT_ROOT"

RUNNER="tools/issue294/run_post277_resume_local.sh"
RECORDER="tools/issue294/record_post277_attempt.sh"
TRACE_DIR="$PROJECT_ROOT/logs/issue294"
TRACE_TAG="$(date +%Y%m%d_%H%M%S)"
TRACE_LOG="$TRACE_DIR/issue294_post277_driver_${TRACE_TAG}.trace.log"
mkdir -p "$TRACE_DIR"

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
