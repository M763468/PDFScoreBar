# Community 40

> 42 nodes · cohesion 0.08

## Key Concepts

- **run()** (20 connections) — `src/pipeline/detection/omr_dln_worker.py`
- **resolve_omr_dln_model_path()** (13 connections) — `src/common/model_artifacts.py`
- **omr_dln_worker.py** (12 connections) — `src/pipeline/detection/omr_dln_worker.py`
- **models/eval_omr_dln.py** (10 connections) — `experiments/models/eval_omr_dln.py`
- **load_candidate()** (10 connections) — `src/pipeline/detection/omr_dln_worker.py`
- **test_omr_dln_worker.py** (9 connections) — `tests/test_omr_dln_worker.py`
- **omr_dln_model_missing_message()** (7 connections) — `src/common/model_artifacts.py`
- **main()** (6 connections) — `experiments/models/eval_omr_dln.py`
- **_Model** (6 connections) — `tests/test_omr_dln_worker.py`
- **_TensorLike** (5 connections) — `tests/test_omr_dln_worker.py`
- **resolve_precomputed_sr()** (4 connections) — `src/pipeline/detection/omr_dln_worker.py`
- **test_runtime_worker_rejects_missing_precomputed_sr()** (4 connections) — `tests/test_omr_dln_worker.py`
- **test_runtime_worker_resolves_model_from_repository_root()** (4 connections) — `tests/test_omr_dln_worker.py`
- **test_runtime_worker_uses_precomputed_sr_and_returns_source_coordinates()** (4 connections) — `tests/test_omr_dln_worker.py`
- **infer_barlines_from_measures()** (3 connections) — `experiments/models/eval_omr_dln.py`
- **infer_barlines_from_measures()** (3 connections) — `src/pipeline/detection/omr_dln_worker.py`
- **Path** (3 connections)
- **Path** (3 connections)
- **_Result** (3 connections) — `tests/test_omr_dln_worker.py`
- **load_gt_boxes()** (2 connections) — `experiments/models/eval_omr_dln.py`
- **parse_args()** (2 connections) — `experiments/models/eval_omr_dln.py`
- **main()** (2 connections) — `src/pipeline/detection/omr_dln_worker.py`
- **Any** (2 connections)
- **_scale_to_source()** (2 connections) — `src/pipeline/detection/omr_dln_worker.py`
- **test_omr_candidate_rejects_wrong_task()** (2 connections) — `tests/test_experiment_model_selection.py`
- *... and 17 more nodes in this community*

## Relationships

- [Community 10](Community_10.md) (6 shared connections)
- [Community 75](Community_75.md) (4 shared connections)
- [Community 60](Community_60.md) (4 shared connections)
- [Community 83](Community_83.md) (3 shared connections)
- [Community 30](Community_30.md) (3 shared connections)
- [Community 53](Community_53.md) (2 shared connections)
- [Community 37](Community_37.md) (2 shared connections)
- [Community 51](Community_51.md) (2 shared connections)
- [Community 73](Community_73.md) (2 shared connections)
- [Community 148](Community_148.md) (1 shared connections)

## Source Files

- `experiments/models/eval_omr_dln.py`
- `src/common/model_artifacts.py`
- `src/pipeline/detection/omr_dln_worker.py`
- `tests/test_experiment_model_selection.py`
- `tests/test_omr_dln_worker.py`

## Audit Trail

- EXTRACTED: 95 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*