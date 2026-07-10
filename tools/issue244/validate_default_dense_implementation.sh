#!/usr/bin/env bash
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

make lint

PYTHONPATH=. python3 -m pytest \
  tests/test_issue244_default_dense_detector_route.py \
  tests/test_apply_corrections.py \
  tests/test_apply_corrections_mmr_suppressions.py \
  tests/test_apply_corrections_existing_overrides.py \
  tests/test_corrected_final_output.py \
  tests/test_apply_corrections_final_output.py

python3 tools/issue244/run_default_dense_page001_smoke.py --force
