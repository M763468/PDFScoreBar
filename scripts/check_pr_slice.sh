#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: bash scripts/check_pr_slice.sh [PROFILE] [--fix] [--lint-only] [--pytest-only] [--list-profiles]

Runs the local validation set for a focused PR slice.

Default PROFILE:
  issue236-apply-corrections

Options:
  --fix           Run make format before validation. This may modify files.
  --lint-only     Run only make lint. Useful for lightweight CI or format checks.
  --pytest-only   Run only the focused pytest set from the selected profile.
  --python PATH   Python executable for pytest. Defaults to $PYTHON or python3.
  --list-profiles List available profile names and exit.
  -h, --help      Show this help.

Profiles are plain text files under scripts/pr_validation_profiles/.
Each non-empty, non-comment line is passed to pytest as one argument.
USAGE
}

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${script_dir}/.." && pwd)"
profile_dir="${script_dir}/pr_validation_profiles"

profile="${PR_SLICE:-issue236-apply-corrections}"
python_bin="${PYTHON:-python3}"
run_fix=0
lint_only=0
pytest_only=0
list_profiles=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --fix|--format)
      run_fix=1
      shift
      ;;
    --lint-only)
      lint_only=1
      shift
      ;;
    --pytest-only)
      pytest_only=1
      shift
      ;;
    --python)
      if [[ $# -lt 2 ]]; then
        echo "Error: --python requires an argument." >&2
        exit 2
      fi
      python_bin="$2"
      shift 2
      ;;
    --list-profiles)
      list_profiles=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    --*)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
    *)
      profile="$1"
      shift
      ;;
  esac
done

if [[ "$list_profiles" -eq 1 ]]; then
  if [[ ! -d "$profile_dir" ]]; then
    echo "No profile directory found: ${profile_dir}" >&2
    exit 1
  fi
  find "$profile_dir" -maxdepth 1 -type f -name '*.txt' \
    | sed -e 's|.*/||' -e 's/\.txt$//' \
    | sort
  exit 0
fi

if [[ "$lint_only" -eq 1 && "$pytest_only" -eq 1 ]]; then
  echo "--lint-only and --pytest-only cannot be combined." >&2
  exit 2
fi

profile_file="${profile_dir}/${profile}.txt"
if [[ ! -f "$profile_file" ]]; then
  echo "Unknown PR slice profile: ${profile}" >&2
  echo "Expected profile file: ${profile_file}" >&2
  echo "Available profiles:" >&2
  if [[ -d "$profile_dir" ]]; then
    find "$profile_dir" -maxdepth 1 -type f -name '*.txt' \
      | sed -e 's|.*/|  |' -e 's/\.txt$//' \
      | sort >&2
  else
    echo "  <none>" >&2
  fi
  exit 2
fi

trim() {
  local value="$1"
  value="${value#"${value%%[![:space:]]*}"}"
  value="${value%"${value##*[![:space:]]}"}"
  printf '%s' "$value"
}

tests=()
while IFS= read -r raw_line || [[ -n "$raw_line" ]]; do
  line="${raw_line%%#*}"
  line="$(trim "$line")"
  [[ -z "$line" ]] && continue
  tests+=("$line")
done <"$profile_file"

if [[ "$lint_only" -ne 1 && "${#tests[@]}" -eq 0 ]]; then
  echo "Profile contains no pytest entries: ${profile_file}" >&2
  exit 2
fi

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
log_dir="${LOG_DIR:-artifacts/pr_slice_validation/${profile}_${timestamp}}"
summary_file="${log_dir}/summary.md"
mkdir -p "$log_dir"

cd "$repo_root"

overall_status=0
format_status="skipped"
lint_status="skipped"
pytest_status="skipped"

run_and_log() {
  local label="$1"
  local outfile="$2"
  shift 2

  echo "==> ${label}: $*"
  set +e
  "$@" 2>&1 | tee "$outfile"
  local status=${PIPESTATUS[0]}
  set -e
  echo "${label}_exit_code=${status}" | tee -a "$outfile"
  return "$status"
}

if [[ "$run_fix" -eq 1 ]]; then
  if run_and_log "make_format" "${log_dir}/format.log" make format; then
    format_status="passed"
  else
    format_status="failed"
    overall_status=1
  fi
else
  format_status="skipped: --fix was not set"
fi

if [[ "$pytest_only" -ne 1 ]]; then
  if run_and_log "make_lint" "${log_dir}/lint.log" make lint; then
    lint_status="passed"
  else
    lint_status="failed"
    overall_status=1
  fi
fi

if [[ "$lint_only" -ne 1 ]]; then
  if run_and_log "focused_pytest" "${log_dir}/focused_pytest.log" env PYTHONPATH=. "$python_bin" -m pytest "${tests[@]}"; then
    pytest_status="passed"
  else
    pytest_status="failed"
    overall_status=1
  fi
fi

{
  echo "## PR slice validation"
  echo
  echo "- Profile: \`${profile}\`"
  echo "- Profile file: \`${profile_file#${repo_root}/}\`"
  echo "- Format fix: ${format_status}"
  echo "- Lint: ${lint_status}"
  echo "- Focused pytest: ${pytest_status}"
  echo "- Python: \`${python_bin}\`"
  echo "- Log path: \`${log_dir}\`"
  echo "- Overall exit code: ${overall_status}"
  echo
  echo "### Focused pytest set"
  echo
  if [[ "${#tests[@]}" -eq 0 ]]; then
    echo "- Not run"
  else
    printf -- '- `%s`\n' "${tests[@]}"
  fi
  echo
  echo "### Commands"
  echo
  if [[ "$run_fix" -eq 1 ]]; then
    echo "- \`make format\`"
  else
    echo "- Format fix skipped. Run \`bash scripts/check_pr_slice.sh ${profile} --fix\` before commit when formatter-only churn is likely."
  fi
  if [[ "$pytest_only" -ne 1 ]]; then
    echo "- \`make lint\`"
  fi
  if [[ "$lint_only" -ne 1 ]]; then
    echo "- \`PYTHONPATH=. ${python_bin} -m pytest <profile tests>\`"
  fi
} >"$summary_file"

cat "$summary_file"
exit "$overall_status"
