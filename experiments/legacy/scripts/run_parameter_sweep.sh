#!/bin/bash
set -euo pipefail

# Define the kernel heights to test
KERNEL_HEIGHTS=(50 25 15 10 5 3)

# Get the current date for the run group
RUN_GROUP=$(date +%Y%m%d)

echo "Starting homr preprocessing parameter sweep..."

for HEIGHT in "${KERNEL_HEIGHTS[@]}"; do
    RUN_ID="${RUN_GROUP}_homr_vc_h${HEIGHT}_w1"
    echo "---"
    echo "Running evaluation for kernel height: ${HEIGHT}"
    echo "Run ID: ${RUN_ID}"
    echo "---"

    # It's safer to capture the output and exit code
    set +e # Disable exit on error temporarily
    output=$(docker exec homr_eval_gpu bash -c "cd /workspace/external/homr && poetry run python /workspace/src/homr_eval_scripts/homr_evaluator.py --images /workspace/data/evaluation/images/page_3.png --ground-truth page_3:/workspace/data/evaluation/annotations/page_003/boxes_sorted.json --output-root /workspace/logs/homr_eval --force-run-id \"${RUN_ID}\" --kernel-height ${HEIGHT}" 2>&1)
    exit_code=$?
    set -e # Re-enable exit on error

    echo "$output"

    if [ $exit_code -ne 0 ]; then
        echo "Evaluation failed for kernel height: ${HEIGHT} (Exit code: $exit_code)"
    else
        echo "Evaluation succeeded for kernel height: ${HEIGHT}"
    fi

    echo ""
done

echo "Parameter sweep finished."
echo "Results and intermediate images are saved in 'logs/homr_eval/' with their respective Run IDs."
