#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/gpu_smoke.sh [--timeout DURATION] [--command COMMAND] [--metadata-only]

Runs a bounded GPU/pipeline smoke command and records reproducibility metadata.

Environment:
  GPU_SMOKE_TIMEOUT   Default timeout duration. Default: 45m
  GPU_SMOKE_CMD       Command to run. Default: make run-smoke
USAGE
}

timeout_duration="${GPU_SMOKE_TIMEOUT:-45m}"
smoke_cmd="${GPU_SMOKE_CMD:-make run-smoke}"
metadata_only=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --timeout)
      timeout_duration="${2:?missing timeout value}"
      shift 2
      ;;
    --command)
      smoke_cmd="${2:?missing command value}"
      shift 2
      ;;
    --metadata-only)
      metadata_only=1
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
log_dir="logs/system/gpu_smoke_${timestamp}"
log_file="${log_dir}/gpu_smoke.log"
mkdir -p "$log_dir"

branch="$(git branch --show-current 2>/dev/null || echo unknown)"
commit="$(git rev-parse HEAD 2>/dev/null || echo unknown)"

{
  echo "timestamp_utc=${timestamp}"
  echo "branch=${branch}"
  echo "commit=${commit}"
  echo "pwd=$(pwd)"
  echo "python_version=$({ python3 --version || python --version; } 2>&1 | head -n 1)"
  echo "timeout=${timeout_duration}"
  echo "command=${smoke_cmd}"
  echo
  echo "git_status:"
  git status --short || true
  echo
  echo "gpu_info:"
  if command -v nvidia-smi >/dev/null 2>&1; then
    nvidia-smi || true
  else
    echo "nvidia-smi not found"
  fi
  echo
} | tee "$log_file"

if [[ "$metadata_only" -eq 1 ]]; then
  echo "metadata_only=1" | tee -a "$log_file"
  echo "GPU smoke metadata written to $log_file"
  exit 0
fi

if ! command -v timeout >/dev/null 2>&1; then
  echo "timeout command is required for GPU smoke" | tee -a "$log_file" >&2
  exit 2
fi

echo "Running GPU smoke command..." | tee -a "$log_file"
set +e
timeout "$timeout_duration" bash -c "$smoke_cmd" >>"$log_file" 2>&1
status=$?
set -e

{
  echo
  echo "exit_code=${status}"
  echo "log_path=${log_file}"
} | tee -a "$log_file"

exit "$status"
