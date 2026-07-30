#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: bash scripts/run_issue255_focused_fresh_with_model.sh [OPTIONS]

Locates the official OMR-DLN measure detector weight, validates it inside the
maintained production GPU container, then runs the Issue #255 two-page fresh batch
inside that same container.

Options:
  --python PATH            Host Python used only for JSON validation.
                           Defaults to $PYTHON or python3.
  --container NAME         Maintained production container.
                           Defaults to pdfscore_pipeline_gpu.
  --container-python PATH  Pipeline Python inside the container.
                           Defaults to /opt/venv_pipeline/bin/python.
  --omr-model PATH         Host path to YOLOv8m_Measures.pt. If omitted, checks
                           $OMR_DLN_MODEL_PATH, the repository default, then $HOME.
  --output-root PATH       Host output root under this repository.
                           Defaults to logs/issue255_focused_fresh.
  --run-tag TAG            Required run tag passed to the underlying batch runner.
  -h, --help               Show this help.

The host .venv_pdf interpreter is not used for HOMR, SR, OMR-DLN or CNN inference.
USAGE
}

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(realpath "${script_dir}/..")"
host_python="${PYTHON:-python3}"
container_name="${ISSUE255_CONTAINER:-pdfscore_pipeline_gpu}"
container_python="/opt/venv_pipeline/bin/python"
omr_model="${OMR_DLN_MODEL_PATH:-}"
output_root="logs/issue255_focused_fresh"
run_tag=""

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
      omr_model="$2"
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
  echo "Running containers:" >&2
  docker ps --format '  {{.Names}}\t{{.Image}}\t{{.Status}}' >&2
  exit 2
fi
if ! docker exec "$container_name" test -x "$container_python"; then
  echo "Container Python is unavailable: ${container_name}:${container_python}" >&2
  exit 2
fi

host_head="$(git rev-parse HEAD)"
container_head="$({
  docker exec \
    -w /workspace \
    -e GIT_CONFIG_COUNT=1 \
    -e GIT_CONFIG_KEY_0=safe.directory \
    -e GIT_CONFIG_VALUE_0=/workspace \
    "$container_name" git rev-parse HEAD
} 2>/dev/null || true)"
if [[ -z "$container_head" || "$container_head" != "$host_head" ]]; then
  echo "Container /workspace does not match the checked-out repository HEAD." >&2
  echo "  host:      $host_head" >&2
  echo "  container: ${container_head:-<unavailable>}" >&2
  exit 2
fi

if [[ -z "$omr_model" ]]; then
  repository_default="external/omr_dln/models/public_models/YOLOv8m_Measures.pt"
  if [[ -f "$repository_default" ]]; then
    omr_model="$repository_default"
  else
    mapfile -t discovered_models < <(
      find "${HOME}" -type f -name 'YOLOv8m_Measures.pt' -print 2>/dev/null | head -n 10
    )
    if [[ "${#discovered_models[@]}" -eq 1 ]]; then
      omr_model="${discovered_models[0]}"
    elif [[ "${#discovered_models[@]}" -gt 1 ]]; then
      echo "Multiple YOLOv8m_Measures.pt files found; select one with --omr-model:" >&2
      printf '  %s\n' "${discovered_models[@]}" >&2
      exit 2
    fi
  fi
fi

if [[ -z "$omr_model" || ! -f "$omr_model" ]]; then
  cat >&2 <<'ERROR'
Official OMR-DLN measure detector weight was not found.

Use the YOLOv8m_Measures.pt measure-detection model from dmgonzalez8/OMR. Then rerun
with --omr-model /absolute/path/to/YOLOv8m_Measures.pt. Historical detector artifacts
must not be substituted for this fresh gate.
ERROR
  exit 2
fi

omr_model="$(realpath "$omr_model")"
if [[ "$(basename "$omr_model")" != "YOLOv8m_Measures.pt" ]]; then
  echo "Unexpected OMR-DLN filename: $omr_model" >&2
  exit 2
fi

