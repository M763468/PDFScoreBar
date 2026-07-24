# Issue #252 focused detector and grouped-numbering audit

This directory traces the remaining box-instance mismatch on
`Va_Prokofiev_Symphony1/page_004` and determines whether it changes the
connector-supported final numbering result.

The investigation conclusion is recorded in:

```text
docs/issue252_prokofiev_detector_conclusion.md
```

## Retained tools

- `probe_boundary.py`: pure report and first-loss helpers.
- `trace_prokofiev_probe_boundary.py`: validates the detector-input contract,
  reproduces hybrid consensus, and traces probe stages.
- `run_grouped_final_numbering_comparison.py`: runs two candidate sets through the
  production CNN, grouping, MMR and final-numbering order.
- `audit_grouped_semantic_impact.py`: compares connector-supported grouped results
  without interpreting serialized component count as musical staff count.
- `render_grouped_numbering_overlay.py`: draws grouping and numbering evidence on the
  original score image.

Rejected candidate-filter mechanisms are not installed in production code or
configuration. The trace tool exposes one explicit, tool-local
`--experimental-paper-side-context-width-ratio` switch solely to reproduce the
rejected side-context experiment.

## Detector-input provenance

A runtime result described as fresh must report:

```text
mode = fresh_upstream
fresh_upstream_authoritative = true
override_keys = []
```

The retained Issue #244 and #245 artifacts used by this audit predate the runtime
manifest introduced by PR #251. The local reproduction therefore used:

```text
logs/issue252_contract_snapshot/detector_input_contract.json
```

with:

```text
provenance_status = retrospective_config_assertion
runtime_manifest = false
source_artifacts_predate_runtime_manifest = true
```

That snapshot records that the current canonical detection config has no candidate
source overrides. It does not reclassify the retained artifacts as newly generated
runtime output. Historical artifacts are forensic inputs only and are not injected as
fresh runtime candidates or CNN bands.

## Coordinate contract

The verified local run used:

```text
original image            = 3600 x 4680
SR/probe image             = 7200 x 9360
probe staff mask           = 7200 x 9360
CNN staff mask             = 3600 x 4680
numbering staff mask       = 3600 x 4680
CNN input image scale      = 2
CNN output coordinates     = original image pixels
```

The original image SHA-256 is:

```text
27755b1ece7abd5cf967cd49020279e3688cc7bdd5618b4690ed8e58136065d1
```

## 1. Probe trace

The probe image and probe staff mask must use the SR coordinate space. Missing masks
must be acknowledged explicitly; they are not silently substituted. The retained clef
artifact was not an authoritative SR-coordinate mask, so the local run used the
explicit `--allow-zero-clef-mask` fallback.

```bash
cd /home/masaki_muramatsu/ws_PDFScoreBar
PYTHON=/home/masaki_muramatsu/ws_PDFScoreBar/.venv_pdf/bin/python

CONTRACT=logs/issue252_contract_snapshot/detector_input_contract.json
ORIGINAL=data/evaluation2/images/Va_Prokofiev_Symphony1/page_004.png
SR_IMAGE=logs/issue244_full_regression/hybrid/production_default_full68/sr/batch/Va_Prokofiev_Symphony1_page_004/Va_Prokofiev_Symphony1_page_004.png
PROBE_STAFF_MASK=logs/issue244_full_regression/hybrid/production_default_full68/sr/batch/Va_Prokofiev_Symphony1_page_004/Va_Prokofiev_Symphony1_page_004_staff_mask.png
CNN_STAFF_MASK=logs/issue244_full_regression/hybrid/production_default_full68/baseline/batch/Va_Prokofiev_Symphony1_page_004/Va_Prokofiev_Symphony1_page_004_staff_mask.png
NUMBERING_STAFF_MASK="$CNN_STAFF_MASK"

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

rm -rf \
  logs/issue252_probe_default \
  logs/issue252_probe_side_context_2x

PYTHONPATH=. "$PYTHON" tools/issue252/trace_prokofiev_probe_boundary.py \
  "${COMMON_ARGS[@]}" \
  --output-root logs/issue252_probe_default

PYTHONPATH=. "$PYTHON" tools/issue252/trace_prokofiev_probe_boundary.py \
  "${COMMON_ARGS[@]}" \
  --experimental-paper-side-context-width-ratio 2 \
  --output-root logs/issue252_probe_side_context_2x
```

