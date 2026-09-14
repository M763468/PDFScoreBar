# [Investigation] Make the MMR classifier robust to small support-geometry perturbations

## Parent / context

Follow-up from #277 and blocker-analysis for #294.

Issue #277 established that OCR is not the only geometry-sensitive MMR component. On the maintained-HOMR candidate-native sensitivity slice, the MMR classifier itself crosses the current 0.5 threshold under only +/-1/2/4 px support-geometry changes:

- `page_010 s2 m1`: approximately `0.318 -> 0.609` (positive fixture)
- `page_011 s8 m0`: approximately `0.327 -> 0.701` (negative fixture)
- `page_033 s0 m0`: approximately `0.443 -> 0.716` (negative / one-bar control)

Therefore an OCR-only fix cannot guarantee stable final behavior when #294 changes the authoritative HOMR geometry producer.

## Existing training provenance

The checkpoint used by the current #277 probes is:

`tools/mmr_training/models/mmr_classifier_best.pth`

Git history shows that this file was added in `b01bf49a2d87c4ddccab7c2b98b2dcf7f43976a7` and has not been replaced since.

The recorded original training contract was approximately:

- dataset: ~3700 measure crops / 192 positives;
- model: ImageNet-pretrained ResNet18, binary head;
- source crop: one numbering measure bbox with fixed 20 px margin;
- train/val: random per-class 80/20 split, seed 42;
- training: 20 epochs, batch size 32, Adam, BCEWithLogitsLoss with positive class weight;
- input: every crop warped to `224x224`;
- augmentation: horizontal flip, +/-5 degree rotation, brightness/contrast jitter;
- no source-space measure bbox translation/expansion/contraction augmentation.

A later text-noise/staff-mask experiment added positive-only text overlays, weighted sampling, AdamW and cosine scheduling and trained a separate checkpoint, but it did not replace the tracked checkpoint and did not directly train support-geometry invariance.

## Goal

Determine whether the MMR classifier can be made robust to the small support-geometry changes actually observed in #294 and to reasonable resolution/crop variation on unseen scores, without weakening semantic precision or moving instability into OCR.

This issue owns classifier/data/training work only. It must not absorb the OCR policy work from #277.

## Phase 0 — reproduce and freeze the current classifier contract

Before retraining:

1. confirm the exact checkpoint used by the current production/validation MMR route and its SHA-256;
2. reconstruct the known training command/config as far as repository evidence supports;
3. run classifier-only inference on retained #277 candidate-native crops and confirm the three threshold-crossing controls above;
4. retain probability distributions, not only thresholded labels.

If production does not use the tracked checkpoint above, record the real checkpoint/provenance and update the rest of this issue accordingly.

## Phase 1 — build a classifier-only robustness benchmark

Do not involve RapidOCR yet.

Use retained candidate-native geometry and evaluate at least:

- native geometry;
- measure `x1` +/-1/2/4 px;
- measure `x2` +/-1/2/4 px;
- whole-measure x translation +/-1/2/4 px;
- staff y translation +/-1/2/4 px where classifier input depends on it;
- a small DPI/resolution metamorphic set with coordinates scaled consistently.

Evaluate positives and negatives, including current #277/#276 controls and zero-fixture/one-bar negatives.

Report:

- threshold crossings at 0.5 and rescue threshold 0.1;
- probability range per semantic sample;
- calibration/margin distribution;
- false-positive / false-negative changes across perturbations.

## Phase 2 — training-data and input-contract candidates

Evaluate causally, one family at a time. Start with the existing ResNet18 before changing architecture.

### A. Source-space geometry augmentation

Regenerate or dynamically crop from the original page so one semantic measure is seen under bounded support-geometry variation. Cover both positive and negative labels.

Prefer staff-relative or scale-relative perturbations derived from the observed #294 envelope rather than a page-specific fixed rule. Include translation and slight expansion/contraction; do not use expected OCR numbers.

Split by source measure/page **before** augmentation so sibling crops cannot leak across train/validation.

### B. Aspect-preserving input normalization

The current pipeline warps wide measure rectangles directly to 224x224. Compare an aspect-preserving letterbox/pad contract, because small source-crop changes currently alter the global interpolation geometry after square resize.

### C. Consistency training only if needed

If ordinary geometry augmentation is insufficient, evaluate a light consistency objective across perturbations of the same semantic crop. Keep the decision contract explainable and bounded.

### D. Alternative lightweight model only if A-C are insufficient

A different backbone (for example MobileNet/EfficientNet-class lightweight models) is allowed only after the input/data hypothesis is tested. Do not change architecture merely to add capacity.

## Phase 3 — out-of-sample validation

The current random crop-level split is not sufficient evidence for unseen-score robustness.

At minimum:

- use a whole-score or whole-page-group holdout where practical;
- prevent augmented siblings from crossing split boundaries;
- report per-score metrics and the geometry-stability benchmark on held-out scores;
- keep a negative-heavy guard set for unrelated numeric/text content.

If available data is insufficient for a meaningful holdout, record that limitation explicitly rather than claiming generalization.

## Acceptance candidate

A classifier candidate is promising only if it:

- materially reduces or eliminates classifier threshold crossings under the observed +/-4 px geometry envelope;
- preserves or improves classifier precision/recall on the canonical retained corpus;
- does not create new negative/one-bar false positives on the #277 controls;
- improves held-out-score stability or exposes explicit uncertainty rather than overclaiming OOS generalization;
- has bounded runtime/memory impact;
- has reproducible dataset/split/training metadata.

Do not accept a model solely because aggregate validation F1 is high.

## Handoff back to #277

After one classifier candidate is accepted (or classifier retraining is rejected with evidence):

1. freeze the classifier checkpoint;
2. rerun #277 focused/risk OCR evaluation on maintained-HOMR candidate-native geometry;
3. rerun the +/-1/2/4 px semantic stability envelope;
4. only then decide whether OCR policy changes are still required;
5. if an OCR candidate remains, run the required geometry-rebased full68 gate before production.

## Model artifact policy

Do not add another large ad-hoc `.pth` to normal Git history merely for an experiment. Keep experiment checkpoints under ignored/artifact storage and record hashes/run metadata. If the repository's model-release manifest/materialization contract from #315 is available when a new production checkpoint is accepted, use that contract (or the then-current equivalent).

## Constraints

- no page/score/coordinate-specific training labels or runtime rules;
- no broad threshold relaxation as a substitute for robustness;
- no RapidOCR changes in this issue;
- no detector/HOMR/SR/OMR behavior changes;
- historical geometry may be evaluation evidence only, never a runtime signal;
- preserve MMR `1` / one-bar semantics at the integrated gate.

## Relationship

- #277 — parent OCR/reliability investigation; resume integrated OCR work after this classifier disposition.
- #294 — maintained HOMR baseline replacement; depends on stable downstream MMR behavior.
- #276 — original crop-geometry robustness investigation.
- #315 — model artifact lifecycle / release-manifest direction.
