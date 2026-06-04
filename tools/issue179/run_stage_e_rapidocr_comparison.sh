#!/usr/bin/env bash
set -Eeuo pipefail

usage() {
  cat <<'EOF'
Run Issue #179 default-vs-CUDA RapidOCR Stage E comparison and package report artifacts.

Usage:
  tools/issue179/run_stage_e_rapidocr_comparison.sh [options]

Options:
  --pages N                 Number of non-excluded Stage E inventory records to compare (default: 10)
  --repetitions N           Repetitions per mode (default: 3)
  --start-index N           Zero-based start index among non-excluded records (default: 0)
  --output-root PATH        Experiment output root (default: logs/issue179_rapidocr_cuda)
  --inventory PATH          Source Stage E inventory (default: logs/issue36_prep/20260208_bench_inventory.json)
  --exclude PATH            Source Stage E exclude file (default: logs/issue36_prep/excluded_pages_for_gt_prep.json)
  --config PATH             Stage E config (default: configs/issue120_stage_e_full_pipeline.yaml)
  --docker-image IMAGE      Docker image (default: pdfscore_pipeline_gpu)
  --sample-interval SEC     Resource sampling interval seconds (default: 1.0)
  --skip-eval               Skip subset detector contract evaluation after each run
  -h, --help                Show this help

Outputs:
  <output-root>/experiment_<timestamp>.log
  <output-root>/comparison_<pages>page.json
  <output-root>/comparison_<pages>page.md
  <output-root>/issue179_rapidocr_cuda_<timestamp>.tar.gz

The tar.gz bundle is intended for issue/PR reporting. It includes summaries and
provider/runtime/resource artifacts, not raw per-run logs.
EOF
}

PAGES=10
REPETITIONS=3
START_INDEX=0
OUTPUT_ROOT="logs/issue179_rapidocr_cuda"
INVENTORY="logs/issue36_prep/20260208_bench_inventory.json"
EXCLUDE="logs/issue36_prep/excluded_pages_for_gt_prep.json"
CONFIG="configs/issue120_stage_e_full_pipeline.yaml"
DOCKER_IMAGE="pdfscore_pipeline_gpu"
SAMPLE_INTERVAL="1.0"
SKIP_EVAL=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --pages) PAGES="$2"; shift 2 ;;
    --repetitions) REPETITIONS="$2"; shift 2 ;;
    --start-index) START_INDEX="$2"; shift 2 ;;
    --output-root) OUTPUT_ROOT="$2"; shift 2 ;;
    --inventory) INVENTORY="$2"; shift 2 ;;
    --exclude) EXCLUDE="$2"; shift 2 ;;
    --config) CONFIG="$2"; shift 2 ;;
    --docker-image) DOCKER_IMAGE="$2"; shift 2 ;;
    --sample-interval) SAMPLE_INTERVAL="$2"; shift 2 ;;
    --skip-eval) SKIP_EVAL=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [[ ! -d .git || ! -f pyproject.toml ]]; then
  echo "ERROR: run from repository root." >&2
  exit 1
fi

mkdir -p "$OUTPUT_ROOT"
TIMESTAMP="$(date +%Y%m%dT%H%M%S%Z)"
LOG_FILE="$OUTPUT_ROOT/experiment_${TIMESTAMP}.log"

exec > >(tee -a "$LOG_FILE") 2>&1

RUN_MANIFEST="$OUTPUT_ROOT/experiment_${TIMESTAMP}.manifest.json"
RUNS_TSV="$OUTPUT_ROOT/experiment_${TIMESTAMP}.runs.tsv"
SUBSET_DIR="$OUTPUT_ROOT/subsets"
SUBSET_INVENTORY="$SUBSET_DIR/inventory_${PAGES}page_start${START_INDEX}.json"
SUBSET_EXCLUDE="$SUBSET_DIR/exclude_${PAGES}page_start${START_INDEX}.json"
SUBSET_SUMMARY="$SUBSET_DIR/summary_${PAGES}page_start${START_INDEX}.json"
COMPARISON_JSON="$OUTPUT_ROOT/comparison_${PAGES}page.json"
COMPARISON_MD="$OUTPUT_ROOT/comparison_${PAGES}page.md"
BUNDLE_DIR="$OUTPUT_ROOT/share/issue179_rapidocr_cuda_${TIMESTAMP}"
BUNDLE_TGZ="$OUTPUT_ROOT/issue179_rapidocr_cuda_${TIMESTAMP}.tar.gz"

RUN_LABELS=()
RUN_ROOTS=()

log_section() {
  echo
  echo "==== $* ===="
}

require_file() {
  local path="$1"
  if [[ ! -f "$path" ]]; then
    echo "ERROR: required file not found: $path" >&2
    exit 1
  fi
}