Here, `2x` in the output directory means a side-context width ratio of `2.0`; it is
separate from the SR image scale, which is also `2`.

### Verified probe result

```text
variant                       final candidates   target in final
canonical default             103                no
side-context width ratio 1    144                no
side-context width ratio 2    282                yes
side-context width ratio 4    447                yes
```

The canonical raw probe contains the target in SR coordinates as approximately:

```text
[1698,5338,1702,5549]
```

It survives the size filter and is rejected by the default candidate filter for
`low_paper_overlap`. Width ratio `2.0` is the minimum tested side-context setting that
recovers it under the correct SR-coordinate contract. Width ratio `4.0` expands the
candidate set further and is not used for downstream comparison.

Primary reports:

```text
logs/issue252_probe_default/probe_boundary_report.json
logs/issue252_probe_side_context_2x/probe_boundary_report.json
```

Candidate inputs for the downstream comparison:

```text
logs/issue252_probe_default/suppression_default/final_candidates.json
logs/issue252_probe_side_context_2x/suppression_default/final_candidates.json
```

## 2. Production-order grouped comparison

The CNN consumes the SR image and SR-coordinate candidates. `_score_directory`
downscales candidate coordinates to original pixels before staff-band filtering.
Therefore `--cnn-staff-mask` must already use original/post-downscale coordinates.
Numbering consumes the original page and original-coordinate staff mask. Do not use
`cnn_bands_from` for this reproduction.

No authoritative original-coordinate proxy connector masks were identified in the
retained artifacts, so the local run explicitly recorded page-image ink as the
connector source with `--allow-page-image-connector-fallback`.

```bash
OUTPUT_ROOT=logs/issue252_grouped_final_numbering_comparison_side_context_ratio_2
rm -rf "$OUTPUT_ROOT"

PYTHONPATH=. "$PYTHON" \
  tools/issue252/run_grouped_final_numbering_comparison.py \
  --config configs/dense_full_pipeline.yaml \
  --default-candidates \
    logs/issue252_probe_default/suppression_default/final_candidates.json \
  --candidate-candidates \
    logs/issue252_probe_side_context_2x/suppression_default/final_candidates.json \
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
  --output-root "$OUTPUT_ROOT"
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
logs/issue252_grouped_final_numbering_comparison_side_context_ratio_2/
  grouped_final_numbering_comparison.json
```

### Verified grouped result

```text
CNN accepted candidates           = 98 -> 105
connector evidence equal          = true
system count                      = 12 -> 12
serialized component count        = 13 -> 13
component grouping equal          = true
page measure count                = 90 -> 91
last measure number               = 93 -> 94
changed geometry systems          = [0, 8]
changed numbering systems         = all 12 systems
classification                    = candidate_page_wide_numbering_drift
```

The target belongs to connector-supported system `6`, whose serialized components are
`[6, 7]`. Its measure count and deduplicated boundary geometry are identical between
routes. In particular, the default route already contains the owning-system boundary
near `x=847/854`. The candidate route adds a high-scoring CNN instance at the target,
but does not change that system's measure geometry. Its row start changes from `36` to
`37` only because an additional measure elsewhere shifts page-wide numbering.

The default and candidate MMR override files are identical. Both contain three raw
page-44 overrides, correctly remapped to isolated page index `0`; both execution
contracts report `base_equals_final = false`.

Therefore the target is a box-instance detector FN but is redundant for the current
connector-supported grouped boundary. The side-context candidate remains rejected
because it changes unrelated page geometry and page-wide numbering.

## 3. Relationship to Issue #254

Issue #254 still owns the separate regression between the current grouping output and
the accepted PR #219 grouping. Issue #252 does not modify grouping logic and does not
use same-x geometry or component count as grouping evidence.

A third expected-grouping overlay may be rendered later from accepted PR #219 artifacts
or corrected Issue #254 output for cross-issue comparison. It is not required to decide
Issue #252's detector-promotion question because the corrected current-route comparison
already shows connector support and unchanged target-system geometry.

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
