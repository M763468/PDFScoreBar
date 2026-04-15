#!/bin/bash
set -e

# Modify the script to skip_existing=False to force native generation
if grep -q "skip_existing=True" experiments/issue53_probe_rescue/evaluate_full_rescue_v1.py; then
    sed -i 's/skip_existing=True/skip_existing=False/g' experiments/issue53_probe_rescue/evaluate_full_rescue_v1.py
fi

# Clean previous runs
rm -rf logs/issue53_full_eval_rescue_v1

# Run the native evaluation
PYTHONPATH=. .venv_cnn_classifier/bin/python experiments/issue53_probe_rescue/evaluate_full_rescue_v1.py > /dev/null 2>&1

# Run global evaluation and check output
OUTPUT=$(PYTHONPATH=. .venv_cnn_classifier/bin/python tools/re_evaluate_global.py --config logs/issue53_full_eval_rescue_v1/eval_config.yaml)

# Check if FP is 0 and FN is 1
if echo "$OUTPUT" | grep "GLOBAL TOTAL" | grep -q "3580.*0.*1.*1.*0"; then
    echo "Good!"
    # cleanup before exit
    git checkout -- experiments/issue53_probe_rescue/evaluate_full_rescue_v1.py || true
    exit 0
else
    echo "Bad!"
    git checkout -- experiments/issue53_probe_rescue/evaluate_full_rescue_v1.py || true
    exit 1
fi
