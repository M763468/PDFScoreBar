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
| filtered | 68 | 3394 | 3384 | +10 | 18 | 9 | 0.9932 | 0.9962 |
| score >= 0.5 | 68 | 3388 | 3384 | +4 | 12 | 6 | 0.9956 | 0.9967 |
| score >= 0.5, min height >= 2.8 unit | 68 | 3382 | 3384 | -2 | 6 | 4 | 0.9979 | 0.9973 |

Interpretation:

- The downstream KPI confirms that many detector-level FN/FP are count-neutral or deduped.
- `score >= 0.5` improves measure-count precision and reduces total count error
  (`abs_delta_sum 18 -> 12`) while keeping the same 68-page input set.
- Adding a unit-scaled minimum candidate height of 2.8 improves the count KPI further
  (`abs_delta_sum 12 -> 6`) by suppressing short high-score internal false positives.
- Remaining count-affecting pages at the current best setting are:
  `Sibelius-Violin_Concerto-Viola/page_006` (-3),
  `Shostakovich-Sym5-Va/page_018` (+1),
  `Va_Prokofiev_Symphony1/page_005` (-1), and
  `Va__Prokofiev_Symphony5/page_019` (+1).
- `Shostakovich-Festival_Overture_Va` is perfect at the measure-count level
  (`349/349`, no delta pages), despite detector-level residuals.

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

Conclusion: no simple global threshold, height cap, or NMS restoration is safe enough to
apply as the next production change. Left-shift recovery proves the failure mode but is too
broad without stronger targeting.

## Proposed Next Steps

1. Treat `score >= 0.5` plus `cnn_min_height_unit_ratio=2.8` as the next candidate downstream
   operating point. It improves the measure-count KPI globally (`-2` net,
   `abs_delta_sum=6`) and reduces detector FP (`125 -> 68`) with only one extra detector FN
   relative to `score >= 0.5`.

2. FP-first filtering on the remaining over-count pages:
   Focus on `Shostakovich/page_018` and `Va__Prokofiev_Symphony5/page_019`. Height max
   filtering and x-distance NMS did not change the downstream count KPI, so the next filter
   needs to inspect the exact system assignment/visual pattern rather than broad geometry.

3. Targeted FN recovery only for under-count pages:
   `Sibelius/page_006` and `Va_Prokofiev_Symphony1/page_005` remain under-counted.
   `Sibelius/page_006` includes true candidate-stage misses in the last system, so CNN
   threshold tuning cannot recover it. Avoid broad double/end-bar one-side recovery because
   12/20 detector FN are likely neutral and the broad left-shift sweep added more than 2700
   synthetic candidates.

4. Separate detector metric from measure-count metric:
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
