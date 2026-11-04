# Community 17

> 57 nodes · cohesion 0.07

## Key Concepts

- **TelemetryRecorder** (40 connections) — `src/pipeline/engine_telemetry.py`
- **ProgressEvent** (27 connections) — `src/pipeline/engine_contract.py`
- **test_engine_telemetry.py** (24 connections) — `tests/test_engine_telemetry.py`
- **ResourceSampler** (19 connections) — `src/pipeline/engine_telemetry.py`
- **ProgressKind** (16 connections) — `src/pipeline/engine_contract.py`
- **engine_telemetry.py** (12 connections) — `src/pipeline/engine_telemetry.py`
- **.emit()** (8 connections) — `src/pipeline/engine_telemetry.py`
- **_SuccessfulOrchestrator** (7 connections) — `tests/test_pipeline_telemetry.py`
- **.start_job()** (6 connections) — `src/pipeline/engine_telemetry.py`
- **.terminal()** (6 connections) — `src/pipeline/engine_telemetry.py`
- **_FailingOrchestrator** (6 connections) — `tests/test_pipeline_telemetry.py`
- **._sample_once()** (5 connections) — `src/pipeline/engine_telemetry.py`
- **_ConstructorFailingOrchestrator** (5 connections) — `tests/test_pipeline_telemetry.py`
- **.from_json()** (4 connections) — `src/pipeline/engine_contract.py`
- **.progress()** (4 connections) — `src/pipeline/engine_telemetry.py`
- **test_recorder_terminal_kind_matches_job_status()** (4 connections) — `tests/test_engine_telemetry.py`
- **test_summary_resources_are_job_result_compatible_without_sampling()** (4 connections) — `tests/test_engine_telemetry.py`
- **._dispatch()** (3 connections) — `src/pipeline/engine_telemetry.py`
- **.__init__()** (3 connections) — `src/pipeline/engine_telemetry.py`
- **.stage()** (3 connections) — `src/pipeline/engine_telemetry.py`
- **.summary()** (3 connections) — `src/pipeline/engine_telemetry.py`
- **parametrize** (3 connections)
- **test_progress_event_rejects_invalid_additive_telemetry_fields()** (3 connections) — `tests/test_engine_telemetry.py`
- **test_progress_event_telemetry_fields_round_trip_deterministically()** (3 connections) — `tests/test_engine_telemetry.py`
- **test_resource_sampler_rejects_non_finite_or_non_positive_interval()** (3 connections) — `tests/test_engine_telemetry.py`
- *... and 32 more nodes in this community*

## Relationships

- [Community 117](Community_117.md) (12 shared connections)
- [Community 48](Community_48.md) (11 shared connections)
- [Community 41](Community_41.md) (9 shared connections)
- [Community 73](Community_73.md) (8 shared connections)
- [Community 30](Community_30.md) (5 shared connections)
- [Community 14](Community_14.md) (5 shared connections)
- [Community 99](Community_99.md) (2 shared connections)
- [Community 81](Community_81.md) (1 shared connections)
- [Community 86](Community_86.md) (1 shared connections)
- [Community 126](Community_126.md) (1 shared connections)

## Source Files

- `src/pipeline/engine_contract.py`
- `src/pipeline/engine_telemetry.py`
- `tests/test_engine_telemetry.py`
- `tests/test_pipeline_telemetry.py`

## Audit Trail

- EXTRACTED: 143 (88%)
- INFERRED: 19 (12%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*