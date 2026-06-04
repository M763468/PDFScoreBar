# Issue #45: CNN Script Inventory and Cleanup Policy

Status: active cleanup branch (`cleanup/issue45-cnn-script-organization`)
Base: `develop`
Date: 2026-06-04

This document records the inventory and placement decisions for CNN-related and CNN-adjacent scripts found under `experiments/` and `tools/`.

Issue #45 is not limited to documentation. Scripts that are clearly one-off diagnostics, temporary visualization helpers, or historical bootstrap utilities may be moved or deleted when repository references have been checked. Deleted paths remain recoverable through Git history.

## Current pipeline boundary

The production pipeline should not depend on ad-hoc scripts in `tools/` or `experiments/`. Current `src/pipeline` code has an in-process CNN scoring implementation under `src/pipeline/steps/cnn_scoring.py` and the detector orchestrator calls that module directly.

Known follow-up candidate:

- `src/pipeline/steps/cnn_scoring.py` still falls back to searching `experiments/cnn_classifier/**/best_model.pth` when the configured model path is missing. This is not a direct function call into `experiments/`, but it is still an implicit experiment-directory dependency and should be removed or made explicit in a follow-up issue.

## Placement rules

| Location | Intended content |
| --- | --- |
| `src/pipeline/` | Current production pipeline implementation. Must not import from `tools/` or `experiments/`. |
| `tools/cnn_classifier/` | Reusable CNN utilities that are still part of a documented training/evaluation workflow. |
| `experiments/cnn_classifier/` | Training and research scripts that are not production runtime code. |
| `experiments/cnn_classifier/active_learning/` | Historical or optional active-learning utilities. |
| `tools/diagnostics/` | Generic diagnostic/visualization utilities not specific to production runtime. |
| deleted path | One-off diagnostics, bootstrap scripts, or stale prototype scripts. Recover through Git history. |

## Cleanup decisions in this branch

### Deleted one-off or obsolete scripts

| Path | Reason |
| --- | --- |
| `experiments/cnn_classifier/debug_probe_values.py` | One-off pixel/probe value inspection for the 2026-01-05 FN diagnosis. |
| `experiments/cnn_classifier/inference_visualize.py` | Prototype inference/overlay script superseded by `tools/cnn_classifier/score_candidates_batch.py` and then by `src/pipeline/steps/cnn_scoring.py`. |
| `tools/cnn_classifier/create_provisional_gt.py` | One-time provisional GT bootstrap utility for evaluation2. |
| `tools/cnn_classifier/finalize_gt.py` | One-time GT finalization copier for the 2026-01-06 provisional GT flow. |
| `tools/analyze_fn_prokofiev.py` | Hard-coded Prokofiev/page/log-path FN diagnosis script. |

### Moved scripts

| Old path | New path | Reason |
| --- | --- | --- |
| `tools/cnn_classifier/extract_fps_by_score_range.py` | `experiments/cnn_classifier/active_learning/extract_fps_by_score_range.py` | v4 FP-based active-learning experiment helper. It is not part of the active production pipeline. |
| `tools/visualize_error_crops.py` | `tools/diagnostics/visualize_error_crops.py` | Generic error-crop visualization, useful for analysis but not CNN production runtime. |

### Kept scripts

| Path | Reason |
| --- | --- |
| `tools/cnn_classifier/score_candidates_batch.py` | Historical and standalone batch CNN scorer. Still useful for reproducing old evaluations, but production pipeline should use `src/pipeline/steps/cnn_scoring.py`. |
| `tools/cnn_classifier/build_cnn_dataset.py` | Dataset builder for CNN retraining. |
| `experiments/cnn_classifier/train.py` | Current documented CNN training entry point. If retraining becomes official production maintenance, consider moving it into `tools/cnn_classifier/`. |
| `tools/re_evaluate_global.py` | Evaluation aggregation utility used by historical and current validation workflows. |
| `tools/run_eval_experiment.py` | Candidate-generation/evaluation wrapper used by historical best-configuration reproduction. |
| `tools/cnn_classifier/create_gt_gui_config.py` | Still potentially useful as a GT GUI config generator, but should be reviewed for relocation to `tools/gt_relabel_gui/`. |

## Recovering deleted scripts

Use Git history when a deleted one-off script is needed for archaeology:

```bash
git log --follow -- <old-path>
git show <commit>:<old-path>
```

For example:

```bash
git log --follow -- experiments/cnn_classifier/inference_visualize.py
git show 23c7a64:experiments/cnn_classifier/inference_visualize.py
```

## Validation expectation

For this cleanup branch, run at least:

```bash
git diff --check
PYTHONPATH=. python3 -m py_compile \
  experiments/cnn_classifier/train.py \
  experiments/cnn_classifier/active_learning/extract_fps_by_score_range.py \
  tools/diagnostics/visualize_error_crops.py \
  tools/cnn_classifier/score_candidates_batch.py
make test-fast
```

If additional production pipeline dependencies on `tools/` or `experiments/` are discovered, do not paper over them in this cleanup issue unless the change is trivial. Record them as follow-up refactoring candidates.
