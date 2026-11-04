# Community 80

> 30 nodes · cohesion 0.13

## Key Concepts

- **JobRequest** (33 connections) — `src/pipeline/engine_contract.py`
- **test_engine_service_readiness.py** (22 connections) — `tests/test_engine_service_readiness.py`
- **validate_progress_sequence()** (17 connections) — `src/pipeline/engine_contract.py`
- **CorrectionSet** (14 connections) — `src/pipeline/engine_contract.py`
- **verify_engine_service_readiness.py** (13 connections) — `tools/verification/verify_engine_service_readiness.py`
- **main()** (8 connections) — `tools/verification/verify_engine_service_readiness.py`
- **test_disk_full_fails_without_publishing_and_cleans_work()** (4 connections) — `tests/test_engine_service_readiness.py`
- **test_executor_publishes_only_contract_artifacts()** (4 connections) — `tests/test_engine_service_readiness.py`
- **_assert_failure()** (4 connections) — `tools/verification/verify_engine_service_readiness.py`
- **_executor()** (4 connections) — `tools/verification/verify_engine_service_readiness.py`
- **Path** (4 connections)
- **test_duplicate_correction_ids_and_internal_override_are_rejected()** (3 connections) — `tests/test_engine_contract.py`
- **test_progress_sequence_is_monotonic_and_terminal()** (3 connections) — `tests/test_engine_contract.py`
- **executor_fixture()** (3 connections) — `tests/test_engine_service_readiness.py`
- **test_executor_maps_worker_failure_and_cleans_public_outputs()** (3 connections) — `tests/test_engine_service_readiness.py`
- **test_executor_reports_correction_source_unavailable()** (3 connections) — `tests/test_engine_service_readiness.py`
- **test_stage_auto_starts_job_stream()** (3 connections) — `tests/test_engine_telemetry.py`
- **_prepare_fixture()** (3 connections) — `tools/verification/verify_engine_service_readiness.py`
- **.to_dict()** (2 connections) — `src/pipeline/engine_contract.py`
- **.to_dict()** (2 connections) — `src/pipeline/engine_contract.py`
- **test_debug_telemetry_contains_completed_materialization_stage()** (2 connections) — `tests/test_engine_service_readiness.py`
- **test_execute_payload_maps_missing_fields_to_structured_failure()** (2 connections) — `tests/test_engine_service_readiness.py`
- **test_executor_preserves_input_filename_through_review_handoff_and_final()** (2 connections) — `tests/test_engine_service_readiness.py`
- **test_executor_sanitized_output_name_uses_materialized_path()** (2 connections) — `tests/test_engine_service_readiness.py`
- **test_executor_truncates_long_multibyte_input_filename_to_utf8_limit()** (2 connections) — `tests/test_engine_service_readiness.py`
- *... and 5 more nodes in this community*

## Relationships

- [Community 72](Community_72.md) (13 shared connections)
- [Community 110](Community_110.md) (10 shared connections)
- [Community 63](Community_63.md) (10 shared connections)
- [Community 19](Community_19.md) (7 shared connections)
- [Community 178](Community_178.md) (4 shared connections)
- [Community 27](Community_27.md) (3 shared connections)
- [Community 34](Community_34.md) (3 shared connections)
- [Community 79](Community_79.md) (2 shared connections)
- [Community 297](Community_297.md) (1 shared connections)
- [Community 33](Community_33.md) (1 shared connections)

## Source Files

- `src/pipeline/engine_contract.py`
- `tests/test_engine_contract.py`
- `tests/test_engine_service_readiness.py`
- `tests/test_engine_telemetry.py`
- `tools/verification/verify_engine_service_readiness.py`

## Audit Trail

- EXTRACTED: 110 (99%)
- INFERRED: 1 (1%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*