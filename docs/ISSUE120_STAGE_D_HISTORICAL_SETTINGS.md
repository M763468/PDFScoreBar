# Issue 120 Stage D Historical Settings Audit

## Purpose

This document records what is currently known about the historical Stage D-equivalent settings behind the Issue #120 detector target.

The selected detector target remains:

```text
TP=3580 FP=0 FN=1
```

The historical Stage C reconstruction path depends on this local artifact:

```text
logs/cnn_barline_classification/issue44_baseline_v1/scoring_input_eval2_v12
```

The goal of Stage D is to determine whether that `bands_from` artifact can be regenerated or replaced by an equivalent current upstream artifact.

## Primary historical source

PR #57 merged the Issue #44 final baseline:

```text
PR #57: feat(cnn): finalize baseline retraining and improve staff clustering logic (#44)
head: b58b988979573e651c5a2f57270ebc1c830135b4
merge: 87fb6d0a47294d7879500285a62e519373498b65
```

The historical full-68 rescue script at the PR head is:

```text
experiments/issue53_probe_rescue/evaluate_full_rescue_v1.py
```

That script did not regenerate `scoring_input_eval2_v12`. It consumed it as an existing local artifact:

```python
bands_from = Path("logs/cnn_barline_classification/issue44_baseline_v1/scoring_input_eval2_v12")
```

Therefore the historical Stage D-equivalent upstream generation settings for `scoring_input_eval2_v12` are still not fully recovered from Git alone.

## Historical Stage C probe-rescue settings

From `experiments/issue53_probe_rescue/evaluate_full_rescue_v1.py` at PR #57 head:

```python
image_root = Path("data/evaluation2/images")
gt_root = Path("data/evaluation2/annotations")
bands_from = Path("logs/cnn_barline_classification/issue44_baseline_v1/scoring_input_eval2_v12")
output_root = Path("logs/issue53_full_eval_rescue_v1")
images = sorted(list(image_root.rglob("page_*.png")))
```

Probe scan settings:

```python
detect_probe_kwargs = {
    "scan_gap_rescue": True,
    "scan_gap_threshold_ratio": 1.5,
    "scan_gap_rescue_min_ratio": 0.3,
    "scan_x_peak_rescue": True,
    "scan_rightmost_rescue": True,
    "divisi_rescue": True,
    "scan_center_on_peak": True,
    "max_per_band": 100,
}

run_probe_scan_batch(
    images=images,
    output_root=output_root,
    bands_from=bands_from,
    staff_mask_dir=None,
    ink_threshold=180,
    min_ratio=0.85,
    min_height_ratio=0.012,
    detect_probe_kwargs=detect_probe_kwargs,
    skip_existing=True,
)
```

CNN scoring settings:

```python
model_path = Path("logs/cnn_barline_classification/issue44_iter7_final_rescue_v1/cnn_classifier_best.pth")
run_scoring_batch(
    model=model_path,
    images_root=image_root,
    logs=output_root,
    threshold=0.1,
    crop_recenter_on_bbox_ink=True,
    crop_recenter_max_shift_unit_ratio=0.5,
    bands_from=bands_from,
    staff_vov_threshold=0.5,
    overwrite=True,
)
```

Evaluation settings:

```yaml
scored_root: logs/issue53_full_eval_rescue_v1
gt_root: data/evaluation2/annotations
output_csv: logs/issue53_full_eval_rescue_v1/global_summary.csv
threshold: 0.1
eval_rule: center_anchor
vov_threshold: 0.5
xdist_threshold: 12.0
scored_glob: "*_scored.json"
```

## Historical staff-band / row-stat logic changes

PR #57 notes that a staff clustering fix was central:

```text
Commit 2aeff17: img_h * 0.05 -> median_bbox_h * 0.5
```

Commit `2aeff170f964680e5f14cd790b7b44bf429c4db9` made these relevant changes:

- `detect_probe_scan(..., band_cluster_max_dist=None)` instead of a fixed default.
- `build_row_stats(..., cluster_max_dist=None, min_row_count=3)`.
- default cluster distance becomes `median_bbox_h * 0.5`.
- staff-like criteria were relaxed from `line_count >= 4` and `long_line_count >= 3` to `line_count >= 3` and `long_line_count >= 2`.
- `run_probe_scan_batch` accepted and forwarded `band_cluster_max_dist`.

Current Stage C already uses the same key probe-rescue knobs:

```text
scan_gap_threshold_ratio=1.5
scan_gap_rescue_min_ratio=0.3
scan_x_peak_rescue=true
scan_rightmost_rescue=true
divisi_rescue=true
scan_center_on_peak=true
max_per_band=100
ink_threshold=180
min_ratio=0.85
min_height_ratio=0.012
```

So the Stage D drift is unlikely to be caused by those Stage C probe settings alone.

## Current Stage D result against regenerated current upstream

A local run using the current upstream regeneration wrapper produced:

```text
Pages: 68/68
Detector: GT=3581 Pred=3769 TP=3527 FP=183 FN=54 FN_det=37 FN_cnn=17 Precision=0.950674 Recall=0.984920
```

The upstream composition itself completed:

```text
expected_pages=68
composed_pages=68
missing_pages=0
disable_sr=False
sr_scale=2
```

The failure is concentrated in `Va__Prokofiev_Symphony5`, especially:

```text
Va__Prokofiev_Symphony5 page_005: FP=11 FN=9 FN_det=9
Va__Prokofiev_Symphony5 page_018: FP=11 FN=6 FN_det=6
Va__Prokofiev_Symphony5 page_021: FP=7 FN=5 FN_det=5
Va__Prokofiev_Symphony5 page_003: FP=8 FN=3 FN_det=3
Va__Prokofiev_Symphony5 page_022: FP=6 FN=3 FN_det=3
```

