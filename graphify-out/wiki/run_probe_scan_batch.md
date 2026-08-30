# run_probe_scan_batch

> 44 nodes · cohesion 0.10

## Key Concepts

- **run_probe_scan_batch()** (47 connections) — `src/pipeline/steps/probe_scan.py`
- **probe_scan.py** (44 connections) — `src/pipeline/steps/probe_scan.py`
- **io.py** (29 connections) — `src/pipeline/utils/io.py`
- **ensure_dir()** (29 connections) — `src/pipeline/utils/io.py`
- **load_json_boxes()** (19 connections) — `src/pipeline/steps/hybrid_consensus.py`
- **build_probe_run_id()** (15 connections) — `src/pipeline/core/run_ids.py`
- **profile_hybrid.py** (13 connections) — `src/pipeline/detection/profile_hybrid.py`
- **hybrid_consensus.py** (13 connections) — `src/pipeline/steps/hybrid_consensus.py`
- **run_ids.py** (11 connections) — `src/pipeline/core/run_ids.py`
- **_load_bands_for_image()** (10 connections) — `src/pipeline/steps/probe_scan.py`
- **verify_final_comparison.py** (10 connections) — `tools/verify_final_comparison.py`
- **unified_recipe.py** (9 connections) — `tools/repro_accuracy/unified_recipe.py`
- **_extract_candidate_postprocess_cfg()** (8 connections) — `src/pipeline/steps/probe_scan.py`
- **reproduce_clean_seed_v12.py** (8 connections) — `tools/repro_accuracy/reproduce_clean_seed_v12.py`
- **issue46_track_a_split_test.py** (7 connections) — `tools/experiments/issue46_track_a_split_test.py`
- **issue46_track_a_split_test_v2.py** (7 connections) — `tools/experiments/issue46_track_a_split_test_v2.py`
- **build_probe_run_id_from_parts()** (6 connections) — `src/pipeline/core/run_ids.py`
- **main()** (6 connections) — `tools/verify_final_comparison.py`
- **_augment_unit_normalized_boxes()** (5 connections) — `src/pipeline/steps/probe_scan.py`
- **_build_staff_mask_map()** (5 connections) — `src/pipeline/steps/probe_scan.py`
- **Any** (5 connections)
- **main()** (5 connections) — `tools/repro_accuracy/reproduce_clean_seed_v12.py`
- **main()** (5 connections) — `tools/repro_accuracy/unified_recipe.py`
- **Path** (4 connections)
- **run_experiment()** (4 connections) — `tools/experiments/issue46_track_a_split_test.py`
- *... and 19 more nodes in this community*

## Relationships

- [cnn_scoring.py](cnn_scoring.py.md) (22 shared connections)
- [score_candidates_batch.py](score_candidates_batch.py.md) (21 shared connections)
- [trace_prokofiev_probe_boundary.py](trace_prokofiev_probe_boundary.py.md) (20 shared connections)
- [detection/orchestrator.py](detection-orchestrator.py.md) (12 shared connections)
- [restored_orchestrator.py](restored_orchestrator.py.md) (9 shared connections)
- [filter_probe_candidates](filter_probe_candidates.md) (9 shared connections)
- [load_json](load_json.md) (8 shared connections)
- [hybrid.py](hybrid.py.md) (7 shared connections)
- [load_yaml](load_yaml.md) (4 shared connections)
- [greedy_barline_match](greedy_barline_match.md) (4 shared connections)
- [score_candidates_then_eval_full68.py](score_candidates_then_eval_full68.py.md) (3 shared connections)
- [run_full_pipeline.py](run_full_pipeline.py.md) (3 shared connections)

## Source Files

- `src/pipeline/core/run_ids.py`
- `src/pipeline/detection/profile_hybrid.py`
- `src/pipeline/steps/hybrid_consensus.py`
- `src/pipeline/steps/probe_scan.py`
- `src/pipeline/utils/io.py`
- `tools/experiments/issue46_track_a_split_test.py`
- `tools/experiments/issue46_track_a_split_test_v2.py`
- `tools/repro_accuracy/reproduce_clean_seed_v12.py`
- `tools/repro_accuracy/unified_recipe.py`
- `tools/verify_final_comparison.py`

## Audit Trail

- EXTRACTED: 261 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*