# get_cnn_apply_nms

> 10 nodes · cohesion 0.29

## Key Concepts

- **get_cnn_apply_nms()** (10 connections) — `src/pipeline/detection/config.py`
- **detection/config.py** (7 connections) — `src/pipeline/detection/config.py`
- **get_probe_kwargs()** (7 connections) — `src/pipeline/detection/config.py`
- **test_detection_config.py** (4 connections) — `tests/test_detection_config.py`
- **Any** (2 connections)
- **test_cnn_apply_nms_can_opt_in()** (2 connections) — `tests/test_detection_config.py`
- **test_cnn_apply_nms_defaults_to_false()** (2 connections) — `tests/test_detection_config.py`
- **Configuration constants and helpers for detection.** (1 connections) — `src/pipeline/detection/config.py`
- **Extracts probe-specific keyword arguments from configuration.** (1 connections) — `src/pipeline/detection/config.py`
- **Return explicit CNN NMS setting, defaulting to False (opt-in).** (1 connections) — `src/pipeline/detection/config.py`

## Relationships

- [probe_scan.py](probe_scan.py.md) (3 shared connections)
- [restored_orchestrator.py](restored_orchestrator.py.md) (3 shared connections)
- [trace_prokofiev_probe_boundary.py](trace_prokofiev_probe_boundary.py.md) (3 shared connections)
- [DetectorOrchestrator](DetectorOrchestrator.md) (2 shared connections)

## Source Files

- `src/pipeline/detection/config.py`
- `tests/test_detection_config.py`

## Audit Trail

- EXTRACTED: 24 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*