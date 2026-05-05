# Issue 120 E2E Full-68 Restore Report

## Purpose

This report fixes the reproducible state of the v12-restore E2E detection experiment for
`data/evaluation2` full 68 pages. It records the exact commands, output locations,
metrics, residual visualizations, and follow-up hypotheses.

## Fixed Inputs

- Base config: `configs/evaluation2_e2e_verification_full_v12_restore.yaml`
- Full-run config generator: `tools/create_eval2_full_restore_configs.py`
- Evaluation report tool: `tools/eval2_full_detection_report.py`
- Measure-impact residual classifier: `tools/eval2_residual_measure_impact.py`
- Measure-count KPI tool: `tools/eval2_measure_count_kpi.py`
- Images: `data/evaluation2/images/<score>/page_*.png`
- GT: `data/evaluation2/annotations/<score>/<page>/boxes_sorted*.json`
- CNN model: `logs/cnn_barline_classification/issue44_iter7_final_rescue_v1/cnn_classifier_best.pth`
- Run root: `logs/full_pipeline_runs/evaluation2_full_v12_restore`

The full 68-page page set is generated into:

```bash
PYTHONPATH=.:external/homr .venv_pdf/bin/python tools/create_eval2_full_restore_configs.py \
  --output-dir logs/issue120_e2e_recovery/eval2_full_configs
```

This writes:

- `logs/issue120_e2e_recovery/eval2_full_configs/manifest.json`
- one YAML config per score under `logs/issue120_e2e_recovery/eval2_full_configs/`

## Execution Environment

Follow `docs/ENVIRONMENTS.md`. The integrated detection path uses the GPU-capable
`pdfscore_pipeline_gpu` container:

```bash
docker start pdfscore_pipeline_gpu || true
```

The full run used in-process detection per score to avoid repeated process setup. The
driver reads the generated manifest and calls `src.pipeline.detection.run_detection_step`.
Outputs are written under `logs/full_pipeline_runs/evaluation2_full_v12_restore`.

## Reproduction Commands

Generate full-run configs:

```bash
PYTHONPATH=.:external/homr .venv_pdf/bin/python tools/create_eval2_full_restore_configs.py \
  --output-dir logs/issue120_e2e_recovery/eval2_full_configs
```

Run detection per manifest inside `pdfscore_pipeline_gpu`:

```bash
docker exec pdfscore_pipeline_gpu bash -lc '
cd /workspace
/opt/venv_pipeline/bin/python -u - <<'"'"'PY'"'"'
import json
import logging
from pathlib import Path

import yaml

from src.pipeline.detection import run_detection_step
from src.pipeline.utils.io import ensure_dir, write_json

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

manifest = json.loads(Path("logs/issue120_e2e_recovery/eval2_full_configs/manifest.json").read_text())
for item in manifest:
    cfg_path = Path(item["config"])
    cfg = yaml.safe_load(cfg_path.read_text())
    run_id = cfg["run"]["run_id"]
    run_dir = Path(cfg["run"].get("output_root", "logs/full_pipeline_runs")) / run_id
    ensure_dir(run_dir)
    image_dir = Path(cfg["inputs"]["pdf_to_images"]["output_dir"])
    page_ids = list(item["pages"])
    images = [image_dir / f"{page}.png" for page in page_ids]

    logging.info("DETECTION_ONLY_START score=%s pages=%d", item["score"], len(images))
    result = run_detection_step(
        cfg,
        images,
        page_ids,
        run_id,
        run_dir,
        dry_run=False,
        in_memory_images=None,
    )
    write_json(
        run_dir / "detection_only_manifest.json",
        {
            "score": item["score"],
            "run_id": run_id,
            "pages": page_ids,
            "images": [str(p) for p in images],
            "commands": result.get("commands", []),
            "hybrid_output_dir": str(result.get("hybrid_output_dir")),
            "probe_output_dir": str(result.get("probe_output_dir")),
        },
    )
    logging.info("DETECTION_ONLY_DONE score=%s", item["score"])
PY
'
```

Generate final detection metrics and FP/FN visualizations:

