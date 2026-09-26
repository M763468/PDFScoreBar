#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  bash experiments/issue43/run_full68_x_domain_ab.sh RUN_TAG [extra Python args...]

Examples:
  bash experiments/issue43/run_full68_x_domain_ab.sh issue43_full68_01
  bash experiments/issue43/run_full68_x_domain_ab.sh issue43_full68_recheck \
    --upstream-manifest \
    logs/issue43/full68_x_domain_ab/issue43_full68_01/retained_upstream_manifest.json

Runs the Issue #43 A/B inside the canonical compatible GPU image, bind-mounting
the active checkout and the manifest-verified external OMR-DLN artifact.

Environment:
  PDFSCORE_EVAL2_IMAGES_ROOT  Optional host path to canonical evaluation2/images.
                              Mounted read-only at /workspace/data/evaluation2/images.
USAGE
}

if [[ $# -lt 1 ]]; then
  usage >&2
  exit 2
fi

run_tag="$1"
shift

for cmd in docker git python3 realpath; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "Required command is missing: $cmd" >&2
    exit 2
  fi
done

repo_root="$(realpath "$(git rev-parse --show-toplevel)")"
source_commit="$(git -C "$repo_root" rev-parse HEAD)"
image_ref="${DOCKER_IMAGE:-pdfscore_pipeline_gpu}"

resolver_args=(resolve --repo-root "$repo_root" --image-ref "$image_ref")
if [[ -n "${DOCKER_IMAGE:-}" ]]; then
  resolver_args+=(--explicit)
fi
image_id="$(
  python3 "$repo_root/scripts/docker_image_resolver.py" "${resolver_args[@]}"
)"

omr_manifest="$repo_root/models/omr_dln/manifest.json"
omr_host="$(
  PYTHONPATH="$repo_root" python3 -m src.common.model_artifacts verify "$omr_manifest"
)"
omr_host="$(realpath "$omr_host")"
omr_container="$(
  python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["runtime_path"])' \
    "$omr_manifest"
)"

extra_mounts=()
if [[ -n "${PDFSCORE_EVAL2_IMAGES_ROOT:-}" ]]; then
  images_root="$(realpath "${PDFSCORE_EVAL2_IMAGES_ROOT}")"
  if [[ ! -d "$images_root" ]]; then
    echo "PDFSCORE_EVAL2_IMAGES_ROOT is not a directory: $images_root" >&2
    exit 2
  fi
  extra_mounts+=(-v "$images_root:/workspace/data/evaluation2/images:ro")
fi

docker run --rm --gpus all \
  -v "$repo_root:/workspace" \
  -v "$omr_host:$omr_container:ro" \
  "${extra_mounts[@]}" \
  -w /workspace \
  -e PYTHONPATH=/workspace \
  -e "OMR_DLN_MODEL_PATH=$omr_container" \
  -e "ISSUE43_SOURCE_COMMIT=$source_commit" \
  "$image_id" \
  /opt/venv_pipeline/bin/python \
  experiments/issue43/compare_full68_x_domain.py \
  --run-tag "$run_tag" \
  "$@"
