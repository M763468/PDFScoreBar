# run_detection_step

> 21 nodes · cohesion 0.19

## Key Concepts

- **run_detection_step()** (21 connections) — `src/pipeline/detection/__init__.py`
- **detection/__init__.py** (20 connections) — `src/pipeline/detection/__init__.py`
- **TestPipelineDetection** (8 connections) — `tests/test_pipeline_detection.py`
- **.__new__()** (6 connections) — `src/pipeline/detection/__init__.py`
- **._base_config()** (6 connections) — `tests/test_pipeline_detection.py`
- **_detector_route()** (5 connections) — `src/pipeline/detection/__init__.py`
- **DetectorOrchestrator** (5 connections) — `src/pipeline/detection/__init__.py`
- **_install_standard_detector_hooks()** (5 connections) — `src/pipeline/detection/__init__.py`
- **_validate_verified_image_stems()** (5 connections) — `src/pipeline/detection/__init__.py`
- **test_pipeline_detection.py** (4 connections) — `tests/test_pipeline_detection.py`
- **Any** (3 connections)
- **Path** (3 connections)
- **.test_precomputed_probe_candidates_are_copied_and_scored_with_cnn_bands()** (3 connections) — `tests/test_pipeline_detection.py`
- **.test_probe_score_name_is_forwarded_to_probe_and_cnn()** (3 connections) — `tests/test_pipeline_detection.py`
- **.test_run_detection_step_allows_explicit_cnn_nms_opt_in()** (3 connections) — `tests/test_pipeline_detection.py`
- **.test_run_detection_step_skips_probe_and_cnn_on_dry_run()** (3 connections) — `tests/test_pipeline_detection.py`
- **.test_run_detection_step_uses_orchestrator()** (3 connections) — `tests/test_pipeline_detection.py`
- **Detection package providing barline detection orchestration.** (1 connections) — `src/pipeline/detection/__init__.py`
- **Dispatch standard or verified Stage E production detection.** (1 connections) — `src/pipeline/detection/__init__.py`
- **Reject ambiguous verified-route calls before profile artifacts can collide.** (1 connections) — `src/pipeline/detection/__init__.py`
- **Route the public orchestrator constructor by the configured detector route.** (1 connections) — `src/pipeline/detection/__init__.py`

## Relationships

- [pipeline/orchestrator.py](pipeline-orchestrator.py.md) (6 shared connections)
- [test_issue254_connector_artifact_contract.py](test_issue254_connector_artifact_contract.py.md) (5 shared connections)
- [restored_orchestrator.py](restored_orchestrator.py.md) (5 shared connections)
- [detection/orchestrator.py](detection-orchestrator.py.md) (5 shared connections)
- [hybrid.py](hybrid.py.md) (3 shared connections)
- [run_full_pipeline.py](run_full_pipeline.py.md) (2 shared connections)
- [verify_detector_full68.py](verify_detector_full68.py.md) (2 shared connections)
- [run_stage_e_full_pipeline.py](run_stage_e_full_pipeline.py.md) (1 shared connections)
- [.run](run.md) (1 shared connections)

## Source Files

- `src/pipeline/detection/__init__.py`
- `tests/test_pipeline_detection.py`

## Audit Trail

- EXTRACTED: 67 (96%)
- INFERRED: 3 (4%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*