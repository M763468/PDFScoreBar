# Community 34

> 45 nodes · cohesion 0.10

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
- **ValidatedPageMetadata** (4 connections) — `src/pipeline/engine_input_safety.py`
- **.checkpoint()** (4 connections) — `src/pipeline/engine_lifecycle.py`
- **.with_timeout()** (4 connections) — `src/pipeline/engine_lifecycle.py`
- **.after()** (4 connections) — `src/pipeline/engine_lifecycle.py`
- **test_explicit_cancellation_wins_when_deadline_is_also_expired()** (4 connections) — `tests/test_job_lifecycle.py`
- **test_cancelled_maps_to_normative_v1_status_and_error()** (3 connections) — `tests/test_job_lifecycle.py`
- **test_deadline_maps_to_failed_resource_error_and_retryable_hint()** (3 connections) — `tests/test_job_lifecycle.py`
- **test_execution_control_raises_cancelled_with_stage_and_reason()** (3 connections) — `tests/test_job_lifecycle.py`
- **test_execution_deadline_rejects_invalid_duration_and_clock_values()** (3 connections) — `tests/test_job_lifecycle.py`
- **.cancel()** (2 connections) — `src/pipeline/engine_lifecycle.py`
- **.remaining_timeout()** (2 connections) — `src/pipeline/engine_lifecycle.py`
- **test_cancellation_token_is_idempotent_and_preserves_first_reason()** (2 connections) — `tests/test_job_lifecycle.py`
- **test_classify_control_error_rejects_unknown_subclass()** (2 connections) — `tests/test_job_lifecycle.py`
- *... and 20 more nodes in this community*

## Relationships

- [Community 27](Community_27.md) (13 shared connections)
- [Community 63](Community_63.md) (10 shared connections)
- [Community 72](Community_72.md) (8 shared connections)
- [Community 19](Community_19.md) (5 shared connections)
- [Community 110](Community_110.md) (4 shared connections)
- [Community 80](Community_80.md) (3 shared connections)
- [Community 178](Community_178.md) (3 shared connections)
- [Community 111](Community_111.md) (1 shared connections)
- [Community 79](Community_79.md) (1 shared connections)
- [Community 52](Community_52.md) (1 shared connections)

## Source Files

- `src/pipeline/engine_contract.py`
- `src/pipeline/engine_input_safety.py`
- `src/pipeline/engine_lifecycle.py`
- `tests/test_job_lifecycle.py`

## Audit Trail

- EXTRACTED: 115 (79%)
- INFERRED: 31 (21%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*