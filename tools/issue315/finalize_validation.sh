#!/usr/bin/env bash
set -uo pipefail

REPO="M763468/PDFScoreBar"
BRANCH="task/issue315-production-model-artifacts"
MANIFEST="models/barline_cnn/manifest.json"
EXPECTED_SHA="f41a9b578396493a83e39ed284b1781f65d6adec8f624e6b7234e917c919c5cd"
EXPECTED_SIZE="16339553"
DEFAULT_CONTAINER="pdfscore_pipeline_pytest_dev"
FALLBACK_CONTAINER="pdfscore_pipeline_pytest_issue315"

ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || {
  echo "ERROR: run this script from inside the PDFScoreBar repository" >&2
  exit 2
}
cd "$ROOT"

TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="logs/issue315/final_validation_${TIMESTAMP}"
STATUS_TSV="${OUT}/status.tsv"
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
  local log="${OUT}/${name}.log"
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
  local head develop_head remote_head
  head="$(git rev-parse HEAD 2>/dev/null || true)"
  develop_head="$(git rev-parse origin/develop 2>/dev/null || true)"
  remote_head="$(git rev-parse "origin/${BRANCH}" 2>/dev/null || true)"
  HEAD_SHA="$head" DEVELOP_SHA="$develop_head" REMOTE_SHA="$remote_head" \
  OUT_DIR="$OUT" STATUS_FILE="$STATUS_TSV" OVERALL_RC="$OVERALL" \
  REPO_NAME="$REPO" BRANCH_NAME="$BRANCH" CONTAINER_NAME="$CONTAINER" \
  python3 - <<'PY'
import json
import os
from pathlib import Path

status = {}
status_file = Path(os.environ["STATUS_FILE"])
if status_file.exists():
    for line in status_file.read_text(encoding="utf-8").splitlines():
        parts = line.split("\t", 2)
        if len(parts) == 3:
            name, result, detail = parts
            status[name] = {"result": result, "detail": detail}

payload = {
    "schema_version": "pdfscorebar.issue315.final_validation.v1",
    "repository": os.environ["REPO_NAME"],
    "branch": os.environ["BRANCH_NAME"],
    "head": os.environ["HEAD_SHA"],
    "remote_head": os.environ["REMOTE_SHA"],
    "develop_head_observed": os.environ["DEVELOP_SHA"],
    "pytest_container": os.environ["CONTAINER_NAME"],
    "overall": "PASS" if os.environ["OVERALL_RC"] == "0" else "FAIL",
    "steps": status,
}
out = Path(os.environ["OUT_DIR"]) / "final_validation_result.json"
out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
print(out)
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
  *) fail_preflight "origin is not M763468/PDFScoreBar: $REMOTE_URL" ;;
esac
CURRENT_BRANCH="$(git branch --show-current)"
[[ "$CURRENT_BRANCH" == "$BRANCH" ]] || fail_preflight "expected branch $BRANCH, got $CURRENT_BRANCH"
[[ -z "$(git status --porcelain)" ]] || fail_preflight "worktree is not clean; refusing to pull or format"

run_step "git_fetch" git fetch origin develop "$BRANCH"
if ! grep -q $'^git_fetch\tPASS\t' "$STATUS_TSV"; then
  write_result
  exit 1
fi

LOCAL_HEAD="$(git rev-parse HEAD)"
REMOTE_HEAD="$(git rev-parse "origin/${BRANCH}")"
if [[ "$LOCAL_HEAD" != "$REMOTE_HEAD" ]]; then
  run_step "git_pull_ff_only" git pull --ff-only origin "$BRANCH"
fi
[[ "$(git rev-parse HEAD)" == "$(git rev-parse "origin/${BRANCH}")" ]] || \
  fail_preflight "local branch does not match origin after ff-only pull"

run_step "diff_check" git diff --check "origin/develop...HEAD"
run_step "test_fast" env PYTEST_ADDOPTS="-p no:cacheprovider" make test-fast

