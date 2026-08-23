# hybrid.py

> 29 nodes · cohesion 0.13

## Key Concepts

- **hybrid.py** (28 connections) — `src/pipeline/detection/hybrid.py`
- **HybridDetector** (21 connections) — `src/pipeline/detection/hybrid.py`
- **HomrPredictor** (13 connections) — `src/homr_eval_scripts/core/predictor.py`
- **.run()** (13 connections) — `src/pipeline/detection/hybrid.py`
- **._run_homr_in_process()** (13 connections) — `src/pipeline/detection/hybrid.py`
- **_HomrInternalLogFilter** (10 connections) — `src/pipeline/detection/hybrid.py`
- **Path** (6 connections)
- **._write_line()** (4 connections) — `src/pipeline/detection/hybrid.py`
- **._all_stems_exist()** (4 connections) — `src/pipeline/detection/hybrid.py`
- **._get_python_cmd()** (4 connections) — `src/pipeline/detection/hybrid.py`
- **_suppress_homr_low_value_internal_logs()** (4 connections) — `src/pipeline/detection/hybrid.py`
- **log_vram_usage()** (4 connections) — `src/pipeline/detection/utils.py`
- **.__init__()** (3 connections) — `src/pipeline/detection/hybrid.py`
- **._omr_all_stems_exist()** (3 connections) — `src/pipeline/detection/hybrid.py`
- **._rel()** (3 connections) — `src/pipeline/detection/hybrid.py`
- **Any** (3 connections)
- **_env_flag_enabled()** (2 connections) — `src/pipeline/detection/hybrid.py`
- **.flush()** (2 connections) — `src/pipeline/detection/hybrid.py`
- **.__init__()** (2 connections) — `src/pipeline/detection/hybrid.py`
- **._should_suppress()** (2 connections) — `src/pipeline/detection/hybrid.py`
- **.write()** (2 connections) — `src/pipeline/detection/hybrid.py`
- **Persistent Homr Predictor for batch processing.** (1 connections) — `src/homr_eval_scripts/core/predictor.py`
- **Hybrid detection engine using Homr and OMR-DLN.** (1 connections) — `src/pipeline/detection/hybrid.py`
- **Encapsulates hybrid detection logic (Baseline, SR, OMR-DLN).** (1 connections) — `src/pipeline/detection/hybrid.py`
- **Returns the appropriate python command, falling back to host if images are…** (1 connections) — `src/pipeline/detection/hybrid.py`
- *... and 4 more nodes in this community*

## Relationships

- [metrics.py](metrics.py.md) (10 shared connections)
- [load_json_boxes](load_json_boxes.md) (5 shared connections)
- [run_stage_d_upstream_regen.py](run_stage_d_upstream_regen.py.md) (4 shared connections)
- [current_support_worker.py](current_support_worker.py.md) (3 shared connections)
- [homr_profile.py](homr_profile.py.md) (3 shared connections)
- [run_probe_scan_batch](run_probe_scan_batch.md) (3 shared connections)
- [apply_advanced_sr](apply_advanced_sr.md) (3 shared connections)
- [run_full_pipeline.py](run_full_pipeline.py.md) (3 shared connections)
- [test_issue254_connector_artifact_contract.py](test_issue254_connector_artifact_contract.py.md) (2 shared connections)
- [heuristics.py](heuristics.py.md) (2 shared connections)
- [.predict](predict.md) (2 shared connections)
- [load_image](load_image.md) (2 shared connections)

## Source Files

- `src/homr_eval_scripts/core/predictor.py`
- `src/pipeline/detection/hybrid.py`
- `src/pipeline/detection/utils.py`

## Audit Trail

- EXTRACTED: 93 (90%)
- INFERRED: 10 (10%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*