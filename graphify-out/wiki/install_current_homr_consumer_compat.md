# install_current_homr_consumer_compat

> 20 nodes · cohesion 0.19

## Key Concepts

- **install_current_homr_consumer_compat()** (16 connections) — `src/pipeline/detection/homr_profile_compat.py`
- **test_current_homr_worker.py** (12 connections) — `tests/test_current_homr_worker.py`
- **build_processing_config_compat()** (11 connections) — `src/pipeline/detection/homr_profile_compat.py`
- **check_current_homr_runtime_contract.py** (11 connections) — `tools/issue255/check_current_homr_runtime_contract.py`
- **run()** (10 connections) — `tools/issue255/check_current_homr_runtime_contract.py`
- **_write_payload()** (4 connections) — `tools/issue255/check_current_homr_runtime_contract.py`
- **test_consumer_compat_adapts_legacy_bound_symbols()** (3 connections) — `tests/test_current_homr_worker.py`
- **_is_within()** (3 connections) — `tools/issue255/check_current_homr_runtime_contract.py`
- **main()** (3 connections) — `tools/issue255/check_current_homr_runtime_contract.py`
- **Any** (3 connections)
- **Path** (3 connections)
- **_signature()** (3 connections) — `tools/issue255/check_current_homr_runtime_contract.py`
- **test_consumer_compat_is_idempotent_for_already_wrapped_symbols()** (2 connections) — `tests/test_current_homr_worker.py`
- **test_consumer_compat_preserves_current_bound_symbols()** (2 connections) — `tests/test_current_homr_worker.py`
- **test_consumer_parse_staffs_does_not_swallow_internal_type_error()** (2 connections) — `tests/test_current_homr_worker.py`
- **test_current_worker_environment_removes_homr_shadow_paths()** (2 connections) — `tests/test_current_homr_worker.py`
- **test_processing_config_with_gpu_field_uses_six_arguments()** (2 connections) — `tests/test_current_homr_worker.py`
- **test_processing_config_without_gpu_field_uses_five_arguments()** (2 connections) — `tests/test_current_homr_worker.py`
- **Adapt the actual HOMR symbols consumed by the current worker. ``HomrPredictor``…** (1 connections) — `src/pipeline/detection/homr_profile_compat.py`
- **Construct ProcessingConfig across the known five/six-field HOMR APIs.** (1 connections) — `src/pipeline/detection/homr_profile_compat.py`

## Relationships

- [homr_profile_compat.py](homr_profile_compat.py.md) (12 shared connections)
- [current_homr_worker.py](current_homr_worker.py.md) (6 shared connections)
- [current_support_worker.py](current_support_worker.py.md) (3 shared connections)
- [heuristics.py](heuristics.py.md) (2 shared connections)
- [MMROCREngine](MMROCREngine.md) (1 shared connections)

## Source Files

- `src/pipeline/detection/homr_profile_compat.py`
- `tests/test_current_homr_worker.py`
- `tools/issue255/check_current_homr_runtime_contract.py`

## Audit Trail

- EXTRACTED: 59 (98%)
- INFERRED: 1 (2%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*