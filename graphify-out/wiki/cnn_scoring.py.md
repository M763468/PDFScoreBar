# cnn_scoring.py

> 24 nodes · cohesion 0.14

## Key Concepts

- **cnn_scoring.py** (33 connections) — `src/pipeline/steps/cnn_scoring.py`
- **_score_directory()** (18 connections) — `src/pipeline/steps/cnn_scoring.py`
- **_resolve_model_path()** (11 connections) — `src/pipeline/steps/cnn_scoring.py`
- **_load_model()** (7 connections) — `src/pipeline/steps/cnn_scoring.py`
- **filter_by_staff_overlap()** (7 connections) — `src/pipeline/steps/filters.py`
- **test_cnn_scoring_model_path.py** (7 connections) — `tests/test_cnn_scoring_model_path.py`
- **apply_nms()** (6 connections) — `src/pipeline/steps/cnn_scoring.py`
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
- **test_resolve_model_path_rejects_directory()** (2 connections) — `tests/test_cnn_scoring_model_path.py`
- **test_resolve_model_path_rejects_none()** (2 connections) — `tests/test_cnn_scoring_model_path.py`
- **test_resolve_model_path_requires_existing_file()** (2 connections) — `tests/test_cnn_scoring_model_path.py`
- **In-process CNN scoring for probe candidates.** (1 connections) — `src/pipeline/steps/cnn_scoring.py`
- **Estimate a better crop X-center from the bbox-local ink profile. Intended for…** (1 connections) — `src/pipeline/steps/cnn_scoring.py`
- **Apply greedy suppression to scored results. Uses a combination of IoU and…** (1 connections) — `src/pipeline/steps/cnn_scoring.py`
- **Return candidates that have at least vov_threshold vertical overlap with at…** (1 connections) — `src/pipeline/steps/filters.py`

## Relationships

- [run_probe_scan_batch](run_probe_scan_batch.md) (15 shared connections)
- [run_grouped_final_numbering_comparison.py](run_grouped_final_numbering_comparison.py.md) (9 shared connections)
- [detect_probe_scan](detect_probe_scan.md) (5 shared connections)
- [greedy_barline_match](greedy_barline_match.md) (4 shared connections)
- [pipeline/orchestrator.py](pipeline-orchestrator.py.md) (3 shared connections)
- [barline_iou](barline_iou.md) (2 shared connections)
- [load_image](load_image.md) (2 shared connections)
- [score_candidates_batch.py](score_candidates_batch.py.md) (2 shared connections)
- [detection/orchestrator.py](detection-orchestrator.py.md) (1 shared connections)
- [score_candidates_then_eval_full68.py](score_candidates_then_eval_full68.py.md) (1 shared connections)
- [verify_repro_batch_final.py](verify_repro_batch_final.py.md) (1 shared connections)

## Source Files

- `src/pipeline/steps/cnn_scoring.py`
- `src/pipeline/steps/filters.py`
- `tests/test_cnn_scoring_model_path.py`

## Audit Trail

- EXTRACTED: 85 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*