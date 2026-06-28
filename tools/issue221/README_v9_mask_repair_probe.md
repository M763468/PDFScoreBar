# Temporary #221 v9/v9b/v10/v10b mask-and-repair probes

This file and the following scripts are temporary experiment scaffolding for Issue #221:

```text
tools/issue221/v9_mask_repair_probe.py
tools/issue221/v9b_rapidocr_eval_mask_repair.py
tools/issue221/v10_windowed_rapidocr_eval.py
tools/issue221/v10b_rescore_windowed_results.py
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

v10 then tests whether restricting the horizontal OCR window can suppress edge/neighbor contamination after v9 preprocessing:

- center-window restriction,
- right-edge trimming,
- left/right edge trimming.

v10b does not run OCR. It re-scores the existing v10 `ocr_rows.csv` and separates the original v10 proxy-risk metric from additional production-review indicators.

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

Run v10b only against an existing completed v10 output:

```bash
docker exec -w /workspace \
  -e PYTHONPATH=/workspace \
  pdfscore_pipeline_pytest_dev \
  bash -lc '
set -euo pipefail
PY=/opt/venv_pipeline/bin/python

$PY tools/issue221/v10b_rescore_windowed_results.py \
  --v10-dir logs/issue221_component_ocr/v10_windowed_rapidocr_eval \
  --output-dir logs/issue221_component_ocr/v10b_windowed_result_rescore

ls -lh \
  logs/issue221_component_ocr/issue221_windowed_rapidocr_v10_pack.zip \
  logs/issue221_component_ocr/issue221_windowed_rescore_v10b_pack.zip
'
```

Run v9, v9b, v10, and v10b together from scratch:

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

$PY tools/issue221/v10_windowed_rapidocr_eval.py \
  --v9-dir logs/issue221_component_ocr/v9_mask_repair_probe \
  --output-dir logs/issue221_component_ocr/v10_windowed_rapidocr_eval

$PY tools/issue221/v10b_rescore_windowed_results.py \
  --v10-dir logs/issue221_component_ocr/v10_windowed_rapidocr_eval \
  --output-dir logs/issue221_component_ocr/v10b_windowed_result_rescore

ls -lh \
  logs/issue221_component_ocr/issue221_mask_repair_probe_v9_pack.zip \
  logs/issue221_component_ocr/issue221_mask_repair_rapidocr_v9b_pack.zip \
  logs/issue221_component_ocr/issue221_windowed_rapidocr_v10_pack.zip \
  logs/issue221_component_ocr/issue221_windowed_rescore_v10b_pack.zip
'
```

Optional v10 debug cap:

```bash
docker exec -w /workspace \
  -e PYTHONPATH=/workspace \
  pdfscore_pipeline_pytest_dev \
  bash -lc '
set -euo pipefail
PY=/opt/venv_pipeline/bin/python

$PY tools/issue221/v10_windowed_rapidocr_eval.py \
  --v9-dir logs/issue221_component_ocr/v9_mask_repair_probe \
  --output-dir logs/issue221_component_ocr/v10_windowed_rapidocr_eval_debug \
  --max-rows 60

$PY tools/issue221/v10b_rescore_windowed_results.py \
  --v10-dir logs/issue221_component_ocr/v10_windowed_rapidocr_eval_debug \
  --output-dir logs/issue221_component_ocr/v10b_windowed_result_rescore_debug
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

v10 writes:

```text
logs/issue221_component_ocr/v10_windowed_rapidocr_eval/summary.json
logs/issue221_component_ocr/v10_windowed_rapidocr_eval/decision.md
logs/issue221_component_ocr/v10_windowed_rapidocr_eval/ocr_rows.csv
logs/issue221_component_ocr/v10_windowed_rapidocr_eval/parsed_rows.csv
logs/issue221_component_ocr/v10_windowed_rapidocr_eval/candidate_rows.csv
logs/issue221_component_ocr/v10_windowed_rapidocr_eval/review_windows/
logs/issue221_component_ocr/issue221_windowed_rapidocr_v10_pack.zip
```

v10b writes:

```text
logs/issue221_component_ocr/v10b_windowed_result_rescore/summary.json
logs/issue221_component_ocr/v10b_windowed_result_rescore/decision.md
logs/issue221_component_ocr/v10b_windowed_result_rescore/scope_summary.csv
logs/issue221_component_ocr/v10b_windowed_result_rescore/candidate_like_v10_scopes.csv
logs/issue221_component_ocr/v10b_windowed_result_rescore/candidate_like_strict_scopes.csv
logs/issue221_component_ocr/issue221_windowed_rescore_v10b_pack.zip
```

Share these zips if possible:

```text
logs/issue221_component_ocr/issue221_mask_repair_probe_v9_pack.zip
logs/issue221_component_ocr/issue221_mask_repair_rapidocr_v9b_pack.zip
logs/issue221_component_ocr/issue221_windowed_rapidocr_v10_pack.zip
logs/issue221_component_ocr/issue221_windowed_rescore_v10b_pack.zip
```

## What to inspect

v9 compares these element-level mask variants:

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

v10 evaluates a selected subset of variants across these horizontal windows:

```text
full
center50
center60
center70
center80
trim_right10
trim_right15
trim_right20
trim_lr10
trim_lr15
```

v10b separates these metrics:

```text
global_v10_risky_rows      # original v10 proxy: parsed number in {2, 3, 4}
global_parsed_rows         # any selected number in global rows
global_parsed_ge2_rows     # selected number >= 2 in global rows
candidate_like_v10         # exact residual recovery + no residual wrong + no global_v10_risky
candidate_like_strict      # exact residual recovery + no residual wrong + no global parsed >= 2
```

Interpretation should focus on RapidOCR first:

- Does horizontal masking improve page_004 without destroying the digit 3?
- Does right-edge trimming or center-window restriction reduce page_001 boxed-number leakage?
- Does right-edge trimming or center-window restriction reduce page_009 `31`-like readings?
- Does windowing merely remove wrong readings, or does it also remove the expected digit?
- Does any variant/window/mode scope produce exact residual hits while avoiding residual wrong outputs and global numeric outputs?
- If `candidate_like_v10` exists but `candidate_like_strict` is empty, treat the scope as diagnostic evidence only.

A candidate-like result in v10/v10b is still not a production candidate. It only means the geometry condition deserves a follow-up issue for production wiring and full 68-page MMR evaluation.

## Constraints

Do not commit logs or zip artifacts.
Do not add dependencies.
Do not modify production code.
Do not add page-specific or key-specific special cases.
Do not add `31 -> 3` mapping.
