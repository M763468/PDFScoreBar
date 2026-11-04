# Community 108

> 24 nodes · cohesion 0.14

## Key Concepts

- **BarlinePrediction** (18 connections) — `src/homr_eval_scripts/homr_evaluator.py`
- **BarlineMatch** (14 connections) — `src/common/barline_evaluation.py`
- **BarlineMatchResult** (14 connections) — `src/common/barline_evaluation.py`
- **BarlineSoftMatch** (14 connections) — `src/common/barline_evaluation.py`
- **.predict()** (13 connections) — `src/homr_eval_scripts/homr_evaluator.py`
- **HomrPredictor** (9 connections) — `src/homr_eval_scripts/homr_evaluator.py`
- **run_homr_on_image()** (9 connections) — `src/homr_eval_scripts/homr_evaluator.py`
- **TransformInfo** (8 connections) — `src/homr_eval_scripts/homr_evaluator.py`
- **AggregateMetrics** (7 connections) — `src/homr_eval_scripts/core/metrics.py`
- **compute_metrics()** (7 connections) — `src/homr_eval_scripts/homr_evaluator.py`
- **draw_overlay()** (7 connections) — `src/homr_eval_scripts/homr_evaluator.py`
- **filter_detections_by_notehead_proximity()** (7 connections) — `src/homr_eval_scripts/homr_evaluator.py`
- **enable_segnet_cache()** (6 connections) — `src/homr_runtime/segnet_cache.py`
- **count_staff_crossings()** (5 connections) — `src/homr_eval_scripts/homr_evaluator.py`
- **map_pred_to_orig()** (4 connections) — `src/homr_eval_scripts/homr_evaluator.py`
- **ProcessingConfig** (4 connections)
- **.__init__()** (3 connections) — `src/homr_eval_scripts/homr_evaluator.py`
- **XmlGeneratorArguments** (3 connections)
- **Counts the number of staff line crossings for a vertical barline candidate. A…** (1 connections) — `src/homr_eval_scripts/homr_evaluator.py`
- **Persistent Homr Predictor for batch processing.** (1 connections) — `src/homr_eval_scripts/homr_evaluator.py`
- **Runs the core homr staff and symbol detection pipeline for a single image with…** (1 connections) — `src/homr_eval_scripts/homr_evaluator.py`
- **Filters barline detections that are horizontally close to noteheads, which are…** (1 connections) — `src/homr_eval_scripts/homr_evaluator.py`
- **.total_scale()** (1 connections) — `src/homr_eval_scripts/homr_evaluator.py`
- **Patch homr.segmentation.inference_segnet.Segnet with a cached variant.** (1 connections) — `src/homr_runtime/segnet_cache.py`

## Relationships

- [Community 40](Community_40.md) (41 shared connections)
- [Community 0](Community_0.md) (18 shared connections)
- [Community 143](Community_143.md) (8 shared connections)
- [Community 49](Community_49.md) (5 shared connections)
- [Community 97](Community_97.md) (5 shared connections)
- [Community 15](Community_15.md) (3 shared connections)
- [Community 273](Community_273.md) (1 shared connections)
- [Community 1](Community_1.md) (1 shared connections)

## Source Files

- `src/common/barline_evaluation.py`
- `src/homr_eval_scripts/core/metrics.py`
- `src/homr_eval_scripts/homr_evaluator.py`
- `src/homr_runtime/segnet_cache.py`

## Audit Trail

- EXTRACTED: 93 (78%)
- INFERRED: 27 (22%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*