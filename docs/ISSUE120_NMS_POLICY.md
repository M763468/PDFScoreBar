# Issue 120 CNN Scoring NMS Policy

## Purpose

This document records what the CNN scoring NMS step means, why it exists, what Stage B proved, and how Issue #120 / #142 should handle it going forward.

## What NMS means here

NMS means non-maximum suppression.

In `src.pipeline.steps.cnn_scoring`, NMS is applied after CNN scoring and thresholding. It takes candidates whose CNN score is above the threshold and suppresses boxes that appear to represent the same barline as a higher-scoring box.

The current implementation uses two suppression tests:

1. IoU overlap between two boxes.
2. Horizontal center distance when vertical overlap is high.

Suppressed boxes have their score set to `0.0`, so they no longer appear in `pipeline2_no_peak_filtered_cnn.json` and no longer count as predictions under the canonical evaluator.

## Intended role of NMS

NMS is intended to reduce duplicate detections.

Without NMS, a detector can emit multiple nearby boxes around the same visual barline. Those duplicates may become false positives under a one-to-one matching evaluator or may cause downstream measure-count instability.

Therefore, NMS is not inherently wrong. It can be useful as a precision and stability mechanism, but it must earn default status with measured evidence.

## What Stage B proved

Stage B isolates this layer:

```text
saved candidates
  -> CNN scoring / scoring-side filtering
  -> canonical full-68 detector evaluation
```

The saved Golden Baseline candidates are sufficient to reproduce the historical detector target through the legacy scorer:

```text
Stage A saved scored:           Pred=3597 TP=3580 FP=0 FN=1
Stage B legacy scorer:          Pred=3597 TP=3580 FP=0 FN=1
```

The current pipeline scorer with NMS enabled fails:

```text
Stage B pipeline scorer + NMS:  Pred=3507 TP=3507 FP=0 FN=74
```

The current pipeline scorer with NMS disabled reproduces the historical detector target:

```text
Stage B pipeline scorer no NMS: Pred=3597 TP=3580 FP=0 FN=1
```

## Interpretation

The Stage B regression is caused by the current pipeline scorer's NMS step.

This proves that the current NMS rule is not compatible with the Issue #120 historical detector target on the canonical 68-page saved candidates.

The current NMS rule suppresses true-positive candidates that the historical scorer retained. Because the false-positive count is already `0` in the historical target, this specific NMS application removes recall without improving precision for this benchmark.

The Issue #120 evaluation2 set is not a single-score special case. It contains multiple score patterns and is the current canonical detector benchmark for this reconstruction. With no known counterexample where CNN scoring NMS improves detector accuracy or downstream measure-count metrics, the observed regression is sufficient reason to make NMS opt-in rather than default-on.

## Policy

### Default behavior

Keep CNN scoring NMS disabled by default in the general pipeline.

NMS remains available as an explicit opt-in setting:

```yaml
detection:
  cnn_apply_nms: true
```

Making NMS default-on again requires canonical evidence that it improves, or at least does not regress, detector metrics and downstream measure-count metrics on the relevant evaluation set.

### Issue #120 reconstruction behavior

Issue #120 canonical reconstruction uses CNN scoring NMS disabled. Route configs and provenance should still record the setting explicitly so historical reports remain self-describing.

### Required recording

Any Issue #120 metric report must record:

```text
cnn_apply_nms: true|false
```

or equivalent provenance field.

For #142 policy evidence, report detector metrics and downstream measure-count metrics separately:

```text
TP / FP / FN
measure-count net delta
measure-count absolute delta sum
pages with measure-count delta
```

If downstream measure numbering was not run, record the measure-count fields as `not_provided` rather than mixing detector metrics with proxy conclusions.

### Forbidden shortcut

Do not silently change NMS behavior. The default is now off because the canonical evidence shows a detector regression when it is on. Any run that opts back into NMS must record that setting in config, command output, or provenance.

### Future repair

NMS can be repaired or tuned in a later targeted task. Candidate approaches include:

- make NMS thresholds configurable;
- replace the current X-distance suppression with a more conservative rule;
- apply NMS only where it improves downstream measure-count metrics;
- compare detector metrics and measure-count metrics before accepting any default-on behavior.

## Current decision

For #142:

```text
cnn_apply_nms=false
```

is the general CNN scoring default and the Issue #120 reconstruction setting.

For explicit NMS experiments:

```text
cnn_apply_nms=true
```

is allowed only as an opt-in config/provenance setting. Current canonical evidence does not support default-on behavior.

The summary helper for #142 evidence is:

```bash
python3 tools/issue120/summarize_nms_policy_evidence.py \
  --case stage_b_nms_on=logs/issue120_e2e_recovery/issue142_nms_policy/stage_b_nms_on_eval \
  --case stage_b_nms_off=logs/issue120_e2e_recovery/issue142_nms_policy/stage_b_nms_off_eval \
  --case dense_route_nms_on=logs/issue120_e2e_recovery/issue142_nms_policy/dense_route_nms_on_eval \
  --case dense_route_nms_off=logs/issue120_e2e_recovery/dense_probe_candidate_route/eval
```

Outputs are written under ignored `logs/issue120_e2e_recovery/issue142_nms_policy/`.
