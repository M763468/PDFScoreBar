#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

info() {
  printf "[INFO] %s\n" "$*"
}

warn() {
  printf "[WARN] %s\n" "$*" >&2
}

run_or_warn() {
  if ! "$@"; then
    warn "Command failed: $*"
  fi
}

usage() {
  cat <<EOF_USAGE
Bootstrap repository checks and GitHub resources.

Usage:
  ./scripts/init.sh [init_repo options]

init_repo options:
  --repo <owner/name>  Target repository (passed through to init_repo.sh)
  --with-issues        Create optional bootstrap issues
  --dry-run            Print planned changes without mutating GitHub resources
  -h, --help           Show this help message
EOF_USAGE
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

DRY_RUN_REQUESTED=0
args_copy=("$@")
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      DRY_RUN_REQUESTED=1
      shift
      ;;
    *)
      shift
      ;;
  esac
done
set -- "${args_copy[@]}"

info "Repository root: ${ROOT_DIR}"

if command -v gh >/dev/null 2>&1; then
  info "gh CLI detected"
  if gh auth status >/dev/null 2>&1; then
    info "gh auth status: OK"
    run_or_warn gh repo view >/dev/null
    run_or_warn "${ROOT_DIR}/scripts/init_repo.sh" "$@"
  elif [[ "${DRY_RUN_REQUESTED}" -eq 1 ]]; then
    warn "gh is not authenticated. Running init_repo.sh in dry-run mode."
    run_or_warn "${ROOT_DIR}/scripts/init_repo.sh" "$@"
  else
    warn "gh is installed but not authenticated. Run: gh auth login"
    warn "Skipping GitHub resource initialization"
  fi
else
  warn "gh CLI is not installed. See: https://cli.github.com/"
  warn "Skipping GitHub resource initialization"
fi

info "Checking required template files"
run_or_warn "${ROOT_DIR}/scripts/check-templates.sh"
info "Tip: run ./scripts/check-templates.sh --help for details"

info "Init complete"
