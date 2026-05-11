# Issue 120 CNN Scoring NMS Policy

## Purpose

This document records what the CNN scoring NMS step means, why it exists, what Stage B proved, and how Issue #120 should handle it going forward.

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

Therefore, NMS is not inherently wrong. It can be useful as a precision and stability mechanism.

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

This does not prove that NMS should be globally removed. It proves only that the current NMS rule is not compatible with the Issue #120 historical detector target on the canonical 68-page saved candidates.

The current NMS rule suppresses true-positive candidates that the historical scorer retained. Because the false-positive count is already `0` in the historical target, this specific NMS application removes recall without improving precision for this benchmark.

## Policy

### Default behavior

Keep NMS enabled by default in the general pipeline until a broader accuracy comparison proves that changing the default is safe.

### Issue #120 reconstruction behavior

Issue #120 canonical reconstruction may disable CNN scoring NMS explicitly.

This must be explicit in config, command, or provenance. A result produced with NMS disabled must not be described as using default pipeline scoring.

### Required recording

Any Issue #120 metric report must record:

```text
cnn_apply_nms: true|false
```

or equivalent provenance field.

### Forbidden shortcut

Do not silently remove or weaken NMS globally just to recover the historical target.

### Future repair

After Stage C/D/E determine the candidate-generation path, NMS can be repaired or tuned under #137. Candidate approaches include:

- disable NMS only for Issue #120 canonical reconstruction;
- make NMS thresholds configurable;
- replace the current X-distance suppression with a more conservative rule;
- apply NMS only where it improves downstream measure-count metrics;
- compare detector metrics and measure-count metrics before accepting any new default.

## Current decision

For #136:

```text
cnn_apply_nms=false
```

is the canonical Stage B setting for reproducing the historical detector target from saved candidates using the current pipeline scorer.

For general pipeline operation:

```text
cnn_apply_nms=true
```

remains the default until #137 or a later PR changes it with evidence.
