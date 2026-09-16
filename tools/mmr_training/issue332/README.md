# Issue #332 classifier geometry benchmark

This directory contains the classifier-only experiment contract for Issue #332. It does not call RapidOCR and must not be used to alter production thresholds or runtime policy.

## Manifest contract

Create a local JSON manifest with a top-level `samples` list. Each sample must contain:

- `sample_id`: stable semantic-measure identifier;
- `score_id`: score-level grouping key;
- `page_id`: page-level grouping key;
- `image_path`: source page image, absolute or relative to the manifest;
- `bbox`: candidate-native semantic measure `[x1, y1, x2, y2]` in source-page pixels;
- `label`: classifier ground truth, `0` or `1`;
- optional `tags`: e.g. `positive`, `negative`, `zero-fixture`, `one-bar`, `issue277-control`.

Do not put expected OCR numbers in the manifest. Labels and tags are evaluation metadata only and are never used to adapt crops or inference.

The required Phase-0 classifier controls from #332 are `page_010 s2 m1`, `page_011 s8 m0`, and `page_033 s0 m0`. Add the retained #276/#277 negative, zero-fixture, and one-bar controls to the same manifest before treating a run as an acceptance benchmark.

## Geometry benchmark

From the repository root, with the model/data environment already materialized:

```bash
python tools/mmr_training/issue332_geometry_benchmark.py \
  --manifest /path/to/issue332_manifest.json \
  --model tools/mmr_training/models/mmr_classifier_best.pth \
  --config tools/mmr_training/issue332/benchmark_config.json \
  --output logs/issue332/baseline_geometry.json
```

The committed config evaluates native crop geometry plus source-space `x1`, `x2`, x-translation, y-translation, and symmetric x expand/contract at +/-1/2/4 px. It also applies coherent whole-page DPI metamorphs at 0.8x/1.0x/1.25x. Source coordinates scale with the page; the production fixed 20 px margin remains fixed so resolution sensitivity is measured rather than hidden.

Both current direct `224x224` warp and an experimental aspect-preserving white letterbox can be measured from the same source variants. The direct result is the production-contract baseline; letterbox is only an input-contract candidate.

The output records checkpoint/config/manifest SHA-256, runtime identity, every probability, decisions at 0.5 and 0.1, per-sample min/max/range/max-delta, threshold crossings, and mean inference time. Retain output under ignored `logs/issue332/` unless the repository artifact policy explicitly says otherwise.

## Issue #332 terminology and coordinate contract

The following terms are normative for the Issue #332 artifacts. The formulas use
the source-page bbox `(x1, y1, x2, y2)` and a signed pixel delta `d`. The
implementation samples `abs(d)` from `{1, 2, 4}` and independently samples the
sign, so the effective values are `-1, -2, -4, +1, +2, +4` pixels.

- **native**: Leave the source-manifest bbox unchanged, crop the source page
  with the fixed `20 px` margin, then apply the production direct `224x224`
  input transform.
- **source-space geometry augmentation**: Change the measure bbox in original
  source-page coordinates before the fixed-margin crop and before the `224x224`
  resize. It does not alter the page image itself.
- **absolute geometry augmentation**: Use fixed source-page pixel deltas
  `d ∈ {-4, -2, -1, +1, +2, +4}`. No staff-height or other resolution
  normalization is applied.
- **all-family absolute**: Select one family uniformly from `x1`, `x2`,
  `translate-x`, `translate-y`, and `expand/contract-x` for each perturbed
  semantic sample.
- **family-targeted absolute**: Restrict that selection to the family or
  families explicitly supplied by `--geometry-augmentation-family`; a
  single-family run selects only that family.
- **augmentation probability `p`**: For each semantic training sample in each
  epoch, apply one source-space perturbation with probability `p`. With
  probability `1-p`, use the native bbox. Thus p10, p25, and p50 mean `0.10`,
  `0.25`, and `0.50`, respectively. Validation and test use native geometry.

