# build_detector_input_contract

> 27 nodes · cohesion 0.14

## Key Concepts

- **build_detector_input_contract()** (17 connections) — `src/pipeline/detection/input_contract.py`
- **test_issue255_production_detector_restoration.py** (14 connections) — `tests/test_issue255_production_detector_restoration.py`
- **test_detector_input_contract.py** (9 connections) — `tests/test_detector_input_contract.py`
- **input_contract.py** (8 connections) — `src/pipeline/detection/input_contract.py`
- **require_fresh_detector_input_contract()** (6 connections) — `src/pipeline/detection/input_contract.py`
- **Path** (5 connections)
- **_configured()** (4 connections) — `src/pipeline/detection/input_contract.py`
- **_config()** (4 connections) — `tests/test_issue255_production_detector_restoration.py`
- **test_current_sr_worker_uses_verified_x4_settings()** (4 connections) — `tests/test_issue255_production_detector_restoration.py`
- **test_dense_inventory_uses_only_current_hybrid_and_profile_masks()** (4 connections) — `tests/test_issue255_production_detector_restoration.py`
- **test_dense_route_cnn_uses_original_coordinates_and_nms_false()** (4 connections) — `tests/test_issue255_production_detector_restoration.py`
- **test_verified_profile_is_selected_for_hybrid_detection()** (4 connections) — `tests/test_issue255_production_detector_restoration.py`
- **Any** (3 connections)
- **test_falsey_override_values_are_unset()** (3 connections) — `tests/test_detector_input_contract.py`
- **test_truthy_path_strings_select_precomputed_route()** (3 connections) — `tests/test_detector_input_contract.py`
- **test_current_support_runs_sr_homr_omr_as_separate_phases()** (3 connections) — `tests/test_issue255_production_detector_restoration.py`
- **parametrize** (2 connections)
- **test_cnn_bands_override_makes_route_checkpoint_only()** (2 connections) — `tests/test_detector_input_contract.py`
- **test_empty_detection_config_is_fresh_upstream()** (2 connections) — `tests/test_detector_input_contract.py`
- **test_fresh_guard_names_all_candidate_source_overrides()** (2 connections) — `tests/test_detector_input_contract.py`
- **test_precomputed_probe_candidates_make_route_checkpoint_only()** (2 connections) — `tests/test_detector_input_contract.py`
- **test_canonical_detector_config_uses_verified_restored_route()** (2 connections) — `tests/test_issue255_production_detector_restoration.py`
- **Classify whether detector candidates come from fresh upstream or overrides. A…** (1 connections) — `src/pipeline/detection/input_contract.py`
- **Match the truthiness gate used by the detector path resolvers.** (1 connections) — `src/pipeline/detection/input_contract.py`
- **Return the authoritative candidate-source contract for one detector run.** (1 connections) — `src/pipeline/detection/input_contract.py`
- *... and 2 more nodes in this community*

## Relationships

- [restored_orchestrator.py](restored_orchestrator.py.md) (7 shared connections)
- [run_probe_scan_batch](run_probe_scan_batch.md) (2 shared connections)
- [span](span.md) (2 shared connections)
- [current_support_worker.py](current_support_worker.py.md) (2 shared connections)
- [DetectorOrchestrator](DetectorOrchestrator.md) (1 shared connections)
- [current_homr_worker.py](current_homr_worker.py.md) (1 shared connections)
- [object](object.md) (1 shared connections)

## Source Files

- `src/pipeline/detection/input_contract.py`
- `tests/test_detector_input_contract.py`
- `tests/test_issue255_production_detector_restoration.py`

## Audit Trail

- EXTRACTED: 63 (98%)
- INFERRED: 1 (2%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*