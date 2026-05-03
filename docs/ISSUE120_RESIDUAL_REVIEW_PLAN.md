# Issue 120 Residual Review Plan

## Purpose

The current evaluation2 full-68 recovery work has improved the downstream measure-count KPI,
but visual review shows that the remaining detector residuals mix several different problem
types:

- real detector/pipeline defects,
- evaluation-label granularity mismatches,
- likely GT issues,
- and residuals that are detector-level errors but measure-count neutral.

Before adding more filters or rescues, classify the residuals visually and use that
classification to decide the next small experiments.

## Current Fixed Baseline

Latest committed operating point:

- Commit: `95d63d0 Add soft-short low confidence barline filter`
- Detection config:
  - `cnn_threshold: 0.5`
  - `cnn_min_height_unit_ratio: 2.8`
  - `cnn_short_low_confidence_min_height_unit_ratio: 2.9`
  - `cnn_short_low_confidence_max_score: 0.9`
  - unit-scaled numbering thresholds:
    - dedup: `1.2u`
    - implicit start: `4.0u`
    - min measure width: `1.8u`

Measure-count KPI on 68 pages:

| variant | pred | gt | net delta | abs delta sum | delta pages | precision | recall |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `score_ge_0p5_minh_2p8` | 3381 | 3384 | -3 | 5 | 3 | 0.998225 | 0.997340 |
| `score_ge_0p5_minh_2p8_softshort_2p9_scorelt_0p9` | 3380 | 3384 | -4 | 4 | 2 | 0.998817 | 0.997636 |

The soft-short filter fixed the previous `Shostakovich-Sym5-Va/page_018` over-count by
removing a short internal FP (`height_ratio ~= 2.88u`, `score=0.7053`) without removing
high-confidence short true bars elsewhere.

Remaining count-delta pages:

| score | page | delta | known structure |
| --- | --- | ---: | --- |
| `Sibelius-Violin_Concerto-Viola` | `page_006` | -3 | two candidate-stage misses near x=969 and x=2143; one very low CNN-score candidate near x=2471 |
| `Va_Prokofiev_Symphony1` | `page_005` | -1 | low-score double-bar candidate near x=2370; local rescue works but broad low-score rescue over-counts globally |

## Visual Review Inputs

Use these artifacts for manual classification:

- FP crops:
  `logs/issue120_e2e_recovery/eval2_full_report_final_68pages/visuals/fp_crops/`
- FN crops:
  `logs/issue120_e2e_recovery/eval2_full_report_final_68pages/visuals/fn_crops/`
- TP/FP/FN overlays:
  `logs/issue120_e2e_recovery/eval2_full_report_final_68pages/visuals/overlays/`
- Residual source CSV:
  `logs/issue120_e2e_recovery/eval2_full_report_final_68pages/measure_impact/measure_impact_residuals.csv`
- Manual review CSV:
  `logs/issue120_e2e_recovery/eval2_full_report_final_68pages/manual_review/residual_manual_review_template.csv`

The manual review CSV has one row per residual and includes `visual_path` and `overlay_path`
so classification can be done directly from the existing crop/overlay images.

## Manual Classification Format

Fill these columns in the manual review CSV:

| column | purpose | suggested values |
| --- | --- | --- |
| `manual_class` | visual/local residual class | see class list below |
| `manual_count_impact` | expected effect on final measure count | `count_affecting`, `count_neutral`, `unclear` |
| `staff_region_judgement` | whether the object belongs to a staff region | `inside_staff`, `outside_staff`, `borderline`, `gt_out_of_staff`, `unclear` |
| `line_reality` | whether the object is visually a real printed line | `real_barline`, `real_nonbarline_line`, `artifact`, `missing_true_line`, `unclear` |
| `root_cause_guess` | likely pipeline/evaluation layer | `staff_filter`, `seed_generation`, `divisi_rescue`, `right_edge_rescue`, `cnn_low_score`, `post_filter`, `evaluation_granularity`, `gt_issue`, `unknown` |
| `recommended_action` | next action after classification | `fix_pipeline`, `fix_eval_rule`, `review_gt`, `ignore_for_count`, `needs_trace`, `unknown` |
| `review_status` | review progress | `todo`, `reviewed`, `needs_second_look` |
| `reviewer_note` | free-form visual note | any short note |

Suggested `manual_class` values:

| class | use when |
| --- | --- |
| `fp_out_of_staff` | FP is visibly outside the staff region and should probably have been filtered |
| `fp_real_double_or_end_side` | FP is the other side of a double/end barline or a true nearby line |
| `fp_divisi_spanning` | FP spans two divisi staves or two systems as one long vertical line |
| `fp_internal_false_bar` | FP is inside a measure and creates or may create an over-count |
| `fp_near_gt_duplicate` | FP is close to an existing GT/predicted line and likely dedup dependent |
| `fp_real_nonbarline_line` | FP is a real printed line but not a logical barline |
| `fn_out_of_staff_gt` | FN GT box itself appears outside/misaligned from the staff |
| `fn_double_or_end_one_side` | only one side of a double/end bar is missing and the logical boundary is preserved |
| `fn_right_edge_missing` | missing line is at the right edge of a system |
| `fn_candidate_stage_miss` | no plausible candidate appears to have reached CNN/post-filter |
| `fn_cnn_low_score` | plausible candidate exists but CNN score is very low |
| `fn_post_filter_loss` | plausible candidate exists and scores well but is removed later |
| `unclear` | visual classification needs a second look |

## Investigation Questions

### 1. Staff-region filtering

Observed issue:

- Many FP crops appear outside the staff region.
- Past work expected staff-region filtering to remove them.

Questions:

