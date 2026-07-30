#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: bash scripts/run_issue255_focused_fresh_gate.sh [OPTIONS]

Bootstraps the three HOMR GPU models as container root, records their provenance,
then delegates to run_issue255_focused_fresh_with_model.sh. The detector batch itself
continues to run as the host UID so repository outputs are not root-owned.

Options are the same as run_issue255_focused_fresh_with_model.sh:
  --python PATH
  --container NAME
  --container-python PATH
  --omr-model PATH
  --output-root PATH
  --run-tag TAG
  -h, --help
USAGE
}

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(realpath "${script_dir}/..")"
host_python="${PYTHON:-python3}"
container_name="${ISSUE255_CONTAINER:-pdfscore_pipeline_gpu}"
container_python="/opt/venv_pipeline/bin/python"
output_root="logs/issue255_focused_fresh"
run_tag=""
forward_args=("$@")

while [[ $# -gt 0 ]]; do
  case "$1" in
    --python)
      [[ $# -ge 2 ]] || { echo "--python requires a path" >&2; exit 2; }
      host_python="$2"
      shift 2
      ;;
    --container)
      [[ $# -ge 2 ]] || { echo "--container requires a name" >&2; exit 2; }
      container_name="$2"
      shift 2
      ;;
    --container-python)
      [[ $# -ge 2 ]] || { echo "--container-python requires a path" >&2; exit 2; }
      container_python="$2"
      shift 2
      ;;
    --omr-model)
      [[ $# -ge 2 ]] || { echo "--omr-model requires a path" >&2; exit 2; }
      shift 2
      ;;
    --output-root)
      [[ $# -ge 2 ]] || { echo "--output-root requires a path" >&2; exit 2; }
      output_root="$2"
      shift 2
      ;;
    --run-tag)
      [[ $# -ge 2 ]] || { echo "--run-tag requires a value" >&2; exit 2; }
      run_tag="$2"
      shift 2
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

[[ -n "$run_tag" ]] || { echo "--run-tag is required" >&2; exit 2; }
cd "$repo_root"

if [[ ! -x "$host_python" ]] && ! command -v "$host_python" >/dev/null 2>&1; then
  echo "Host Python executable not found: $host_python" >&2
  exit 2
fi
if ! command -v docker >/dev/null 2>&1; then
  echo "docker command not found" >&2
  exit 2
fi
if ! docker ps --format '{{.Names}}' | grep -Fxq "$container_name"; then
  echo "Maintained production container is not running: $container_name" >&2
  exit 2
fi
if ! docker exec "$container_name" test -x "$container_python"; then
  echo "Container Python is unavailable: ${container_name}:${container_python}" >&2
  exit 2
fi

output_root="$(realpath -m "$output_root")"
case "$output_root" in
  "$repo_root"/*) ;;
  *)
    echo "--output-root must be inside the repository: $output_root" >&2
    exit 2
    ;;
esac
mkdir -p "$output_root"
container_output_root="/workspace/${output_root#"$repo_root"/}"
bootstrap_json="${output_root}/issue255_homr_model_bootstrap_${run_tag}.json"
container_bootstrap_json="${container_output_root}/issue255_homr_model_bootstrap_${run_tag}.json"
if [[ -e "$bootstrap_json" ]]; then
  echo "Refusing to overwrite HOMR bootstrap report: $bootstrap_json" >&2
  exit 2
fi

set +e
docker exec \
  --user 0:0 \
  -w /workspace \
  -e PYTHONPATH=/workspace \
  "$container_name" \
  "$container_python" tools/issue255/bootstrap_homr_models.py \
  --output "$container_bootstrap_json"
bootstrap_status=$?
set -e

uid_gid="$(id -u):$(id -g)"
if docker exec "$container_name" test -f "$container_bootstrap_json"; then
  docker exec --user 0:0 "$container_name" chown "$uid_gid" "$container_bootstrap_json"
fi

if [[ "$bootstrap_status" -ne 0 ]]; then
  echo "HOMR model bootstrap failed: $bootstrap_json" >&2
  if [[ -f "$bootstrap_json" ]]; then
    "$host_python" - "$bootstrap_json" <<'PY' >&2
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print(json.dumps(payload, indent=2, ensure_ascii=False))
PY
  fi
  exit "$bootstrap_status"
fi

echo "HOMR model bootstrap passed: $bootstrap_json"
exec bash scripts/run_issue255_focused_fresh_with_model.sh "${forward_args[@]}"
