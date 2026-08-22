# run_detection_step

> 10 nodes · cohesion 0.42

## Key Concepts

- **run_detection_step()** (21 connections) — `src/pipeline/detection/__init__.py`
- **TestPipelineDetection** (8 connections) — `tests/test_pipeline_detection.py`
- **._base_config()** (6 connections) — `tests/test_pipeline_detection.py`
- **test_pipeline_detection.py** (4 connections) — `tests/test_pipeline_detection.py`
- **.test_precomputed_probe_candidates_are_copied_and_scored_with_cnn_bands()** (3 connections) — `tests/test_pipeline_detection.py`
- **.test_probe_score_name_is_forwarded_to_probe_and_cnn()** (3 connections) — `tests/test_pipeline_detection.py`
- **.test_run_detection_step_allows_explicit_cnn_nms_opt_in()** (3 connections) — `tests/test_pipeline_detection.py`
- **.test_run_detection_step_skips_probe_and_cnn_on_dry_run()** (3 connections) — `tests/test_pipeline_detection.py`
- **.test_run_detection_step_uses_orchestrator()** (3 connections) — `tests/test_pipeline_detection.py`
- **Dispatch standard or verified Stage E production detection.** (1 connections) — `src/pipeline/detection/__init__.py`

## Relationships

- [detection/__init__.py](detection-__init__.py.md) (7 shared connections)
- [hybrid.py](hybrid.py.md) (3 shared connections)
- [run_full_pipeline.py](run_full_pipeline.py.md) (2 shared connections)
- [verify_detector_full68.py](verify_detector_full68.py.md) (2 shared connections)
- [DetectorOrchestrator](DetectorOrchestrator.md) (1 shared connections)
- [get_nested](get_nested.md) (1 shared connections)
- [pipeline/orchestrator.py](pipeline-orchestrator.py.md) (1 shared connections)

## Source Files

- `src/pipeline/detection/__init__.py`
- `tests/test_pipeline_detection.py`

## Audit Trail

- EXTRACTED: 35 (97%)
- INFERRED: 1 (3%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*