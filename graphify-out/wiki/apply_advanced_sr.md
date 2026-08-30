# apply_advanced_sr

> 27 nodes · cohesion 0.11

## Key Concepts

- **apply_advanced_sr()** (14 connections) — `src/common/preprocessing.py`
- **preprocessing.py** (13 connections) — `src/common/preprocessing.py`
- **models/eval_omr_dln.py** (7 connections) — `experiments/models/eval_omr_dln.py`
- **_RealESRGANTileLogFilter** (7 connections) — `src/common/preprocessing.py`
- **main()** (4 connections) — `experiments/models/eval_omr_dln.py`
- **_perf_span()** (4 connections) — `src/common/preprocessing.py`
- **_suppress_realesrgan_tile_logs()** (4 connections) — `src/common/preprocessing.py`
- **infer_barlines_from_measures()** (3 connections) — `experiments/models/eval_omr_dln.py`
- **apply_super_resolution()** (3 connections) — `src/common/preprocessing.py`
- **apply_vertical_closing()** (3 connections) — `src/common/preprocessing.py`
- **ndarray** (3 connections)
- **._write_line()** (3 connections) — `src/common/preprocessing.py`
- **load_gt_boxes()** (2 connections) — `experiments/models/eval_omr_dln.py`
- **parse_args()** (2 connections) — `experiments/models/eval_omr_dln.py`
- **_env_flag_enabled()** (2 connections) — `src/common/preprocessing.py`
- **Any** (2 connections)
- **.flush()** (2 connections) — `src/common/preprocessing.py`
- **.__init__()** (2 connections) — `src/common/preprocessing.py`
- **.write()** (2 connections) — `src/common/preprocessing.py`
- **# TODO: If batching, pre-computed SR needs to be a mapping or directory.** (1 connections) — `experiments/models/eval_omr_dln.py`
- **Loads ground truth barlines.** (1 connections) — `experiments/models/eval_omr_dln.py`
- **Converts measure bounding boxes into barline bounding boxes. A measure (x1, y1,…** (1 connections) — `experiments/models/eval_omr_dln.py`
- **Applies super-resolution to an image using OpenCV's dnn_superres module.…** (1 connections) — `src/common/preprocessing.py`
- **Applies advanced super-resolution using a locally cloned Real-ESRGAN…** (1 connections) — `src/common/preprocessing.py`
- **Use pipeline perf tracing only when the opt-in trace is enabled.** (1 connections) — `src/common/preprocessing.py`
- *... and 2 more nodes in this community*

## Relationships

- [span](span.md) (5 shared connections)
- [homr_evaluator.py](homr_evaluator.py.md) (3 shared connections)
- [hybrid.py](hybrid.py.md) (3 shared connections)
- [apply_vertical_closing.py](apply_vertical_closing.py.md) (1 shared connections)

## Source Files

- `experiments/models/eval_omr_dln.py`
- `src/common/preprocessing.py`

## Audit Trail

- EXTRACTED: 51 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*