#!/bin/bash
set -e

# Phase 5b.1 - homr Recall Expansion
# Experiment: Vary barline-min-height-factor to recover short missing barlines.

# Constants
CONTAINER="homr_eval_gpu"
HOMR_DIR="/workspace/external/homr"
EVALUATOR="/workspace/src/homr_eval_scripts/homr_evaluator.py"
OUTPUT_ROOT_BASE="/workspace/logs/phase5b_homr_recall"

# Pages and GTMaps
# Format: stem:/path/to/gt.json
PAGES=(
  "page_3:/workspace/data/evaluation/annotations/page_003/boxes_sorted.json"
  "page_10:/workspace/data/training/annotations/page_010/fn_only.json"
  "page_15:/workspace/data/training/annotations/page_015/fn_only.json"
  "page_001:/workspace/data/evaluation2/annotations/Va_Prokofiev_Symphony1/page_001/fn_only.json"
  "page_004:/workspace/data/evaluation2/annotations/Va_Prokofiev_Symphony1/page_004/fn_only.json"
)

# Image Paths corresponding to the stems (hardcoded map for simplicity)
declare -A IMG_MAP
IMG_MAP["page_3"]="/workspace/data/evaluation/images/page_3.png"
IMG_MAP["page_10"]="/workspace/data/training/images/page_10.png"
IMG_MAP["page_15"]="/workspace/data/training/images/page_15.png"
IMG_MAP["page_001"]="/workspace/data/evaluation2/images/Va_Prokofiev_Symphony1/page_001.png"
IMG_MAP["page_004"]="/workspace/data/evaluation2/images/Va_Prokofiev_Symphony1/page_004.png"

# Factors to test
FACTORS=("1.0" "0.8" "0.6")

echo "Starting Phase 5b.1 homr Recall Sweep..."

for FACTOR in "${FACTORS[@]}"; do
    RUN_ID="homr_factor_${FACTOR//./p}"
    echo "--------------------------------------------------"
    echo "Running with barline-min-height-factor = $FACTOR (RunID: $RUN_ID)"
    
    # Construct arguments
    IMG_ARGS=""
    GT_ARGS=""
    
    for PAIR in "${PAGES[@]}"; do
        STEM="${PAIR%%:*}"
        GT_PATH="${PAIR#*:}"
        IMG_PATH="${IMG_MAP[$STEM]}"
        
        IMG_ARGS="$IMG_ARGS $IMG_PATH"
        GT_ARGS="$GT_ARGS --ground-truth $STEM:$GT_PATH"
    done
    
    echo "DEBUG: IMG_ARGS='$IMG_ARGS'"
    echo "DEBUG: GT_ARGS='$GT_ARGS'"

    # Run Docker Command
    docker exec $CONTAINER bash -c "
        cd $HOMR_DIR && \
        poetry run python $EVALUATOR \
        --images $IMG_ARGS \
        $GT_ARGS \
        --output-root $OUTPUT_ROOT_BASE \
        --force-run-id $RUN_ID \
        --barline-min-height-factor $FACTOR \
        --barline-max-width-factor 1.0
    "
    
    echo "Run $RUN_ID complete."
done

echo "All runs complete. Check logs in logs/phase5b_homr_recall/ inside the container (mapped to host logs/phase5b_homr_recall/)."
