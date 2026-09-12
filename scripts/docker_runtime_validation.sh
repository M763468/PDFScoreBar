#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/docker_runtime_validation.sh [--config PATH] [--preflight-only]

Validates the canonical Docker runtime contract, then runs the configured pipeline smoke.
The OMR-DLN model is an explicit external asset and must be available via either:

  OMR_DLN_MODEL_PATH=/absolute/path/to/YOLOv8m_Measures.pt

or the legacy local path:

  external/omr_dln/models/public_models/YOLOv8m_Measures.pt

Environment:
  DOCKER_IMAGE       Docker image name. Default: pdfscore_pipeline_gpu
  DOCKER_EXTRA_ARGS  Extra arguments passed to docker run.
USAGE
}

config="configs/smoke_test.yaml"
preflight_only=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --config)
      config="${2:?missing config path}"
      shift 2
      ;;
    --preflight-only)
      preflight_only=1
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

repo_root="$(git rev-parse --show-toplevel)"
image="${DOCKER_IMAGE:-pdfscore_pipeline_gpu}"

if [[ "$config" = /* ]]; then
  case "$config" in
    "$repo_root"/*)
      config_relative="${config#"$repo_root"/}"
      ;;
    *)
      echo "Config must be inside the repository mounted at /workspace: $config" >&2
      exit 2
      ;;
  esac
else
  config_relative="$config"
fi

config_host="$repo_root/$config_relative"
if [[ ! -f "$config_host" ]]; then
  echo "Config not found: $config_host" >&2
  exit 2
fi

omr_host="${OMR_DLN_MODEL_PATH:-$repo_root/external/omr_dln/models/public_models/YOLOv8m_Measures.pt}"
if [[ ! -f "$omr_host" ]]; then
  cat >&2 <<EOF
OMR-DLN external model is missing: $omr_host
Set OMR_DLN_MODEL_PATH to the existing read-only YOLOv8m_Measures.pt path.
The model is intentionally not owned or downloaded by the Docker image.
EOF
  exit 2
fi
omr_host="$(realpath "$omr_host")"
omr_container="/opt/pdfscore-external/omr-dln/YOLOv8m_Measures.pt"

if ! docker image inspect "$image" >/dev/null 2>&1; then
  echo "Docker image not found: $image. Run 'make docker-build' first." >&2
  exit 2
fi

extra_args=()
if [[ -n "${DOCKER_EXTRA_ARGS:-}" ]]; then
  # Existing Makefile usage treats DOCKER_EXTRA_ARGS as shell words. Preserve
  # that contract without evaluating shell syntax.
  read -r -a extra_args <<<"${DOCKER_EXTRA_ARGS}"
fi

common_args=(
  run --rm --gpus all
  "${extra_args[@]}"
  -v "$repo_root:/workspace"
  -v "$omr_host:$omr_container:ro"
  -w /workspace
  -e PYTHONPATH=/workspace
  -e "OMR_DLN_MODEL_PATH=$omr_container"
  "$image"
)

container_config="/workspace/$config_relative"

echo "Validating Docker runtime contract..."
docker "${common_args[@]}" \
  /opt/venv_pipeline/bin/python /opt/pdfscore-runtime/runtime_contract.py preflight \
  --workspace /workspace \
  --config "$container_config"

if [[ "$preflight_only" -eq 1 ]]; then
  echo "Docker runtime preflight passed."
  exit 0
fi

echo "Running canonical pipeline smoke..."
docker "${common_args[@]}" \
  /opt/venv_pipeline/bin/python src/pipeline/main.py --config "$container_config"

echo "Docker runtime validation completed successfully."
