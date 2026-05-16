# Issue 141: Stage E Full Pipeline Validation Report

## Purpose
This document records the results and failure boundary of the full 68-page pipeline run (Stage E) against the Issue #120 detector target. 
As defined in the roadmap, this run uses the general pipeline's default configuration, which differs from the specialized Issue #36 dense candidate reproduction route.

## Execution Configuration
- **Run ID**: `issue120_stage_e_full_pipeline`
- **Output location**: `logs/issue120_e2e_recovery/stage_e_full_pipeline/`
- **Components run**: HOMR generation, SR enhancement (scale=2), `probe_scan` detection, CNN scoring, and downstream measure numbering.
- **NMS Policy**: `cnn_apply_nms: false` (per Issue #142 canonical rule)

## Detector Metrics vs Target
The detector intermediate metrics were generated using the standard `eval_stage_e_from_manifest.py` on the pipeline's output.

- **Target (Historical Best)**: `TP=3580 / FP=0 / FN=1`
- **Actual (Stage E Run)**: `TP=3359 / FP=145 / FN=222`

### Failure Boundary Analysis
The Stage E full pipeline **does not** reproduce the historical dense route detector target. 
The observed metric deltas are driven by two main structural differences between the general pipeline default and the Issue #36 dense candidate generator:

1. **High False Negatives (FN = 222)**
   - All 222 FNs are detector-level misses (`fn_det=222`, `fn_cnn=0`), meaning the true barlines were never generated as candidates before CNN scoring.
   - For example, on `Sibelius-Violin_Concerto-Viola, page_004`, the Stage E pipeline generated 75 candidates, while the historical dense route generated 418 filtered candidates. This significantly reduced candidate density is the primary cause of the recall regression.

2. **High False Positives (FP = 145)**
   - With `cnn_apply_nms: false` set globally, the pipeline relies entirely on upstream logic (like clef-mask filtering or tight band-clustering) to avoid duplicate candidate generation.
   - The dense candidate route (#149/#151) uses an explicit clef-mask filter that correctly eliminates these false candidates. The standard `probe_scan` default configuration produces duplicate overlapping candidates which survive the CNN threshold and are no longer suppressed by NMS.

## Downstream Measure-Count Metrics
As required, detector metrics are kept strictly separate from downstream proxy metrics. 
The downstream numbering step was executed, and outputs reside in `logs/issue120_e2e_recovery/stage_e_full_pipeline/outputs/numbering_final.json`. However, due to the high detector-level error rate (222 missed barlines, 145 spurious barlines), the measure numbering is structurally compromised and a proxy net delta comparison against GT measures is not meaningful for detector tuning. 

*Measure-count proxy evaluation is logged as `not_provided` in the evaluation contract until the upstream detector target can be achieved via the productionized dense route.*

## Conclusion & Next Steps
- Stage E audit is complete. 
- The full slow pipeline with its current default candidate generator configuration does not meet the canonical detector target.
- **Next Step**: As per the roadmap, Issue #151 must productionize the recovered "dense probe candidate route" to replace the standard `probe_scan` defaults before targeted accuracy repairs (Issue #137) or general pipeline adjustments can safely continue.