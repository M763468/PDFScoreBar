#!/bin/bash
set -euo pipefail

# Activate the correct virtual environment
source .venv_omr_dln/bin/activate

# Define the kernel heights to test
KERNEL_HEIGHTS=(15 10 5)

# Get the current date for the run group
RUN_GROUP=$(date +%Y%m%d)

echo "Starting OMR-DLN preprocessing parameter sweep..."

for HEIGHT in "${KERNEL_HEIGHTS[@]}"; do
    RUN_ID="${RUN_GROUP}_omr_vc_h${HEIGHT}_w1_bin"
    OUTPUT_DIR="logs/model_experiments/omr_dln/${RUN_ID}"
    
    echo "---"
    echo "Running evaluation for kernel height: ${HEIGHT}"
    echo "Run ID: ${RUN_ID}"
    echo "---"

    python experiments/models/eval_omr_dln.py \
        --image data/evaluation/images/page_3.png \
        --gt data/evaluation/annotations/page_003/boxes_sorted.json \
        --output-dir "${OUTPUT_DIR}" \
        --conf 0.25 \
        --kernel-height ${HEIGHT}

    echo ""
done

echo "Parameter sweep finished."
echo "Results and intermediate images are saved in 'logs/model_experiments/omr_dln/'"