write_manifest() {
  : > "$RUNS_TSV"
  for idx in "${!RUN_LABELS[@]}"; do
    printf '%s\t%s\n' "${RUN_LABELS[$idx]}" "${RUN_ROOTS[$idx]}" >> "$RUNS_TSV"
  done

  ISSUE179_TIMESTAMP="$TIMESTAMP" \
  ISSUE179_PAGES="$PAGES" \
  ISSUE179_REPETITIONS="$REPETITIONS" \
  ISSUE179_START_INDEX="$START_INDEX" \
  ISSUE179_OUTPUT_ROOT="$OUTPUT_ROOT" \
  ISSUE179_INVENTORY="$INVENTORY" \
  ISSUE179_EXCLUDE="$EXCLUDE" \
  ISSUE179_SUBSET_INVENTORY="$SUBSET_INVENTORY" \
  ISSUE179_SUBSET_EXCLUDE="$SUBSET_EXCLUDE" \
  ISSUE179_SUBSET_SUMMARY="$SUBSET_SUMMARY" \
  ISSUE179_CONFIG="$CONFIG" \
  ISSUE179_DOCKER_IMAGE="$DOCKER_IMAGE" \
  ISSUE179_SAMPLE_INTERVAL="$SAMPLE_INTERVAL" \
  ISSUE179_SKIP_EVAL="$SKIP_EVAL" \
  ISSUE179_COMPARISON_JSON="$COMPARISON_JSON" \
  ISSUE179_COMPARISON_MD="$COMPARISON_MD" \
  ISSUE179_LOG_FILE="$LOG_FILE" \
  ISSUE179_BUNDLE_TGZ="$BUNDLE_TGZ" \
  PYTHONPATH=. python3 - "$RUN_MANIFEST" "$RUNS_TSV" <<'PY'
import json
import os
import sys
from pathlib import Path

runs = []
runs_tsv = Path(sys.argv[2])
if runs_tsv.exists():
    for line in runs_tsv.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        label, root = line.split("\t", 1)
        runs.append({"label": label, "root": root})

manifest = {
    "schema_version": "tools.issue179.rapidocr_comparison_manifest.v1",
    "timestamp": os.environ["ISSUE179_TIMESTAMP"],
    "pages": int(os.environ["ISSUE179_PAGES"]),
    "repetitions": int(os.environ["ISSUE179_REPETITIONS"]),
    "start_index": int(os.environ["ISSUE179_START_INDEX"]),
    "output_root": os.environ["ISSUE179_OUTPUT_ROOT"],
    "inventory": os.environ["ISSUE179_INVENTORY"],
    "exclude": os.environ["ISSUE179_EXCLUDE"],
    "subset_inventory": os.environ["ISSUE179_SUBSET_INVENTORY"],
    "subset_exclude": os.environ["ISSUE179_SUBSET_EXCLUDE"],
    "subset_summary": os.environ["ISSUE179_SUBSET_SUMMARY"],
    "config": os.environ["ISSUE179_CONFIG"],
    "docker_image": os.environ["ISSUE179_DOCKER_IMAGE"],
    "sample_interval_sec": os.environ["ISSUE179_SAMPLE_INTERVAL"],
    "skip_eval": bool(int(os.environ["ISSUE179_SKIP_EVAL"])),
    "comparison_json": os.environ["ISSUE179_COMPARISON_JSON"],
    "comparison_md": os.environ["ISSUE179_COMPARISON_MD"],
    "log_file": os.environ["ISSUE179_LOG_FILE"],
    "bundle_tgz": os.environ["ISSUE179_BUNDLE_TGZ"],
    "runs": runs,
}
Path(sys.argv[1]).write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
PY
}

run_stage_e() {
  local mode="$1"
  local rep="$2"
  local run_label="${mode}_${PAGES}page_run${rep}"
  local run_root="$OUTPUT_ROOT/$run_label"

  log_section "Run $run_label"
  RUN_LABELS+=("$run_label")
  RUN_ROOTS+=("$run_root")

  local env_args=(-e PYTHONPATH=/workspace -e PDFSCORE_HOMR_VERBOSE_INTERNAL_LOGS -e PDFSCORE_SR_TILE_LOGS)
  if [[ "$mode" == "cuda" ]]; then
    env_args+=(-e PDFSCORE_RAPIDOCR_USE_CUDA=1)
  else
    env_args+=(-e PDFSCORE_RAPIDOCR_USE_CUDA)
  fi

  docker run --rm --gpus all \
    -v "$PWD":/workspace \
    -w /workspace \
    "${env_args[@]}" \
    "$DOCKER_IMAGE" \
    /bin/sh -lc "/opt/venv_pipeline/bin/python tools/issue179/run_stage_e_rapidocr_cuda_experiment.py \
      --config '$CONFIG' \
      --output-root '$run_root' \
      --inventory '$SUBSET_INVENTORY' \
      --exclude '$SUBSET_EXCLUDE' \
      --expected-pages '$PAGES' \
      --resource-sample-interval-sec '$SAMPLE_INTERVAL'; \
      status=\$?; chmod -R a+rwX '$run_root' 2>/dev/null || true; exit \$status"

  if [[ "$SKIP_EVAL" != "1" ]]; then
    log_section "Subset detector contract $run_label"
    PYTHONPATH=. python3 tools/issue120/eval_stage_e_contract.py \
      --output-root "$run_root" \
      --eval-inputs-dir "$run_root/stage_e_full_pipeline/eval_inputs_smoke" \
      --eval-output-dir "$run_root/stage_e_full_pipeline/eval_detector_smoke" \
      --gt-root data/evaluation2/annotations \
      --score-threshold 0.1 \
      --xdist-threshold 12.0 \
      --page-limit "$PAGES" \
      --allow-partial \
      --allow-target-mismatch
  fi
}

