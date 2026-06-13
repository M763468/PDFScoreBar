# Issue #206 context-FOV experiment path

This document records the first repository-side experiment path for #206.
It intentionally does not train, retrain, or change the production scoring default.

## Scope

- Add a shared crop-contract helper for CNN candidate crops.
- Add a proxy-free preview helper for comparing `current_like`, `wider_x`, and `square_context` crops.
- Keep the existing default crop behavior compatible with the historical binary CNN setting.
- Defer multi-class training until real-domain accidental-like labels are defined.

## Baseline policy

- Use current `develop` tooling and data roots as canonical inputs.
- Do not use PR #204 logs/configs as current evidence.
- Do not treat the exact historical L1.5 `0.6585` artifact as recovered.
- Treat crop-only high-clefs artifacts as references, not safety evidence.
- Use full-68 scoring/evaluation as the safety gate only after explicit approval.

## Local smoke commands

From the repository root after pulling `task/issue206-context-fov-contract`:

```bash
python3 -m py_compile \
  tools/cnn_classifier/crop_contract.py \
  tools/cnn_classifier/preview_context_crops.py
```

Generate target-page context previews without scoring or training:

```bash
python3 tools/cnn_classifier/preview_context_crops.py \
  --manifest configs/cnn_barline_runs/issue206_context_fov_preview_manifest.example.json \
  --output-dir logs/issue206_context_fov_preview/manual_target_preview \
  --variant current_like \
  --variant wider_x \
  --variant square_context \
  --max-crops 9
```

Expected outputs:

- `logs/issue206_context_fov_preview/manual_target_preview/summary.md`
- `logs/issue206_context_fov_preview/manual_target_preview/preview_manifest.json`
- `logs/issue206_context_fov_preview/manual_target_preview/preview_manifest.csv`
- `logs/issue206_context_fov_preview/manual_target_preview/preview_crops/*.png`

## Next implementation step

After the preview helper is validated locally, the next code step should wire the shared crop contract into both:

- `tools/cnn_classifier/build_cnn_dataset.py`
- `tools/cnn_classifier/score_candidates_batch.py`

That wiring should be done in a separate commit so default behavior can be tested against current outputs before any context-FOV scoring experiment.
