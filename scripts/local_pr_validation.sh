#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/local_pr_validation.sh [--pr NUMBER] [--base REF] [--with-gpu] [--with-full-eval] [--pull] [--post-comment]

Runs local PR validation and writes a reproducible summary.
The script also inspects changed paths and reports validation that may be required
by docs/dev/VALIDATION_POLICY.md.

Environment:
  FULL_EVAL_CMD       Default: make run-pipeline CONFIG=configs/evaluation2_e2e_verification_full.yaml LOG_FILE=/dev/stdout
  FULL_EVAL_TIMEOUT   Default: 8h
USAGE
}

pr_number=""
base_ref_override=""
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
    --base)
      base_ref_override="${2:?missing base ref}"
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

summary_file="${log_dir}/summary.md"
test_log="${log_dir}/test_fast.log"
gpu_log="${log_dir}/gpu_smoke_launcher.log"
full_eval_log="${log_dir}/full_eval_launcher.log"
changed_files_file="${log_dir}/changed_files.txt"
change_categories_file="${log_dir}/change_categories.txt"
required_validation_file="${log_dir}/required_validation.txt"
validation_warnings_file="${log_dir}/validation_warnings.txt"

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

add_unique_line() {
  local file="$1"
  local line="$2"
  grep -Fxq "$line" "$file" 2>/dev/null || echo "$line" >>"$file"
}

resolve_base_candidate() {
  local candidate="$1"
  [[ -z "$candidate" ]] && return 1

  if git rev-parse --verify "origin/${candidate}" >/dev/null 2>&1; then
    echo "origin/${candidate}"
  elif git rev-parse --verify "$candidate" >/dev/null 2>&1; then
    echo "$candidate"
  else
    return 1
  fi
}

determine_base_ref() {
  local pr_base=""

  if [[ -n "$base_ref_override" ]]; then
    if ! resolve_base_candidate "$base_ref_override"; then
      echo "Unable to resolve --base ref: ${base_ref_override}" >&2
      exit 2
    fi
    return
  fi

  if [[ -n "$pr_number" ]] && command -v gh >/dev/null 2>&1; then
    pr_base="$(gh pr view "$pr_number" --json baseRefName -q .baseRefName 2>/dev/null || true)"
    if [[ -n "$pr_base" ]]; then
      if ! resolve_base_candidate "$pr_base"; then
        echo "Unable to resolve PR base ref: ${pr_base}" >&2
        exit 2
      fi
      return
    fi
  fi

  if git rev-parse --verify origin/develop >/dev/null 2>&1; then
    echo "origin/develop"
  elif git rev-parse --verify develop >/dev/null 2>&1; then
    echo "develop"
  elif git rev-parse --verify origin/main >/dev/null 2>&1; then
    echo "origin/main"
  elif git rev-parse --verify main >/dev/null 2>&1; then
    echo "main"
  elif git rev-parse --verify HEAD~1 >/dev/null 2>&1; then
    echo "HEAD~1"
  else
    echo ""
  fi
}

collect_changed_files() {
  : >"$changed_files_file"

  if [[ -n "$base_ref" ]]; then
    git diff --name-only --diff-filter=d "$base_ref...HEAD" >>"$changed_files_file"
  fi

  git diff --name-only --diff-filter=d HEAD >>"$changed_files_file" || true
  git diff --name-only --diff-filter=d --cached >>"$changed_files_file" || true
  git ls-files --others --exclude-standard >>"$changed_files_file" || true
  sort -u "$changed_files_file" -o "$changed_files_file"
}