# Use the repository-documented persistent pytest-capable pipeline container when it is
# mounted to this worktree. If that standard container belongs to another worktree, create
# a separate Issue #315 container rather than modifying/removing the existing one.
setup_log="${OUT}/pytest_container_setup.log"
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
    [[ "$(readlink -f "$mount_src")" == "$(readlink -f "$ROOT")" ]] || {
      echo "container $CONTAINER is mounted to a different worktree: $mount_src" >&2
      false
    }
    running="$(docker inspect -f '{{.State.Running}}' "$CONTAINER")"
    if [[ "$running" != "true" ]]; then
      docker start "$CONTAINER"
    fi
  else
    docker run -dit --gpus all --name "$CONTAINER" \
      -v "$ROOT:/workspace" -w /workspace -e PYTHONPATH=/workspace \
      pdfscore_pipeline_gpu bash
  fi
  if ! docker exec -w /workspace "$CONTAINER" /opt/venv_pipeline/bin/python -c 'import pytest' >/dev/null 2>&1; then
    docker exec -w /workspace "$CONTAINER" \
      /opt/venv_pipeline/bin/python -m pip install pytest
  fi
} >"$setup_log" 2>&1; then
  record "pytest_container_setup" "PASS" "$setup_log"
else
  record "pytest_container_setup" "FAIL" "$setup_log"
  OVERALL=1
fi

if grep -q $'^pytest_container_setup\tPASS\t' "$STATUS_TSV"; then
  run_step "focused_pytest" docker exec -w /workspace -e PYTHONPATH=/workspace "$CONTAINER" \
    /opt/venv_pipeline/bin/python -m pytest -p no:cacheprovider \
    tests/test_model_artifacts.py \
    tests/test_issue315_production_model_artifact_contract.py \
    tests/test_issue255_production_detector_restoration.py \
    tests/test_issue296_verified_cnn_contract.py
fi

# Materialize from an actually empty, run-specific cache using the committed manifest.
MODEL_CACHE="${OUT}/model_cache"
run_step "materialize_committed_manifest" python3 -m src.common.model_artifacts materialize \
  "$MANIFEST" --cache-root "$MODEL_CACHE"

ARTIFACT="${MODEL_CACHE}/barline_cnn/issue296-d27-v1/cnn_classifier_epoch_9.pth"
if [[ -f "$ARTIFACT" ]]; then
  actual_sha="$(sha256sum "$ARTIFACT" | awk '{print $1}')"
  actual_size="$(stat -c %s "$ARTIFACT")"
  if [[ "$actual_sha" == "$EXPECTED_SHA" && "$actual_size" == "$EXPECTED_SIZE" ]]; then
    record "materialized_identity" "PASS" "sha256=$actual_sha size=$actual_size"
  else
    record "materialized_identity" "FAIL" "sha256=$actual_sha size=$actual_size"
    OVERALL=1
  fi
else
  record "materialized_identity" "FAIL" "artifact missing: $ARTIFACT"
  OVERALL=1
fi

# Load the freshly materialized bytes through the committed production YAML and verified
# Stage-E artifact resolver. This exercises the real torch checkpoint/architecture guard.
if grep -q $'^pytest_container_setup\tPASS\t' "$STATUS_TSV" && [[ -f "$ARTIFACT" ]]; then
  container_cache="/workspace/${MODEL_CACHE}"
  run_step "verified_stage_e_config_load" docker exec -w /workspace \
    -e PYTHONPATH=/workspace -e PDFSCOREBAR_MODEL_CACHE="$container_cache" "$CONTAINER" \
    /opt/venv_pipeline/bin/python -c \
    'import yaml; from pathlib import Path; from src.pipeline.detection.restored_orchestrator import _resolve_verified_cnn_artifact; cfg=yaml.safe_load(Path("configs/dense_full_pipeline.yaml").read_text(encoding="utf-8"))["detection"]; p=_resolve_verified_cnn_artifact(cfg["cnn_model_manifest"], cnn_threshold=float(cfg["cnn_threshold"])); print(p)'
fi

# Required repository style commands. The branch should already be formatter-clean, so
# make format must be a no-op; any unexpected edit is reported as a failure.
run_step "make_format" make format
run_step "post_format_clean" git diff --exit-code
run_step "make_lint" make lint
run_step "final_worktree_clean" bash -c 'test -z "$(git status --porcelain)"'

write_result
RESULT="${OUT}/final_validation_result.json"
echo
echo "Result: $RESULT"
cat "$RESULT"
exit "$OVERALL"
