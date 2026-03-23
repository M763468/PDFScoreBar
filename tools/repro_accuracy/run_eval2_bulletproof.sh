#!/bin/bash
# run_eval2_bulletproof.sh
# Runs v10 fixed-pipeline specifically on evaluation2 datasets sequentially
DATASETS=(
  "Shostakovich-Festival_Overture_Va"
  "Shostakovich-Sym5-Va"
  "Sibelius-Violin_Concerto-Viola"
  "Va_Prokofiev_Symphony1"
  "Va__Prokofiev_Symphony5"
)

for ds in "${DATASETS[@]}"; do
    echo "Processing $ds..."
    CONFIG="configs/verify_v10_${ds}.yaml"
    # Ensure config exists or generate it
    if [ ! -f "$CONFIG" ]; then
        cp configs/verify_fixed_v10_Shostakovich-Festival_Overture_Va.yaml "$CONFIG"
        sed -i "s/Shostakovich-Festival_Overture_Va/$ds/g" "$CONFIG"
    fi
    ./run_pipeline.sh "$CONFIG"
done
