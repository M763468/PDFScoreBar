# detection/orchestrator.py

> 42 nodes · cohesion 0.10

## Key Concepts

- **detection/orchestrator.py** (26 connections) — `src/pipeline/detection/orchestrator.py`
- **DetectorOrchestrator** (21 connections) — `src/pipeline/detection/orchestrator.py`
- **._run_probe_scan()** (13 connections) — `src/pipeline/detection/orchestrator.py`
- **Path** (11 connections)
- **get_cnn_apply_nms()** (10 connections) — `src/pipeline/detection/config.py`
- **._run_cnn_scoring()** (10 connections) — `src/pipeline/detection/orchestrator.py`
- **detection/config.py** (7 connections) — `src/pipeline/detection/config.py`
- **get_probe_kwargs()** (7 connections) — `src/pipeline/detection/config.py`
- **.run_detection()** (7 connections) — `src/pipeline/detection/orchestrator.py`
- **Any** (7 connections)
- **run_detection_step()** (7 connections) — `src/pipeline/detection/orchestrator.py`
- **_candidate_json_candidates()** (6 connections) — `src/pipeline/detection/orchestrator.py`
- **._copy_precomputed_probe_candidates()** (6 connections) — `src/pipeline/detection/orchestrator.py`
- **.__init__()** (6 connections) — `src/pipeline/detection/orchestrator.py`
- **._get_effective_images_for_probe()** (5 connections) — `src/pipeline/detection/orchestrator.py`
- **._record_input_contract()** (5 connections) — `src/pipeline/detection/orchestrator.py`
- **._run_hybrid_detection()** (5 connections) — `src/pipeline/detection/orchestrator.py`
- **_split_score_page_from_stem()** (4 connections) — `src/pipeline/detection/orchestrator.py`
- **test_detection_config.py** (4 connections) — `tests/test_detection_config.py`
- **._get_effective_score_name()** (3 connections) — `src/pipeline/detection/orchestrator.py`
- **._resolve_clef_mask_dir()** (3 connections) — `src/pipeline/detection/orchestrator.py`
- **._resolve_cnn_bands_from()** (3 connections) — `src/pipeline/detection/orchestrator.py`
- **._resolve_precomputed_probe_candidates_root()** (3 connections) — `src/pipeline/detection/orchestrator.py`
- **._resolve_staff_mask_dir()** (3 connections) — `src/pipeline/detection/orchestrator.py`
- **_reject_removed_detector_route_keys()** (3 connections) — `src/pipeline/detection/orchestrator.py`
- *... and 17 more nodes in this community*

## Relationships

- [run_probe_scan_batch](run_probe_scan_batch.md) (9 shared connections)
- [restored_orchestrator.py](restored_orchestrator.py.md) (5 shared connections)
- [run_detection_step](run_detection_step.md) (5 shared connections)
- [score_candidates_batch.py](score_candidates_batch.py.md) (5 shared connections)
- [hybrid.py](hybrid.py.md) (4 shared connections)
- [trace_prokofiev_probe_boundary.py](trace_prokofiev_probe_boundary.py.md) (3 shared connections)
- [build_detector_input_contract](build_detector_input_contract.md) (3 shared connections)
- [_orchestrator](_orchestrator.md) (3 shared connections)
- [pipeline/orchestrator.py](pipeline-orchestrator.py.md) (2 shared connections)
- [run_stage_e_full_pipeline.py](run_stage_e_full_pipeline.py.md) (1 shared connections)
- [cnn_scoring.py](cnn_scoring.py.md) (1 shared connections)

## Source Files

- `src/pipeline/detection/config.py`
- `src/pipeline/detection/orchestrator.py`
- `tests/test_detection_config.py`

## Audit Trail

- EXTRACTED: 121 (98%)
- INFERRED: 2 (2%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*