output_root="$(realpath -m "$output_root")"
case "$output_root" in
  "$repo_root"/*) ;;
  *)
    echo "--output-root must be inside the repository so the container can persist it:" >&2
    echo "  repository: $repo_root" >&2
    echo "  output:     $output_root" >&2
    exit 2
    ;;
esac
mkdir -p "$output_root"
container_output_root="/workspace/${output_root#"$repo_root"/}"
preflight_json="${output_root}/issue255_omr_dln_preflight_${run_tag}.json"
container_preflight_json="${container_output_root}/issue255_omr_dln_preflight_${run_tag}.json"
if [[ -e "$preflight_json" ]]; then
  echo "Refusing to overwrite OMR-DLN preflight: $preflight_json" >&2
  exit 2
fi

copied_model_dir=""
case "$omr_model" in
  "$repo_root"/*)
    container_model="/workspace/${omr_model#"$repo_root"/}"
    if ! docker exec "$container_name" test -f "$container_model"; then
      echo "Repository model is not visible in the container: $container_model" >&2
      exit 2
    fi
    ;;
  *)
    model_sha="$(sha256sum "$omr_model" | awk '{print $1}')"
    copied_model_dir="/tmp/issue255_omr_${model_sha}"
    container_model="${copied_model_dir}/YOLOv8m_Measures.pt"
    docker exec "$container_name" mkdir -p "$copied_model_dir"
    docker cp "$omr_model" "${container_name}:${container_model}" >/dev/null
    docker exec "$container_name" chmod 0444 "$container_model"
    ;;
esac

cleanup() {
  if [[ -n "$copied_model_dir" ]]; then
    docker exec "$container_name" rm -rf "$copied_model_dir" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

uid_gid="$(id -u):$(id -g)"
common_exec=(
  docker exec
  --user "$uid_gid"
  -w /workspace
  -e PYTHONPATH=/workspace
  -e HOME=/tmp
  -e YOLO_CONFIG_DIR=/tmp/issue255_ultralytics
  -e OMR_DLN_MODEL_PATH="$container_model"
  -e GIT_CONFIG_COUNT=1
  -e GIT_CONFIG_KEY_0=safe.directory
  -e GIT_CONFIG_VALUE_0=/workspace
)

set +e
"${common_exec[@]}" -i "$container_name" "$container_python" - \
  "$container_model" "$container_preflight_json" "$omr_model" "$container_name" <<'PY'
from __future__ import annotations

import hashlib
import json
import sys
import traceback
from pathlib import Path

model_path = Path(sys.argv[1]).resolve()
output_path = Path(sys.argv[2]).resolve()
host_model_path = sys.argv[3]
container_name = sys.argv[4]
report = {
    "schema_version": "issue255.omr_dln_preflight.v2",
    "status": "running",
    "host_model_path": host_model_path,
    "container_model_path": str(model_path),
    "container": container_name,
    "python": sys.executable,
}

try:
    import torch
    from ultralytics import YOLO

    digest = hashlib.sha256()
    with model_path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    model = YOLO(model_path)
    raw_names = model.names
    if isinstance(raw_names, dict):
        names = [str(raw_names[key]) for key in sorted(raw_names)]
    else:
        names = [str(value) for value in raw_names]
    required = {"systemMeasure", "staffMeasure"}
    missing = sorted(required - set(names))
    if missing:
        raise ValueError(
            "The selected weight is not the official OMR measure detector; "
            f"missing classes: {missing}; classes={names}"
        )
    report.update(
        {
            "status": "completed",
            "size_bytes": model_path.stat().st_size,
            "sha256": digest.hexdigest(),
            "task": getattr(model, "task", None),
            "class_names": names,
            "cuda_available": bool(torch.cuda.is_available()),
            "cuda_device_count": int(torch.cuda.device_count()),
        }
    )
except Exception as error:  # noqa: BLE001
    report.update(
        {
            "status": "failed",
            "error_type": type(error).__name__,
            "error": str(error),
            "traceback": traceback.format_exc(),
        }
    )

output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(json.dumps({"status": report["status"], "preflight": str(output_path)}, ensure_ascii=False))
raise SystemExit(0 if report["status"] == "completed" else 1)
PY
preflight_status=$?
set -e

if [[ "$preflight_status" -ne 0 ]]; then
  echo "OMR-DLN container preflight failed: $preflight_json" >&2
  if [[ -f "$preflight_json" ]]; then
    "$host_python" - "$preflight_json" <<'PY' >&2
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print(json.dumps(payload, indent=2, ensure_ascii=False))
PY
  fi
  exit "$preflight_status"
fi

echo "OMR-DLN container preflight passed: $preflight_json"
echo "OMR-DLN host model: $omr_model"
echo "OMR-DLN container model: $container_model"
echo "Production container: $container_name"

"${common_exec[@]}" "$container_name" /bin/bash \
  scripts/run_issue255_focused_fresh.sh \
  --python "$container_python" \
  --output-root "$container_output_root" \
  --run-tag "$run_tag"
