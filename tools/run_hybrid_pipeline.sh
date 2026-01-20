#!/bin/bash
set -euo pipefail

usage() {
    echo "Usage: $0 --image <path> --run-id <id> [--gt <path>]"
    echo ""
    echo "Orchestrates the Hybrid Barline Detection Pipeline:"
    echo "1. homr Baseline (Standard)"
    echo "2. homr SR (Real-ESRGAN x4)"
    echo "3. OMR-DLN SR (YOLOv8 Measure Detection x4)"
    echo "4. Hybrid Generation (Consensus Logic)"
    exit 1
}

IMAGE_PATH=""
RUN_ID=""
GT_PATH=""

while [[ "$#" -gt 0 ]]; do
    case $1 in
        --image) IMAGE_PATH="$2"; shift ;;
        --run-id) RUN_ID="$2"; shift ;;
        --gt) GT_PATH="$2"; shift ;;
        *) echo "Unknown parameter: $1"; usage ;;
    esac
    shift
done

if [[ -z "$IMAGE_PATH" || -z "$RUN_ID" ]]; then
    usage
fi

# Resolve paths
REPO_ROOT=$(pwd)

# Improved path handling to support symlinks (like data/evaluation2)
if [[ "$IMAGE_PATH" != /* ]]; then
    # Relative path: Assume it is inside the repo
    CONTAINER_IMAGE="/workspace/$IMAGE_PATH"
else
    # Absolute path: Try to relativize
    ABS_IMAGE=$(realpath "$IMAGE_PATH")
    if [[ "$ABS_IMAGE" == "$REPO_ROOT"* ]]; then
        CONTAINER_IMAGE="/workspace${ABS_IMAGE#$REPO_ROOT}"
    else
        # Fallback: Check if it matches the structure even if realpath drifted (symlinks)
        # But for now, just warn and try strictly mapping if possible, or fail.
        # However, for this fix, we primarily trust the relative path provided.
        echo "Error: Absolute path provided matches outside repository or symlink resolution failed."
        echo "Repo: $REPO_ROOT"
        echo "Image: $ABS_IMAGE"
        exit 1
    fi
fi
STEM=$(basename "$IMAGE_PATH" .png)

CONTAINER_GT=""
if [[ -n "$GT_PATH" ]]; then
    ABS_GT=$(realpath "$GT_PATH")
    if [[ "$ABS_GT" != "$REPO_ROOT"* ]]; then
        echo "Error: GT must be inside the repository."
        exit 1
    fi
    CONTAINER_GT="/workspace${ABS_GT#$REPO_ROOT}"
fi

# Define Output Root in Container
OUTPUT_ROOT="/workspace/logs/hybrid_generalization/$RUN_ID"
HOST_OUTPUT_ROOT="logs/hybrid_generalization/$RUN_ID"

echo "=== Running Hybrid Pipeline ==="
echo "Image: $CONTAINER_IMAGE ($STEM)"
echo "Run ID: $RUN_ID"
echo "GT: ${CONTAINER_GT:-(None)}" 
echo "Output: $OUTPUT_ROOT"

# SR evaluation container + interpreter.
# This script assumes `sr_eval_gpu` (or specified container) was built from `Dockerfile.sr_eval` and is running.
CONTAINER_NAME="${CONTAINER_NAME:-sr_eval_gpu}"
CONTAINER_PY="/opt/venv_sr/bin/python"

# Ensure output directory exists on host (mapped to container)
mkdir -p "$HOST_OUTPUT_ROOT"

# 1. homr Baseline
echo ""
echo "--- Step 1: homr Baseline ---"
CMD_BASELINE="$CONTAINER_PY /workspace/src/homr_eval_scripts/homr_evaluator.py \
    --images \"$CONTAINER_IMAGE\" \
    --output-root \"$OUTPUT_ROOT/baseline\" \
    --force-run-id \"$STEM\""

if [[ -n "$CONTAINER_GT" ]]; then
    CMD_BASELINE="$CMD_BASELINE --ground-truth \"$STEM:$CONTAINER_GT\""
fi

echo "Running: $CMD_BASELINE"
docker exec "$CONTAINER_NAME" bash -lc "$CMD_BASELINE"

# 2. homr SR
echo ""
echo "--- Step 2: homr SR ---"
CMD_SR="$CONTAINER_PY /workspace/src/homr_eval_scripts/homr_evaluator.py \
    --images \"$CONTAINER_IMAGE\" \
    --output-root \"$OUTPUT_ROOT/sr\" \
    --force-run-id \"$STEM\" \
    --enable-sr"

if [[ -n "$CONTAINER_GT" ]]; then
    CMD_SR="$CMD_SR --ground-truth \"$STEM:$CONTAINER_GT\""
fi

echo "Running: $CMD_SR"
docker exec "$CONTAINER_NAME" bash -lc "$CMD_SR"

# 3. OMR-DLN SR
echo ""
echo "--- Step 3: OMR-DLN SR ---"
CMD_OMR="$CONTAINER_PY /workspace/experiments/models/eval_omr_dln.py \
    --image \"$CONTAINER_IMAGE\" \
    --output-dir \"$OUTPUT_ROOT/omr_sr\" \
    --enable-sr"

if [[ -n "$CONTAINER_GT" ]]; then
    CMD_OMR="$CMD_OMR --gt \"$CONTAINER_GT\""
fi

echo "Running: $CMD_OMR"
docker exec "$CONTAINER_NAME" bash -lc "$CMD_OMR"

# 4. Generate Hybrid Results
echo ""
echo "--- Step 4: Hybrid Generation ---"

# Locate inputs
# homr_evaluator creates <output_root>/<run_id>/<stem>/<stem>_detections.json
# Here run_id is forced to STEM.
# So: $OUTPUT_ROOT/baseline/$STEM/$STEM/$STEM_detections.json ... wait.
# Let's re-read homr_evaluator logic.
# run_dir = args.output_root / run_id
# image_run_dir = run_dir / stem
# detections_path = image_run_dir / f"{stem}_detections.json"

BASELINE_JSON="$OUTPUT_ROOT/baseline/$STEM/$STEM/${STEM}_detections.json"
SR_JSON="$OUTPUT_ROOT/sr/$STEM/$STEM/${STEM}_detections.json"
OMR_JSON="$OUTPUT_ROOT/omr_sr/predictions.json"
HYBRID_JSON="$OUTPUT_ROOT/hybrid_predictions.json"

CMD_HYBRID="$CONTAINER_PY /workspace/tools/generate_hybrid_results.py \
    --baseline \"$BASELINE_JSON\" \
    --sr \"$SR_JSON\" \
    --omr \"$OMR_JSON\" \
    --output \"$HYBRID_JSON\""

if [[ -n "$CONTAINER_GT" ]]; then
    CMD_HYBRID="$CMD_HYBRID --gt \"$CONTAINER_GT\""
fi

echo "Running: $CMD_HYBRID"
docker exec "$CONTAINER_NAME" bash -lc "$CMD_HYBRID"

echo ""
echo "=== Hybrid Pipeline Completed ==="
echo "Results saved to $HOST_OUTPUT_ROOT/hybrid_predictions.json"
