# run_probe_scan_batch

> 44 nodes · cohesion 0.10

## Key Concepts

- **run_probe_scan_batch()** (47 connections) — `src/pipeline/steps/probe_scan.py`
- **score_candidates_batch.py** (31 connections) — `tools/cnn_classifier/score_candidates_batch.py`
- **ensure_dir()** (29 connections) — `src/pipeline/utils/io.py`
- **run_scoring_batch()** (21 connections) — `tools/cnn_classifier/score_candidates_batch.py`
- **process_dir()** (13 connections) — `tools/cnn_classifier/score_candidates_batch.py`
- **split_wide_candidates()** (11 connections) — `src/pipeline/utils/wide_split_utils.py`
- **reproduce_issue44_validation.py** (8 connections) — `tools/reproduce_issue44_validation.py`
- **wide_split_utils.py** (7 connections) — `src/pipeline/utils/wide_split_utils.py`
- **Path** (7 connections)
- **issue46_track_a_split_test.py** (7 connections) — `tools/experiments/issue46_track_a_split_test.py`
- **issue46_track_a_split_test_v2.py** (7 connections) — `tools/experiments/issue46_track_a_split_test_v2.py`
- **evaluate_full_rescue_v1.py** (5 connections) — `experiments/issue53_probe_rescue/evaluate_full_rescue_v1.py`
- **estimate_unit_size_from_box_height()** (5 connections) — `src/pipeline/utils/wide_split_utils.py`
- **main()** (5 connections) — `tools/reproduce_issue44_validation.py`
- **Path** (4 connections)
- **extract_x_profile_peaks()** (4 connections) — `src/pipeline/utils/wide_split_utils.py`
- **_compute_bbox_ink_center_x()** (4 connections) — `tools/cnn_classifier/score_candidates_batch.py`
- **GPUNormalize** (4 connections) — `tools/cnn_classifier/score_candidates_batch.py`
- **main()** (4 connections) — `tools/cnn_classifier/score_candidates_batch.py`
- **parse_eval2_context()** (4 connections) — `tools/cnn_classifier/score_candidates_batch.py`
- **_resolve_model_path()** (4 connections) — `tools/cnn_classifier/score_candidates_batch.py`
- **run_experiment()** (4 connections) — `tools/experiments/issue46_track_a_split_test.py`
- **run_experiment()** (4 connections) — `tools/experiments/issue46_track_a_split_test_v2.py`
- **run_full_evaluation()** (3 connections) — `experiments/issue53_probe_rescue/evaluate_full_rescue_v1.py`
- **_build_clef_mask_map()** (3 connections) — `src/pipeline/steps/probe_scan.py`
- *... and 19 more nodes in this community*

## Relationships

- [probe_scan.py](probe_scan.py.md) (28 shared connections)
- [barline_evaluation.py](barline_evaluation.py.md) (7 shared connections)
- [detect_probe_scan](detect_probe_scan.md) (6 shared connections)
- [mine_fn_cnn_hardpositives.py](mine_fn_cnn_hardpositives.py.md) (6 shared connections)
- [_extract_candidate_postprocess_cfg](_extract_candidate_postprocess_cfg.md) (5 shared connections)
- [write_json](write_json.md) (5 shared connections)
- [DetectorOrchestrator](DetectorOrchestrator.md) (4 shared connections)
- [filter_probe_candidates](filter_probe_candidates.md) (4 shared connections)
- [hybrid.py](hybrid.py.md) (3 shared connections)
- [restored_orchestrator.py](restored_orchestrator.py.md) (3 shared connections)
- [score_candidates_then_eval_full68.py](score_candidates_then_eval_full68.py.md) (3 shared connections)
- [dense_full_pipeline.py](dense_full_pipeline.py.md) (2 shared connections)

## Source Files

- `experiments/issue53_probe_rescue/evaluate_full_rescue_v1.py`
- `src/pipeline/steps/probe_scan.py`
- `src/pipeline/utils/io.py`
- `src/pipeline/utils/wide_split_utils.py`
- `tools/cnn_classifier/score_candidates_batch.py`
- `tools/experiments/issue46_track_a_split_test.py`
- `tools/experiments/issue46_track_a_split_test_v2.py`
- `tools/reproduce_issue44_validation.py`

## Audit Trail

- EXTRACTED: 187 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*