# Community 154

> 56 nodes · cohesion 0.08

## Key Concepts

- **run_probe_scan_batch()** (48 connections) — `src/pipeline/steps/probe_scan.py`
- **probe_scan.py** (44 connections) — `src/pipeline/steps/probe_scan.py`
- **cnn_scoring.py** (40 connections) — `src/pipeline/steps/cnn_scoring.py`
- **ensure_dir()** (30 connections) — `src/pipeline/core/__init__.py`
- **run_cnn_scoring_batch()** (29 connections) — `src/pipeline/steps/cnn_scoring.py`
- **detection/orchestrator.py** (23 connections) — `src/pipeline/detection/orchestrator.py`
- **_score_directory()** (22 connections) — `src/pipeline/steps/cnn_scoring.py`
- **unified_recipe.py** (9 connections) — `tools/repro_accuracy/unified_recipe.py`
- **verify_final_comparison.py** (9 connections) — `tools/verify_final_comparison.py`
- **_extract_candidate_postprocess_cfg()** (8 connections) — `src/pipeline/steps/probe_scan.py`
- **verify_sr_bypass_filtering.py** (8 connections) — `tools/verify_sr_bypass_filtering.py`
- **trim_box_to_ink()** (7 connections) — `src/pipeline/steps/candidate_filters.py`
- **GPUNormalize** (7 connections) — `src/pipeline/steps/cnn_scoring.py`
- **batch_re_evaluate_bench.py** (7 connections) — `tools/batch_re_evaluate_bench.py`
- **verify_repro_batch_final.py** (7 connections) — `tools/repro_accuracy/verify_repro_batch_final.py`
- **apply_nms()** (6 connections) — `src/pipeline/steps/cnn_scoring.py`
- **Path** (6 connections)
- **_write_scoring_results()** (6 connections) — `src/pipeline/steps/cnn_scoring.py`
- **issue46_track_a_split_test.py** (6 connections) — `tools/experiments/issue46_track_a_split_test.py`
- **issue46_track_a_split_test_v2.py** (6 connections) — `tools/experiments/issue46_track_a_split_test_v2.py`
- **main()** (6 connections) — `tools/verify_final_comparison.py`
- **_augment_unit_normalized_boxes()** (5 connections) — `src/pipeline/steps/probe_scan.py`
- **_build_staff_mask_map()** (5 connections) — `src/pipeline/steps/probe_scan.py`
- **Any** (5 connections)
- **run_batch_verification()** (5 connections) — `tools/batch_re_evaluate_bench.py`
- *... and 31 more nodes in this community*

## Relationships

- [Community 0](Community_0.md) (21 shared connections)
- [Community 11](Community_11.md) (19 shared connections)
- [Community 13](Community_13.md) (17 shared connections)
- [Community 79](Community_79.md) (14 shared connections)
- [Community 60](Community_60.md) (13 shared connections)
- [Community 37](Community_37.md) (13 shared connections)
- [Community 68](Community_68.md) (10 shared connections)
- [Community 71](Community_71.md) (10 shared connections)
- [Community 81](Community_81.md) (10 shared connections)
- [Community 91](Community_91.md) (5 shared connections)
- [Community 61](Community_61.md) (5 shared connections)
- [Community 50](Community_50.md) (4 shared connections)

## Source Files

- `src/pipeline/core/__init__.py`
- `src/pipeline/detection/orchestrator.py`
- `src/pipeline/steps/candidate_filters.py`
- `src/pipeline/steps/cnn_scoring.py`
- `src/pipeline/steps/probe_scan.py`
- `tests/test_staff_strokes.py`
- `tools/batch_re_evaluate_bench.py`
- `tools/experiments/issue46_track_a_split_test.py`
- `tools/experiments/issue46_track_a_split_test_v2.py`
- `tools/repro_accuracy/unified_recipe.py`
- `tools/repro_accuracy/verify_repro_batch_final.py`
- `tools/verify_final_comparison.py`
- `tools/verify_sr_bypass_filtering.py`

## Audit Trail

- EXTRACTED: 303 (100%)
- INFERRED: 1 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*