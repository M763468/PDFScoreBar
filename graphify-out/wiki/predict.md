# .predict

> 13 nodes · cohesion 0.17

## Key Concepts

- **.predict()** (13 connections) — `src/homr_eval_scripts/homr_evaluator.py`
- **run_homr_on_image()** (9 connections) — `src/homr_eval_scripts/homr_evaluator.py`
- **filter_detections_by_notehead_proximity()** (7 connections) — `src/homr_eval_scripts/homr_evaluator.py`
- **enable_segnet_cache()** (7 connections) — `src/homr_eval_scripts/segnet_cache.py`
- **count_staff_crossings()** (5 connections) — `src/homr_eval_scripts/homr_evaluator.py`
- **map_pred_to_orig()** (4 connections) — `src/homr_eval_scripts/homr_evaluator.py`
- **ProcessingConfig** (4 connections)
- **.__init__()** (3 connections) — `src/homr_eval_scripts/homr_evaluator.py`
- **XmlGeneratorArguments** (3 connections)
- **Counts the number of staff line crossings for a vertical barline candidate. A…** (1 connections) — `src/homr_eval_scripts/homr_evaluator.py`
- **Runs the core homr staff and symbol detection pipeline for a single image with…** (1 connections) — `src/homr_eval_scripts/homr_evaluator.py`
- **Filters barline detections that are horizontally close to noteheads, which are…** (1 connections) — `src/homr_eval_scripts/homr_evaluator.py`
- **Patch homr.segmentation.inference_segnet.Segnet with a cached variant.** (1 connections) — `src/homr_eval_scripts/segnet_cache.py`

## Relationships

- [homr_evaluator.py](homr_evaluator.py.md) (19 shared connections)
- [ndarray](ndarray.md) (6 shared connections)
- [metrics.py](metrics.py.md) (3 shared connections)
- [ThinBarlineConfig](ThinBarlineConfig.md) (2 shared connections)
- [heuristics.py](heuristics.py.md) (2 shared connections)
- [hybrid.py](hybrid.py.md) (1 shared connections)

## Source Files

- `src/homr_eval_scripts/homr_evaluator.py`
- `src/homr_eval_scripts/segnet_cache.py`

## Audit Trail

- EXTRACTED: 46 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*