# Community 111

> 25 nodes · cohesion 0.14

## Key Concepts

- **run_pipeline()** (30 connections) — `src/pipeline/main.py`
- **test_pipeline_telemetry.py** (22 connections) — `tests/test_pipeline_telemetry.py`
- **main.py** (17 connections) — `src/pipeline/main.py`
- **test_pipeline_integration.py** (6 connections) — `tests/test_pipeline_integration.py`
- **_patch_minimal_pipeline()** (6 connections) — `tests/test_pipeline_telemetry.py`
- **faults.py** (6 connections) — `tools/issue458/faults.py`
- **_assert_input_validation_aborted()** (5 connections) — `tests/test_pipeline_telemetry.py`
- **test_input_validation_does_not_complete_for_malformed_structured_input()** (5 connections) — `tests/test_pipeline_telemetry.py`
- **test_input_validation_does_not_complete_when_external_images_are_missing()** (4 connections) — `tests/test_pipeline_telemetry.py`
- **test_input_validation_does_not_complete_when_pdf_path_is_missing()** (4 connections) — `tests/test_pipeline_telemetry.py`
- **main()** (3 connections) — `src/pipeline/main.py`
- **test_resource_sampling_keeps_default_summary_in_run_directory()** (3 connections) — `tests/test_pipeline_telemetry.py`
- **test_run_pipeline_default_path_does_not_construct_telemetry()** (3 connections) — `tests/test_pipeline_telemetry.py`
- **test_run_pipeline_emits_terminal_failure_when_orchestrator_construction_fails()** (3 connections) — `tests/test_pipeline_telemetry.py`
- **test_run_pipeline_emits_terminal_failure_without_swallowing_exception()** (3 connections) — `tests/test_pipeline_telemetry.py`
- **test_run_pipeline_emits_terminal_success_and_summary()** (3 connections) — `tests/test_pipeline_telemetry.py`
- **child()** (3 connections) — `tools/issue458/faults.py`
- **main()** (2 connections) — `tools/issue458/faults.py`
- **Path** (1 connections)
- **ProgressCallback** (1 connections)
- **End-to-end pipeline entrypoint (no CLI wrapper).** (1 connections) — `src/pipeline/main.py`
- **CLI entry point for the pipeline.** (1 connections) — `src/pipeline/main.py`
- **Entry point for running the full pipeline.** (1 connections) — `src/pipeline/main.py`
- **parametrize** (1 connections)
- **Real pipeline failure/publication checks using retained SR, without inference.** (1 connections) — `tools/issue458/faults.py`

## Relationships

- [Community 19](Community_19.md) (14 shared connections)
- [Community 98](Community_98.md) (6 shared connections)
- [Community 112](Community_112.md) (6 shared connections)
- [Community 21](Community_21.md) (4 shared connections)
- [Community 132](Community_132.md) (3 shared connections)
- [Community 154](Community_154.md) (2 shared connections)
- [Community 110](Community_110.md) (2 shared connections)
- [Community 222](Community_222.md) (2 shared connections)
- [Community 72](Community_72.md) (2 shared connections)
- [Community 61](Community_61.md) (2 shared connections)
- [Community 38](Community_38.md) (2 shared connections)
- [Community 63](Community_63.md) (2 shared connections)

## Source Files

- `src/pipeline/main.py`
- `tests/test_pipeline_integration.py`
- `tests/test_pipeline_telemetry.py`
- `tools/issue458/faults.py`

## Audit Trail

- EXTRACTED: 92 (99%)
- INFERRED: 1 (1%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*