classify_changes() {
  : >"$change_categories_file"
  : >"$required_validation_file"
  : >"$validation_warnings_file"

  if [[ ! -s "$changed_files_file" ]]; then
    add_unique_line "$change_categories_file" "no changed files detected"
    add_unique_line "$required_validation_file" "manual inspection"
    return
  fi

  while IFS= read -r path; do
    [[ -z "$path" ]] && continue

    case "$path" in
      *.md|docs/*)
        add_unique_line "$change_categories_file" "docs"
        add_unique_line "$required_validation_file" "git diff --check and local doc review"
        ;;
    esac

    case "$path" in
      Makefile|scripts/*.sh)
        add_unique_line "$change_categories_file" "shell-or-makefile"
        add_unique_line "$required_validation_file" "bash -n for touched scripts, make help, relevant help/dry-run"
        ;;
    esac

    case "$path" in
      Makefile)
        add_unique_line "$change_categories_file" "keyword-sensitive"
        add_unique_line "$required_validation_file" "explain Makefile-sensitive changes and run or explicitly skip stronger validation"
        ;;
    esac

    case "$path" in
      *.py|tests/*.py|tools/*.py|tools/**/*.py)
        add_unique_line "$change_categories_file" "python"
        add_unique_line "$required_validation_file" "targeted pytest or import/compile check plus make test-fast when applicable"
        ;;
    esac

    case "$path" in
      src/pipeline/*|src/pipeline/**/*|tools/issue120/*|tools/issue120/**/*)
        add_unique_line "$change_categories_file" "pipeline-sensitive"
        add_unique_line "$required_validation_file" "make test-fast plus verify-pipeline-smoke or verify-gpu-smoke"
        ;;
    esac

    case "$path" in
      configs/*|configs/**/*|experiments/*|experiments/**/*)
        add_unique_line "$change_categories_file" "evaluation-sensitive"
        add_unique_line "$required_validation_file" "evaluation-sensitive review plus full evaluation or explicit human skip/defer decision"
        ;;
    esac

    case "$path" in
      Dockerfile|requirements.txt|pyproject.toml|uv.lock)
        add_unique_line "$change_categories_file" "environment-sensitive"
        add_unique_line "$required_validation_file" "environment/build validation plus GPU smoke when runtime stack is affected"
        ;;
    esac
  done <"$changed_files_file"

  if [[ -n "$base_ref" ]] && git diff --unified=0 "$base_ref" 2>/dev/null | grep -Eiq 'threshold|seed|dataset|metric|evaluation|baseline|canonical|filter|detector|orchestrator|route'; then
    add_unique_line "$change_categories_file" "keyword-sensitive"
    add_unique_line "$required_validation_file" "explain sensitive diff terms and run or explicitly skip stronger validation"
  fi

  if grep -Eq 'pipeline-sensitive|evaluation-sensitive|environment-sensitive|keyword-sensitive' "$change_categories_file"; then
    if [[ "$with_gpu" -ne 1 ]]; then
      add_unique_line "$validation_warnings_file" "GPU or pipeline-sensitive changes detected, but --with-gpu was not set."
    fi
  fi

  if grep -Eq 'evaluation-sensitive|keyword-sensitive' "$change_categories_file"; then
    if [[ "$with_full_eval" -ne 1 ]]; then
      add_unique_line "$validation_warnings_file" "Evaluation-sensitive changes detected, but --with-full-eval was not set. Record human skip/defer decision if this is intentional."
    fi
  fi
}

render_summary() {
  cat >"$summary_file" <<EOF_SUMMARY
## Local PR validation

- Branch: \`${branch}\`
- Commit: \`${commit}\`
- Test fast: ${test_status}
- GPU smoke: ${gpu_status}
- Full evaluation: ${full_eval_status}
- GitHub post: ${post_status}
- Log path: \`${log_dir}\`
- Overall exit code: ${overall_status}
- Diff base: \`${base_ref:-none}\`

### Detected change categories

$(sed 's/^/- /' "$change_categories_file")

### Required or recommended validation

$(sed 's/^/- /' "$required_validation_file")

### Validation warnings

$(if [[ -s "$validation_warnings_file" ]]; then sed 's/^/- WARNING: /' "$validation_warnings_file"; else echo "- None"; fi)

### Changed files

$(if [[ -s "$changed_files_file" ]]; then sed 's/^/- /' "$changed_files_file"; else echo "- No changed files detected"; fi)

### Commands

- \`make test-fast\`
$(if [[ "$with_gpu" -eq 1 ]]; then echo "- \`scripts/gpu_smoke.sh\`"; else echo "- GPU smoke not requested"; fi)
$(if [[ "$with_full_eval" -eq 1 ]]; then echo "- \`scripts/gpu_smoke.sh --timeout \"${FULL_EVAL_TIMEOUT:-8h}\" --command \"${FULL_EVAL_CMD:-make run-pipeline CONFIG=configs/evaluation2_e2e_verification_full.yaml LOG_FILE=/dev/stdout}\"\`"; else echo "- Full evaluation not requested"; fi)

### Notes

$(if [[ "$with_full_eval" -eq 1 ]]; then echo "- Full evaluation was explicitly requested for this run."; else echo "- Full evaluation was not run by this script. It remains governed by docs/dev/VALIDATION_POLICY.md."; fi)
- If GitHub posting is requested, this script uses \`gh pr comment --body-file\`.
EOF_SUMMARY
}

if [[ "$pull_first" -eq 1 ]]; then
  run_and_capture "git_pull_ff_only" "${log_dir}/git_pull.log" git pull --ff-only || overall_status=$?
fi

branch="$(git branch --show-current 2>/dev/null || echo unknown)"
commit="$(git rev-parse HEAD 2>/dev/null || echo unknown)"
base_ref="$(determine_base_ref)"

collect_changed_files
classify_changes

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
  full_eval_cmd="${FULL_EVAL_CMD:-make run-pipeline CONFIG=configs/evaluation2_e2e_verification_full.yaml LOG_FILE=/dev/stdout}"
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

render_summary

if [[ "$post_comment" -eq 1 ]]; then
  if [[ -z "$pr_number" ]]; then
    post_status="skipped: --pr was not provided"
    render_summary
  elif ! command -v gh >/dev/null 2>&1; then
    post_status="skipped: gh not found"
    render_summary
  elif ! gh auth status >/dev/null 2>&1; then
    post_status="skipped: gh is not authenticated or cannot reach GitHub"
    render_summary
  else
    post_status="posted"
    render_summary
    if ! gh pr comment "$pr_number" --body-file "$summary_file"; then
      post_status="failed"
      overall_status=1
      render_summary
    fi
  fi
fi

cat "$summary_file"
exit "$overall_status"
