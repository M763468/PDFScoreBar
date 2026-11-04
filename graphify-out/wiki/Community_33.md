# Community 33

> 44 nodes · cohesion 0.10

## Key Concepts

- **test_omr_job.py** (20 connections) — `tests/test_omr_job.py`
- **omr_job.py** (15 connections) — `src/pipeline/detection/omr_job.py`
- **digest()** (14 connections) — `src/pipeline/detection/omr_job.py`
- **consume()** (13 connections) — `src/pipeline/detection/omr_job.py`
- **build()** (10 connections) — `src/pipeline/detection/omr_job.py`
- **prediction_bytes()** (9 connections) — `src/pipeline/detection/omr_job.py`
- **Path** (8 connections)
- **omr_job_worker.py** (8 connections) — `src/pipeline/detection/omr_job_worker.py`
- **run()** (8 connections) — `src/pipeline/detection/omr_job_worker.py`
- **atomic_publish()** (7 connections) — `src/pipeline/detection/omr_job.py`
- **bind_sources()** (6 connections) — `src/pipeline/detection/omr_job.py`
- **bind_sr()** (6 connections) — `src/pipeline/detection/omr_job.py`
- **execute_worker()** (6 connections) — `src/pipeline/detection/omr_job.py`
- **Handoff** (6 connections) — `src/pipeline/detection/omr_job.py`
- **build()** (6 connections) — `tests/test_omr_job.py`
- **prepared()** (6 connections) — `tests/test_omr_job.py`
- **Any** (5 connections)
- **inputs()** (5 connections) — `tests/test_omr_job.py`
- **test_bind_sr_rejects_changed_source_and_foreign_sr()** (5 connections) — `tests/test_omr_job_route.py`
- **test_failed_directory_cannot_be_reused_but_fresh_job_recovers()** (5 connections) — `tests/test_omr_job.py`
- **test_worker_fault_cannot_publish_complete_and_retains_diagnostics()** (5 connections) — `tests/test_omr_job.py`
- **.from_request()** (4 connections) — `src/pipeline/detection/omr_job.py`
- **_sr()** (4 connections) — `tests/test_omr_job_route.py`
- **test_any_tampered_identity_rejects_even_when_consuming_another_page()** (4 connections) — `tests/test_omr_job.py`
- **.cancelled()** (3 connections) — `src/pipeline/engine_lifecycle.py`
- *... and 19 more nodes in this community*

## Relationships

- [Community 65](Community_65.md) (7 shared connections)
- [Community 111](Community_111.md) (4 shared connections)
- [Community 80](Community_80.md) (2 shared connections)
- [Community 81](Community_81.md) (2 shared connections)
- [Community 16](Community_16.md) (1 shared connections)
- [Community 30](Community_30.md) (1 shared connections)
- [Community 77](Community_77.md) (1 shared connections)
- [Community 2](Community_2.md) (1 shared connections)

## Source Files

- `src/pipeline/detection/omr_job.py`
- `src/pipeline/detection/omr_job_worker.py`
- `src/pipeline/engine_lifecycle.py`
- `tests/test_omr_job.py`
- `tests/test_omr_job_route.py`

## Audit Trail

- EXTRACTED: 113 (96%)
- INFERRED: 5 (4%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*