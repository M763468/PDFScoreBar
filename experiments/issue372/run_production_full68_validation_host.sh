#!/usr/bin/env bash
set -euo pipefail

repo_root="$(realpath "$(git rev-parse --show-toplevel)")"
cd "$repo_root"

branch="$(git branch --show-current)"
if [[ "$branch" != "fix/issue372-detector-regression" ]]; then
  echo "Unexpected branch: $branch" >&2
  exit 2
fi
if [[ -n "$(git status --porcelain)" ]]; then
  echo "Production full68 validation requires a clean checkout." >&2
  git status --short >&2
  exit 2
fi

commit="$(git rev-parse HEAD)"
eval2_data_root="${PDFSCORE_EVAL2_DATA_ROOT:-$repo_root/data/evaluation2}"
eval2_data_root="$(realpath "$eval2_data_root")"
for required in \
  "$eval2_data_root/pdfs/Va_Prokofiev_Symphony1.pdf" \
  "$eval2_data_root/images" \
  "$eval2_data_root/annotations" \
  "$eval2_data_root/staff_units.json"; do
  if [[ ! -e "$required" ]]; then
    echo "Required evaluation2 data missing: $required" >&2
    exit 2
  fi
done

counterfactual="$repo_root/logs/issue372/late_raw_frozen_hybrid_bands_20260923T093728Z/counterfactual_report.json"
reference="$repo_root/logs/issue372/combined_downstream_semantic_replay_20260923T095833Z/combined_downstream_semantic_replay.json"
for path in "$counterfactual" "$reference"; do
  if [[ ! -f "$path" ]]; then
    echo "Required retained reference missing: $path" >&2
    exit 2
  fi
done

image_ref="${DOCKER_IMAGE:-pdfscore_pipeline_gpu}"
resolver_args=(resolve --repo-root "$repo_root" --image-ref "$image_ref")
if [[ -n "${DOCKER_IMAGE:-}" ]]; then
  resolver_args+=(--explicit)
fi
image_id="$(python3 scripts/docker_image_resolver.py "${resolver_args[@]}")"

omr_manifest="$repo_root/models/omr_dln/manifest.json"
if [[ -n "${OMR_DLN_MODEL_PATH:-}" ]]; then
  omr_host="$(
    PYTHONPATH="$repo_root" python3 -m src.common.model_artifacts verify-file \
      "$omr_manifest" "$OMR_DLN_MODEL_PATH"
  )"
else
  cached_omr="$(
    PYTHONPATH="$repo_root" python3 -m src.common.model_artifacts path "$omr_manifest"
  )"
  if [[ -e "$cached_omr" || -L "$cached_omr" ]]; then
    omr_host="$(
      PYTHONPATH="$repo_root" python3 -m src.common.model_artifacts verify "$omr_manifest"
    )"
  else
    legacy="$repo_root/external/omr_dln/models/public_models/YOLOv8m_Measures.pt"
    if [[ ! -f "$legacy" ]]; then
      echo "OMR-DLN model is not registered and legacy model is absent." >&2
      exit 2
    fi
    omr_host="$(
      PYTHONPATH="$repo_root" python3 -m src.common.model_artifacts verify-file \
        "$omr_manifest" "$legacy"
    )"
  fi
fi
omr_host="$(realpath "$omr_host")"
omr_container="$(
  python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["runtime_path"])' \
    "$omr_manifest"
)"

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
output="$repo_root/logs/issue372/production_full68_validation_$timestamp"
output_rel="${output#"$repo_root"/}"
container_output="/workspace/$output_rel"
if [[ -e "$output" ]]; then
  echo "Refusing to reuse output: $output" >&2
  exit 2
fi

echo "=== Issue #372 production full68 ==="
echo "commit=$commit"
echo "image_id=$image_id"
echo "eval2_data_root=$eval2_data_root"
echo "output=$output"
echo "container_user=root (matches canonical Docker validation and image-owned model permissions)"

set +e
docker run --rm --gpus all \
  -v "$repo_root:/workspace" \
  -v "$eval2_data_root:/workspace/data/evaluation2:ro" \
  -v "$omr_host:$omr_container:ro" \
  -w /workspace \
  -e HOME=/tmp \
  -e XDG_CACHE_HOME=/tmp/.cache \
  -e TORCHINDUCTOR_CACHE_DIR=/tmp/torchinductor \
  -e TRITON_CACHE_DIR=/tmp/triton \
  -e PYTHONPATH=/workspace \
  -e "OMR_DLN_MODEL_PATH=$omr_container" \
  "$image_id" \
  /opt/venv_pipeline/bin/python \
  experiments/issue372/run_production_full68_validation.py \
  --project-root /workspace \
  --output "$container_output" \
  --source-commit "$commit" \
  --counterfactual-report "/workspace/${counterfactual#"$repo_root"/}" \
  --reference-replay "/workspace/${reference#"$repo_root"/}"
status=$?
set -e

# The canonical runtime runs as root because image-owned model artifacts are
# root-readable. Return retained validation artifacts to the host operator even
# when the validation command itself fails.
if [[ -e "$output" ]]; then
  docker run --rm \
    -v "$repo_root:/workspace" \
    "$image_id" \
    chmod -R a+rwX "$container_output" >/dev/null 2>&1 || true
fi

exit "$status"
