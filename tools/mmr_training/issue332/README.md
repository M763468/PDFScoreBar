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

## Run

From the repository root, with the model/data environment already materialized:

```bash
uv run python tools/mmr_training/issue332_geometry_benchmark.py \
  --manifest /path/to/issue332_manifest.json \
  --model tools/mmr_training/models/mmr_classifier_best.pth \
  --config tools/mmr_training/issue332/benchmark_config.json \
  --output logs/issue332/baseline_geometry.json
```

The committed config evaluates native crop geometry plus source-space `x1`, `x2`, x-translation, y-translation, and symmetric x expand/contract at +/-1/2/4 px. It also applies coherent whole-page DPI metamorphs at 0.8x/1.0x/1.25x. Source coordinates scale with the page; the production fixed 20 px margin remains fixed so resolution sensitivity is measured rather than hidden.

Both current direct `224x224` warp and an experimental aspect-preserving white letterbox can be measured from the same source variants. The direct result is the production-contract baseline; letterbox is only an input-contract candidate.

The output records checkpoint/config/manifest SHA-256, runtime identity, every probability, decisions at 0.5 and 0.1, per-sample min/max/range/max-delta, threshold crossings, and mean inference time. Retain output under ignored `logs/issue332/` unless the repository artifact policy explicitly says otherwise.

## Split/training rule

Any retraining dataset must freeze score/page/semantic-measure membership before generating perturbations. Augmented siblings from one semantic measure must never cross train/validation/test boundaries. Prefer whole-score holdout; otherwise use page-group holdout and report per-score results.
