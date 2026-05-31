#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/local_pr_validation.sh [--pr NUMBER] [--with-gpu] [--with-full-eval] [--pull] [--post-comment]

Runs lightweight local PR validation and writes a reproducible summary.
GPU smoke is opt-in because it depends on local WSL/GPU/Docker availability.

Environment:
  FULL_EVAL_CMD       Default: make run-pipeline CONFIG=configs/evaluation2_e2e_verification_full.yaml
  FULL_EVAL_TIMEOUT   Default: 8h
USAGE
}

pr_number=""
with_gpu=0
pull_first=0
post_comment=0
with_full_eval=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --pr)
      pr_number="${2:?missing PR number}"
      shift 2
      ;;
    --with-gpu)
      with_gpu=1
      shift
      ;;
    --with-full-eval)
      with_full_eval=1
      shift
      ;;
    --pull)
      pull_first=1
      shift
      ;;
    --post-comment)
      post_comment=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
log_dir="logs/system/local_pr_validation_${timestamp}"
mkdir -p "$log_dir"

branch="$(git branch --show-current 2>/dev/null || echo unknown)"
commit="$(git rev-parse HEAD 2>/dev/null || echo unknown)"
summary_file="${log_dir}/summary.md"
test_log="${log_dir}/test_fast.log"
gpu_log="${log_dir}/gpu_smoke_launcher.log"
full_eval_log="${log_dir}/full_eval_launcher.log"

overall_status=0
test_status="not-run"
gpu_status="not-run"
full_eval_status="not-run"
post_status="not-requested"

run_and_capture() {
  local label="$1"
  local outfile="$2"
  shift 2

  echo "Running ${label}: $*" | tee -a "$outfile"
  set +e
  "$@" >>"$outfile" 2>&1
  local status=$?
  set -e
  echo "${label}_exit_code=${status}" | tee -a "$outfile"
  return "$status"
}

{
  echo "timestamp_utc=${timestamp}"
  echo "branch=${branch}"
  echo "commit=${commit}"
  echo "pwd=$(pwd)"
  echo "python_version=$({ python3 --version || python --version; } 2>&1 | head -n 1)"
  echo
  echo "git_status:"
  git status --short || true
} >"${log_dir}/metadata.txt"

if [[ "$pull_first" -eq 1 ]]; then
  run_and_capture "git_pull_ff_only" "${log_dir}/git_pull.log" git pull --ff-only || overall_status=$?
fi

if run_and_capture "make_test_fast" "$test_log" make test-fast; then
  test_status="passed"
else
  test_status="failed"
  overall_status=1
fi

if [[ "$with_gpu" -eq 1 ]]; then
  if run_and_capture "gpu_smoke" "$gpu_log" scripts/gpu_smoke.sh; then
    gpu_status="passed"
  else
    gpu_status="failed"
    overall_status=1
  fi
else
  gpu_status="skipped: --with-gpu was not set"
fi

if [[ "$with_full_eval" -eq 1 ]]; then
  full_eval_cmd="${FULL_EVAL_CMD:-make run-pipeline CONFIG=configs/evaluation2_e2e_verification_full.yaml}"
  full_eval_timeout="${FULL_EVAL_TIMEOUT:-8h}"
  if run_and_capture "full_eval" "$full_eval_log" scripts/gpu_smoke.sh --timeout "$full_eval_timeout" --command "$full_eval_cmd"; then
    full_eval_status="passed"
  else
    full_eval_status="failed"
    overall_status=1
  fi
else
  full_eval_status="skipped: --with-full-eval was not set"
fi

cat >"$summary_file" <<EOF_SUMMARY
## Local PR validation

- Branch: \`${branch}\`
- Commit: \`${commit}\`
- Test fast: ${test_status}
- GPU smoke: ${gpu_status}
- Full evaluation: ${full_eval_status}
- Log path: \`${log_dir}\`
- Overall exit code: ${overall_status}

### Commands

- \`make test-fast\`
$(if [[ "$with_gpu" -eq 1 ]]; then echo "- \`scripts/gpu_smoke.sh\`"; else echo "- GPU smoke not requested"; fi)
$(if [[ "$with_full_eval" -eq 1 ]]; then echo "- \`scripts/gpu_smoke.sh --timeout \"${FULL_EVAL_TIMEOUT:-8h}\" --command \"${FULL_EVAL_CMD:-make run-pipeline CONFIG=configs/evaluation2_e2e_verification_full.yaml}\"\`"; else echo "- Full evaluation not requested"; fi)

### Notes

$(if [[ "$with_full_eval" -eq 1 ]]; then echo "- Full evaluation was explicitly requested for this run."; else echo "- Full evaluation was not run by this script. It remains opt-in."; fi)
- If GitHub posting is requested, this script uses \`gh pr comment --body-file\`.
EOF_SUMMARY

if [[ "$post_comment" -eq 1 ]]; then
  if [[ -z "$pr_number" ]]; then
    post_status="skipped: --pr was not provided"
  elif ! command -v gh >/dev/null 2>&1; then
    post_status="skipped: gh not found"
  elif ! gh auth status >/dev/null 2>&1; then
    post_status="skipped: gh is not authenticated or cannot reach GitHub"
  else
    if gh pr comment "$pr_number" --body-file "$summary_file"; then
      post_status="posted"
    else
      post_status="failed"
      overall_status=1
    fi
  fi
fi

{
  echo
  echo "- GitHub post: ${post_status}"
} >>"$summary_file"

cat "$summary_file"
exit "$overall_status"
