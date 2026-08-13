# apply_advanced_sr

> 39 nodes · cohesion 0.08

## Key Concepts

- **apply_advanced_sr()** (13 connections) — `src/common/preprocessing.py`
- **preprocessing.py** (11 connections) — `src/common/preprocessing.py`
- **current_sr_worker.py** (10 connections) — `src/pipeline/detection/current_sr_worker.py`
- **run()** (8 connections) — `src/pipeline/detection/current_sr_worker.py`
- **models/eval_omr_dln.py** (7 connections) — `experiments/models/eval_omr_dln.py`
- **_RealESRGANTileLogFilter** (7 connections) — `src/common/preprocessing.py`
- **main()** (4 connections) — `experiments/models/eval_omr_dln.py`
- **_suppress_realesrgan_tile_logs()** (4 connections) — `src/common/preprocessing.py`
- **_load_request()** (4 connections) — `src/pipeline/detection/current_sr_worker.py`
- **apply_vertical_closing.py** (4 connections) — `tools/apply_vertical_closing.py`
- **main()** (4 connections) — `tools/apply_vertical_closing.py`
- **infer_barlines_from_measures()** (3 connections) — `experiments/models/eval_omr_dln.py`
- **apply_super_resolution()** (3 connections) — `src/common/preprocessing.py`
- **apply_vertical_closing()** (3 connections) — `src/common/preprocessing.py`
- **ndarray** (3 connections)
- **._write_line()** (3 connections) — `src/common/preprocessing.py`
- **Path** (3 connections)
- **_sha256()** (3 connections) — `src/pipeline/detection/current_sr_worker.py`
- **parse_args()** (3 connections) — `tools/apply_vertical_closing.py`
- **resolve_output_path()** (3 connections) — `tools/apply_vertical_closing.py`
- **load_gt_boxes()** (2 connections) — `experiments/models/eval_omr_dln.py`
- **parse_args()** (2 connections) — `experiments/models/eval_omr_dln.py`
- **_env_flag_enabled()** (2 connections) — `src/common/preprocessing.py`
- **Any** (2 connections)
- **.flush()** (2 connections) — `src/common/preprocessing.py`
- *... and 14 more nodes in this community*

## Relationships

- [homr_evaluator.py](homr_evaluator.py.md) (3 shared connections)
- [hybrid.py](hybrid.py.md) (3 shared connections)
- [load_image](load_image.md) (3 shared connections)
- [build_detector_input_contract](build_detector_input_contract.md) (2 shared connections)

## Source Files

- `experiments/models/eval_omr_dln.py`
- `src/common/preprocessing.py`
- `src/pipeline/detection/current_sr_worker.py`
- `tools/apply_vertical_closing.py`

## Audit Trail

- EXTRACTED: 71 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*