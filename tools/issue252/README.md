# Issue #252 focused detector and grouped-numbering audit

This directory traces the remaining fresh box-instance mismatch on
`Va_Prokofiev_Symphony1/page_004` and determines whether it changes connector-supported
final numbering.

The investigation conclusion is recorded in:

```text
docs/issue252_prokofiev_detector_conclusion.md
```

## Retained tools

- `probe_boundary.py`: pure report and first-loss helpers.
- `trace_prokofiev_probe_boundary.py`: verifies the fresh contract, reproduces hybrid
  consensus, and traces probe stages.
- `run_grouped_final_numbering_comparison.py`: runs two candidate sets through the
  production CNN, grouping, MMR and final numbering order.
- `audit_grouped_semantic_impact.py`: compares connector-supported grouped results
  without interpreting serialized component count as musical staff count.
- `render_grouped_numbering_overlay.py`: draws the required evidence on the original
  score image.

Rejected candidate-filter mechanisms are not installed in production code or
configuration. The trace tool has one explicit, tool-local
`--experimental-paper-side-context-width-ratio` switch solely to reproduce the
rejected side-context experiment.

## Fresh-input contract

A result described as fresh must report:

```text
mode = fresh_upstream
fresh_upstream_authoritative = true
override_keys = []
```

Historical artifacts may be forensic comparison inputs, but must not replace fresh
runtime candidates or CNN bands.

## 1. Correct probe trace

The probe image and masks must match the production SR coordinate space. Missing masks
must be acknowledged explicitly; they are not silently replaced.

```bash
cd /home/masaki_muramatsu/ws_PDFScoreBar
PYTHON=/home/masaki_muramatsu/ws_PDFScoreBar/.venv_pdf/bin/python

CONTRACT=<verified-fresh-run>/intermediate/detector_input_contract.json
ORIGINAL=data/evaluation2/images/Va_Prokofiev_Symphony1/page_004.png
SR_IMAGE=<verified-fresh-run>/intermediate/<page-004-sr-2x-image>.png
PROBE_STAFF_MASK=<verified-fresh-run>/intermediate/<page-004-sr-staff-mask>.png
CNN_STAFF_MASK=<verified-fresh-run>/intermediate/<page-004-original-coordinate-staff-mask>.png
NUMBERING_STAFF_MASK=<verified-fresh-run>/intermediate/<page-004-numbering-staff-mask>.png

COMMON_ARGS=(
  --input-contract "$CONTRACT"
  --config configs/dense_full_pipeline.yaml
  --image "$ORIGINAL"
  --probe-image "$SR_IMAGE"
  --input-image-scale 2
  --expected-image-sha256 27755b1ece7abd5cf967cd49020279e3688cc7bdd5618b4690ed8e58136065d1
  --fresh-baseline logs/issue245_fresh_upstream_full68_probe/pages/045_vaprokofievsymphony1page004/evaluator/issue245_fresh_upstream_full68_045/page_004/page_004_detections.json
  --current-sr logs/issue244_full_regression/hybrid/production_default_full68/sr/batch/Va_Prokofiev_Symphony1_page_004/Va_Prokofiev_Symphony1_page_004_detections.json
  --current-omr logs/issue244_full_regression/hybrid/production_default_full68/omr_sr/Va_Prokofiev_Symphony1_page_004/predictions.json
  --hybrid logs/issue245_accuracy_first_mixed_route/mixed_hybrid/Va_Prokofiev_Symphony1/page_004_hybrid.json
  --staff-mask "$PROBE_STAFF_MASK"
  --allow-zero-clef-mask
  --score Va_Prokofiev_Symphony1
  --page page_004
  --missing-reference 847 2675 854 2776
  --nearby-reference 847 2490 854 2591
)

rm -rf logs/issue252_probe_default logs/issue252_probe_side_context_1x

PYTHONPATH=. "$PYTHON" tools/issue252/trace_prokofiev_probe_boundary.py \
  "${COMMON_ARGS[@]}" \
  --output-root logs/issue252_probe_default

PYTHONPATH=. "$PYTHON" tools/issue252/trace_prokofiev_probe_boundary.py \
  "${COMMON_ARGS[@]}" \
  --experimental-paper-side-context-width-ratio 1 \
  --output-root logs/issue252_probe_side_context_1x
```

