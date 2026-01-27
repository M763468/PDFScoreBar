#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

required_files=(
  "README.md"
  ".github/pull_request_template.md"
  ".github/ISSUE_TEMPLATE/feature.yml"
  ".github/ISSUE_TEMPLATE/bug.yml"
  ".github/ISSUE_TEMPLATE/task.yml"
  "docs/WORKFLOW.md"
  "docs/PROMPTS.md"
)

usage() {
  cat <<EOF
Check whether the minimum template files for this repository exist.

This script is intended to be run right after "Use this template".
If any required file is missing, it exits with a non-zero status.

Files checked:
$(for rel_path in "${required_files[@]}"; do printf "  - %s\n" "${rel_path}"; done)
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

missing=0

cat <<EOF
Template presence check (repo root: ${ROOT_DIR})
The following files should exist so that:
  - README alone explains the first 10 minutes
  - Issue / PR templates are available in GitHub UI
  - Docs entry points are present
EOF

for rel_path in "${required_files[@]}"; do
  abs_path="${ROOT_DIR}/${rel_path}"
  if [[ -f "${abs_path}" ]]; then
    printf "  [OK] %s\n" "${rel_path}"
  else
    printf "  [MISSING] %s\n" "${rel_path}"
    missing=1
  fi
done

if [[ "${missing}" -ne 0 ]]; then
  printf "One or more required template files are missing.\n"
  exit 1
fi

printf "All required template files are present.\n"
