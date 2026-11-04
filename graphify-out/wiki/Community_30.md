# Community 30

> 49 nodes · cohesion 0.09

## Key Concepts

- **EngineError** (25 connections) — `src/pipeline/engine_contract.py`
- **JobStatus** (24 connections) — `src/pipeline/engine_contract.py`
- **ErrorCategory** (22 connections) — `src/pipeline/engine_contract.py`
- **test_job_lifecycle.py** (21 connections) — `tests/test_job_lifecycle.py`
- **engine_lifecycle.py** (13 connections) — `src/pipeline/engine_lifecycle.py`
- **CancellationToken** (13 connections) — `src/pipeline/engine_lifecycle.py`
- **ExecutionControl** (12 connections) — `src/pipeline/engine_lifecycle.py`
- **ExecutionDeadline** (12 connections) — `src/pipeline/engine_lifecycle.py`
- **LifecycleControlError** (11 connections) — `src/pipeline/engine_lifecycle.py`
- **classify_control_error()** (9 connections) — `src/pipeline/engine_lifecycle.py`
- **JobCancelled** (9 connections) — `src/pipeline/engine_lifecycle.py`
- **JobDeadlineExceeded** (9 connections) — `src/pipeline/engine_lifecycle.py`
- **ValidatedPdfMetadata** (5 connections) — `src/pipeline/engine_input_safety.py`
- **ValidatedPageMetadata** (4 connections) — `src/pipeline/engine_input_safety.py`
- **.checkpoint()** (4 connections) — `src/pipeline/engine_lifecycle.py`
- **.with_timeout()** (4 connections) — `src/pipeline/engine_lifecycle.py`
- **.after()** (4 connections) — `src/pipeline/engine_lifecycle.py`
- **test_explicit_cancellation_wins_when_deadline_is_also_expired()** (4 connections) — `tests/test_job_lifecycle.py`
- **.__init__()** (3 connections) — `src/pipeline/engine_input_safety.py`
- **Any** (3 connections)
- **test_cancelled_maps_to_normative_v1_status_and_error()** (3 connections) — `tests/test_job_lifecycle.py`
- **test_deadline_maps_to_failed_resource_error_and_retryable_hint()** (3 connections) — `tests/test_job_lifecycle.py`
- **test_execution_control_raises_cancelled_with_stage_and_reason()** (3 connections) — `tests/test_job_lifecycle.py`
- **test_execution_deadline_rejects_invalid_duration_and_clock_values()** (3 connections) — `tests/test_job_lifecycle.py`
- **.to_dict()** (2 connections) — `src/pipeline/engine_input_safety.py`
- *... and 24 more nodes in this community*

## Relationships

- [Community 41](Community_41.md) (14 shared connections)
- [Community 19](Community_19.md) (10 shared connections)
- [Community 48](Community_48.md) (10 shared connections)
- [Community 73](Community_73.md) (7 shared connections)
- [Community 17](Community_17.md) (5 shared connections)
- [Community 196](Community_196.md) (1 shared connections)
- [Community 14](Community_14.md) (1 shared connections)
- [Community 81](Community_81.md) (1 shared connections)
- [Community 33](Community_33.md) (1 shared connections)

## Source Files

- `src/pipeline/engine_contract.py`
- `src/pipeline/engine_input_safety.py`
- `src/pipeline/engine_lifecycle.py`
- `tests/test_job_lifecycle.py`

## Audit Trail

- EXTRACTED: 122 (80%)
- INFERRED: 31 (20%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*