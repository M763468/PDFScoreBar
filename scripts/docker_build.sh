#!/usr/bin/env bash
set -euo pipefail

image_ref="${DOCKER_IMAGE:-pdfscore_pipeline_gpu}"
python_bin="${PYTHON:-python3}"
artifact_dir="artifacts"
build_log="$artifact_dir/docker_build.log"
provenance_file="$artifact_dir/docker_build_provenance.txt"

mkdir -p "$artifact_dir"

provenance_tmp="$(mktemp "$artifact_dir/.docker_build_provenance.XXXXXX")"
cleanup() {
  rm -f "$provenance_tmp"
}
trap cleanup EXIT

source_fingerprint="$(PYTHONPATH=. "$python_bin" docker/runtime_contract.py fingerprint .)"
source_commit="$(git rev-parse HEAD)"
source_branch="$(git branch --show-current)"
if [[ -z "$source_branch" ]]; then
  source_branch="(detached)"
fi

printf 'source_root=%s\nsource_branch=%s\nsource_commit=%s\nsource_fingerprint=%s\nimage_ref=%s\n' \
  "$(pwd)" \
  "$source_branch" \
  "$source_commit" \
  "$source_fingerprint" \
  "$image_ref" \
  >"$provenance_tmp"

set +e
docker build \
  --build-arg "PDFSCORE_SOURCE_FINGERPRINT=$source_fingerprint" \
  --build-arg "PDFSCORE_SOURCE_COMMIT=$source_commit" \
  --build-arg "PDFSCORE_SOURCE_BRANCH=$source_branch" \
  -t "$image_ref" \
  . >"$build_log" 2>&1
status=$?
set -e

if [[ "$status" -ne 0 ]]; then
  echo "Docker build failed with exit code $status. See $build_log" >&2
  exit "$status"
fi

mv -f "$provenance_tmp" "$provenance_file"
echo "Docker build finished successfully. Provenance: $provenance_file"
