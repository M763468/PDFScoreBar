# current_homr_worker.py

> 13 nodes · cohesion 0.22

## Key Concepts

- **current_homr_worker.py** (16 connections) — `src/pipeline/detection/current_homr_worker.py`
- **install_homr_connector_artifact_capture()** (14 connections) — `src/pipeline/detection/connector_artifacts.py`
- **run()** (14 connections) — `src/pipeline/detection/current_homr_worker.py`
- **_resize_mask_to_image_size()** (6 connections) — `src/pipeline/detection/current_homr_worker.py`
- **_load_request()** (4 connections) — `src/pipeline/detection/current_homr_worker.py`
- **main()** (2 connections) — `src/pipeline/detection/current_homr_worker.py`
- **Path** (2 connections)
- **test_current_homr_worker_restores_sr_masks_to_original_page_size()** (2 connections) — `tests/test_issue264_phase_a_connector_geometry.py`
- **Wrap ``HomrPredictor.predict`` so semantic connector masks survive production…** (1 connections) — `src/pipeline/detection/connector_artifacts.py`
- **Any** (1 connections)
- **ndarray** (1 connections)
- **Run current HOMR on one precomputed x4 image for connector semantics.** (1 connections) — `src/pipeline/detection/current_homr_worker.py`
- **Restore an SR-space HOMR mask to the original page-image coordinates.** (1 connections) — `src/pipeline/detection/current_homr_worker.py`

## Relationships

- [install_current_homr_consumer_compat](install_current_homr_consumer_compat.md) (6 shared connections)
- [common/connector_artifacts.py](common-connector_artifacts.py.md) (4 shared connections)
- [test_issue254_connector_artifact_contract.py](test_issue254_connector_artifact_contract.py.md) (4 shared connections)
- [metrics.py](metrics.py.md) (4 shared connections)
- [test_issue264_phase_a_connector_geometry.py](test_issue264_phase_a_connector_geometry.py.md) (3 shared connections)
- [phase_c_phase_a_support.py](phase_c_phase_a_support.py.md) (3 shared connections)
- [install_homr_skip_existing_guard](install_homr_skip_existing_guard.md) (2 shared connections)
- [heuristics.py](heuristics.py.md) (2 shared connections)
- [get_nested](get_nested.md) (1 shared connections)
- [restored_orchestrator.py](restored_orchestrator.py.md) (1 shared connections)
- [hybrid.py](hybrid.py.md) (1 shared connections)

## Source Files

- `src/pipeline/detection/connector_artifacts.py`
- `src/pipeline/detection/current_homr_worker.py`
- `tests/test_issue264_phase_a_connector_geometry.py`

## Audit Trail

- EXTRACTED: 48 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*