- Is `staff_vov_threshold` currently disabled by config?
- Does `filter_by_staff_overlap` use staff-mask bands, row-stat bands, or raw mask pixels?
- Are the apparent outside-staff FPs still overlapping an overly broad staff band?
- Does `candidate_filter_kwargs.min_staff_overlap_ratio` apply before or after probe rescues?

Files to inspect:

- `src/pipeline/steps/cnn_scoring.py`
- `src/pipeline/probe_detector/bands.py`
- `src/pipeline/steps/probe_scan.py`
- `configs/evaluation2_e2e_verification_full_v12_restore.yaml`

Expected output:

- Count of `fp_out_of_staff`.
- Whether those FPs entered at seed generation, probe scan, or CNN/post-filter.
- A small staff-filter replay experiment only after the visual count is known.

### 2. True-line FP and double/end-bar granularity

Observed issue:

- Some FPs are visually real lines, including one side of a double/end bar.

Questions:

- Are these real errors for the final measure-count objective?
- Should evaluation treat double/end bars as one logical event more consistently?
- Which of these are count-neutral because the neighboring matched line preserves the
  measure boundary?

Expected output:

- Count of `fp_real_double_or_end_side` and `fn_double_or_end_one_side`.
- Recommendation: `fix_eval_rule` or `ignore_for_count` unless they change measure count.

### 3. Divisi-spanning FP

Observed issue:

- Some FPs appear to connect two divisi staves as one vertical line.
- These should not come from homr baseline detections, so the insertion path needs tracing.

Questions:

- Did the candidate originate from `homr`, hybrid union, probe seed, or probe scan rescue?
- Which rescue mechanism generated it?
  - `divisi_rescue`
  - `scan_x_peak_rescue`
  - `scan_gap_rescue`
  - `scan_rightmost_rescue`
- Are staff bands being merged too broadly for divisi systems?

Expected output:

- Count of `fp_divisi_spanning`.
- For representative examples, trace presence through:
  - homr baseline JSON,
  - hybrid JSON,
  - probe seed JSON,
  - probe scan candidates,
  - scored/filtered CNN JSON.

### 4. FN outside staff / GT quality

Observed issue:

- Some FN crops show GT boxes that appear offset from the staff.

Questions:

- Are these valid labels, intentionally covering a logical event, or GT alignment errors?
- Should they remain in detector evaluation?

Expected output:

- Count of `fn_out_of_staff_gt`.
- Recommendation: `review_gt` where applicable, not detector rescue.

### 5. Right-edge missing lines

Observed issue:

- Several FN patterns appear at the right edge of a system.
- Past pipeline versions had right-edge rescue behavior.

Questions:

- Is `scan_rightmost_rescue` enabled in the current config?
- If enabled, does it fail at seed generation, CNN scoring, or post-filtering?
- If relaxed, which FP categories increase?

Files to inspect:

- `src/pipeline/probe_detector/__init__.py`
- `src/pipeline/steps/probe_scan.py`
- current config `scan_rightmost_rescue` options

Expected output:

- Count of `fn_right_edge_missing`.
- Stage classification: `FN_det`, `FN_cnn`, or `post_filter_loss`.
- A small right-edge-only replay experiment after visual review.

## Proposed Investigation Order

1. Manually classify all 145 residual rows in
   `manual_review/residual_manual_review_template.csv`.
2. Summarize counts by `manual_class`, `manual_count_impact`, and `recommended_action`.
3. Start with categories that are both frequent and `count_affecting`.
4. For `fp_out_of_staff`, trace the staff-filter implementation before changing thresholds.
5. For `fp_divisi_spanning`, trace candidate origin through homr/hybrid/seed/probe/CNN.
6. For `fn_right_edge_missing`, separate candidate-stage misses from CNN/post-filter losses.
7. Treat `fn_double_or_end_one_side` and `fp_real_double_or_end_side` as evaluation/count
   semantics first, not detector fixes.

## Regenerating The Manual Review CSV

The current template was generated from `measure_impact_residuals.csv` with 145 rows.
To regenerate:

```bash
mkdir -p logs/issue120_e2e_recovery/eval2_full_report_final_68pages/manual_review
.venv_pdf/bin/python - <<'PY'
import csv
from pathlib import Path

src = Path("logs/issue120_e2e_recovery/eval2_full_report_final_68pages/measure_impact/measure_impact_residuals.csv")
out = Path("logs/issue120_e2e_recovery/eval2_full_report_final_68pages/manual_review/residual_manual_review_template.csv")
manual_fields = [
    "manual_class",
    "manual_count_impact",
    "staff_region_judgement",
    "line_reality",
    "root_cause_guess",
    "recommended_action",
    "review_status",
    "reviewer_note",
]
keep_fields = [
    "score", "page", "residual_type", "index", "bbox",
    "category", "count_impact", "fn_stage", "gt_type", "gt_measure",
    "nearest_gt_index", "nearest_gt_type", "nearest_gt_xdist", "nearest_gt_vov",
    "nearest_pred_index", "nearest_pred_bbox", "nearest_pred_xdist", "nearest_pred_vov",
    "best_near_score", "height_unit_ratio", "numbering_dedup_likely",
    "visual_path", "overlay_path",
]
with src.open(newline="") as handle:
    reader = csv.DictReader(handle)
    rows = []
    for row in reader:
        out_row = {field: "" for field in manual_fields}
        out_row.update({field: row.get(field, "") for field in keep_fields})
        rows.append(out_row)
with out.open("w", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=manual_fields + keep_fields)
    writer.writeheader()
    writer.writerows(rows)
print(f"wrote {out} rows={len(rows)}")
PY
```
