# build_detector_input_contract

> 17 nodes · cohesion 0.21

## Key Concepts

- **build_detector_input_contract()** (17 connections) — `src/pipeline/detection/input_contract.py`
- **test_detector_input_contract.py** (9 connections) — `tests/test_detector_input_contract.py`
- **input_contract.py** (8 connections) — `src/pipeline/detection/input_contract.py`
- **require_fresh_detector_input_contract()** (6 connections) — `src/pipeline/detection/input_contract.py`
- **_configured()** (4 connections) — `src/pipeline/detection/input_contract.py`
- **Any** (3 connections)
- **test_falsey_override_values_are_unset()** (3 connections) — `tests/test_detector_input_contract.py`
- **test_truthy_path_strings_select_precomputed_route()** (3 connections) — `tests/test_detector_input_contract.py`
- **parametrize** (2 connections)
- **test_cnn_bands_override_makes_route_checkpoint_only()** (2 connections) — `tests/test_detector_input_contract.py`
- **test_empty_detection_config_is_fresh_upstream()** (2 connections) — `tests/test_detector_input_contract.py`
- **test_fresh_guard_names_all_candidate_source_overrides()** (2 connections) — `tests/test_detector_input_contract.py`
- **test_precomputed_probe_candidates_make_route_checkpoint_only()** (2 connections) — `tests/test_detector_input_contract.py`
- **Classify whether detector candidates come from fresh upstream or overrides. A…** (1 connections) — `src/pipeline/detection/input_contract.py`
- **Match the truthiness gate used by the detector path resolvers.** (1 connections) — `src/pipeline/detection/input_contract.py`
- **Return the authoritative candidate-source contract for one detector run.** (1 connections) — `src/pipeline/detection/input_contract.py`
- **Return the contract or reject a route that substitutes candidate inputs.** (1 connections) — `src/pipeline/detection/input_contract.py`

## Relationships

- [restored_orchestrator.py](restored_orchestrator.py.md) (3 shared connections)
- [test_issue255_production_detector_restoration.py](test_issue255_production_detector_restoration.py.md) (3 shared connections)
- [probe_scan.py](probe_scan.py.md) (2 shared connections)
- [DetectorOrchestrator](DetectorOrchestrator.md) (1 shared connections)

## Source Files

- `src/pipeline/detection/input_contract.py`
- `tests/test_detector_input_contract.py`

## Audit Trail

- EXTRACTED: 38 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*