```bash
PYTHONPATH=.:external/homr .venv_pdf/bin/python tools/eval2_full_detection_report.py \
  --manifest logs/issue120_e2e_recovery/eval2_full_configs/manifest.json \
  --run-root logs/full_pipeline_runs/evaluation2_full_v12_restore \
  --gt-root data/evaluation2/annotations \
  --images-root data/evaluation2/images \
  --output-dir logs/issue120_e2e_recovery/eval2_full_report_final_68pages \
  --score-thresholds 0.08 0.1 0.5
```

Classify residuals by likely measure-count impact and generate a review index:

```bash
PYTHONPATH=.:external/homr .venv_pdf/bin/python tools/eval2_residual_measure_impact.py \
  --manifest logs/issue120_e2e_recovery/eval2_full_configs/manifest.json \
  --run-root logs/full_pipeline_runs/evaluation2_full_v12_restore \
  --gt-root data/evaluation2/annotations \
  --report-dir logs/issue120_e2e_recovery/eval2_full_report_final_68pages \
  --output-dir logs/issue120_e2e_recovery/eval2_full_report_final_68pages/measure_impact
```

Run downstream measure-count KPI on the same 68-page outputs:

```bash
PYTHONPATH=.:external/homr .venv_pdf/bin/python tools/eval2_measure_count_kpi.py \
  --manifest logs/issue120_e2e_recovery/eval2_full_configs/manifest.json \
  --run-root logs/full_pipeline_runs/evaluation2_full_v12_restore \
  --gt-root data/evaluation2/annotations \
  --images-root data/evaluation2/images \
  --output-dir logs/issue120_e2e_recovery/eval2_full_report_final_68pages/measure_count_kpi \
  --variants filtered score_ge_0p5 score_ge_0p5_minh_2p8
```

## Detection Metrics

Final report path:

- `logs/issue120_e2e_recovery/eval2_full_report_final_68pages/summary_by_layer.csv`
- `logs/issue120_e2e_recovery/eval2_full_report_final_68pages/per_page_stats.csv`
- `logs/issue120_e2e_recovery/eval2_full_report_final_68pages/residuals.csv`

Global result at `cnn_threshold=0.08`:

| layer | pages | TP | FP | FN | FN_cnn | FN_det | GT | precision | recall |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| filtered_cnn_json | 68 | 3561 | 125 | 20 | 17 | 3 | 3581 | 0.9661 | 0.9944 |
| probe_candidates | 68 | 3574 | 59298 | 7 | 4 | 3 | 3581 | 0.0568 | 0.9980 |
| scored_json 0.5 | 68 | 3559 | 77 | 22 | 19 | 3 | 3581 | 0.9788 | 0.9939 |

Per-score filtered result:

| score | pages | TP | FP | FN |
| --- | ---: | ---: | ---: | ---: |
| Shostakovich-Festival_Overture_Va | 9 | 350 | 4 | 1 |
| Shostakovich-Sym5-Va | 22 | 946 | 54 | 8 |
| Sibelius-Violin_Concerto-Viola | 10 | 676 | 36 | 7 |
| Va_Prokofiev_Symphony1 | 6 | 543 | 2 | 4 |
| Va__Prokofiev_Symphony5 | 21 | 1046 | 29 | 0 |

## Visual Review Artifacts

Detection FP/FN visualization:

- FP crops: `logs/issue120_e2e_recovery/eval2_full_report_final_68pages/visuals/fp_crops/`
- FN crops: `logs/issue120_e2e_recovery/eval2_full_report_final_68pages/visuals/fn_crops/`
- page overlays: `logs/issue120_e2e_recovery/eval2_full_report_final_68pages/visuals/overlays/`

Generated counts:

- FP crops: 125
- FN crops: 20
- overlays: 40

Measure-impact review:

- `logs/issue120_e2e_recovery/eval2_full_report_final_68pages/measure_impact/measure_impact_summary.csv`
- `logs/issue120_e2e_recovery/eval2_full_report_final_68pages/measure_impact/measure_impact_residuals.csv`
- `logs/issue120_e2e_recovery/eval2_full_report_final_68pages/measure_impact/measure_impact_review.md`

Measure-count KPI review:

