# Community 18

> 54 nodes · cohesion 0.07

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
- **._query_device_gpu_utilization()** (2 connections) — `src/pipeline/engine_telemetry.py`
- *... and 29 more nodes in this community*

## Relationships

- [Community 110](Community_110.md) (14 shared connections)
- [Community 71](Community_71.md) (10 shared connections)
- [Community 79](Community_79.md) (7 shared connections)
- [Community 62](Community_62.md) (7 shared connections)
- [Community 109](Community_109.md) (6 shared connections)
- [Community 33](Community_33.md) (5 shared connections)
- [Community 20](Community_20.md) (3 shared connections)
- [Community 78](Community_78.md) (1 shared connections)
- [Community 178](Community_178.md) (1 shared connections)
- [Community 98](Community_98.md) (1 shared connections)
- [Community 111](Community_111.md) (1 shared connections)

## Source Files

- `src/pipeline/engine_contract.py`
- `src/pipeline/engine_telemetry.py`
- `tests/test_engine_telemetry.py`
- `tests/test_pipeline_telemetry.py`

## Audit Trail

- EXTRACTED: 140 (89%)
- INFERRED: 18 (11%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*