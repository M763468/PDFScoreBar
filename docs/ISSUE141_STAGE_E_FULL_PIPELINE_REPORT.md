# Issue 141: Stage E Full Pipeline Validation Report

## Purpose

This document records the final full 68-page Stage E pipeline validation result against the Issue #120 detector target.

Stage E validates the real full pipeline path. It is intentionally distinct from the #151 dense probe-candidate route, which is a detector-level partial route and does not run the full HOMR/SR/OMR-inclusive pipeline or downstream measure numbering.

## Execution Configuration

- **Run ID**: `stage_e_full_pipeline`
- **Output location**: `logs/issue120_e2e_recovery/stage_e_full_pipeline/`
- **Components run**: dense candidate reconstruction, Issue53-style probe rescue candidate reconstruction, HOMR/SR/OMR-inclusive full pipeline execution, CNN scoring, and downstream measure numbering.
- **NMS policy**: `cnn_apply_nms: false` per Issue #142.

## Detector Metrics vs Target

The detector metrics are produced from the full-pipeline `manifest.json` using `tools/issue120/eval_stage_e_from_manifest.py` and recorded in `evaluation_contract.json`.

- **Target**: `TP=3580 / FP=0 / FN=1`
- **Observed Stage E run**: `TP=3580 / FP=0 / FN=1`
- **Target met**: yes

Additional detector summary:

```text
Pages=68/68
GT=3581
Pred=3600
TP=3580
FP=0
FN=1
FN_det=0
FN_cnn=1
Precision=1.000000
Recall=0.999721
cnn_apply_nms=false
```

## Repair Summary

The initial Stage E full-pipeline route did not reproduce the recovered detector target:

```text
Initial Stage E: TP=3359 FP=145 FN=222 FN_det=222 FN_cnn=0
```

The failure was not caused by CNN NMS policy. It was caused by the full pipeline not using the same reconstructed candidate route as the recovered dense detector path.

The repair connects Stage E to the recovered route without consuming historical candidate logs as runtime input:

1. Regenerate dense probe candidates inside the current Stage E run.
2. Apply clef/staff-aware candidate filtering inside the current Stage E run.
3. Regenerate Issue53-style probe rescue candidates from that filtered root inside the current Stage E run.
4. Feed the freshly regenerated Issue53 candidate root into the full pipeline detector/CNN scoring path.
5. Evaluate detector metrics from the full-pipeline manifest.

This keeps #151 as detector-level evidence while making #141 validate a real full-pipeline Stage E run.

## Downstream Measure-Count Metrics

Detector metrics and downstream measure-count metrics remain separate.

The full pipeline writes downstream numbering output under:

```text
logs/issue120_e2e_recovery/stage_e_full_pipeline/outputs/numbering_final.json
```

A canonical downstream measure-count comparator is not attached in this audit. The Stage E evaluation contract records measure-count status as `not_provided` rather than deriving detector conclusions from downstream numbering output.

## Conclusion

- Stage E now completes all 68 canonical evaluation pages.
- The full HOMR/SR/OMR-inclusive Stage E pipeline now meets the Issue #120 canonical detector target: `TP=3580 / FP=0 / FN=1`.
- Detector metrics and downstream measure-count status are recorded separately in the machine-readable evaluation contract.
- #151 remains a detector-level partial route and should not be reported as a full-pipeline result by itself.
- Remaining productionization/refactor work should focus on replacing Stage E runner glue with a cleaner pipeline module/API while preserving the recovered route and evaluation contract semantics.