copy_if_exists() {
  local src="$1"
  local dst="$2"
  if [[ -e "$src" ]]; then
    mkdir -p "$(dirname "$dst")"
    cp -a "$src" "$dst"
  fi
}

package_bundle() {
  log_section "Package report bundle"
  rm -rf "$BUNDLE_DIR"
  mkdir -p "$BUNDLE_DIR/runs"

  copy_if_exists "$LOG_FILE" "$BUNDLE_DIR/$(basename "$LOG_FILE")"
  copy_if_exists "$RUN_MANIFEST" "$BUNDLE_DIR/$(basename "$RUN_MANIFEST")"
  copy_if_exists "$COMPARISON_JSON" "$BUNDLE_DIR/$(basename "$COMPARISON_JSON")"
  copy_if_exists "$COMPARISON_MD" "$BUNDLE_DIR/$(basename "$COMPARISON_MD")"
  copy_if_exists "$SUBSET_SUMMARY" "$BUNDLE_DIR/$(basename "$SUBSET_SUMMARY")"

  for idx in "${!RUN_LABELS[@]}"; do
    local label="${RUN_LABELS[$idx]}"
    local root="${RUN_ROOTS[$idx]}/stage_e_full_pipeline"
    local dst="$BUNDLE_DIR/runs/$label"
    mkdir -p "$dst"
    copy_if_exists "$root/rapidocr_provider_summary.json" "$dst/rapidocr_provider_summary.json"
    copy_if_exists "$root/stage_e_runtime_summary.json" "$dst/stage_e_runtime_summary.json"
    copy_if_exists "$root/stage_e_resource_samples.summary.json" "$dst/stage_e_resource_samples.summary.json"
    copy_if_exists "$root/pipeline_stdout_stderr.summary.json" "$dst/pipeline_stdout_stderr.summary.json"
    copy_if_exists "$root/eval_detector_smoke/evaluation_contract.json" "$dst/evaluation_contract.json"
  done

  tar -czf "$BUNDLE_TGZ" -C "$(dirname "$BUNDLE_DIR")" "$(basename "$BUNDLE_DIR")"
  echo "Bundle: $BUNDLE_TGZ"
}

log_section "Preflight"
echo "timestamp=$TIMESTAMP"
echo "output_root=$OUTPUT_ROOT"
echo "pages=$PAGES repetitions=$REPETITIONS start_index=$START_INDEX"
echo "docker_image=$DOCKER_IMAGE"
echo "log_file=$LOG_FILE"
require_file "$INVENTORY"
require_file "$EXCLUDE"
require_file "$CONFIG"
require_file "tools/issue179/run_stage_e_rapidocr_cuda_experiment.py"
require_file "tools/issue179/make_stage_e_inventory_subset.py"
require_file "tools/issue179/summarize_stage_e_rapidocr_runs.py"
require_file "tools/issue120/eval_stage_e_contract.py"

docker image inspect "$DOCKER_IMAGE" >/dev/null

log_section "Create ${PAGES}-page subset"
PYTHONPATH=. python3 tools/issue179/make_stage_e_inventory_subset.py \
  --inventory "$INVENTORY" \
  --exclude "$EXCLUDE" \
  --count "$PAGES" \
  --start-index "$START_INDEX" \
  --output-inventory "$SUBSET_INVENTORY" \
  --output-exclude "$SUBSET_EXCLUDE" \
  --summary-out "$SUBSET_SUMMARY"

for i in $(seq 1 "$REPETITIONS"); do
  run_stage_e default "$i"
  run_stage_e cuda "$i"
  write_manifest
done

log_section "Summarize runs"
SUMMARY_ARGS=()
for idx in "${!RUN_LABELS[@]}"; do
  SUMMARY_ARGS+=(--run "${RUN_LABELS[$idx]}:${RUN_ROOTS[$idx]}")
done
PYTHONPATH=. python3 tools/issue179/summarize_stage_e_rapidocr_runs.py \
  "${SUMMARY_ARGS[@]}" \
  --output-json "$COMPARISON_JSON" \
  --output-md "$COMPARISON_MD"

write_manifest
package_bundle

log_section "Done"
echo "Main log:     $LOG_FILE"
echo "Summary MD:   $COMPARISON_MD"
echo "Summary JSON: $COMPARISON_JSON"
echo "Manifest:     $RUN_MANIFEST"
echo "Bundle:       $BUNDLE_TGZ"
