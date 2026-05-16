# Issue 120 Historical Best Accuracy Audit

## Purpose

This document records the completed #136 audit that was merged by PR #143. It separates detector-level evidence from full-pipeline reproduction claims.

The key distinction is:

1. saved scored intermediates can reproduce the detector target;
2. saved or regenerated candidates can reproduce the detector target when current CNN scoring runs with `cnn_apply_nms=false`;
3. slow upstream HOMR/OMR/SR artifact regeneration is still not proven.

## Completed audit status

PR:

```text
#143 docs/tools: audit Issue 120 historical best and reconstruction path
merge commit: 0c0eaafcb9dda3c3d48be2db6cea41c603187f0a
base: rebuild/issue120
```

Issue:

```text
#136 closed by #143
```

## Current verified detector target

The current detector-level target is:

```text
TP=3580 / FP=0 / FN=1
```

This is a detector metric, not a downstream measure-count metric.

Canonical evaluator:

```bash
make eval-issue120-full
```

The evaluator validates the canonical 68-page `evaluation2` manifest and writes regenerated summaries under ignored `logs/` paths.

## Stage A: saved scored intermediates

Input:

```text
data/evaluation2/golden_baseline_eval2_bc23deb/**/pipeline2_no_peak_scored.json
```

Result:

```text
Pages: 68/68
Detector: GT=3581 Pred=3597 TP=3580 FP=0 FN=1 FN_det=0 FN_cnn=1 Precision=1.000000 Recall=0.999721
```

Interpretation:

- The saved post-CNN-scoring detector intermediates reproduce the detector target under the #134 canonical evaluator.
- This does not prove full pipeline reproduction.

## Stage B: saved candidates -> CNN scoring -> canonical evaluation

Input:

```text
data/evaluation2/golden_baseline_eval2_bc23deb/**/pipeline2_no_peak_candidates.json
```

Stage B isolates this layer:

```text
saved candidates
  -> CNN scoring / scoring-side filtering
  -> canonical full-68 detector evaluation
```

Observed results:

```text
saved candidates + legacy scorer:
  Pred=3597 TP=3580 FP=0 FN=1

saved candidates + pipeline scorer + NMS enabled:
  Pred=3507 TP=3507 FP=0 FN=74

saved candidates + pipeline scorer + NMS disabled:
  Pred=3597 TP=3580 FP=0 FN=1
```

Interpretation:

- The saved candidates, model artifact, images, GT, and current CNN inference path are sufficient to reproduce the detector target.
- The Stage B regression is caused by current pipeline CNN scoring NMS.
- #142 later changed the general CNN scoring default to `cnn_apply_nms=false`; NMS is retained as an explicit opt-in setting.
- Issue #120 reconstruction must explicitly record `cnn_apply_nms=false`.

Primary Stage B command:

```bash
make verify-issue120-stage-b ISSUE120_CLEAN_OUTPUT=1
```

Optional historical staff-band input:

```bash
make verify-issue120-stage-b \
  ISSUE120_CLEAN_OUTPUT=1 \
  ISSUE120_BANDS_FROM=logs/cnn_barline_classification/issue44_baseline_v1/scoring_input_eval2_v12
```

## Stage C: regenerated candidates -> CNN scoring -> canonical evaluation

The previous `reproduce_clean_seed_v12.py` path was tested and found not to regenerate the full Golden Baseline candidate layer:

```text
baseline candidates: 29443
regenerated candidates: 180
empty pages: 40
```

This path is treated as a residual/rescue/filtered-subset experiment, not the canonical full candidate regeneration path.

The recovered #57 / Issue53 probe-rescue path is the current clean detector-level candidate regeneration path:

```text
Issue53 probe rescue candidates:
  baseline candidates: 29443
  regenerated candidates: 29772
  empty pages: 0
  detector result: TP=3580 FP=0 FN=1
```

Current Stage C verifier:

```bash
docker run --rm --gpus all \
  -v "$PWD":/workspace \
  -w /workspace \
  -e PYTHONPATH=/workspace \
  pdfscore_pipeline_gpu \
  /opt/venv_pipeline/bin/python tools/issue120/run_issue53_probe_rescue_then_eval.py
```

## Current clean detector-level reconstruction target

```text
#57 / Issue53 probe rescue candidate generation
  -> current pipeline CNN scoring
  -> cnn_apply_nms=false
  -> #134 canonical full-68 evaluator
  -> TP=3580 FP=0 FN=1
```

This is the clean detector-level target until a later audited issue changes it.

## Remaining limitation

The Stage C path still depends on the historical `bands_from` artifact:

```text
logs/cnn_barline_classification/issue44_baseline_v1/scoring_input_eval2_v12
```

That artifact has not yet been regenerated from the current slow upstream HOMR/OMR/SR pipeline.

Stage D (#140) owns this boundary:

```text
HOMR / OMR / SR / SR-side HOMR / OMR-DLN or equivalent
  -> bands_from-like artifact
  -> Issue53 probe rescue Stage C
  -> canonical evaluator
```

## Artifact evidence and retention

The retained detector-intermediate fixture is:

```text
data/evaluation2/golden_baseline_eval2_bc23deb/
```

Retained per-page evidence:

```text
pipeline2_no_peak_candidates.json
pipeline2_no_peak_filtered_cnn.json
pipeline2_no_peak_scored.json
```

Retained metadata:

```text
eval_config.yaml
```

Generated summaries such as `global_summary.csv` are not evaluator inputs and should be regenerated under ignored `logs/` output paths rather than tracked.

The retention policy is documented in:

```text
docs/ISSUE120_ARTIFACT_RETENTION.md
```

## Historical evidence inventory

### PR #57: Issue #44 final baseline

- PR: #57 `feat(cnn): finalize baseline retraining and improve staff clustering logic (#44)`
- Head branch: `task/cnn-barline-classifier-retrain-eval2-gt`
- Head commit: `b58b988979573e651c5a2f57270ebc1c830135b4`
- Merge commit: `87fb6d0a47294d7879500285a62e519373498b65`
- Recovered script: `experiments/issue53_probe_rescue/evaluate_full_rescue_v1.py`

Recovered script behavior:

```text
bands_from = logs/cnn_barline_classification/issue44_baseline_v1/scoring_input_eval2_v12
output_root = logs/issue53_full_eval_rescue_v1
model_path = logs/cnn_barline_classification/issue44_iter7_final_rescue_v1/cnn_classifier_best.pth
```

### PR #127: Golden Baseline introduction

- Merge commit: `7d3fbf89dcd52b22b3919d36a30b2d46959fdd84`
- Added the saved Golden Baseline tree.
- Added `tools/repro_accuracy/verify_golden_baseline.py`.
- Limitation: introduced saved outputs; did not prove current full regeneration.

### PR #139: canonical intermediate evaluator

- Merge commit: `0febdf8da383c26367b20d75ca98f4554190f2c9`
- Added `make eval-issue120-full`.
- Verified saved post-CNN-scoring intermediates only.

### PR #143: completed #136 audit

- Merge commit: `0c0eaafcb9dda3c3d48be2db6cea41c603187f0a`
- Added Stage B/C tooling and policy docs.
- Defined the clean detector-level reconstruction target.
- Left Stage D/E full-upstream boundaries open.

## Follow-up issues

- #135: generated artifact cleanup and retention policy.
- #140: Stage D slow upstream artifact regeneration.
- #142: NMS repair/tuning.
- #141: Stage E full 68-page pipeline validation.
- #137: targeted accuracy repair after audit/policy gates.
