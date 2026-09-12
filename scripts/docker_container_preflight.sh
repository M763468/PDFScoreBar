#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/docker_container_preflight.sh CONTAINER [options]

Validate a persistent/development container before running issue-specific commands.
This script is host-side by design: Git provenance belongs to the host checkout, while
the container is checked for the exact /workspace mount and a still-available image ID.

Options:
  --require-command NAME        Require an executable inside the container (repeatable).
  --require-python-module NAME  Require a Python module in /opt/venv_pipeline (repeatable).
  -h, --help                    Show this help.

Examples:
  scripts/docker_container_preflight.sh pdfscore_pipeline_pytest_dev \
    --require-python-module pytest
  scripts/docker_container_preflight.sh issue294_container --require-command git
USAGE
}

if [[ $# -lt 1 ]]; then
  usage >&2
  exit 2
fi

container="$1"
shift
required_commands=()
required_modules=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --require-command)
      required_commands+=("${2:?missing command name}")
      shift 2
      ;;
    --require-python-module)
      required_modules+=("${2:?missing module name}")
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

for cmd in docker git realpath; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "Required host command is missing: $cmd" >&2
    exit 2
  fi
done

for name in "${required_commands[@]}"; do
  if [[ ! "$name" =~ ^[A-Za-z0-9_.+-]+$ ]]; then
    echo "Invalid command name: $name" >&2
    exit 2
  fi
done
for name in "${required_modules[@]}"; do
  if [[ ! "$name" =~ ^[A-Za-z0-9_.]+$ ]]; then
    echo "Invalid Python module name: $name" >&2
    exit 2
  fi
done

repo_root="$(realpath "$(git rev-parse --show-toplevel)")"
host_commit="$(git -C "$repo_root" rev-parse HEAD)"
host_branch="$(git -C "$repo_root" branch --show-current)"
if [[ -z "$host_branch" ]]; then
  host_branch="(detached)"
fi

if ! docker inspect "$container" >/dev/null 2>&1; then
  echo "Container not found: $container" >&2
  exit 2
fi

running="$(docker inspect --format '{{.State.Running}}' "$container")"
if [[ "$running" != "true" ]]; then
  echo "Container is not running: $container. Start or recreate it before validation." >&2
  exit 2
fi

workspace_source="$(docker inspect --format '{{range .Mounts}}{{if eq .Destination "/workspace"}}{{.Source}}{{end}}{{end}}' "$container")"
if [[ -z "$workspace_source" ]]; then
  echo "Container does not have a bind mount at /workspace: $container" >&2
  exit 2
fi
if [[ ! -e "$workspace_source" ]]; then
  echo "Container /workspace source no longer exists on the host: $workspace_source" >&2
  exit 2
fi
workspace_source="$(realpath "$workspace_source")"
if [[ "$workspace_source" != "$repo_root" ]]; then
  cat >&2 <<EOF
Container /workspace points at the wrong checkout/worktree.
  expected: $repo_root
  actual:   $workspace_source
Recreate the container from the active issue worktree instead of reusing it.
EOF
  exit 2
fi

container_image_id="$(docker inspect --format '{{.Image}}' "$container")"
if [[ -z "$container_image_id" ]]; then
  echo "Container image metadata is missing: $container" >&2
  exit 2
fi
if ! docker image inspect "$container_image_id" >/dev/null 2>&1; then
  cat >&2 <<EOF
Container metadata references an image ID that is no longer available locally:
  container: $container
  image_id:  $container_image_id
Treat .Image as historical provenance only. Recreate the container from the current
canonical image reference instead of attempting to run the stale image ID.
EOF
  exit 2
fi

for name in "${required_commands[@]}"; do
  if ! docker exec "$container" sh -lc "command -v '$name' >/dev/null 2>&1"; then
    if [[ "$name" == "git" ]]; then
      cat >&2 <<EOF
Required container command is missing: git
The canonical runtime intentionally does not require Git. Record branch/commit/merge-base
provenance on the host, or use an explicitly prepared disposable development environment
when a legacy workflow truly needs Git inside the container.
EOF
    else
      echo "Required container command is missing: $name" >&2
    fi
    exit 2
  fi
done

for name in "${required_modules[@]}"; do
  if ! docker exec "$container" /opt/venv_pipeline/bin/python -c \
    'import importlib.util, sys; raise SystemExit(0 if importlib.util.find_spec(sys.argv[1]) else 1)' \
    "$name"; then
    if [[ "$name" == "pytest" ]]; then
      cat >&2 <<EOF
Required validation module is missing: pytest
The production runtime intentionally does not include pytest. Use the documented
pdfscore_pipeline_pytest_dev pattern in AGENTS.md and install pytest there once, then rerun
this preflight before executing repository tests.
EOF
    else
      echo "Required container Python module is missing: $name" >&2
    fi
    exit 2
  fi
done

cat <<EOF
Persistent container preflight passed.
  container:        $container
  workspace_source: $workspace_source
  host_branch:      $host_branch
  host_commit:      $host_commit
  image_id:         $container_image_id
EOF