- `logs/issue120_e2e_recovery/eval2_full_report_final_68pages/measure_count_kpi/measure_count_summary.csv`
- `logs/issue120_e2e_recovery/eval2_full_report_final_68pages/measure_count_kpi/measure_count_per_page.csv`
- `logs/issue120_e2e_recovery/eval2_full_report_final_68pages/measure_count_kpi/measure_count_delta_pages.csv`
- `logs/issue120_e2e_recovery/eval2_full_report_final_68pages/measure_count_kpi/measure_count_review.md`

## Measure-Count Impact Classification

The detector-level `FN=20` overstates likely measure-count impact because many FN cases are
one side of a close double/end-style pair or a nearby vertical segment already covered by a
matched prediction. The residual classifier uses `center_anchor` matching plus a 20 px
logic-neighborhood to separate those cases.

Summary:

| residual_type | category | count_impact | count |
| --- | --- | --- | ---: |
| FN | covered_by_matched_prediction | likely_count_neutral | 12 |
| FN | isolated_missing | likely_count_affecting | 6 |
| FN | complex_pair_uncovered | likely_count_affecting | 2 |
| FP | near_matched_gt_duplicate | dedup_dependent | 25 |
| FP | remote_fp | likely_count_affecting | 42 |
| FP | tall_or_system_spanning_fp | likely_count_affecting | 58 |

Interpretation:

- 12/20 FN are likely count-neutral because a matched prediction already exists within the
  same close logical barline neighborhood.
- 8/20 FN remain likely count-affecting and should be reviewed first.
- FP is still a significant count risk. 25/125 are close duplicates and may be suppressed by
  numbering deduplication, but 100/125 are remote or tall/system-spanning detections.

## Downstream Measure-Count KPI

The final purpose is measure counting, so the current detection outputs were also evaluated
by running `MeasureNumberingPipeline` on GT boxes and on predicted boxes using the same staff
masks. This does not replace detector metrics, but it reveals which detector residuals matter
downstream.

Global result:

| variant | pages | pred measures | gt measures | delta | abs delta sum | pages with delta | measure precision | measure recall |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| filtered | 68 | 3386 | 3384 | +2 | 10 | 5 | 0.9956 | 0.9962 |
| score >= 0.5 | 68 | 3384 | 3384 | 0 | 8 | 4 | 0.9967 | 0.9967 |
| score >= 0.5, min height >= 2.8 unit | 68 | 3381 | 3384 | -3 | 5 | 3 | 0.9982 | 0.9973 |
| score >= 0.5, min height >= 2.8 unit, soft-short low-confidence | 68 | 3380 | 3384 | -4 | 4 | 2 | 0.9988 | 0.9976 |

Note:

- `abs delta sum` is a measure-count metric: the sum of page-level absolute differences
  between predicted and GT measure counts.
- The residual CSV is a detector residual list. It can contain far more rows than
  `abs delta sum` because many residuals are count-neutral.

Interpretation:

- The downstream KPI confirms that many detector-level FN/FP are count-neutral or deduped.
- Unit-scaled numbering thresholds improve all variants by rejecting narrow pseudo-measures
  consistently across page resolutions.
- `score >= 0.5` improves measure-count precision and reduces total count error
  (`abs_delta_sum 10 -> 8`) while keeping the same 68-page input set.
- Adding a unit-scaled minimum candidate height of 2.8 improves the count KPI further
  (`abs_delta_sum 8 -> 5`) by suppressing short high-score internal false positives.
- Adding the soft-short low-confidence post-filter improves the count KPI again
  (`abs_delta_sum 5 -> 4`, delta pages `3 -> 2`). It keeps the 2.8-unit hard floor but
  additionally suppresses candidates below 2.9 units only when `score < 0.9`.
- Remaining count-affecting pages at the current best setting are:
  `Sibelius-Violin_Concerto-Viola/page_006` (-3),
  and `Va_Prokofiev_Symphony1/page_005` (-1).
- `Shostakovich-Festival_Overture_Va` is perfect at the measure-count level
  (`349/349`, no delta pages), despite detector-level residuals.

Residual local structures at the soft-short setting:

