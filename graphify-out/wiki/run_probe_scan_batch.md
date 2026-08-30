# run_probe_scan_batch

> 63 nodes · cohesion 0.08

## Key Concepts

- **run_probe_scan_batch()** (47 connections) — `src/pipeline/steps/probe_scan.py`
- **probe_scan.py** (44 connections) — `src/pipeline/steps/probe_scan.py`
- **cnn_scoring.py** (33 connections) — `src/pipeline/steps/cnn_scoring.py`
- **io.py** (29 connections) — `src/pipeline/utils/io.py`
- **ensure_dir()** (29 connections) — `src/pipeline/utils/io.py`
- **detection/orchestrator.py** (26 connections) — `src/pipeline/detection/orchestrator.py`
- **run_cnn_scoring_batch()** (26 connections) — `src/pipeline/steps/cnn_scoring.py`
- **_score_directory()** (18 connections) — `src/pipeline/steps/cnn_scoring.py`
- **build_probe_run_id()** (15 connections) — `src/pipeline/core/run_ids.py`
- **run_ids.py** (11 connections) — `src/pipeline/core/run_ids.py`
- **_load_bands_for_image()** (10 connections) — `src/pipeline/steps/probe_scan.py`
- **verify_final_comparison.py** (10 connections) — `tools/verify_final_comparison.py`
- **unified_recipe.py** (9 connections) — `tools/repro_accuracy/unified_recipe.py`
- **split_score_page_from_composite_stem()** (8 connections) — `src/pipeline/core/run_ids.py`
- **verify_sr_bypass_filtering.py** (8 connections) — `tools/verify_sr_bypass_filtering.py`
- **_load_model()** (7 connections) — `src/pipeline/steps/cnn_scoring.py`
- **batch_re_evaluate_bench.py** (7 connections) — `tools/batch_re_evaluate_bench.py`
- **issue46_track_a_split_test.py** (7 connections) — `tools/experiments/issue46_track_a_split_test.py`
- **issue46_track_a_split_test_v2.py** (7 connections) — `tools/experiments/issue46_track_a_split_test_v2.py`
- **verify_repro_batch_final.py** (7 connections) — `tools/repro_accuracy/verify_repro_batch_final.py`
- **build_probe_run_id_from_parts()** (6 connections) — `src/pipeline/core/run_ids.py`
- **_candidate_json_candidates()** (6 connections) — `src/pipeline/detection/orchestrator.py`
- **apply_nms()** (6 connections) — `src/pipeline/steps/cnn_scoring.py`
- **main()** (6 connections) — `tools/verify_final_comparison.py`
- **_augment_unit_normalized_boxes()** (5 connections) — `src/pipeline/steps/probe_scan.py`
- *... and 38 more nodes in this community*

## Relationships

- [score_candidates_batch.py](score_candidates_batch.py.md) (20 shared connections)
- [trace_prokofiev_probe_boundary.py](trace_prokofiev_probe_boundary.py.md) (13 shared connections)
- [DetectorOrchestrator](DetectorOrchestrator.md) (10 shared connections)
- [load_json](load_json.md) (10 shared connections)
- [restored_orchestrator.py](restored_orchestrator.py.md) (9 shared connections)
- [run_grouped_final_numbering_comparison.py](run_grouped_final_numbering_comparison.py.md) (8 shared connections)
- [filter_probe_candidates](filter_probe_candidates.md) (8 shared connections)
- [load_json_boxes](load_json_boxes.md) (8 shared connections)
- [greedy_barline_match](greedy_barline_match.md) (8 shared connections)
- [barline_evaluation.py](barline_evaluation.py.md) (7 shared connections)
- [detect_probe_scan](detect_probe_scan.md) (7 shared connections)
- [score_candidates_then_eval_full68.py](score_candidates_then_eval_full68.py.md) (6 shared connections)

## Source Files

- `src/pipeline/core/run_ids.py`
- `src/pipeline/detection/orchestrator.py`
- `src/pipeline/steps/cnn_scoring.py`
- `src/pipeline/steps/probe_scan.py`
- `src/pipeline/utils/io.py`
- `tools/batch_re_evaluate_bench.py`
- `tools/experiments/issue46_track_a_split_test.py`
- `tools/experiments/issue46_track_a_split_test_v2.py`
- `tools/repro_accuracy/unified_recipe.py`
- `tools/repro_accuracy/verify_repro_batch_final.py`
- `tools/verify_final_comparison.py`
- `tools/verify_sr_bypass_filtering.py`

## Audit Trail

- EXTRACTED: 329 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*