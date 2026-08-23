# probe_scan.py

> 49 nodes · cohesion 0.09

## Key Concepts

- **probe_scan.py** (44 connections) — `src/pipeline/steps/probe_scan.py`
- **cnn_scoring.py** (33 connections) — `src/pipeline/steps/cnn_scoring.py`
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
- **filter_by_staff_overlap()** (7 connections) — `src/pipeline/steps/filters.py`
- **batch_re_evaluate_bench.py** (7 connections) — `tools/batch_re_evaluate_bench.py`
- **verify_repro_batch_final.py** (7 connections) — `tools/repro_accuracy/verify_repro_batch_final.py`
- **build_probe_run_id_from_parts()** (6 connections) — `src/pipeline/core/run_ids.py`
- **apply_nms()** (6 connections) — `src/pipeline/steps/cnn_scoring.py`
- **main()** (6 connections) — `tools/verify_final_comparison.py`
- **_build_staff_mask_map()** (5 connections) — `src/pipeline/steps/probe_scan.py`
- **run_batch_verification()** (5 connections) — `tools/batch_re_evaluate_bench.py`
- **main()** (5 connections) — `tools/repro_accuracy/unified_recipe.py`
- **main()** (5 connections) — `tools/repro_accuracy/verify_repro_batch_final.py`
- **main()** (5 connections) — `tools/verify_sr_bypass_filtering.py`
- **_split_score_page_from_stem()** (4 connections) — `src/pipeline/detection/orchestrator.py`
- *... and 24 more nodes in this community*

## Relationships

- [run_probe_scan_batch](run_probe_scan_batch.md) (28 shared connections)
- [barline_evaluation.py](barline_evaluation.py.md) (10 shared connections)
- [run_grouped_final_numbering_comparison.py](run_grouped_final_numbering_comparison.py.md) (8 shared connections)
- [greedy_barline_match](greedy_barline_match.md) (8 shared connections)
- [DetectorOrchestrator](DetectorOrchestrator.md) (7 shared connections)
- [score_candidates_then_eval_full68.py](score_candidates_then_eval_full68.py.md) (6 shared connections)
- [detect_probe_scan](detect_probe_scan.md) (6 shared connections)
- [load_json_boxes](load_json_boxes.md) (6 shared connections)
- [_extract_candidate_postprocess_cfg](_extract_candidate_postprocess_cfg.md) (6 shared connections)
- [restored_orchestrator.py](restored_orchestrator.py.md) (5 shared connections)
- [run_full_pipeline.py](run_full_pipeline.py.md) (5 shared connections)
- [get_nested](get_nested.md) (4 shared connections)

## Source Files

- `src/pipeline/core/run_ids.py`
- `src/pipeline/detection/orchestrator.py`
- `src/pipeline/steps/cnn_scoring.py`
- `src/pipeline/steps/filters.py`
- `src/pipeline/steps/probe_scan.py`
- `tools/batch_re_evaluate_bench.py`
- `tools/repro_accuracy/unified_recipe.py`
- `tools/repro_accuracy/verify_repro_batch_final.py`
- `tools/verify_final_comparison.py`
- `tools/verify_sr_bypass_filtering.py`

## Audit Trail

- EXTRACTED: 233 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*