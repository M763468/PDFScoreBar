#!/usr/bin/env bash
# Temporary safe runner for Issue #284 retained-artifact FN diagnostics.
# Intentionally does not propagate the diagnostic exit code to the interactive shell.
# Remove before PR together with diagnose_stage_e_fn_regression.py.

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$PROJECT_ROOT" || {
  echo "ERROR: failed to cd to $PROJECT_ROOT" >&2
  return 0 2>/dev/null || exit 0
}

PYTHON_BIN="${PYTHON:-$PROJECT_ROOT/.venv_pdf/bin/python}"
ACCEPTED_ROOT="${1:-logs/verification/detector_full68/issue255_production_restore_full68_top_level_worker_01}"
CURRENT_ROOT="${2:-logs/issue284/issue284_compile_full68_01_eager}"
OUTPUT_JSON="${3:-logs/issue284/issue284_fn_regression_diagnostics.json}"
RUN_LOG="${4:-logs/issue284/issue284_fn_regression_diagnostics.run.log}"
STATUS_FILE="${5:-logs/issue284/issue284_fn_regression_diagnostics.status.txt}"

mkdir -p "$(dirname "$OUTPUT_JSON")" "$(dirname "$RUN_LOG")" "$(dirname "$STATUS_FILE")"
: > "$RUN_LOG"

{
  echo "=== Issue #284 retained-artifact FN diagnostic ==="
  date --iso-8601=seconds 2>/dev/null || date
  echo "PROJECT_ROOT=$PROJECT_ROOT"
  echo "PYTHON_BIN=$PYTHON_BIN"
  echo "ACCEPTED_ROOT=$ACCEPTED_ROOT"
  echo "CURRENT_ROOT=$CURRENT_ROOT"
  echo "OUTPUT_JSON=$OUTPUT_JSON"
  echo "RUN_LOG=$RUN_LOG"
  echo "STATUS_FILE=$STATUS_FILE"
  echo

  if [ ! -x "$PYTHON_BIN" ]; then
    echo "ERROR: Python executable not found or not executable: $PYTHON_BIN" >&2
    DIAG_STATUS=127
  elif [ ! -d "$ACCEPTED_ROOT" ]; then
    echo "ERROR: accepted root not found: $ACCEPTED_ROOT" >&2
    DIAG_STATUS=64
  elif [ ! -d "$CURRENT_ROOT" ]; then
    echo "ERROR: current root not found: $CURRENT_ROOT" >&2
    DIAG_STATUS=65
  else
    echo "=== running diagnostic ==="
    set +e
    PYTHONPATH=. "$PYTHON_BIN" \
      tools/issue284/diagnose_stage_e_fn_regression.py \
      --accepted-root "$ACCEPTED_ROOT" \
      --current-root "$CURRENT_ROOT" \
      --output "$OUTPUT_JSON"
    DIAG_STATUS=$?
    set +e
  fi

  echo
  echo "=== diagnostic status ==="
  echo "$DIAG_STATUS"
  echo
  echo "=== output artifact ==="
  if [ -f "$OUTPUT_JSON" ]; then
    ls -lh "$OUTPUT_JSON"
  else
    echo "not created"
  fi
} > >(tee -a "$RUN_LOG") 2> >(tee -a "$RUN_LOG" >&2)

{
  echo "diagnostic_exit_code=$DIAG_STATUS"
  echo "output_json=$OUTPUT_JSON"
  echo "run_log=$RUN_LOG"
  if [ -f "$OUTPUT_JSON" ]; then
    echo "output_json_exists=true"
  else
    echo "output_json_exists=false"
  fi
} > "$STATUS_FILE"

echo
echo "Safe runner finished. The interactive shell will remain open."
echo "Diagnostic exit code: $DIAG_STATUS"
echo "Run log: $RUN_LOG"
echo "Status file: $STATUS_FILE"
echo "Output JSON: $OUTPUT_JSON"

# Deliberately do not `exit $DIAG_STATUS`: when pasted/run from an interactive
# terminal that could close the shell or be surfaced only as a terminal error.
return 0 2>/dev/null || exit 0
