# Temporary #221 v9 mask-and-repair probe

This file and `tools/issue221/v9_mask_repair_probe.py` are temporary experiment scaffolding for Issue #221.
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

This is not a production patch. It is a bounded diagnostic to decide whether a follow-up issue about staff-line-aware / symbol-aware digit isolation is justified.

## Run

From the working tree that contains the previous ignored #221 logs:

```bash
cd /home/masaki_muramatsu/ws_PDFScoreBar
git fetch origin --prune
git checkout investigate/issue221-component-ocr-residuals
git pull --ff-only origin investigate/issue221-component-ocr-residuals

PYTHONPATH=. python3 tools/issue221/v9_mask_repair_probe.py \
  --input-root logs/issue221_component_ocr \
  --output-dir logs/issue221_component_ocr/v9_mask_repair_probe
```

If optional Tesseract OCR should be disabled:

```bash
PYTHONPATH=. python3 tools/issue221/v9_mask_repair_probe.py \
  --input-root logs/issue221_component_ocr \
  --output-dir logs/issue221_component_ocr/v9_mask_repair_probe \
  --skip-ocr
```

## Output

The script writes:

```text
logs/issue221_component_ocr/v9_mask_repair_probe/summary.json
logs/issue221_component_ocr/v9_mask_repair_probe/decision.md
logs/issue221_component_ocr/v9_mask_repair_probe/input_inventory.json
logs/issue221_component_ocr/v9_mask_repair_probe/selected_manifest.csv
logs/issue221_component_ocr/v9_mask_repair_probe/variant_rows.csv
logs/issue221_component_ocr/v9_mask_repair_probe/review_pack/
logs/issue221_component_ocr/issue221_mask_repair_probe_v9_pack.zip
```

Share only this zip after running:

```text
logs/issue221_component_ocr/issue221_mask_repair_probe_v9_pack.zip
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

Interpretation should focus on element separation, not only OCR exact hits:

- Does horizontal masking improve page_004 without destroying the digit 3?
- Does edge-component masking reduce page_001 boxed-number leakage?
- Does vertical masking help page_009, or does it erase part of the digit?
- Does dilation repair holes, or does it reconnect the digit with neighboring symbols?
- Does any variant produce residual exact hits while avoiding wrong residual outputs and global risky outputs?

## Constraints

Do not commit logs or zip artifacts.
Do not add dependencies.
Do not modify production code.
Do not add page-specific or key-specific special cases.
Do not add `31 -> 3` mapping.
