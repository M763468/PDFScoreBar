# run_probe_scan_batch

> 37 nodes · cohesion 0.12

## Key Concepts

- **run_probe_scan_batch()** (47 connections) — `src/pipeline/steps/probe_scan.py`
- **probe_scan.py** (44 connections) — `src/pipeline/steps/probe_scan.py`
- **io.py** (29 connections) — `src/pipeline/utils/io.py`
- **ensure_dir()** (29 connections) — `src/pipeline/utils/io.py`
- **detection/orchestrator.py** (26 connections) — `src/pipeline/detection/orchestrator.py`
- **build_probe_run_id()** (15 connections) — `src/pipeline/core/run_ids.py`
- **run_ids.py** (11 connections) — `src/pipeline/core/run_ids.py`
- **_load_bands_for_image()** (10 connections) — `src/pipeline/steps/probe_scan.py`
- **verify_final_comparison.py** (10 connections) — `tools/verify_final_comparison.py`
- **split_score_page_from_composite_stem()** (8 connections) — `src/pipeline/core/run_ids.py`
- **_extract_candidate_postprocess_cfg()** (8 connections) — `src/pipeline/steps/probe_scan.py`
- **issue46_track_a_split_test.py** (7 connections) — `tools/experiments/issue46_track_a_split_test.py`
- **issue46_track_a_split_test_v2.py** (7 connections) — `tools/experiments/issue46_track_a_split_test_v2.py`
- **build_probe_run_id_from_parts()** (6 connections) — `src/pipeline/core/run_ids.py`
- **_candidate_json_candidates()** (6 connections) — `src/pipeline/detection/orchestrator.py`
- **main()** (6 connections) — `tools/verify_final_comparison.py`
- **_augment_unit_normalized_boxes()** (5 connections) — `src/pipeline/steps/probe_scan.py`
- **Any** (5 connections)
- **_split_score_page_from_stem()** (4 connections) — `src/pipeline/detection/orchestrator.py`
- **Path** (4 connections)
- **run_experiment()** (4 connections) — `tools/experiments/issue46_track_a_split_test.py`
- **run_experiment()** (4 connections) — `tools/experiments/issue46_track_a_split_test_v2.py`
- **_build_clef_mask_map()** (3 connections) — `src/pipeline/steps/probe_scan.py`
- **_parse_bool_like()** (3 connections) — `src/pipeline/steps/probe_scan.py`
- **_clip_box()** (2 connections) — `src/pipeline/steps/probe_scan.py`
- *... and 12 more nodes in this community*

## Relationships

- [cnn_scoring.py](cnn_scoring.py.md) (23 shared connections)
- [score_candidates_batch.py](score_candidates_batch.py.md) (20 shared connections)
- [trace_prokofiev_probe_boundary.py](trace_prokofiev_probe_boundary.py.md) (14 shared connections)
- [filter_probe_candidates](filter_probe_candidates.md) (11 shared connections)
- [load_json](load_json.md) (10 shared connections)
- [DetectorOrchestrator](DetectorOrchestrator.md) (9 shared connections)
- [restored_orchestrator.py](restored_orchestrator.py.md) (7 shared connections)
- [hybrid.py](hybrid.py.md) (6 shared connections)
- [run_full_pipeline.py](run_full_pipeline.py.md) (5 shared connections)
- [load_yaml](load_yaml.md) (5 shared connections)
- [pipeline/orchestrator.py](pipeline-orchestrator.py.md) (4 shared connections)
- [score_candidates_then_eval_full68.py](score_candidates_then_eval_full68.py.md) (3 shared connections)

## Source Files

- `src/pipeline/core/run_ids.py`
- `src/pipeline/detection/orchestrator.py`
- `src/pipeline/steps/probe_scan.py`
- `src/pipeline/utils/io.py`
- `tools/experiments/issue46_track_a_split_test.py`
- `tools/experiments/issue46_track_a_split_test_v2.py`
- `tools/verify_final_comparison.py`

## Audit Trail

- EXTRACTED: 235 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*