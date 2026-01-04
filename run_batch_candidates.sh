#!/bin/bash

IMAGE_ROOT="data/evaluation2/images"
SCRIPT="./tools/run_hybrid_pipeline.sh"

# Read into array to handle potential spaces (though unlikely here)
mapfile -t files < <(find "$IMAGE_ROOT" -name "*.png" | sort)

for img_path in "${files[@]}"; do
    subdir=$(basename "$(dirname "$img_path")")
    stem=$(basename "$img_path" .png)
    
    run_id="eval2_${subdir}_${stem}"
    
    echo "---------------------------------------------------"
    echo "Processing $subdir / $stem -> $run_id"
    bash "$SCRIPT" --image "$img_path" --run-id "$run_id"
    
    ret=$?
    if [ $ret -ne 0 ]; then
        echo "Failed processing $img_path with code $ret"
    else
        echo "Success: $run_id"
    fi
done