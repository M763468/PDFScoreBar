#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/setup_shared_worktree.sh --branch BRANCH --worktree PATH [--shared-root PATH]

Creates a Git worktree and links local generated-output directories to a shared
manager worktree. Existing destinations are never overwritten.
USAGE
}

branch=""
worktree=""
shared_root=""
items="${PDFSCORE_SHARED_WORKTREE_ITEMS:-logs artifacts datasets debug_outputs temp tmp .venv .venv_pdf .venv_cnn_classifier .venv_host_gui}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --branch) branch="${2:?missing branch}"; shift 2 ;;
    --worktree) worktree="${2:?missing worktree}"; shift 2 ;;
    --shared-root) shared_root="${2:?missing shared root}"; shift 2 ;;
    --items) items="${2:?missing items}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

[[ -n "$branch" ]] || { echo "--branch is required" >&2; exit 2; }
[[ -n "$worktree" ]] || { echo "--worktree is required" >&2; exit 2; }

repo_root="$(git rev-parse --show-toplevel)"
shared_root="${shared_root:-$repo_root}"
shared_root="$(cd "$shared_root" && pwd -P)"
worktree="$(mkdir -p "$(dirname "$worktree")" && cd "$(dirname "$worktree")" && printf '%s/%s' "$PWD" "$(basename "$worktree")")"

if [[ -e "$worktree" || -L "$worktree" ]]; then
  echo "Worktree destination already exists: $worktree" >&2
  exit 2
fi

git worktree add "$worktree" "$branch"

for item in $items; do
  source_path="$shared_root/$item"
  destination="$worktree/$item"

  if [[ ! -e "$source_path" ]]; then
    echo "skip: shared source missing: $source_path"
    continue
  fi
  if [[ -e "$destination" || -L "$destination" ]]; then
    echo "skip: destination exists: $destination"
    continue
  fi

  mkdir -p "$(dirname "$destination")"
  ln -s "$source_path" "$destination"
  echo "linked: $destination -> $source_path"
done

echo "worktree ready: $worktree"
