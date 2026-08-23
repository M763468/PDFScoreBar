# apply_advanced_sr

> 26 nodes · cohesion 0.12

## Key Concepts

- **apply_advanced_sr()** (13 connections) — `src/common/preprocessing.py`
- **preprocessing.py** (11 connections) — `src/common/preprocessing.py`
- **current_sr_worker.py** (10 connections) — `src/pipeline/detection/current_sr_worker.py`
- **run()** (8 connections) — `src/pipeline/detection/current_sr_worker.py`
- **models/eval_omr_dln.py** (7 connections) — `experiments/models/eval_omr_dln.py`
- **main()** (4 connections) — `experiments/models/eval_omr_dln.py`
- **_suppress_realesrgan_tile_logs()** (4 connections) — `src/common/preprocessing.py`
- **_load_request()** (4 connections) — `src/pipeline/detection/current_sr_worker.py`
- **infer_barlines_from_measures()** (3 connections) — `experiments/models/eval_omr_dln.py`
- **apply_super_resolution()** (3 connections) — `src/common/preprocessing.py`
- **apply_vertical_closing()** (3 connections) — `src/common/preprocessing.py`
- **ndarray** (3 connections)
- **Path** (3 connections)
- **_sha256()** (3 connections) — `src/pipeline/detection/current_sr_worker.py`
- **load_gt_boxes()** (2 connections) — `experiments/models/eval_omr_dln.py`
- **parse_args()** (2 connections) — `experiments/models/eval_omr_dln.py`
- **_env_flag_enabled()** (2 connections) — `src/common/preprocessing.py`
- **main()** (2 connections) — `src/pipeline/detection/current_sr_worker.py`
- **# TODO: If batching, pre-computed SR needs to be a mapping or directory.** (1 connections) — `experiments/models/eval_omr_dln.py`
- **Loads ground truth barlines.** (1 connections) — `experiments/models/eval_omr_dln.py`
- **Converts measure bounding boxes into barline bounding boxes. A measure (x1, y1,…** (1 connections) — `experiments/models/eval_omr_dln.py`
- **Applies super-resolution to an image using OpenCV's dnn_superres module.…** (1 connections) — `src/common/preprocessing.py`
- **Applies advanced super-resolution using a locally cloned Real-ESRGAN…** (1 connections) — `src/common/preprocessing.py`
- **Applies a vertical closing operation to an image to connect broken vertical…** (1 connections) — `src/common/preprocessing.py`
- **Any** (1 connections)
- *... and 1 more nodes in this community*

## Relationships

- [_RealESRGANTileLogFilter](_RealESRGANTileLogFilter.md) (4 shared connections)
- [homr_evaluator.py](homr_evaluator.py.md) (3 shared connections)
- [hybrid.py](hybrid.py.md) (3 shared connections)
- [load_image](load_image.md) (3 shared connections)
- [test_issue255_production_detector_restoration.py](test_issue255_production_detector_restoration.py.md) (2 shared connections)

## Source Files

- `experiments/models/eval_omr_dln.py`
- `src/common/preprocessing.py`
- `src/pipeline/detection/current_sr_worker.py`

## Audit Trail

- EXTRACTED: 55 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*