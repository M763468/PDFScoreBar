# Community 213

> 6 nodes · cohesion 0.33

## Key Concepts

- **clear_segnet_cache()** (5 connections) — `src/homr_runtime/segnet_cache.py`
- **.cleanup()** (3 connections) — `src/homr_eval_scripts/homr_evaluator.py`
- **.cleanup()** (3 connections) — `src/homr_runtime/predictor.py`
- **Release VRAM and other resources.** (1 connections) — `src/homr_eval_scripts/homr_evaluator.py`
- **Release VRAM and other resources.** (1 connections) — `src/homr_runtime/predictor.py`
- **Clear the Segnet session cache and release VRAM/RAM.** (1 connections) — `src/homr_runtime/segnet_cache.py`

## Relationships

- [Community 38](Community_38.md) (2 shared connections)
- [Community 152](Community_152.md) (1 shared connections)
- [Community 180](Community_180.md) (1 shared connections)

## Source Files

- `src/homr_eval_scripts/homr_evaluator.py`
- `src/homr_runtime/predictor.py`
- `src/homr_runtime/segnet_cache.py`

## Audit Trail

- EXTRACTED: 8 (89%)
- INFERRED: 1 (11%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*