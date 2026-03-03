#!/bin/bash
OUTPUT_FILE=$1
echo "timestamp,memory.used [MiB],memory.total [MiB],utilization.gpu [%]" > $OUTPUT_FILE
while true; do
    nvidia-smi --query-gpu=timestamp,memory.used,memory.total,utilization.gpu --format=csv,noheader,nounits >> $OUTPUT_FILE
    sleep 1
done
