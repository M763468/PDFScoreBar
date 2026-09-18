#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/docker_runtime_validation.sh [--config PATH] [--preflight-only]

Validates the canonical Docker runtime contract, then runs the configured pipeline smoke.
OMR-DLN is an external/operator-supplied artifact. Canonical validation resolves the
selected, digest-verified version from the common model cache. One-time registration:

  python3 -m src.common.model_artifacts import models/omr_dln/manifest.json /path/to/YOLOv8m_Measures.pt

OMR_DLN_MODEL_PATH remains a verified explicit compatibility override.

Environment:
  DOCKER_IMAGE              Canonical Docker image reference. Default: pdfscore_pipeline_gpu
  DOCKER_EXTRA_ARGS         Extra arguments passed to docker run.
  PDFSCOREBAR_MODEL_CACHE   Optional shared host model-cache root. Default: .model_cache
  OMR_DLN_MODEL_PATH        Optional explicit OMR-DLN compatibility override.
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

for cmd in docker git realpath python3; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "Required host command is missing: $cmd" >&2
    exit 2
  fi
done

repo_root="$(realpath "$(git rev-parse --show-toplevel)")"
host_commit="$(git -C "$repo_root" rev-parse HEAD)"
host_branch="$(git -C "$repo_root" branch --show-current)"
if [[ -z "$host_branch" ]]; then
  host_branch="(detached)"
fi
image_ref="${DOCKER_IMAGE:-pdfscore_pipeline_gpu}"

# Resolve the mutable canonical reference exactly once. All subsequent container
# launches use the immutable ID so a concurrent rebuild/tag update cannot mix
# runtimes within one validation run.
image_id="$(docker image inspect "$image_ref" --format '{{.Id}}' 2>/dev/null || true)"
if [[ -z "$image_id" ]]; then
  echo "Docker image reference is not available locally: $image_ref. Run 'make docker-build' first." >&2
  exit 2
fi
asset_contract="$(
  docker image inspect "$image_id" \
    --format '{{index .Config.Labels "pdfscore.runtime.asset_contract"}}' 2>/dev/null || true
)"
if [[ "$asset_contract" != "v1" ]]; then
  cat >&2 <<EOF
Docker image does not expose the expected PDFScoreBar runtime contract label.
  image_ref:      $image_ref
  image_id:       $image_id
  asset_contract: ${asset_contract:-<missing>}
Rebuild the canonical image from the active checkout.
EOF
  exit 2
fi

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

omr_manifest="$repo_root/models/omr_dln/manifest.json"
omr_container="$(
  python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["runtime_path"])' \
    "$omr_manifest"
)"

verify_explicit_omr() {
  local candidate="$1"
  PYTHONPATH="$repo_root" python3 -m src.common.model_artifacts verify-file \
    "$omr_manifest" "$candidate"
}

resolve_cached_omr() {
  PYTHONPATH="$repo_root" python3 -m src.common.model_artifacts verify "$omr_manifest"
}

if [[ -n "${OMR_DLN_MODEL_PATH:-}" ]]; then
  omr_host="$(verify_explicit_omr "$OMR_DLN_MODEL_PATH")"
else
  set +e
  omr_host="$(resolve_cached_omr 2>/dev/null)"
  omr_status=$?
  set -e
  if [[ "$omr_status" -ne 0 ]]; then
    legacy_omr="$repo_root/external/omr_dln/models/public_models/YOLOv8m_Measures.pt"
    if [[ -f "$legacy_omr" ]]; then
      echo "Using verified legacy OMR-DLN path; import it into the common cache for canonical reuse." >&2
      omr_host="$(verify_explicit_omr "$legacy_omr")"
    else
      cat >&2 <<EOF
Selected OMR-DLN artifact is not registered in the common model cache.
Manifest: $omr_manifest
Register the official YOLOv8m_Measures.pt once with:
  python3 -m src.common.model_artifacts import models/omr_dln/manifest.json /path/to/YOLOv8m_Measures.pt
The import verifies the selected version digest before publishing to .model_cache.
OMR_DLN_MODEL_PATH remains available as a verified compatibility override.
EOF
      exit 2
    fi
  fi
fi
omr_host="$(realpath "$omr_host")"

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
  -e "PDFSCORE_HOST_SOURCE_ROOT=$repo_root"
  -e "PDFSCORE_HOST_SOURCE_BRANCH=$host_branch"
  -e "PDFSCORE_HOST_SOURCE_COMMIT=$host_commit"
  -e "PDFSCORE_DOCKER_IMAGE_REF=$image_ref"
  -e "PDFSCORE_DOCKER_IMAGE_ID=$image_id"
  "$image_id"
)

container_config="/workspace/$config_relative"

cat <<EOF
Canonical Docker validation provenance:
  source_root: $repo_root
  branch:      $host_branch
  commit:      $host_commit
  image_ref:   $image_ref
  image_id:    $image_id
  omr_manifest: models/omr_dln/manifest.json
  omr_host:    $omr_host
  omr_runtime: $omr_container
EOF

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
