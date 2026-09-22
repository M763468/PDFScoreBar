#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
expected_base_sha="${ISSUE267_BASE_SHA:-6bef8bc0c74b2237ef5cda2e4e837c698eb90dde}"
artifact_root="${ARTIFACT_ROOT:-}"
base_code_root="${BASE_CODE_ROOT:-}"
candidate_code_root="${CANDIDATE_CODE_ROOT:-$repo_root}"
python_bin="${PYTHON_BIN:-python3}"

usage() {
  cat <<'EOF'
Usage:
  ARTIFACT_ROOT=/path/to/artifact-checkout \
  BASE_CODE_ROOT=/path/to/pre-267-worktree \
  [CANDIDATE_CODE_ROOT=/path/to/issue267-worktree] \
  [PYTHON_BIN=/path/to/python] \
  scripts/validate_issue267_numbering_counts.sh

Required:
  ARTIFACT_ROOT    Checkout containing retained data/ and logs/ inputs.
  BASE_CODE_ROOT   Worktree pinned to the pre-#267 develop commit.

Optional:
  CANDIDATE_CODE_ROOT  Defaults to the checkout containing this script.
  PYTHON_BIN           Defaults to python3.
  ISSUE267_BASE_SHA    Override only if #267 is deliberately rebased to a new baseline.
  OUTPUT_ROOT          Defaults to ARTIFACT_ROOT/logs/issue267/count_validation/<candidate-short-sha>.
EOF
}

if [[ -z "$artifact_root" || -z "$base_code_root" ]]; then
  usage >&2
  exit 2
fi

for root in "$artifact_root" "$base_code_root" "$candidate_code_root"; do
  if [[ ! -d "$root" ]]; then
    echo "Missing directory: $root" >&2
    exit 2
  fi
done

actual_base_sha="$(git -C "$base_code_root" rev-parse HEAD)"
if [[ "$actual_base_sha" != "$expected_base_sha" ]]; then
  echo "Refusing to use the wrong #267 baseline." >&2
  echo "expected: $expected_base_sha" >&2
  echo "actual:   $actual_base_sha" >&2
  exit 2
fi

candidate_sha="$(git -C "$candidate_code_root" rev-parse HEAD)"
candidate_short_sha="$(git -C "$candidate_code_root" rev-parse --short=12 HEAD)"
output_root="${OUTPUT_ROOT:-$artifact_root/logs/issue267/count_validation/$candidate_short_sha}"
baseline_run="$output_root/baseline"
candidate_run="$output_root/candidate"
compare_report="$output_root/count_compare.json"

mkdir -p "$output_root"

echo "Issue #267 physical-measure count validation"
echo "baseline:  $actual_base_sha"
echo "candidate: $candidate_sha"
echo "artifacts: $artifact_root"
echo "output:    $output_root"
echo

echo "=== baseline replay ==="
"$python_bin" "$repo_root/tools/issue267/run_numbering_count_replay.py" \
  --code-root "$base_code_root" \
  --input-root "$artifact_root" \
  --output-root "$baseline_run"

echo
echo "=== candidate replay ==="
"$python_bin" "$repo_root/tools/issue267/run_numbering_count_replay.py" \
  --code-root "$candidate_code_root" \
  --input-root "$artifact_root" \
  --output-root "$candidate_run"

echo
echo "=== physical-measure count comparison with semantic diagnostics ==="
"$python_bin" "$repo_root/tools/issue267/compare_numbering_count_signatures.py" \
  --baseline-run "$baseline_run" \
  --candidate-run "$candidate_run" \
  --output "$compare_report"

echo
echo "PASS: #267 physical-measure counts are identical; inspect semantic_match separately for geometry diagnostics."
echo "report: $compare_report"
