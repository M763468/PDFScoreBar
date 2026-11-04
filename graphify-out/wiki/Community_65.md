# Community 65

> 17 nodes · cohesion 0.21

## Key Concepts

- **test_omr_job_route.py** (21 connections) — `tests/test_omr_job_route.py`
- **_drive()** (6 connections) — `tests/test_omr_job_route.py`
- **select_route()** (5 connections) — `src/pipeline/detection/omr_job.py`
- **_detector()** (4 connections) — `tests/test_omr_job_route.py`
- **_pages()** (4 connections) — `tests/test_omr_job_route.py`
- **test_support_worker_consumes_job_prediction_without_running_omr()** (4 connections) — `tests/test_omr_job_route.py`
- **parametrize** (3 connections)
- **_support_request()** (3 connections) — `tests/test_omr_job_route.py`
- **test_coordinator_rejects_result_from_the_other_route()** (3 connections) — `tests/test_omr_job_route.py`
- **test_excluded_jobs_keep_the_per_page_route()** (3 connections) — `tests/test_omr_job_route.py`
- **test_invalid_policy_is_rejected()** (3 connections) — `tests/test_omr_job_route.py`
- **test_route_is_selected_from_explicit_envelope()** (3 connections) — `tests/test_omr_job_route.py`
- **test_support_worker_rejects_incomplete_job_without_publishing()** (3 connections) — `tests/test_omr_job_route.py`
- **test_job_failure_never_falls_back_to_per_page_sources()** (2 connections) — `tests/test_omr_job_route.py`
- **test_root_multi_page_job_runs_one_omr_phase_before_sources()** (2 connections) — `tests/test_omr_job_route.py`
- **Decide the OMR route before the job starts; never changes after a failure.…** (1 connections) — `src/pipeline/detection/omr_job.py`
- **Route selection and production wiring of the per-job OMR route (Issue #459).** (1 connections) — `tests/test_omr_job_route.py`

## Relationships

- [Community 33](Community_33.md) (7 shared connections)
- [Community 154](Community_154.md) (3 shared connections)
- [Community 111](Community_111.md) (3 shared connections)
- [Community 16](Community_16.md) (2 shared connections)

## Source Files

- `src/pipeline/detection/omr_job.py`
- `tests/test_omr_job_route.py`

## Audit Trail

- EXTRACTED: 42 (98%)
- INFERRED: 1 (2%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*