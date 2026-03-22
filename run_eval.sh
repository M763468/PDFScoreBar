#!/bin/bash
rm -rf logs/full_pipeline_runs/eval2_v9
docker run --rm --gpus all -v $(pwd):/workspace -w /workspace -e PYTHONPATH=/workspace pdfscore_pipeline_gpu bash -c "/opt/venv_pipeline/bin/python tools/run_full_eval2_inprocess.py && /opt/venv_pipeline/bin/python tools/calculate_metrics.py --scored-root logs/full_pipeline_runs/eval2_v9 --gt-root data/evaluation2/annotations" > artifacts/full_eval_fix.log 2>&1
