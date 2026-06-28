# Temporary #221 v9/v9b mask-and-repair probe

This file and the following scripts are temporary experiment scaffolding for Issue #221:

```text
tools/issue221/v9_mask_repair_probe.py
tools/issue221/v9b_rapidocr_eval_mask_repair.py
```

They are intended to be removed by a cleanup commit after the diagnostic is complete.

## Purpose

The previous #221 analysis suggests that the remaining MMR digit failures are primarily caused before OCR:

- staff lines overlap digit strokes,
- rest-count horizontal bars remain connected to digits,
- neighboring boxed numbers or vertical marks can leak into the crop,
- broad OCR fallback then reads unstable values such as `2`, `31`, `34`, or `7`.

The v9 diagnostic tests a preprocessing hypothesis:

```text
white-mask selected interfering elements
then dilate remaining black foreground to repair gaps introduced by the mask
```

v9 only generates transformed images and proxy metrics. v9b evaluates those transformed images with the production-relevant RapidOCR path:

- `rapidocr_onnxruntime.RapidOCR`
- `src.measure_numbering.mmr.MMROCREngine.select_best_candidate()`

This is not a production patch. It is a bounded diagnostic to decide whether a follow-up issue about staff-line-aware / symbol-aware digit isolation is justified.

## Run

Run inside the maintained pipeline container. The host `python3` environment is not sufficient because RapidOCR is installed in the pipeline virtual environment.

From the host working tree that contains the previous ignored #221 logs:

```bash
cd /home/masaki_muramatsu/ws_PDFScoreBar

git fetch origin --prune
git checkout investigate/issue221-component-ocr-residuals
git pull --ff-only origin investigate/issue221-component-ocr-residuals

docker start pdfscore_pipeline_pytest_dev >/dev/null
```

Run v9 and v9b together:

```bash
docker exec -w /workspace \
  -e PYTHONPATH=/workspace \
  pdfscore_pipeline_pytest_dev \
  bash -lc '
set -euo pipefail
PY=/opt/venv_pipeline/bin/python

$PY - <<'"'"'PYCHK'"'"'
import sys
print("python:", sys.executable)
from rapidocr_onnxruntime import RapidOCR
from src.measure_numbering.mmr import MMROCREngine
engine = MMROCREngine(ocr_engine=RapidOCR())
print("rapidocr_onnxruntime + MMROCREngine: ok")
PYCHK

$PY tools/issue221/v9_mask_repair_probe.py \
  --input-root logs/issue221_component_ocr \
  --output-dir logs/issue221_component_ocr/v9_mask_repair_probe \
  --skip-ocr

$PY tools/issue221/v9b_rapidocr_eval_mask_repair.py \
  --v9-dir logs/issue221_component_ocr/v9_mask_repair_probe \
  --output-dir logs/issue221_component_ocr/v9b_rapidocr_mask_repair_eval

ls -lh \
  logs/issue221_component_ocr/issue221_mask_repair_probe_v9_pack.zip \
  logs/issue221_component_ocr/issue221_mask_repair_rapidocr_v9b_pack.zip
'
```

Optional debug cap:

```bash
docker exec -w /workspace \
  -e PYTHONPATH=/workspace \
  pdfscore_pipeline_pytest_dev \
  bash -lc '
set -euo pipefail
PY=/opt/venv_pipeline/bin/python

$PY tools/issue221/v9b_rapidocr_eval_mask_repair.py \
  --v9-dir logs/issue221_component_ocr/v9_mask_repair_probe \
  --output-dir logs/issue221_component_ocr/v9b_rapidocr_mask_repair_eval_debug \
  --max-rows 60
'
```

## Output

v9 writes:

```text
logs/issue221_component_ocr/v9_mask_repair_probe/summary.json
logs/issue221_component_ocr/v9_mask_repair_probe/decision.md
logs/issue221_component_ocr/v9_mask_repair_probe/input_inventory.json
logs/issue221_component_ocr/v9_mask_repair_probe/selected_manifest.csv
logs/issue221_component_ocr/v9_mask_repair_probe/variant_rows.csv
logs/issue221_component_ocr/v9_mask_repair_probe/review_pack/
logs/issue221_component_ocr/issue221_mask_repair_probe_v9_pack.zip
```

v9b writes:

```text
logs/issue221_component_ocr/v9b_rapidocr_mask_repair_eval/summary.json
logs/issue221_component_ocr/v9b_rapidocr_mask_repair_eval/decision.md
logs/issue221_component_ocr/v9b_rapidocr_mask_repair_eval/ocr_rows.csv
logs/issue221_component_ocr/issue221_mask_repair_rapidocr_v9b_pack.zip
```

Share both zips if possible, but the v9b zip is the primary result for judging OCR impact:

```text
logs/issue221_component_ocr/issue221_mask_repair_probe_v9_pack.zip
logs/issue221_component_ocr/issue221_mask_repair_rapidocr_v9b_pack.zip
```

## What to inspect

The diagnostic compares these element-level mask variants:

```text
baseline_binary
mask_horizontal_dilate1
mask_horizontal_dilate2
mask_vertical_dilate1
mask_edge_components_dilate1
mask_horizontal_vertical_dilate1
mask_horizontal_edge_dilate1
mask_horizontal_vertical_edge_dilate1
mask_horizontal_vertical_edge_dilate2
```

v9b evaluates each variant in two input modes:

```text
direct
production_standard
```

Interpretation should focus on RapidOCR first:

- Does horizontal masking improve page_004 without destroying the digit 3?
- Does edge-component masking reduce page_001 boxed-number leakage, or does it erase too much?
- Does vertical masking help page_009, or does it erase part of the digit?
- Does dilation repair holes, or does it reconnect the digit with neighboring symbols?
- Does any variant produce RapidOCR residual exact hits while avoiding residual wrong outputs and global risky outputs?
- If OCR remains empty, inspect `raw_repr_head`, `ocr_result_repr_head`, `raw_text_count`, and `extraction_suspect` before treating the run as a negative result.

A candidate-like result in v9b is still not a production candidate. It only means the preprocessing deserves a follow-up issue for production wiring and full 68-page MMR evaluation.

## Constraints

Do not commit logs or zip artifacts.
Do not add dependencies.
Do not modify production code.
Do not add page-specific or key-specific special cases.
Do not add `31 -> 3` mapping.