The five absolute families are exactly these coordinate transforms:

| Family | Transformed bbox |
| --- | --- |
| `x1` | `(x1 + d, y1, x2, y2)` |
| `x2` | `(x1, y1, x2 + d, y2)` |
| `translate-x` | `(x1 + d, y1, x2 + d, y2)` |
| `translate-y` | `(x1, y1 + d, x2, y2 + d)` |
| `expand/contract-x` | `(x1 - d, y1, x2 + d, y2)`; positive `d` expands and negative `d` contracts |

These definitions are asserted by
`tests/test_issue332_geometry_dataset.py::test_geometry_family_coordinates_match_benchmark_contract`.

- **direct resize**: Resize the cropped image directly to `(224, 224)` with
  `torchvision.transforms.Resize`, allowing independent horizontal and
  vertical scaling (the production input contract).
- **aspect-preserving resize + letterbox**: Resize while preserving the crop's
  aspect ratio, then pad the remaining area to a `224x224` canvas. This is an
  experimental input-contract comparison, not the current baseline contract.
- **main crossing (0.5)**: A semantic sample for which native and at least one
  source-space perturbation make different binary decisions at probability
  threshold `0.5` (`p >= 0.5` is positive).
- **rescue crossing (0.1)**: The same definition at the rescue threshold
  `0.1`.
- **native FP**: A native sample with label `0` whose native probability is at
  least `0.5`.
- **perturbation crossing**: A main- or rescue-threshold crossing caused by a
  perturbation relative to that sample's native decision. A sample is counted
  once per threshold even if several families or deltas cross; the detailed
  artifact retains every crossing family, delta, sign, and probability.

## Split/training rule

The regular `tools/mmr_training/train_mmr_classifier.py` entrypoint is the authoritative training path. In semantic-manifest mode it excludes retained acceptance controls before splitting, freezes train/validation/test membership by complete score groups (falling back to page groups only when required for class coverage), and reuses the same split artifact across baseline and candidate runs.

Geometry augmentation is sampled on-the-fly from the source-page bbox. One semantic sample remains one training item per epoch, so an augmentation candidate does not gain extra optimizer steps merely because more perturbation variants exist. Validation and test always use native geometry; test metrics are computed only after the best validation-F1 checkpoint has been selected.

Semantic-manifest mode defaults to the recorded production-checkpoint training profile: 20 epochs, batch size 32, Adam, BCEWithLogitsLoss positive weighting, no weighted sampler, no positive-only text-noise overlay, and no cosine scheduler. The later AdamW/text-noise experiment remains available through `--training-profile current` but is not part of the primary Issue #332 causal comparison.

Baseline example:

```bash
python tools/mmr_training/train_mmr_classifier.py \
  --manifest /path/to/training_manifest.json \
  --acceptance-manifest logs/issue332/acceptance_controls_manifest.json \
  --split-manifest logs/issue332/training_split_v1.json \
  --geometry-config tools/mmr_training/issue332/geometry_augmentation_config.json \
  --training-profile historical \
  --geometry-augmentation none \
  --output-model logs/issue332/models/retrain_baseline.pth \
  --metrics-output logs/issue332/retrain_baseline_metrics.json
```

Absolute-pixel geometry candidate:

```bash
python tools/mmr_training/train_mmr_classifier.py \
  --manifest /path/to/training_manifest.json \
  --acceptance-manifest logs/issue332/acceptance_controls_manifest.json \
  --split-manifest logs/issue332/training_split_v1.json \
  --geometry-config tools/mmr_training/issue332/geometry_augmentation_config.json \
  --training-profile historical \
  --geometry-augmentation absolute \
  --output-model logs/issue332/models/geometry_aug_v1.pth \
  --metrics-output logs/issue332/geometry_aug_v1_metrics.json
```

The two runs above share the same frozen split, optimizer/training profile, and semantic epoch length. Their intended causal difference is source-space bbox augmentation only.
