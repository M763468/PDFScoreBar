# cnn_scoring.py

> 38 nodes · cohesion 0.10

## Key Concepts

- **cnn_scoring.py** (33 connections) — `src/pipeline/steps/cnn_scoring.py`
- **run_cnn_scoring_batch()** (26 connections) — `src/pipeline/steps/cnn_scoring.py`
- **load_image()** (23 connections) — `src/pipeline/utils/images.py`
- **_score_directory()** (18 connections) — `src/pipeline/steps/cnn_scoring.py`
- **_resolve_model_path()** (11 connections) — `src/pipeline/steps/cnn_scoring.py`
- **verify_sr_bypass_filtering.py** (8 connections) — `tools/verify_sr_bypass_filtering.py`
- **_load_model()** (7 connections) — `src/pipeline/steps/cnn_scoring.py`
- **filter_by_staff_overlap()** (7 connections) — `src/pipeline/steps/filters.py`
- **test_cnn_scoring_model_path.py** (7 connections) — `tests/test_cnn_scoring_model_path.py`
- **batch_re_evaluate_bench.py** (7 connections) — `tools/batch_re_evaluate_bench.py`
- **verify_repro_batch_final.py** (7 connections) — `tools/repro_accuracy/verify_repro_batch_final.py`
- **apply_nms()** (6 connections) — `src/pipeline/steps/cnn_scoring.py`
- **run_batch_verification()** (5 connections) — `tools/batch_re_evaluate_bench.py`
- **main()** (5 connections) — `tools/repro_accuracy/verify_repro_batch_final.py`
- **main()** (5 connections) — `tools/verify_sr_bypass_filtering.py`
- **_compute_bbox_ink_center_x()** (4 connections) — `src/pipeline/steps/cnn_scoring.py`
- **Path** (4 connections)
- **_center_crop()** (3 connections) — `src/pipeline/steps/cnn_scoring.py`
- **Any** (3 connections)
- **_crop_size_from_bbox()** (2 connections) — `src/pipeline/steps/cnn_scoring.py`
- **device** (2 connections)
- **Module** (2 connections)
- **ndarray** (2 connections)
- **test_resolve_model_path_accepts_existing_file()** (2 connections) — `tests/test_cnn_scoring_model_path.py`
- **test_resolve_model_path_accepts_existing_file_string()** (2 connections) — `tests/test_cnn_scoring_model_path.py`
- *... and 13 more nodes in this community*

## Relationships

- [run_probe_scan_batch](run_probe_scan_batch.md) (22 shared connections)
- [run_grouped_final_numbering_comparison.py](run_grouped_final_numbering_comparison.py.md) (10 shared connections)
- [barline_evaluation.py](barline_evaluation.py.md) (5 shared connections)
- [detect_probe_scan](detect_probe_scan.md) (5 shared connections)
- [get_nested](get_nested.md) (5 shared connections)
- [greedy_barline_match](greedy_barline_match.md) (4 shared connections)
- [detection/orchestrator.py](detection-orchestrator.py.md) (3 shared connections)
- [score_candidates_then_eval_full68.py](score_candidates_then_eval_full68.py.md) (3 shared connections)
- [score_candidates_batch.py](score_candidates_batch.py.md) (3 shared connections)
- [barline_iou](barline_iou.md) (2 shared connections)
- [restored_orchestrator.py](restored_orchestrator.py.md) (2 shared connections)
- [test_issue284_sr_batch_contract.py](test_issue284_sr_batch_contract.py.md) (2 shared connections)

## Source Files

- `src/pipeline/steps/cnn_scoring.py`
- `src/pipeline/steps/filters.py`
- `src/pipeline/utils/images.py`
- `tests/test_cnn_scoring_model_path.py`
- `tools/batch_re_evaluate_bench.py`
- `tools/repro_accuracy/verify_repro_batch_final.py`
- `tools/verify_sr_bypass_filtering.py`

## Audit Trail

- EXTRACTED: 150 (99%)
- INFERRED: 1 (1%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*