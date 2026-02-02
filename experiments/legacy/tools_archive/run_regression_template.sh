#!/usr/bin/env bash
# Regression harness template for running homr and oemer on a multi-page suite.
#
# Usage:
#   1. Copy this script to a working location (or symlink it) and adjust the
#      IMAGES_* arrays below to match the PDF render set you want to scan.
#   2. Optionally export RUN_TAG, HOMR_OUTPUT_ROOT, OEMER_OUTPUT_ROOT, or
#      OEMER_IMAGE_DIR before invoking the script.
#   3. Run: ./tools/run_regression_template.sh
#      Additional arguments are forwarded to both evaluators.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Rendered score images with ground-truth annotations.
# Format: "<image_path>|<stem>:<ground_truth_json>"
# 現状 `data/evaluation/images` で楽譜を含むのは page_003 のみ。追加 GT は
# `data/training/annotations/` 系の資材が整った時点で追記する。
IMAGES_WITH_GT=(
  # Symlink `page_003.png` resolves to `page_3.png`, so ground-truth stemは `page_3` を指定する。
  "data/evaluation/images/page_003.png|page_3:data/evaluation/annotations/page_003/boxes_sorted.json"
)

# Optional images without GT; homr will emit overlays only.
IMAGES_WITHOUT_GT=(
  # "data/evaluation/images/page_005.png"
)

# Target pages for the oemer runner (indexes follow page_* numbering).
# page_003 のみを評価。追加 GT が揃った際に延伸する。
OEMER_TARGET_PAGES=(3)

# Override when using the higher resolution workbench renders:
# export OEMER_IMAGE_OVERRIDE_PAGE_3="data/workbench/pdf_render/20251007T011612JST_gpu/dpi200_area/page_003.png"
# export OEMER_IMAGE_OVERRIDE_PAGE_4="..."

RUN_TAG="${RUN_TAG:-regression_smoke}"
HOMR_OUTPUT_ROOT="${HOMR_OUTPUT_ROOT:-logs/homr_eval}"
OEMER_OUTPUT_ROOT="${OEMER_OUTPUT_ROOT:-logs/oemer_eval_regression}"

# ---------------------------------------------------------------------------
# homr evaluator
# ---------------------------------------------------------------------------

homr_images=()
homr_gt_args=()

for entry in "${IMAGES_WITH_GT[@]}"; do
  IFS="|" read -r image gt_spec <<<"${entry}"
  homr_images+=("${image}")
  homr_gt_args+=("--ground-truth" "${gt_spec}")
done

for image in "${IMAGES_WITHOUT_GT[@]}"; do
  homr_images+=("${image}")
done

if ((${#homr_images[@]} > 0)); then
  echo "[homr] Evaluating ${#homr_images[@]} image(s) → ${HOMR_OUTPUT_ROOT}"
  "${PYTHON_BIN}" src/homr/homr_evaluator.py \
    --images "${homr_images[@]}" \
    --output-root "${HOMR_OUTPUT_ROOT}" \
    --run-tag "${RUN_TAG}" \
    "${homr_gt_args[@]}" \
    "$@"
else
  echo "[homr] Skipping (no images configured)"
fi

# ---------------------------------------------------------------------------
# oemer evaluator
# ---------------------------------------------------------------------------

if ((${#IMAGES_WITH_GT[@]} > 0)); then
  export OEMER_OUTPUT_ROOT="${OEMER_OUTPUT_ROOT}"
  export OEMER_TARGET_PAGES="$(IFS=,; echo "${OEMER_TARGET_PAGES[*]}")"
  echo "[oemer] Evaluating pages ${OEMER_TARGET_PAGES[*]} → ${OEMER_OUTPUT_ROOT}"
  "${PYTHON_BIN}" src/archive/oemer/run_omerer.py "$@"
else
  echo "[oemer] Skipping (no GT-backed pages configured)"
fi

echo "[regression] Completed homr/oemer passes under run tag '${RUN_TAG}'"
