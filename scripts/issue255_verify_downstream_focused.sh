#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE="${PDFSCORE_PIPELINE_IMAGE:-pdfscore_pipeline_gpu}"
BRANCH="fix/issue255-production-detector-restoration"
RUN_TAG="${1:-issue255_downstream_focused_scores_$(date -u +%Y%m%dT%H%M%SZ)}"
RUN_ROOT="logs/verification/downstream_full68/${RUN_TAG}"
REPORT="${RUN_ROOT}/downstream_full68_verification_report.json"
LOG="logs/verification/${RUN_TAG}.log"
STATUS="logs/verification/issue255_downstream_focused_run_status.json"
DIAGNOSTIC="logs/verification/issue255_downstream_path_diagnostic.json"

cd "$ROOT"
mkdir -p logs/verification
rm -f "$STATUS" "$LOG"

write_status() {
  local exit_code="$1"
  local stage="$2"
  python3 - "$STATUS" "$exit_code" "$stage" "$RUN_TAG" "$REPORT" "$LOG" "$DIAGNOSTIC" <<'PY'
import json
import sys
from pathlib import Path

status_path = Path(sys.argv[1])
exit_code = int(sys.argv[2])
stage = sys.argv[3]
run_tag = sys.argv[4]
report_path = Path(sys.argv[5])
log_path = Path(sys.argv[6])
diagnostic_path = Path(sys.argv[7])

payload = {
    "schema_version": "verification.issue255_downstream_focused_run_status.v1",
    "run_tag": run_tag,
    "stage": stage,
    "exit_code": exit_code,
    "passed": exit_code == 0,
    "report_path": str(report_path),
    "report_exists": report_path.is_file(),
    "log_path": str(log_path),
    "diagnostic_path": str(diagnostic_path),
}

if diagnostic_path.is_file():
    try:
        diagnostic = json.loads(diagnostic_path.read_text(encoding="utf-8"))
        payload["diagnostic_passed"] = diagnostic.get("passed")
        payload["git"] = diagnostic.get("git")
    except Exception as exc:
        payload["diagnostic_read_error"] = repr(exc)

if report_path.is_file():
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
        payload["report_status"] = report.get("status")
        payload["score_count"] = report.get("score_count")
        payload["page_count"] = report.get("page_count")
        payload["focused_contract_met"] = report.get("focused_contract_met")
        mismatches = report.get("focused_contract_mismatches") or {}
        payload["focused_mismatch_pages"] = sorted(mismatches)
        payload["physical_measure_count"] = report.get("physical_measure_count")
        payload["mmr_override_count"] = report.get("mmr_override_count")
    except Exception as exc:
        payload["report_read_error"] = repr(exc)

if log_path.is_file():
    lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    payload["log_tail"] = lines[-60:]

status_path.write_text(
    json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
    encoding="utf-8",
)
PY
}

# Host-side repository checks.
git fetch origin >/dev/null 2>&1 || {
  printf '%s\n' 'git fetch origin failed' >"$LOG"
  write_status 2 "preflight_git_fetch"
  printf '%s\n' "$STATUS"
  exit 2
}

LOCAL_SHA="$(git rev-parse HEAD)"
REMOTE_SHA="$(git rev-parse "origin/${BRANCH}")"
CURRENT_BRANCH="$(git branch --show-current)"

if [[ "$CURRENT_BRANCH" != "$BRANCH" ]]; then
  printf 'Wrong branch: %s\n' "$CURRENT_BRANCH" >"$LOG"
  write_status 2 "preflight_branch"
  printf '%s\n' "$STATUS"
  exit 2
fi
if [[ "$LOCAL_SHA" != "$REMOTE_SHA" ]]; then
  printf 'Local SHA: %s\nRemote SHA: %s\n' "$LOCAL_SHA" "$REMOTE_SHA" >"$LOG"
  write_status 2 "preflight_commit"
  printf '%s\n' "$STATUS"
  exit 2
fi
if [[ -n "$(git status --porcelain)" ]]; then
  git status --short >"$LOG"
  write_status 2 "preflight_dirty_tree"
  printf '%s\n' "$STATUS"
  exit 2
fi

# Cheap path-resolution diagnostic before the expensive replay.
if ! bash scripts/issue255_diagnose_downstream_paths.sh >/dev/null 2>"$LOG"; then
  write_status 2 "path_diagnostic_execution"
  printf '%s\n' "$STATUS"
  exit 2
fi

if ! python3 - "$DIAGNOSTIC" <<'PY' >/dev/null 2>>"$LOG"
import json
import sys
from pathlib import Path
p = Path(sys.argv[1])
r = json.loads(p.read_text(encoding="utf-8"))
raise SystemExit(0 if r.get("passed") is True else 1)
PY
then
  write_status 2 "path_diagnostic_contract"
  printf '%s\n' "$STATUS"
  exit 2
fi

# A timestamped default RUN_TAG avoids collisions with partially created prior runs.
if [[ -e "$RUN_ROOT" ]]; then
  printf 'Run root already exists: %s\n' "$RUN_ROOT" >"$LOG"
  write_status 2 "run_root_exists"
  printf '%s\n' "$STATUS"
  exit 2
fi

set +e
docker run --rm \
  --gpus all \
  -v "$ROOT:/workspace" \
  -w /workspace \
  -e PYTHONPATH=/workspace \
  "$IMAGE" \
  /opt/venv_pipeline/bin/python \
  tools/verification/verify_downstream_full68.py \
  --run-tag "$RUN_TAG" \
  --score Shostakovich-Sym5-Va \
  --score Va_Prokofiev_Symphony1 \
  >"$LOG" 2>&1
RC=$?
set -e

if [[ "$RC" -ne 0 ]]; then
  write_status "$RC" "downstream_replay"
  printf '%s\n' "$STATUS"
  exit "$RC"
fi

if [[ ! -f "$REPORT" ]]; then
  printf '\nExpected report was not created: %s\n' "$REPORT" >>"$LOG"
  write_status 3 "report_missing"
  printf '%s\n' "$STATUS"
  exit 3
fi

write_status 0 "completed"
printf '%s\n' "$STATUS"
