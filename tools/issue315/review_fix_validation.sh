#!/usr/bin/env bash
set -uo pipefail

REPO="M763468/PDFScoreBar"
BRANCH="task/issue315-production-model-artifacts"
DEFAULT_CONTAINER="pdfscore_pipeline_pytest_dev"
FALLBACK_CONTAINER="pdfscore_pipeline_pytest_issue315"

ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || {
  echo "ERROR: run inside the PDFScoreBar repository" >&2
  exit 2
}
cd "$ROOT"

TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="logs/issue315/review_fix_validation_${TIMESTAMP}"
STATUS_TSV="$OUT/status.tsv"
mkdir -p "$OUT"
: > "$STATUS_TSV"
OVERALL=0
CONTAINER=""

record() {
  printf '%s\t%s\t%s\n' "$1" "$2" "$3" >> "$STATUS_TSV"
}

run_step() {
  local name="$1"
  shift
  local log="$OUT/${name}.log"
  printf '\n== %s ==\n' "$name"
  if "$@" >"$log" 2>&1; then
    echo "PASS ($log)"
    record "$name" "PASS" "$log"
  else
    local rc=$?
    echo "FAIL rc=$rc ($log)"
    record "$name" "FAIL" "$log"
    OVERALL=1
  fi
}

write_result() {
  HEAD_SHA="$(git rev-parse HEAD 2>/dev/null || true)" \
  REMOTE_SHA="$(git rev-parse "origin/$BRANCH" 2>/dev/null || true)" \
  DEVELOP_SHA="$(git rev-parse origin/develop 2>/dev/null || true)" \
  STATUS_FILE="$STATUS_TSV" OUT_DIR="$OUT" OVERALL_RC="$OVERALL" \
  REPO_NAME="$REPO" BRANCH_NAME="$BRANCH" CONTAINER_NAME="$CONTAINER" \
  python3 - <<'PY'
import json
import os
from pathlib import Path

steps = {}
for line in Path(os.environ["STATUS_FILE"]).read_text(encoding="utf-8").splitlines():
    name, result, detail = line.split("\t", 2)
    steps[name] = {"result": result, "detail": detail}

payload = {
    "schema_version": "pdfscorebar.issue315.review_fix_validation.v1",
    "repository": os.environ["REPO_NAME"],
    "branch": os.environ["BRANCH_NAME"],
    "head": os.environ["HEAD_SHA"],
    "remote_head": os.environ["REMOTE_SHA"],
    "develop_head_observed": os.environ["DEVELOP_SHA"],
    "pytest_container": os.environ["CONTAINER_NAME"],
    "overall": "PASS" if os.environ["OVERALL_RC"] == "0" else "FAIL",
    "steps": steps,
}
path = Path(os.environ["OUT_DIR"]) / "review_fix_validation_result.json"
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
print(path)
PY
}

fail_preflight() {
  echo "ERROR: $1" >&2
  record "preflight" "FAIL" "$1"
  OVERALL=1
  write_result
  exit 1
}

REMOTE_URL="$(git remote get-url origin 2>/dev/null || true)"
case "$REMOTE_URL" in
  *github.com/M763468/PDFScoreBar*|*github.com:M763468/PDFScoreBar*) ;;
  *) fail_preflight "origin is not $REPO: $REMOTE_URL" ;;
esac
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail_preflight "wrong branch"
[[ -z "$(git status --porcelain)" ]] || fail_preflight "worktree is not clean"

run_step "git_fetch" git fetch origin develop "$BRANCH"
[[ "$(git rev-parse HEAD)" == "$(git rev-parse "origin/$BRANCH")" ]] || \
  fail_preflight "local HEAD does not match origin/$BRANCH; pull first"

run_step "diff_check" git diff --check "origin/develop...HEAD"
run_step "test_fast" env PYTEST_ADDOPTS="-p no:cacheprovider" make test-fast

setup_log="$OUT/pytest_container_setup.log"
if {
  candidate="$DEFAULT_CONTAINER"
  if docker inspect "$candidate" >/dev/null 2>&1; then
    mount_src="$(docker inspect -f '{{range .Mounts}}{{if eq .Destination "/workspace"}}{{.Source}}{{end}}{{end}}' "$candidate")"
    if [[ "$(readlink -f "$mount_src")" != "$(readlink -f "$ROOT")" ]]; then
      candidate="$FALLBACK_CONTAINER"
    fi
  fi
  CONTAINER="$candidate"

  if docker inspect "$CONTAINER" >/dev/null 2>&1; then
    mount_src="$(docker inspect -f '{{range .Mounts}}{{if eq .Destination "/workspace"}}{{.Source}}{{end}}{{end}}' "$CONTAINER")"
    [[ "$(readlink -f "$mount_src")" == "$(readlink -f "$ROOT")" ]] || false
    [[ "$(docker inspect -f '{{.State.Running}}' "$CONTAINER")" == "true" ]] || docker start "$CONTAINER"
  else
    docker run -dit --gpus all --name "$CONTAINER" \
      -v "$ROOT:/workspace" -w /workspace -e PYTHONPATH=/workspace \
      pdfscore_pipeline_gpu bash
  fi
  docker exec -w /workspace "$CONTAINER" /opt/venv_pipeline/bin/python -c 'import pytest'
} >"$setup_log" 2>&1; then
  record "pytest_container_setup" "PASS" "$setup_log"
else
  record "pytest_container_setup" "FAIL" "$setup_log"
  OVERALL=1
fi

if grep -q $'^pytest_container_setup\tPASS\t' "$STATUS_TSV"; then
  run_step "focused_pytest" docker exec -w /workspace -e PYTHONPATH=/workspace "$CONTAINER" \
    /opt/venv_pipeline/bin/python -m pytest -p no:cacheprovider \
    tests/test_issue315_production_model_artifact_contract.py \
    tests/test_model_artifacts.py \
    tests/test_issue255_production_detector_restoration.py \
    tests/test_issue296_verified_cnn_contract.py
fi

run_step "make_lint" make lint
run_step "final_worktree_clean" bash -c 'test -z "$(git status --porcelain)"'

write_result
RESULT="$OUT/review_fix_validation_result.json"
echo
echo "Result: $RESULT"
cat "$RESULT"
exit "$OVERALL"
