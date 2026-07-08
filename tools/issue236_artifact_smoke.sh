#!/usr/bin/env bash
set -euo pipefail

# Temporary helper for PR #243 / Issue #236 real-artifact smoke.
# This file is intentionally temporary and should be removed before merging the PR.
#
# Usage:
#   bash tools/issue236_artifact_smoke.sh [path/to/review/manual_correction_input.json]
#
# Optional environment variables:
#   CONTAINER=pdfscore_pipeline_pytest_dev
#   WORKDIR=/workspace
#   OUTPUT_NAME=issue236_artifact_smoke_YYYYmmdd_HHMMSS

CONTAINER="${CONTAINER:-pdfscore_pipeline_pytest_dev}"
WORKDIR="${WORKDIR:-/workspace}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
OUTPUT_NAME="${OUTPUT_NAME:-issue236_artifact_smoke_${TIMESTAMP}}"
HANDOFF_INPUT="${1:-${HANDOFF_REL:-}}"

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

REPORT_PATH="issue236_artifact_smoke_report_${TIMESTAMP}.md"
RUN_LOG="$(mktemp)"
DETAIL_LOG="$(mktemp)"
trap 'rm -f "$RUN_LOG" "$DETAIL_LOG"' EXIT

as_repo_relative_path() {
  local path="$1"
  case "$path" in
    "$REPO_ROOT"/*)
      printf '%s\n' "${path#"$REPO_ROOT"/}"
      ;;
    /*)
      printf 'ERROR: absolute handoff path is outside this repository: %s\n' "$path" >&2
      exit 2
      ;;
    *)
      printf '%s\n' "${path#./}"
      ;;
  esac
}

select_latest_handoff() {
  local -a candidates=()
  if [[ -d logs ]]; then
    mapfile -t candidates < <(
      find logs -path '*/review/manual_correction_input.json' -type f -printf '%T@\t%p\n' 2>/dev/null \
        | sort -n
    )
  fi

  if (( ${#candidates[@]} == 0 )); then
    mapfile -t candidates < <(
      find . \
        -path './.git' -prune -o \
        -path './.venv*' -prune -o \
        -path './__pycache__' -prune -o \
        -path '*/review/manual_correction_input.json' -type f -printf '%T@\t%p\n' 2>/dev/null \
        | sort -n
    )
  fi

  if (( ${#candidates[@]} == 0 )); then
    cat >&2 <<'EOF'
ERROR: no review/manual_correction_input.json was found.
Pass the handoff path explicitly:
  bash tools/issue236_artifact_smoke.sh logs/<run>/review/manual_correction_input.json
EOF
    exit 2
  fi

  local last_index=$(( ${#candidates[@]} - 1 ))
  local latest_line="${candidates[$last_index]}"
  local latest_path="${latest_line#*$'\t'}"
  printf '%s\n' "${latest_path#./}"
}

if [[ -n "$HANDOFF_INPUT" ]]; then
  HANDOFF_REL="$(as_repo_relative_path "$HANDOFF_INPUT")"
else
  HANDOFF_REL="$(select_latest_handoff)"
fi

if [[ ! -f "$HANDOFF_REL" ]]; then
  printf 'ERROR: handoff does not exist on host: %s\n' "$HANDOFF_REL" >&2
  exit 2
fi

echo "== start container =="
docker start "$CONTAINER" >/dev/null

echo "== run corrected final artifact smoke =="
echo "container: $CONTAINER"
echo "workdir:   $WORKDIR"
echo "handoff:   $HANDOFF_REL"
echo "output:    $OUTPUT_NAME"

set +e
docker exec \
  -w "$WORKDIR" \
  -e PYTHONPATH="$WORKDIR" \
  -e HANDOFF_REL="$HANDOFF_REL" \
  -e OUTPUT_NAME="$OUTPUT_NAME" \
  "$CONTAINER" \
  bash -lc '
set -euo pipefail

echo "== container environment =="
pwd
python3 --version
echo "PYTHONPATH=${PYTHONPATH:-}"
echo "git_head=$(git rev-parse HEAD 2>/dev/null || true)"
echo "git_branch=$(git branch --show-current 2>/dev/null || true)"

echo "== input handoff =="
test -f "$HANDOFF_REL"
ls -lh "$HANDOFF_REL"

echo "== apply_corrections --generate-final-pdf =="
python3 -m src.pipeline.review.apply_corrections \
  "$HANDOFF_REL" \
  --overwrite \
  --generate-final-pdf \
  --output-name "$OUTPUT_NAME"
' 2>&1 | tee "$RUN_LOG"
RUN_STATUS=${PIPESTATUS[0]}
set -e

FINAL_LINE="$(docker exec \
  -w "$WORKDIR" \
  -e OUTPUT_NAME="$OUTPUT_NAME" \
  "$CONTAINER" \
  bash -lc 'find . -path "*/final/${OUTPUT_NAME}_score_numbered.pdf" -type f -printf "%T@\t%p\t%s\n" 2>/dev/null | sort -n | tail -1' \
  || true)"

FINAL_REL=""
FINAL_SIZE=""
CORRECTED_RUN_DIR_REL=""
if [[ -n "$FINAL_LINE" ]]; then
  FINAL_REL="$(printf '%s' "$FINAL_LINE" | awk -F '\t' '{print $2}')"
  FINAL_SIZE="$(printf '%s' "$FINAL_LINE" | awk -F '\t' '{print $3}')"
  FINAL_REL="${FINAL_REL#./}"
  CORRECTED_RUN_DIR_REL="$(dirname "$(dirname "$FINAL_REL")")"
fi

DETAIL_STATUS=0
if [[ -n "$CORRECTED_RUN_DIR_REL" ]]; then
  set +e
  docker exec \
    -w "$WORKDIR" \
    -e PYTHONPATH="$WORKDIR" \
    -e CORRECTED_RUN_DIR_REL="$CORRECTED_RUN_DIR_REL" \
    "$CONTAINER" \
    bash -lc '
set -euo pipefail

echo "== corrected run dir =="
echo "$CORRECTED_RUN_DIR_REL"
test -d "$CORRECTED_RUN_DIR_REL"

echo "== final directory =="
find "$CORRECTED_RUN_DIR_REL/final" -maxdepth 1 -type f -printf "%f\t%s bytes\n" | sort

echo "== expected review summaries =="
ls -lh \
  "$CORRECTED_RUN_DIR_REL/review/correction_summary.json" \
  "$CORRECTED_RUN_DIR_REL/review/corrected_final_summary.json"

echo "== corrected_final_summary excerpt =="
python3 - <<PY
from pathlib import Path
import json

run = Path("$CORRECTED_RUN_DIR_REL")
summary_path = run / "review" / "corrected_final_summary.json"
summary = json.loads(summary_path.read_text(encoding="utf-8"))

final_pdf = summary.get("final_pdf")
output_name = summary.get("output_name")
warnings = summary.get("warnings")
pages = summary.get("pages", [])
row_label_counts = [len(page.get("row_labels", [])) for page in pages]

print("summary_path:", summary_path)
print("final_pdf:", final_pdf)
print("output_name:", output_name)
print("warnings:", warnings)
print("pages:", len(pages))
print("row_label_counts:", row_label_counts)
print("total_row_labels:", sum(row_label_counts))

for page in pages[:3]:
    print({
        "page_id": page.get("page_id"),
        "source_image": page.get("source_image"),
        "numbering_json": page.get("numbering_json"),
        "row_labels_count": len(page.get("row_labels", [])),
        "first_row_labels": page.get("row_labels", [])[:5],
    })
PY

echo "== pdf header check =="
python3 - <<PY
from pathlib import Path

run = Path("$CORRECTED_RUN_DIR_REL")
final_dir = run / "final"
pdfs = sorted(final_dir.glob("*_score_numbered.pdf"))
print("pdf_count:", len(pdfs))
for pdf in pdfs:
    data = pdf.read_bytes()[:5]
    print({"path": str(pdf), "size": pdf.stat().st_size, "header": data.decode("latin1")})
PY
' 2>&1 | tee "$DETAIL_LOG"
  DETAIL_STATUS=${PIPESTATUS[0]}
  set -e
else
  DETAIL_STATUS=1
  echo "ERROR: final PDF was not found for output name: $OUTPUT_NAME" | tee "$DETAIL_LOG"
fi

FINAL_FILE_COUNT="unknown"
if [[ -n "$CORRECTED_RUN_DIR_REL" ]]; then
  FINAL_FILE_COUNT="$(docker exec \
    -w "$WORKDIR" \
    -e CORRECTED_RUN_DIR_REL="$CORRECTED_RUN_DIR_REL" \
    "$CONTAINER" \
    bash -lc 'find "$CORRECTED_RUN_DIR_REL/final" -maxdepth 1 -type f | wc -l' \
    2>/dev/null | tr -d '[:space:]' || true)"
fi

OVERALL_STATUS="PASS"
if [[ "$RUN_STATUS" -ne 0 || "$DETAIL_STATUS" -ne 0 || -z "$FINAL_REL" ]]; then
  OVERALL_STATUS="FAIL"
elif [[ "$FINAL_FILE_COUNT" != "1" ]]; then
  OVERALL_STATUS="WARN_final_file_count_${FINAL_FILE_COUNT}"
fi

{
  echo "# Issue #236 corrected final artifact smoke report"
  echo
  echo "- status: $OVERALL_STATUS"
  echo "- timestamp: $TIMESTAMP"
  echo "- container: $CONTAINER"
  echo "- workdir: $WORKDIR"
  echo "- host_repo: $REPO_ROOT"
  echo "- host_branch: $(git branch --show-current)"
  echo "- host_head: $(git rev-parse HEAD)"
  echo "- handoff: $HANDOFF_REL"
  echo "- output_name: $OUTPUT_NAME"
  echo "- corrected_run_dir: ${CORRECTED_RUN_DIR_REL:-NOT_FOUND}"
  echo "- final_pdf: ${FINAL_REL:-NOT_FOUND}"
  echo "- final_pdf_size: ${FINAL_SIZE:-NOT_FOUND}"
  echo "- final_file_count: $FINAL_FILE_COUNT"
  echo "- apply_corrections_exit_status: $RUN_STATUS"
  echo "- detail_check_exit_status: $DETAIL_STATUS"
  echo
  echo "## apply_corrections output"
  echo
  echo '```text'
  cat "$RUN_LOG"
  echo '```'
  echo
  echo "## generated artifact checks"
  echo
  echo '```text'
  cat "$DETAIL_LOG"
  echo '```'
  echo
  echo "## manual visual check"
  echo
  echo "Open this PDF from the host workspace and record only OK/NG in the PR comment/body:"
  echo
  echo '```text'
  if [[ -n "$FINAL_REL" ]]; then
    echo "$REPO_ROOT/$FINAL_REL"
  else
    echo "NOT_FOUND"
  fi
  echo '```'
  echo
  echo "Required visual confirmation: PDF opens, row-start measure numbers are visible, and no review/debug overlays are mixed into final output."
} > "$REPORT_PATH"

echo
echo "== smoke report: $REPORT_PATH =="
cat "$REPORT_PATH"

if [[ "$OVERALL_STATUS" == FAIL* ]]; then
  exit 1
fi
