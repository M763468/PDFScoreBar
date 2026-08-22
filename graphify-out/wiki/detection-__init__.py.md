# detection/__init__.py

> 26 nodes · cohesion 0.15

## Key Concepts

- **detection/__init__.py** (20 connections) — `src/pipeline/detection/__init__.py`
- **DetectorOrchestrator** (16 connections) — `src/pipeline/detection/restored_orchestrator.py`
- **Path** (8 connections)
- **.run_detection()** (7 connections) — `src/pipeline/detection/restored_orchestrator.py`
- **run_detection_step()** (7 connections) — `src/pipeline/detection/restored_orchestrator.py`
- **.__new__()** (6 connections) — `src/pipeline/detection/__init__.py`
- **._run_cnn_scoring()** (6 connections) — `src/pipeline/detection/restored_orchestrator.py`
- **._write_dense_inventory()** (6 connections) — `src/pipeline/detection/restored_orchestrator.py`
- **Any** (6 connections)
- **_detector_route()** (5 connections) — `src/pipeline/detection/__init__.py`
- **DetectorOrchestrator** (5 connections) — `src/pipeline/detection/__init__.py`
- **_install_standard_detector_hooks()** (5 connections) — `src/pipeline/detection/__init__.py`
- **_validate_verified_image_stems()** (5 connections) — `src/pipeline/detection/__init__.py`
- **._run_dense_route()** (5 connections) — `src/pipeline/detection/restored_orchestrator.py`
- **.__init__()** (4 connections) — `src/pipeline/detection/restored_orchestrator.py`
- **._record_input_contract()** (4 connections) — `src/pipeline/detection/restored_orchestrator.py`
- **._run_hybrid_detection()** (4 connections) — `src/pipeline/detection/restored_orchestrator.py`
- **_score_page()** (4 connections) — `src/pipeline/detection/restored_orchestrator.py`
- **Any** (3 connections)
- **Path** (3 connections)
- **_first_existing()** (3 connections) — `src/pipeline/detection/restored_orchestrator.py`
- **Detection package providing barline detection orchestration.** (1 connections) — `src/pipeline/detection/__init__.py`
- **Reject ambiguous verified-route calls before profile artifacts can collide.** (1 connections) — `src/pipeline/detection/__init__.py`
- **Route the public orchestrator constructor by the configured detector route.** (1 connections) — `src/pipeline/detection/__init__.py`
- **Run the verified Stage E detector from fresh upstream inputs.** (1 connections) — `src/pipeline/detection/restored_orchestrator.py`
- *... and 1 more nodes in this community*

## Relationships

- [run_probe_scan_batch](run_probe_scan_batch.md) (10 shared connections)
- [run_detection_step](run_detection_step.md) (7 shared connections)
- [common/connector_artifacts.py](common-connector_artifacts.py.md) (3 shared connections)
- [get_nested](get_nested.md) (3 shared connections)
- [DetectorOrchestrator](DetectorOrchestrator.md) (3 shared connections)
- [test_issue255_production_detector_restoration.py](test_issue255_production_detector_restoration.py.md) (3 shared connections)
- [test_issue264_phase_a_connector_geometry.py](test_issue264_phase_a_connector_geometry.py.md) (2 shared connections)
- [test_issue254_connector_artifact_contract.py](test_issue254_connector_artifact_contract.py.md) (2 shared connections)
- [VerifiedProfileHybridDetector](VerifiedProfileHybridDetector.md) (2 shared connections)
- [load_yaml](load_yaml.md) (1 shared connections)
- [build_detector_input_contract](build_detector_input_contract.md) (1 shared connections)
- [get_cnn_apply_nms](get_cnn_apply_nms.md) (1 shared connections)

## Source Files

- `src/pipeline/detection/__init__.py`
- `src/pipeline/detection/restored_orchestrator.py`

## Audit Trail

- EXTRACTED: 85 (97%)
- INFERRED: 3 (3%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*