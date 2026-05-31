#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/setup_local_worktree_links.sh --source PATH [--items "datasets logs/models cache"]

Creates symlinks from this worktree to local-only assets without moving or deleting data.

Environment:
  PDFSCORE_LOCAL_DATA_ROOT  Source root if --source is omitted.
  PDFSCORE_LINK_ITEMS       Space-separated items to link.
                            Default: datasets logs/models cache
USAGE
}

source_root="${PDFSCORE_LOCAL_DATA_ROOT:-}"
items="${PDFSCORE_LINK_ITEMS:-datasets logs/models cache}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --source)
      source_root="${2:?missing source path}"
      shift 2
      ;;
    --items)
      items="${2:?missing items list}"
      shift 2
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

if [[ -z "$source_root" ]]; then
  echo "Source root is required. Use --source or PDFSCORE_LOCAL_DATA_ROOT." >&2
  exit 2
fi

if [[ ! -d "$source_root" ]]; then
  echo "Source root does not exist: $source_root" >&2
  exit 2
fi

echo "source_root=$source_root"
echo "items=$items"

for item in $items; do
  src="${source_root%/}/$item"
  dest="$item"

  if [[ ! -e "$src" ]]; then
    echo "skip: source missing: $src"
    continue
  fi

  if [[ -L "$dest" ]]; then
    current="$(readlink "$dest")"
    if [[ "$current" == "$src" ]]; then
      echo "ok: $dest already links to $src"
      continue
    fi
    echo "skip: $dest is already a symlink to $current"
    continue
  fi

  if [[ -e "$dest" ]]; then
    echo "skip: destination exists and will not be replaced: $dest"
    continue
  fi

  mkdir -p "$(dirname "$dest")"
  ln -s "$src" "$dest"
  echo "linked: $dest -> $src"
done