- `Shostakovich-Sym5-Va/page_018` is fixed. The removed over-count FP was a partial
  internal barline `[2386, 3790, 2390, 3862]` with `score=0.7053` and height ratio
  about `2.88u`. A global `2.9u` minimum height also removes it, but creates new FN on
  `Va__Prokofiev_Symphony5`; the score guard avoids those high-confidence true bars.
- `Sibelius-Violin_Concerto-Viola/page_006` remains `-3`. The count-affecting misses are
  two candidate-stage misses around x=`969` and x=`2143`, plus one very low CNN score
  candidate around x=`2471` (`score=0.00063`). This is not recoverable by a small
  post-CNN score/height filter.
- `Va_Prokofiev_Symphony1/page_005` remains `-1`. The local double-bar candidate around
  x=`2370` has `score=0.00019`; adding it fixes the page locally, but broad low-score
  gap rescue over-counts globally.

## Small Verification Sweeps

Post-processing sweeps were run on the final 68-page JSON outputs only.

| variant | TP | FP | FN | note |
| --- | ---: | ---: | ---: | --- |
| baseline | 3561 | 125 | 20 | current filtered output |
| score >= 0.5 | 3559 | 77 | 22 | FP improves, FN worsens |
| score >= 0.5 + min height 2.8 unit | 3558 | 68 | 23 | best downstream count KPI so far |
| max height 5.5 unit | 3553 | 63 | 28 | FP improves, FN worsens |
| max height 7.5 unit + left shift | 3568 | 66 | 13 | better metrics, but adds 2759 synthetic candidates |
| x-distance NMS 0.15 unit | 3561 | 123 | 20 | too small to matter |
| x-distance NMS 0.3 unit | 3555 | 121 | 26 | FN starts rising |
| numbering min measure width 45 px equivalent | n/a | n/a | n/a | count abs delta improves 6 -> 5 |
| numbering unit thresholds 1.2u/4.0u/1.8u | n/a | n/a | n/a | adopted; count abs delta improves 6 -> 5 |
| staff coverage filter 0.45 | n/a | n/a | n/a | rejected; count abs delta worsens 5 -> 26 |
| x-align gap rescue | n/a | n/a | n/a | rejected; best tested count abs delta worsens 5 -> 6 |
| low-score gap rescue | n/a | n/a | n/a | rejected; best tested count abs delta worsens 5 -> 24 |
| min height 2.9/3.0/3.1 after unit numbering | n/a | n/a | n/a | rejected; fixes Shostakovich page_018 but worsens global abs delta to 6/7/8 |
| score threshold 0.6/0.7/0.75 after unit numbering | n/a | n/a | n/a | rejected; creates Shostakovich page_008 under-count or does not improve abs delta |
| numbering partial internal bar suppression | n/a | n/a | n/a | rejected; changed GT measure extraction as well as predictions |
| soft-short low-confidence 2.9u score<0.9 | n/a | n/a | n/a | adopted; count abs delta improves 5 -> 4 |

Conclusion: no simple global threshold, height cap, or NMS restoration is safe enough to
apply as the next production change. Left-shift recovery proves the failure mode but is too
broad without stronger targeting.

Additional rejected sweeps after adopting unit numbering thresholds:

- Staff coverage filter:
  `logs/issue120_e2e_recovery/eval2_full_report_final_68pages/measure_count_kpi_sweeps/staffcov_v1/summary.csv`.
  Filtering by candidate coverage over staff height suppresses true barlines too often.
  The loosest tested threshold (`0.45`) worsened `abs_delta_sum` from 5 to 26.
- Page x-alignment rescue:
  `logs/issue120_e2e_recovery/eval2_full_report_final_68pages/measure_count_kpi_sweeps/xalign_rescue_v1/summary.csv`.
  Adding inferred barlines in large gaps from page-wide x clusters increased over-count.
  The strictest tested variant added only one candidate but still worsened `abs_delta_sum`
  from 5 to 6.
- Low-score gap rescue:
  `logs/issue120_e2e_recovery/eval2_full_report_final_68pages/measure_count_kpi_sweeps/low_score_gap_rescue_v1/summary.csv`.
  This locally fixes `Va_Prokofiev_Symphony1/page_005` by rescuing one low-score double-bar
  candidate, but globally it adds too many false internal barlines. The best tested variant
  worsened `abs_delta_sum` from 5 to 24.
