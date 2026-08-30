# enable_segnet_cache

> 21 nodes · cohesion 0.11

## Key Concepts

- **enable_segnet_cache()** (7 connections) — `src/homr_eval_scripts/segnet_cache.py`
- **segnet_cache.py** (6 connections) — `src/homr_eval_scripts/segnet_cache.py`
- **clear_segnet_cache()** (6 connections) — `src/homr_eval_scripts/segnet_cache.py`
- **_get_session()** (5 connections) — `src/homr_eval_scripts/segnet_cache.py`
- **ProcessingConfig** (4 connections)
- **CachedSegnet** (4 connections) — `src/homr_eval_scripts/segnet_cache.py`
- **.cleanup()** (3 connections) — `src/homr_eval_scripts/core/predictor.py`
- **.__init__()** (3 connections) — `src/homr_eval_scripts/core/predictor.py`
- **.cleanup()** (3 connections) — `src/homr_eval_scripts/homr_evaluator.py`
- **.__init__()** (3 connections) — `src/homr_eval_scripts/homr_evaluator.py`
- **_create_session()** (3 connections) — `src/homr_eval_scripts/segnet_cache.py`
- **InferenceSession** (2 connections)
- **ProcessingConfig** (2 connections)
- **.__init__()** (2 connections) — `src/homr_eval_scripts/segnet_cache.py`
- **Release VRAM and other resources.** (1 connections) — `src/homr_eval_scripts/core/predictor.py`
- **Release VRAM and other resources.** (1 connections) — `src/homr_eval_scripts/homr_evaluator.py`
- **.run()** (1 connections) — `src/homr_eval_scripts/segnet_cache.py`
- **Segnet cache patcher to avoid repeated ONNXRuntime model loads.** (1 connections) — `src/homr_eval_scripts/segnet_cache.py`
- **Patch homr.segmentation.inference_segnet.Segnet with a cached variant.** (1 connections) — `src/homr_eval_scripts/segnet_cache.py`
- **Drop-in replacement for homr.segmentation.inference_segnet.Segnet.** (1 connections) — `src/homr_eval_scripts/segnet_cache.py`
- **Clear the Segnet session cache and release VRAM/RAM.** (1 connections) — `src/homr_eval_scripts/segnet_cache.py`

## Relationships

- [homr_evaluator.py](homr_evaluator.py.md) (5 shared connections)
- [heuristics.py](heuristics.py.md) (3 shared connections)
- [hybrid.py](hybrid.py.md) (2 shared connections)
- [metrics.py](metrics.py.md) (2 shared connections)
- [ndarray](ndarray.md) (1 shared connections)
- [homr_profile_compat.py](homr_profile_compat.py.md) (1 shared connections)

## Source Files

- `src/homr_eval_scripts/core/predictor.py`
- `src/homr_eval_scripts/homr_evaluator.py`
- `src/homr_eval_scripts/segnet_cache.py`

## Audit Trail

- EXTRACTED: 36 (97%)
- INFERRED: 1 (3%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*