Primary reports:

```text
logs/issue252_probe_default/probe_boundary_report.json
logs/issue252_probe_side_context_1x/probe_boundary_report.json
```

The default and side-context final candidate files are:

```text
logs/issue252_probe_default/suppression_default/final_candidates.json
logs/issue252_probe_side_context_1x/suppression_default/final_candidates.json
```

## 2. Correct production-order grouped comparison

The CNN consumes the SR image and SR-coordinate candidates. `_score_directory`
downscales both to original coordinates before staff-band filtering. Therefore
`--cnn-staff-mask` must already use original/post-downscale coordinates. Numbering
then consumes the original page and may scale its own staff mask. Do not use
`cnn_bands_from` for a result claimed as fresh.

Use the same connector source as the production run. Supply proxy symbol/brace masks
when they are authoritative. If production intentionally uses page-image ink, state
that explicitly with `--allow-page-image-connector-fallback`.

```bash
rm -rf logs/issue252_grouped_final_numbering_comparison

PYTHONPATH=. "$PYTHON" \
  tools/issue252/run_grouped_final_numbering_comparison.py \
  --config configs/dense_full_pipeline.yaml \
  --default-candidates \
    logs/issue252_probe_default/suppression_default/final_candidates.json \
  --candidate-candidates \
    logs/issue252_probe_side_context_1x/suppression_default/final_candidates.json \
  --cnn-image "$SR_IMAGE" \
  --numbering-image "$ORIGINAL" \
  --cnn-staff-mask "$CNN_STAFF_MASK" \
  --numbering-staff-mask "$NUMBERING_STAFF_MASK" \
  --cnn-input-image-scale 2 \
  --allow-page-image-connector-fallback \
  --score-name Va_Prokofiev_Symphony1 \
  --page-number 45 \
  --target-bbox 847 2675 854 2776 \
  --nearby-bbox 847 2490 854 2591 \
  --overlay-crop 650 2300 1100 2920 \
  --output-root logs/issue252_grouped_final_numbering_comparison
```

When proxy masks are the production source, replace the fallback switch with:

```text
--symbol-mask <symbol-mask>
--brace-dot-mask <brace-dot-mask>
```

The runner writes separate base/final and raw/local MMR artifacts:

```text
<route>/numbering/numbering_base.json
<route>/numbering/overrides_mmr_raw.json
<route>/numbering/overrides_mmr_local_page_index.json
<route>/numbering/numbering_final.json
<route>/numbering/numbering_execution_contract.json
<route>/numbering/grouped_numbering_overlay.png
<route>/numbering/grouped_numbering_overlay.json
```

Primary comparison:

```text
logs/issue252_grouped_final_numbering_comparison/grouped_final_numbering_comparison.json
```

## 3. Expected-grouping diagnostic overlay

Do not infer expected grouping from same-x geometry. Render a third overlay only from
a retained accepted PR #219 numbering/connector artifact or from the corrected Issue
#254 route:

```bash
PYTHONPATH=. "$PYTHON" tools/issue252/render_grouped_numbering_overlay.py \
  --image "$ORIGINAL" \
  --staff-mask "$NUMBERING_STAFF_MASK" \
  --connector-evidence <accepted-or-corrected-connector-evidence.json> \
  --numbering <accepted-or-corrected-numbering-final.json> \
  --cnn-barlines <accepted-or-corrected-cnn-barlines.json> \
  --target-bbox 847 2675 854 2776 \
  --nearby-bbox 847 2490 854 2591 \
  --label expected_grouping \
  --crop 650 2300 1100 2920 \
  --output \
    logs/issue252_grouped_final_numbering_comparison/expected_grouping_overlay.png
```

All three overlays must use the same crop and legend.

## Validation

```bash
bash scripts/check_pr_slice.sh \
  issue252-prokofiev-probe-boundary \
  --pytest-only \
  --python "$PYTHON"

make lint
```

The focused tests verify fresh-contract rejection, first-loss classification, explicit
connector-supported grouping, three-component grouping without a maximum-two limit,
same-x non-evidence, and isolated MMR page-key remapping.