- Higher hard min-height after unit numbering:
  `logs/issue120_e2e_recovery/eval2_full_report_final_68pages/measure_count_kpi_sweeps/minh_after_unit_v1/measure_count_summary.csv`.
  `2.9u` fixes the `Shostakovich-Sym5-Va/page_018` over-count, but removes
  high-confidence true short bars in `Va__Prokofiev_Symphony5`; global `abs_delta_sum`
  worsens from 5 to 6.
- Higher score threshold after unit numbering:
  `logs/issue120_e2e_recovery/eval2_full_report_final_68pages/measure_count_kpi_sweeps/score_threshold_after_unit_v1/measure_count_summary.csv`.
  Thresholds `0.6` and `0.7` do not remove the `score=0.705` FP; `0.75` removes it but
  creates `Shostakovich-Sym5-Va/page_008` under-count, so global `abs_delta_sum` does not
  improve.
- Numbering partial internal bar suppression:
  `logs/issue120_e2e_recovery/eval2_full_report_final_68pages/measure_count_kpi_sweeps/numbering_partial_bar_v1/measure_count_summary.csv`.
  This fixed the `Shostakovich-Sym5-Va/page_018` prediction count, but it also changed GT
  measure extraction (`gt_measure_count 3384 -> 3374`), so it is not a valid prediction-side
  correction.

Adopted local-structure correction:

- Soft-short low-confidence post-filter:
  `logs/issue120_e2e_recovery/eval2_full_report_final_68pages/measure_count_kpi_sweeps/softshort_lowconf_v1/measure_count_summary.csv`.
  Reproduction command:

  ```bash
  PYTHONPATH=.:external/homr .venv_pdf/bin/python tools/eval2_measure_count_kpi.py \
    --manifest logs/issue120_e2e_recovery/eval2_full_configs/manifest.json \
    --run-root logs/full_pipeline_runs/evaluation2_full_v12_restore \
    --gt-root data/evaluation2/annotations \
    --images-root data/evaluation2/images \
    --output-dir logs/issue120_e2e_recovery/eval2_full_report_final_68pages/measure_count_kpi_sweeps/softshort_lowconf_v1 \
    --variants score_ge_0p5_minh_2p8 score_ge_0p5_minh_2p8_softshort_2p9_scorelt_0p9
  ```

  The adopted variant improves global measure-count KPI from `3381/3384`, net `-3`,
  `abs_delta_sum=5`, `delta_pages=3` to `3380/3384`, net `-4`, `abs_delta_sum=4`,
  `delta_pages=2`.

## Proposed Next Steps

1. Treat `score >= 0.5`, `cnn_min_height_unit_ratio=2.8`,
   `cnn_short_low_confidence_min_height_unit_ratio=2.9`,
   `cnn_short_low_confidence_max_score=0.9`, and unit-scaled numbering thresholds as the
   current downstream operating point. It improves the measure-count KPI globally to
   `abs_delta_sum=4` and leaves only two count-delta pages.

2. Targeted FN recovery only for under-count pages:
   `Sibelius/page_006` and `Va_Prokofiev_Symphony1/page_005` remain under-counted.
   `Sibelius/page_006` includes true candidate-stage misses in the last system, so CNN
   threshold tuning cannot recover it. Avoid broad double/end-bar one-side recovery because
   12/20 detector FN are likely neutral and the broad left-shift sweep added more than 2700
   synthetic candidates.

3. Separate detector metric from measure-count metric:
   Continue reporting `TP/FP/FN/FN_cnn/FN_det`, but gate future decisions on the downstream
   measure-count error as well. Detector-level one-side FN can be misleading when a matched
   neighboring line still preserves the logical measure boundary.

## Verification

Commands run after implementation:

```bash
make format
make lint
PYTHONPATH=.:external/homr .venv_pdf/bin/python -m pytest \
  tests/test_pipeline_detection.py tests/test_cnn_scoring_recenter.py
git diff --check
```

Observed result:

- `make format`: passed
- `make lint`: passed
- pytest: 7 passed
- `git diff --check`: passed
