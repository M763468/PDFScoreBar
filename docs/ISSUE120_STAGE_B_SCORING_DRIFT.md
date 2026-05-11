# Issue 120 Stage B Scoring Drift Results

## Purpose

This document records the Stage B results for #136.

Stage B starts from saved `pipeline2_no_peak_candidates.json` files, reruns CNN scoring, and then evaluates the newly scored outputs with the canonical #134 full-68 evaluator.

This isolates the following layer:

```text
saved candidates
  -> CNN scoring / scoring-side filtering
  -> canonical full-68 detector evaluation
```

It does not regenerate candidates from HOMR/OMR/SR/hybrid/probe outputs.

## Stage A reference

The #134 evaluator verifies the saved post-CNN-scoring Golden Baseline intermediates:

```text
Pages: 68/68
Detector: GT=3581 Pred=3597 TP=3580 FP=0 FN=1 FN_det=0 FN_cnn=1 Precision=1.000000 Recall=0.999721
```

This is the Stage A reference.

## Stage B result: current pipeline scorer

Command:

```bash
make verify-issue120-stage-b ISSUE120_CLEAN_OUTPUT=1
```

Result:

```text
Issue #120 full-68 intermediate evaluation
Pages: 68/68
Detector: GT=3581 Pred=3507 TP=3507 FP=0 FN=74 FN_det=0 FN_cnn=74 Precision=1.000000 Recall=0.979335
Wrote: logs/issue120_e2e_recovery/stage_b_candidate_scoring_eval
Attached intermediate provenance: logs/issue120_e2e_recovery/stage_b_candidate_scoring_eval/evaluation_contract.json
Stage-B evaluation complete: logs/issue120_e2e_recovery/stage_b_candidate_scoring_eval
```

Command with historical bands source:

```bash
make verify-issue120-stage-b \
  ISSUE120_CLEAN_OUTPUT=1 \
  ISSUE120_BANDS_FROM=logs/cnn_barline_classification/issue44_baseline_v1/scoring_input_eval2_v12
```

Result was identical:

```text
Pages: 68/68
Detector: GT=3581 Pred=3507 TP=3507 FP=0 FN=74 FN_det=0 FN_cnn=74 Precision=1.000000 Recall=0.979335
```

Interpretation:

- Saved candidates contain all GT-relevant candidates: `FN_det=0`.
- The failure occurs after candidate generation: `FN_cnn=74`.
- Historical bands source does not change the result, so this specific mismatch is not explained by missing `bands_from` alone.
- The current `src.pipeline.steps.cnn_scoring.run_cnn_scoring_batch` path does not reproduce the saved Golden Baseline scored outputs from the saved Golden Baseline candidates.

## Stage B result: legacy scorer

Command:

```bash
make verify-issue120-stage-b \
  ISSUE120_CLEAN_OUTPUT=1 \
  ISSUE120_STAGE_B_SCORER=legacy
```

Result:

```text
Issue #120 full-68 intermediate evaluation
Pages: 68/68
Detector: GT=3581 Pred=3597 TP=3580 FP=0 FN=1 FN_det=0 FN_cnn=1 Precision=1.000000 Recall=0.999721
Wrote: logs/issue120_e2e_recovery/stage_b_candidate_scoring_eval
Attached intermediate provenance: logs/issue120_e2e_recovery/stage_b_candidate_scoring_eval/evaluation_contract.json
Stage-B evaluation complete: logs/issue120_e2e_recovery/stage_b_candidate_scoring_eval
```

Command with historical bands source:

```bash
make verify-issue120-stage-b \
  ISSUE120_CLEAN_OUTPUT=1 \
  ISSUE120_STAGE_B_SCORER=legacy \
  ISSUE120_BANDS_FROM=logs/cnn_barline_classification/issue44_baseline_v1/scoring_input_eval2_v12
```

Result was identical:

```text
Pages: 68/68
Detector: GT=3581 Pred=3597 TP=3580 FP=0 FN=1 FN_det=0 FN_cnn=1 Precision=1.000000 Recall=0.999721
```

Interpretation:

- Saved candidates plus the legacy scoring implementation reproduce the Golden Baseline exactly.
- This confirms the model artifact, image data, candidate files, threshold, and canonical evaluator are sufficient to recover `TP=3580 / FP=0 / FN=1`.
- The regression is therefore not in saved candidates, not in GT, and not in the canonical evaluator.
- The immediate drift is between legacy scoring and current pipeline scoring.

## Current narrowed root cause

The historical path uses:

```text
tools.cnn_classifier.score_candidates_batch.run_scoring_batch
```

The current pipeline path uses:

```text
src.pipeline.steps.cnn_scoring.run_cnn_scoring_batch
```

The latter produces 90 fewer predictions and 74 additional FN from the same saved candidates:

```text
Stage A / legacy Stage B: Pred=3597, TP=3580, FP=0, FN=1
current pipeline Stage B: Pred=3507, TP=3507, FP=0, FN=74
```

Likely difference areas to audit next:

1. NMS behavior in `src.pipeline.steps.cnn_scoring`.
2. Staff-overlap filtering behavior and whether it mutates scores differently.
3. Crop recentering parameter differences.
4. Candidate object handling and threshold comparison differences.
5. Any preprocessing difference between `tools.cnn_classifier.score_candidates_batch` and `src.pipeline.steps.cnn_scoring`.

One notable code-level difference already observed:

- `src.pipeline.steps.cnn_scoring` applies `apply_nms(candidate_objects_for_filter)`.
- `tools.cnn_classifier.score_candidates_batch` does not appear to apply the same NMS step in its final filtered output path.

This is a strong candidate for the 90-prediction drop, but it is not yet proven. The next step should compare page-level metrics and/or run an ablation with pipeline NMS disabled.

## Decision

Stage B is now partially verified:

- `legacy` scorer: verified, reproduces Golden Baseline.
- `pipeline` scorer: fails, produces `TP=3507 / FP=0 / FN=74`.

Therefore the clean transplant target should be described as:

> Saved Golden Baseline candidates can reproduce `TP=3580 / FP=0 / FN=1` through the historical legacy scorer, but the current pipeline scorer has drifted and currently fails Stage B.

This should be fixed before treating the current full pipeline as a candidate for final Issue #120 accuracy work.

## Recommended next steps

1. Add a controlled ablation for current pipeline scorer with NMS disabled.
2. Compare current pipeline scored output against legacy scored output page by page.
3. If NMS is confirmed as the cause, make NMS optional or align it with legacy behavior for Issue #120 canonical mode.
4. After pipeline scorer reproduces Stage B, proceed to Stage C: seed/candidate regeneration.
5. Keep `verify_repro_batch_final.py` non-canonical and plan deletion/archive after the Stage B wrapper is accepted.
