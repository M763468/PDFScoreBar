#!/bin/bash
# download_deepscores_dense.sh
# Script to download and extract DeepScores V2 Dense dataset.

DATASET_ROOT="/mnt/d/datasets/DeepScoresV2"
mkdir -p "$DATASET_ROOT"
cd "$DATASET_ROOT"

echo "Starting download of DeepScores V2 Dense (approx. 742 MB)..."
wget -c https://zenodo.org/record/4012193/files/ds2_dense.tar.gz

echo "Extracting dataset..."
tar -xzf ds2_dense.tar.gz

echo "Download and extraction complete."
echo "Location: $DATASET_ROOT"
ls -F "$DATASET_ROOT"
