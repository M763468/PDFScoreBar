#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: bash scripts/validate_issue255_local.sh [OPTIONS]

Validates the Issue #255 implementation slice without running GPU inference.

Options:
  --python PATH   Python executable for py_compile and pytest.
                  Defaults to $PYTHON or python3.
  --base REF      Base ref used by git diff checks.
                  Defaults to origin/develop.
  --pytest-only   Skip make lint and run only compile/UTF-8/diff/focused pytest.
  --lint-only     Skip focused pytest and run only compile/UTF-8/diff/make lint.
  --fix           Run make format before lint/pytest through check_pr_slice.sh.
  -h, --help      Show this help.

Example:
  bash scripts/validate_issue255_local.sh \
    --python /home/masaki_muramatsu/ws_PDFScoreBar/.venv_pdf/bin/python
USAGE
}

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${script_dir}/.." && pwd)"
python_bin="${PYTHON:-python3}"
base_ref="origin/develop"
pytest_only=0
lint_only=0
run_fix=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --python)
      [[ $# -ge 2 ]] || { echo "--python requires a path" >&2; exit 2; }
      python_bin="$2"
      shift 2
      ;;
    --base)
      [[ $# -ge 2 ]] || { echo "--base requires a ref" >&2; exit 2; }
      base_ref="$2"
      shift 2
      ;;
    --pytest-only)
      pytest_only=1
      shift
      ;;
    --lint-only)
      lint_only=1
      shift
      ;;
    --fix)
      run_fix=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ "$pytest_only" -eq 1 && "$lint_only" -eq 1 ]]; then
  echo "--pytest-only and --lint-only cannot be combined" >&2
  exit 2
fi

cd "$repo_root"

if [[ ! -x "$python_bin" ]] && ! command -v "$python_bin" >/dev/null 2>&1; then
  echo "Python executable not found: $python_bin" >&2
  exit 2
fi

if ! git rev-parse --verify --quiet "$base_ref^{commit}" >/dev/null; then
  echo "Base ref not found: $base_ref" >&2
  echo "Run 'git fetch origin develop' or pass --base <existing-ref>." >&2
  exit 2
fi

required_files=(
  src/pipeline/detection/omr_dln_model.py
  tools/issue255/run_focused_fresh_detector.py
  tools/issue255/trace_focused_detector_boundaries.py
  tests/test_issue255_focused_fresh_run.py
  tests/test_issue255_focused_detector_inventory.py
  tests/test_omr_dln_model_contract.py
  scripts/run_issue255_focused_fresh.sh
  scripts/run_issue255_focused_fresh_with_model.sh
  scripts/pr_validation_profiles/issue255-fresh-detector-production-recovery.txt
)
for path in "${required_files[@]}"; do
  [[ -f "$path" ]] || { echo "Required file missing: $path" >&2; exit 1; }
done

echo "==> git diff --check (${base_ref}...HEAD)"
git diff --check "$base_ref"...HEAD

echo "==> UTF-8 validation for changed text files"
mapfile -t changed_files < <(
  git diff --name-only --diff-filter=ACMR "$base_ref"...HEAD
)
printf '%s\n' "${changed_files[@]}" | "$python_bin" -c '
import pathlib
import sys

failed = []
checked = 0
for raw in sys.stdin:
    value = raw.rstrip("\n")
    if not value:
        continue
    path = pathlib.Path(value)
    if not path.is_file():
        continue
    data = path.read_bytes()
    if b"\0" in data[:8192]:
        continue
    checked += 1
    try:
        data.decode("utf-8")
    except UnicodeDecodeError as exc:
        failed.append(f"{path}: {exc}")
if failed:
    raise SystemExit("Invalid UTF-8 in changed files:\n" + "\n".join(failed))
print(f"UTF-8 OK: {checked} changed text files")
'

echo "==> Bash syntax"
bash -n \
  scripts/run_issue255_focused_fresh.sh \
  scripts/run_issue255_focused_fresh_with_model.sh \
  scripts/validate_issue255_local.sh

echo "==> Python compile"
PYTHONPATH=. "$python_bin" -m py_compile \
  src/pipeline/core/python_env.py \
  src/pipeline/core/subprocess_utils.py \
  src/pipeline/detection/omr_dln_model.py \
  experiments/models/eval_omr_dln.py \
  tools/issue255/run_focused_fresh_detector.py \
  tools/issue255/trace_focused_detector_boundaries.py \
  tests/test_issue255_focused_fresh_run.py \
  tests/test_issue255_focused_detector_inventory.py \
  tests/test_omr_dln_model_contract.py \
  tests/test_subprocess_utils.py

check_args=(
  issue255-fresh-detector-production-recovery
  --python "$python_bin"
)
if [[ "$run_fix" -eq 1 ]]; then
  check_args+=(--fix)
fi
if [[ "$pytest_only" -eq 1 ]]; then
  check_args+=(--pytest-only)
elif [[ "$lint_only" -eq 1 ]]; then
  check_args+=(--lint-only)
fi

echo "==> PR slice validation"
bash scripts/check_pr_slice.sh "${check_args[@]}"

echo
printf 'Issue #255 local validation passed.\n'
printf '  base:    %s\n' "$base_ref"
printf '  head:    %s\n' "$(git rev-parse HEAD)"
printf '  python:  %s\n' "$python_bin"
