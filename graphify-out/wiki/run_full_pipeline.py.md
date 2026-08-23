# run_full_pipeline.py

> 75 nodes · cohesion 0.07

## Key Concepts

- **run_full_pipeline.py** (32 connections) — `tools/run_full_pipeline.py`
- **main()** (26 connections) — `tools/run_full_pipeline.py`
- **run_detection_step()** (21 connections) — `src/pipeline/detection/__init__.py`
- **detection/__init__.py** (20 connections) — `src/pipeline/detection/__init__.py`
- **Any** (20 connections)
- **Path** (20 connections)
- **verify_detector_full68.py** (17 connections) — `tools/verification/verify_detector_full68.py`
- **_get_nested()** (12 connections) — `tools/run_full_pipeline.py`
- **run()** (12 connections) — `tools/verification/verify_detector_full68.py`
- **TestPipelineDetection** (8 connections) — `tests/test_pipeline_detection.py`
- **Path** (8 connections)
- **_run_production_groups()** (8 connections) — `tools/verification/verify_detector_full68.py`
- **run_detection_step()** (7 connections) — `src/pipeline/detection/orchestrator.py`
- **_resolve_page_filters()** (7 connections) — `tools/run_full_pipeline.py`
- **.__new__()** (6 connections) — `src/pipeline/detection/__init__.py`
- **._base_config()** (6 connections) — `tests/test_pipeline_detection.py`
- **_build_pdf_command()** (6 connections) — `tools/run_full_pipeline.py`
- **_resolve_barlines_and_masks_config()** (6 connections) — `tools/run_full_pipeline.py`
- **_run_detection_step()** (6 connections) — `tools/run_full_pipeline.py`
- **_detector_route()** (5 connections) — `src/pipeline/detection/__init__.py`
- **DetectorOrchestrator** (5 connections) — `src/pipeline/detection/__init__.py`
- **_install_standard_detector_hooks()** (5 connections) — `src/pipeline/detection/__init__.py`
- **_validate_verified_image_stems()** (5 connections) — `src/pipeline/detection/__init__.py`
- **_collect_images()** (5 connections) — `tools/run_full_pipeline.py`
- **_empty_numbering_payload()** (5 connections) — `tools/run_full_pipeline.py`
- *... and 50 more nodes in this community*

## Relationships

- [test_issue254_connector_artifact_contract.py](test_issue254_connector_artifact_contract.py.md) (5 shared connections)
- [restored_orchestrator.py](restored_orchestrator.py.md) (5 shared connections)
- [probe_scan.py](probe_scan.py.md) (5 shared connections)
- [DetectorOrchestrator](DetectorOrchestrator.md) (5 shared connections)
- [load_yaml](load_yaml.md) (4 shared connections)
- [hybrid.py](hybrid.py.md) (3 shared connections)
- [test_issue264_phase_a_connector_geometry.py](test_issue264_phase_a_connector_geometry.py.md) (2 shared connections)
- [pipeline/orchestrator.py](pipeline-orchestrator.py.md) (2 shared connections)
- [get_nested](get_nested.md) (2 shared connections)
- [barline_iou](barline_iou.md) (2 shared connections)
- [.run](run.md) (1 shared connections)
- [barline_evaluation.py](barline_evaluation.py.md) (1 shared connections)

## Source Files

- `src/pipeline/detection/__init__.py`
- `src/pipeline/detection/orchestrator.py`
- `tests/test_pipeline_detection.py`
- `tools/run_full_pipeline.py`
- `tools/verification/verify_detector_full68.py`

## Audit Trail

- EXTRACTED: 229 (99%)
- INFERRED: 3 (1%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*