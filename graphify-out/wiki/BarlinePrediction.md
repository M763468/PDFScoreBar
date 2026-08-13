# BarlinePrediction

> 21 nodes · cohesion 0.12

## Key Concepts

- **BarlinePrediction** (18 connections) — `src/homr_eval_scripts/homr_evaluator.py`
- **.predict()** (13 connections) — `src/homr_eval_scripts/homr_evaluator.py`
- **recover_end_barlines()** (9 connections) — `src/homr_eval_scripts/homr_evaluator.py`
- **run_homr_on_image()** (9 connections) — `src/homr_eval_scripts/homr_evaluator.py`
- **compute_candidate_stats()** (7 connections) — `src/homr_eval_scripts/homr_evaluator.py`
- **filter_detections_by_notehead_proximity()** (7 connections) — `src/homr_eval_scripts/homr_evaluator.py`
- **export_measure_grid_candidates()** (6 connections) — `src/homr_eval_scripts/homr_evaluator.py`
- **resolve_clusters_dry_run()** (6 connections) — `src/homr_eval_scripts/homr_evaluator.py`
- **save_homr_results()** (6 connections) — `src/homr_eval_scripts/homr_evaluator.py`
- **count_staff_crossings()** (5 connections) — `src/homr_eval_scripts/homr_evaluator.py`
- **_scan_vertical_line()** (4 connections) — `src/homr_eval_scripts/homr_evaluator.py`
- **XmlGeneratorArguments** (3 connections)
- **_cluster_by_y_centers()** (2 connections) — `src/homr_eval_scripts/homr_evaluator.py`
- **Box** (1 connections)
- **Counts the number of staff line crossings for a vertical barline candidate. A…** (1 connections) — `src/homr_eval_scripts/homr_evaluator.py`
- **Dry-run implementation of Cluster Resolution Heuristic. Groups barline…** (1 connections) — `src/homr_eval_scripts/homr_evaluator.py`
- **Phase 13: Export data for Measure Grid Consistency (DP) validation. Saves…** (1 connections) — `src/homr_eval_scripts/homr_evaluator.py`
- **Computes and saves statistics for each candidate barline to a CSV file. Stats…** (1 connections) — `src/homr_eval_scripts/homr_evaluator.py`
- **Runs the core homr staff and symbol detection pipeline for a single image with…** (1 connections) — `src/homr_eval_scripts/homr_evaluator.py`
- **Saves Homr detection results (JSON and masks) to the specified directory.** (1 connections) — `src/homr_eval_scripts/homr_evaluator.py`
- **Filters barline detections that are horizontally close to noteheads, which are…** (1 connections) — `src/homr_eval_scripts/homr_evaluator.py`

## Relationships

- [homr_evaluator.py](homr_evaluator.py.md) (31 shared connections)
- [ndarray](ndarray.md) (12 shared connections)
- [metrics.py](metrics.py.md) (4 shared connections)
- [detect_thin_vertical_runs](detect_thin_vertical_runs.md) (3 shared connections)
- [TransformInfo](TransformInfo.md) (2 shared connections)
- [enable_segnet_cache](enable_segnet_cache.md) (1 shared connections)

## Source Files

- `src/homr_eval_scripts/homr_evaluator.py`

## Audit Trail

- EXTRACTED: 74 (95%)
- INFERRED: 4 (5%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*