# install_current_homr_consumer_compat

> 19 nodes · cohesion 0.18

## Key Concepts

- **install_current_homr_consumer_compat()** (16 connections) — `src/pipeline/detection/homr_profile_compat.py`
- **current_homr_worker.py** (13 connections) — `src/pipeline/detection/current_homr_worker.py`
- **test_current_homr_worker.py** (12 connections) — `tests/test_current_homr_worker.py`
- **run()** (11 connections) — `src/pipeline/detection/current_homr_worker.py`
- **build_processing_config_compat()** (11 connections) — `src/pipeline/detection/homr_profile_compat.py`
- **_load_request()** (4 connections) — `src/pipeline/detection/current_homr_worker.py`
- **test_consumer_compat_adapts_legacy_bound_symbols()** (3 connections) — `tests/test_current_homr_worker.py`
- **main()** (2 connections) — `src/pipeline/detection/current_homr_worker.py`
- **Path** (2 connections)
- **test_consumer_compat_is_idempotent_for_already_wrapped_symbols()** (2 connections) — `tests/test_current_homr_worker.py`
- **test_consumer_compat_preserves_current_bound_symbols()** (2 connections) — `tests/test_current_homr_worker.py`
- **test_consumer_parse_staffs_does_not_swallow_internal_type_error()** (2 connections) — `tests/test_current_homr_worker.py`
- **test_current_worker_environment_removes_homr_shadow_paths()** (2 connections) — `tests/test_current_homr_worker.py`
- **test_processing_config_with_gpu_field_uses_six_arguments()** (2 connections) — `tests/test_current_homr_worker.py`
- **test_processing_config_without_gpu_field_uses_five_arguments()** (2 connections) — `tests/test_current_homr_worker.py`
- **Any** (1 connections)
- **Run current HOMR on one precomputed x4 image for connector semantics.** (1 connections) — `src/pipeline/detection/current_homr_worker.py`
- **Adapt the actual HOMR symbols consumed by the current worker. ``HomrPredictor``…** (1 connections) — `src/pipeline/detection/homr_profile_compat.py`
- **Construct ProcessingConfig across the known five/six-field HOMR APIs.** (1 connections) — `src/pipeline/detection/homr_profile_compat.py`

## Relationships

- [homr_profile_compat.py](homr_profile_compat.py.md) (10 shared connections)
- [test_issue254_connector_artifact_contract.py](test_issue254_connector_artifact_contract.py.md) (4 shared connections)
- [metrics.py](metrics.py.md) (4 shared connections)
- [check_current_homr_runtime_contract.py](check_current_homr_runtime_contract.py.md) (4 shared connections)
- [current_support_worker.py](current_support_worker.py.md) (3 shared connections)
- [heuristics.py](heuristics.py.md) (2 shared connections)
- [build_detector_input_contract](build_detector_input_contract.md) (1 shared connections)
- [hybrid.py](hybrid.py.md) (1 shared connections)
- [object](object.md) (1 shared connections)

## Source Files

- `src/pipeline/detection/current_homr_worker.py`
- `src/pipeline/detection/homr_profile_compat.py`
- `tests/test_current_homr_worker.py`

## Audit Trail

- EXTRACTED: 59 (98%)
- INFERRED: 1 (2%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*