# Issue 141: Stage E Full Pipeline Validation Report

## Purpose

This document records the result and failure boundary of the full 68-page Stage E pipeline run against the Issue #120 detector target.

Stage E validates the real full pipeline path. It is intentionally distinct from the #151 dense probe-candidate route, which is a detector-level partial route and does not run the slow HOMR/SR/OMR upstream pipeline or downstream measure numbering.

## Execution Configuration

- **Run ID**: `issue120_stage_e_full_pipeline`
- **Output location**: `logs/issue120_e2e_recovery/stage_e_full_pipeline/`
- **Components run**: HOMR generation, SR enhancement, `probe_scan` detection, CNN scoring, and downstream measure numbering.
- **NMS policy**: `cnn_apply_nms: false` per Issue #142.

## Detector Metrics vs Target

The detector metrics are produced from the full-pipeline `manifest.json` using `tools/issue120/eval_stage_e_from_manifest.py`.

- **Target**: `TP=3580 / FP=0 / FN=1`
- **Observed Stage E run**: `TP=3359 / FP=145 / FN=222`

## Failure Boundary

The current full pipeline does not reproduce the historical dense-route detector target.

The observed delta is a route-boundary issue, not an NMS-policy issue:

1. **False negatives**: the observed `FN=222` are detector-level misses (`fn_det=222`, `fn_cnn=0`). The missed barlines were not present in the generated candidate set before CNN scoring.
2. **False positives**: with CNN NMS disabled, the current full-pipeline candidate generator emits duplicate or spurious candidates that survive CNN thresholding. The #151 dense route uses different dense generation and clef-mask-aware filtering and remains detector-level only.

## Downstream Measure-Count Metrics

Detector metrics and downstream measure-count metrics must remain separate.

The full pipeline writes downstream numbering output under:

```text
logs/issue120_e2e_recovery/stage_e_full_pipeline/outputs/numbering_final.json
```

A canonical downstream measure-count comparator is not attached in this audit. The Stage E evaluation contract records measure-count status as `not_provided` rather than deriving detector conclusions from downstream numbering output.

## Conclusion

- Stage E is an audit of the current full HOMR/SR/OMR-inclusive pipeline route.
- The current full pipeline does not meet the canonical detector target.
- The failure boundary is candidate generation/filtering route mismatch versus the recovered dense detector route.
- #151 is completed, but its route remains detector-level partial and should not be reported as a full-pipeline result.
- Accuracy repair or true full-pipeline integration of the dense route should be handled in a follow-up issue, not inside #141.
