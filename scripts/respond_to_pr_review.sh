#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/respond_to_pr_review.sh --pr NUMBER [--codex]

Collects PR comments/reviews with gh and writes an artifact that can be passed to
Codex CLI. With --codex, runs a read-only planning prompt through codex exec.
USAGE
}

pr_number=""
run_codex=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --pr)
      pr_number="${2:?missing PR number}"
      shift 2
      ;;
    --codex)
      run_codex=1
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

if [[ -z "$pr_number" ]]; then
  echo "--pr is required" >&2
  exit 2
fi

if ! command -v gh >/dev/null 2>&1; then
  echo "gh is required to collect PR review context" >&2
  exit 2
fi

mkdir -p artifacts
context_file="artifacts/pr_${pr_number}_review_context.json"
plan_file="artifacts/pr_${pr_number}_review_response_plan.md"

gh pr view "$pr_number" \
  --json title,body,state,headRefName,baseRefName,comments,reviews \
  >"$context_file"

cat >"$plan_file" <<EOF_PLAN
# PR #${pr_number} review response entrypoint

Collected context: \`${context_file}\`

Suggested manual loop:

1. Read unresolved or actionable comments from \`${context_file}\`.
2. Implement only those requested changes.
3. Run \`make test-fast\` and any targeted smoke command required by the diff.
4. Post a PR comment with changed files, commands, log paths, skipped validation, and remaining risks.

Use \`codex exec\` only when the local checkout is clean enough to avoid unrelated edits.
EOF_PLAN

if [[ "$run_codex" -eq 1 ]]; then
  if ! command -v codex >/dev/null 2>&1; then
    echo "codex CLI not found; skipping codex execution" >&2
  else
    codex exec --sandbox read-only "Review ${context_file} and list only actionable PR review items. Do not edit files." >>"$plan_file" 2>&1
  fi
fi

echo "Wrote $context_file"
echo "Wrote $plan_file"
