# Issue 120 Stage D Historical Settings Audit

## Purpose

This document records what is currently known about the historical Stage D-equivalent settings behind the Issue #120 detector target.

The detector target remains:

```text
TP=3580 FP=0 FN=1
```

The historical Stage C reconstruction path depends on this local artifact:

```text
logs/cnn_barline_classification/issue44_baseline_v1/scoring_input_eval2_v12
```

## Historical source evidence

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

That script consumed, but did not regenerate:

```python
bands_from = Path("logs/cnn_barline_classification/issue44_baseline_v1/scoring_input_eval2_v12")
```

Therefore Git history recovers the successful Stage C consumer settings, but not the producer settings for `scoring_input_eval2_v12`.

## Historical Stage C settings

Probe scan:

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

CNN scoring:

```python
run_scoring_batch(
    model=Path(
        "logs/cnn_barline_classification/issue44_iter7_final_rescue_v1/cnn_classifier_best.pth"
    ),
    images_root=Path("data/evaluation2/images"),
    logs=Path("logs/issue53_full_eval_rescue_v1"),
    threshold=0.1,
    crop_recenter_on_bbox_ink=True,
    crop_recenter_max_shift_unit_ratio=0.5,
    bands_from=bands_from,
    staff_vov_threshold=0.5,
    overwrite=True,
)
```

Evaluation:

```yaml
scored_root: logs/issue53_full_eval_rescue_v1
gt_root: data/evaluation2/annotations
threshold: 0.1
eval_rule: center_anchor
vov_threshold: 0.5
xdist_threshold: 12.0
scored_glob: "*_scored.json"
```

## Historical staff-band logic

PR #57 records a key staff clustering fix:

```text
Commit 2aeff17: img_h * 0.05 -> median_bbox_h * 0.5
```

Relevant changes:

- `detect_probe_scan(..., band_cluster_max_dist=None)` instead of a fixed default.
- `build_row_stats(..., cluster_max_dist=None, min_row_count=3)`.
- default cluster distance becomes `median_bbox_h * 0.5`.
- staff-like criteria were relaxed from `line_count >= 4` / `long_line_count >= 3` to `line_count >= 3` / `long_line_count >= 2`.
- `run_probe_scan_batch` accepted and forwarded `band_cluster_max_dist`.

The current Stage C wrapper mirrors the recovered probe-rescue knobs, so the remaining Stage D drift is unlikely to be caused by Stage C settings alone.

## Current Stage D tests

### Hybrid-source composition

```text
GT=3581 Pred=3769 TP=3527 FP=183 FN=54 FN_det=37 FN_cnn=17 Precision=0.950674 Recall=0.984920
```

The failure is concentrated in `Va__Prokofiev_Symphony5` and shows both detector-side candidate loss and false positives.

### Source-specific comparison against historical artifact

Current upstream outputs were recomposed source-by-source without rerunning HOMR/SR/OMR:

```text
baseline: composed=68 missing=0 by_source={'baseline': 68}
sr:       composed=68 missing=0 by_source={'sr': 68}
omr_sr:   composed=68 missing=0 by_source={'omr_sr': 68}
```

Largest count-loss examples vs historical `scoring_input_eval2_v12`:

```text
baseline:
  Shostakovich-Sym5-Va page_020: 618 -> 66 ratio=0.107
  Sibelius-Violin_Concerto-Viola page_006: 675 -> 89 ratio=0.132
  Shostakovich-Sym5-Va page_019: 381 -> 60 ratio=0.157

sr:
  Shostakovich-Sym5-Va page_020: 618 -> 31 ratio=0.050
  Sibelius-Violin_Concerto-Viola page_006: 675 -> 53 ratio=0.079
  Shostakovich-Sym5-Va page_019: 381 -> 35 ratio=0.092

omr_sr:
  Shostakovich-Festival_Overture_Va page_002: 139 -> 0 ratio=0.000
  Shostakovich-Festival_Overture_Va page_005: 236 -> 2 ratio=0.008
  Shostakovich-Festival_Overture_Va page_009: 171 -> 4 ratio=0.023
```

Interpretation:

- `baseline` is the only source-specific candidate worth evaluating directly.
- `sr` remains too sparse.
- `omr_sr` has empty/nearly empty pages and is not a viable direct replacement.

### Baseline-source Stage C verifier

After normalizing composed boxes to plain `[x1, y1, x2, y2]` lists, baseline-source Stage C produced usable candidates:

```text
Candidate coverage comparison
Pages: 68
Baseline candidates: 29443
Compared candidates: 21415
Ratio: 0.7273375675033115
Empty compared pages: 0
```

Detector result:

```text
GT=3581 Pred=3907 TP=3543 FP=288 FN=38 FN_det=19 FN_cnn=19 Precision=0.924824 Recall=0.989388
```

Comparison:

```text
hybrid-source:
  Pred=3769 TP=3527 FP=183 FN=54 FN_det=37 FN_cnn=17

baseline-source:
  Pred=3907 TP=3543 FP=288 FN=38 FN_det=19 FN_cnn=19
```

Interpretation:

- Baseline source improves recall and reduces detector-side misses relative to hybrid source.
- Baseline source substantially increases false positives.
- It still does not reproduce the target `TP=3580 FP=0 FN=1`.
- The boundary is upstream semantic/geometry mismatch plus scoring/filtering drift, not an unreadable source tree.

## Current conclusion

Current upstream components can regenerate structurally complete 68-page artifacts, but none of the tested compositions reproduce the historical detector target.

```text
Target: TP=3580 FP=0 FN=1
Best current Stage D composition tested: baseline source
Observed: TP=3543 FP=288 FN=38
```

The historical `scoring_input_eval2_v12` artifact remains non-reproduced. Further progress should be split into historical source recovery or upstream/geometry repair after this diagnostic foundation is merged.
