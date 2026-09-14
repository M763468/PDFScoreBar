# Issue #277 classifier-geometry handoff

This note is experiment-branch only. It records why classifier training has become a
separate investigation boundary before further OCR production work.

## Observed #277 evidence

On the maintained-HOMR candidate-native geometry sensitivity slice, the current MMR
classifier probability crossed the production 0.5 threshold for three measures under
only +/-1/2/4 px support-geometry perturbations:

- page_010 s2 m1: approximately 0.318 -> 0.609 (positive fixture)
- page_011 s8 m0: approximately 0.327 -> 0.701 (negative fixture)
- page_033 s0 m0: approximately 0.443 -> 0.716 (negative/one-bar control)

This means OCR-only robustness cannot by itself guarantee stable final MMR behavior.

## Existing checkpoint provenance

The checkpoint used by the #277 probes is:

`tools/mmr_training/models/mmr_classifier_best.pth`

Git history shows that this file was added in commit
`b01bf49a2d87c4ddccab7c2b98b2dcf7f43976a7` and has not been replaced since.
The corresponding Session Log records the original training as roughly 3700 samples,
192 positives, ResNet18, 20 epochs, batch size 32, with validation F1 > 0.99.

The original training transform included:

- resize to 224x224;
- random horizontal flip;
- random rotation +/-5 degrees;
- brightness/contrast jitter.

It did **not** include measure-bbox translation/expansion/contraction jitter matching the
current +/-1..4 px support-geometry failure mode. Dataset generation materialized each
measure crop from one numbering bbox with a fixed 20 px margin.

A later text-noise/staff-mask training experiment refreshed the dataset and added music
text overlays, weighted sampling, AdamW and cosine scheduling. That experiment produced
a separate text-noise checkpoint and did not replace the tracked
`mmr_classifier_best.pth`; it also did not directly train support-geometry invariance.

## Recommended separation

Keep Issue #277 focused on OCR/reliability policy. Treat classifier checkpoint changes as
a separate child investigation because they require their own dataset, split,
retraining, model-artifact and validation contract.

After a classifier candidate is accepted or rejected, rerun the #277 OCR stability and
full68 gates with that fixed classifier before deciding whether any OCR production change
is still necessary.