Interpretation:

- The current regenerated upstream artifact is structurally complete but not semantically equivalent to the historical `scoring_input_eval2_v12` artifact.
- `FN_det=37` indicates candidate-generation or upstream-band coverage loss before CNN scoring.
- `FP=183` indicates geometry/coverage drift or over-generation.
- The concentration in Prokofiev Symphony 5 suggests a score-specific upstream artifact mismatch, not a uniform scorer-only regression.

## Box-tree statistics from local comparison

Two local comparisons were run:

```text
Golden Baseline fixture -> current Stage-D bands_from_candidate
historical scoring_input_eval2_v12 -> current Stage-D bands_from_candidate
```

Both comparisons show that the current composed `bands_from_candidate` is much sparser than the historical/local artifacts.

Examples from `scoring_input_eval2_v12` vs current Stage-D:

```text
Shostakovich-Sym5-Va page_020: 618 -> 30 ratio=0.049
Sibelius-Violin_Concerto-Viola page_006: 675 -> 44 ratio=0.065
Shostakovich-Sym5-Va page_018: 459 -> 35 ratio=0.076
Shostakovich-Sym5-Va page_019: 381 -> 30 ratio=0.079
Va__Prokofiev_Symphony5 page_003: 461 -> 65 ratio=0.141
```

The largest width shifts also show a repeated `+5 px` pattern for Shostakovich Festival and Sibelius pages, while several Prokofiev 5 pages show `-3 px` width deltas and height shifts of about 3-5 px.

Interpretation:

- The current Stage-D composed tree is not simply a noisy version of `scoring_input_eval2_v12`; it is a substantially different source/granularity.
- The current `hybrid_results` source is likely too sparse for use as the Stage-C `bands_from` replacement.
- The next test should compose `bands_from_candidate` from individual upstream sources (`baseline`, `sr`, `omr_sr`) without rerunning HOMR/SR/OMR.

## Important current tooling caveat

`run_issue53_probe_rescue_then_eval.py` originally wrote candidate-coverage comparison output before invoking `score_candidates_then_eval_full68.py` with `--clean-output`.

That deleted `candidate_coverage_comparison.json` from the shared eval output directory before Stage D drift summarization could read it.

This was fixed by running candidate coverage comparison after evaluation unless `--coverage-only` is used.

After this fix, rerun:

```bash
make verify-issue120-stage-d
make summarize-issue120-stage-d
```

No HOMR/SR/OMR upstream regeneration rerun is needed for this diagnostic rerun if `stage_d_upstream_regen/bands_from_candidate` already exists.

## Compose-source diagnostic

`tools/issue120/run_stage_d_upstream_regen.py` supports recomposing `bands_from_candidate` from existing upstream outputs without rerunning HOMR/SR/OMR:

```bash
PYTHONPATH=. python3 tools/issue120/run_stage_d_upstream_regen.py \
  --compose-only \
  --compose-source baseline

PYTHONPATH=. python3 tools/issue120/run_stage_d_upstream_regen.py \
  --compose-only \
  --compose-source sr

PYTHONPATH=. python3 tools/issue120/run_stage_d_upstream_regen.py \
  --compose-only \
  --compose-source omr_sr
```

This writes separate directories:

```text
logs/issue120_e2e_recovery/stage_d_upstream_regen/bands_from_candidate_baseline
logs/issue120_e2e_recovery/stage_d_upstream_regen/bands_from_candidate_sr
logs/issue120_e2e_recovery/stage_d_upstream_regen/bands_from_candidate_omr_sr
```

Compare each against the historical local artifact if available:

```bash
PYTHONPATH=. python3 tools/issue120/compare_box_tree_stats.py \
  --left logs/cnn_barline_classification/issue44_baseline_v1/scoring_input_eval2_v12 \
  --right logs/issue120_e2e_recovery/stage_d_upstream_regen/bands_from_candidate_baseline \
  --output-dir logs/issue120_e2e_recovery/stage_d_box_tree_stats_historical_vs_baseline
```

Repeat for `bands_from_candidate_sr` and `bands_from_candidate_omr_sr`.

## Remaining unknown

Git history confirms how `scoring_input_eval2_v12` was consumed by the successful historical rescue path, but not how it was generated.

Open questions:

1. Was `scoring_input_eval2_v12` produced by a pre-PR #57 baseline run, by copied curated intermediates, or by a now-untracked script/config?
2. Did the artifact use baseline HOMR, SR HOMR, OMR-DLN, or a manually selected hybrid source per page?
3. Did it include score-specific postprocessing for `Va__Prokofiev_Symphony5`?
4. Did it contain plain candidates, scored outputs, filtered CNN outputs, or row-stat-friendly boxes with geometry different from current hybrid consensus?

## Next investigation steps

1. Recompose current upstream outputs by source without rerunning HOMR/SR/OMR:

```bash
PYTHONPATH=. python3 tools/issue120/run_stage_d_upstream_regen.py --compose-only --compose-source baseline
PYTHONPATH=. python3 tools/issue120/run_stage_d_upstream_regen.py --compose-only --compose-source sr
PYTHONPATH=. python3 tools/issue120/run_stage_d_upstream_regen.py --compose-only --compose-source omr_sr
```

2. Compare each source-composed tree against `scoring_input_eval2_v12`.

3. Pick the closest source by count and geometry, then run Stage C verifier against that source-specific `bands_from_candidate_*` directory.

4. If none is close, Stage D should document that the historical artifact cannot be regenerated from current upstream components without additional source-recovery or algorithm repair.
