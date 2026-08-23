# current_support_worker.py

> 19 nodes · cohesion 0.20

## Key Concepts

- **current_support_worker.py** (15 connections) — `src/pipeline/detection/current_support_worker.py`
- **get_pipeline_python()** (11 connections) — `src/pipeline/core/python_env.py`
- **run()** (10 connections) — `src/pipeline/detection/current_support_worker.py`
- **python_env.py** (7 connections) — `src/pipeline/core/python_env.py`
- **_build_worker_environment()** (6 connections) — `src/pipeline/detection/current_support_worker.py`
- **Path** (6 connections)
- **_run_child_worker()** (6 connections) — `src/pipeline/detection/current_support_worker.py`
- **get_docker_exec_prefix()** (4 connections) — `src/pipeline/core/python_env.py`
- **is_in_container()** (4 connections) — `src/pipeline/core/python_env.py`
- **_load_completed_result()** (4 connections) — `src/pipeline/detection/current_support_worker.py`
- **_load_request()** (4 connections) — `src/pipeline/detection/current_support_worker.py`
- **Any** (4 connections)
- **main()** (2 connections) — `src/pipeline/detection/current_support_worker.py`
- **Python interpreter selection for pipeline sub-processes.** (1 connections) — `src/pipeline/core/python_env.py`
- **Checks if the current process is running inside a Docker container.** (1 connections) — `src/pipeline/core/python_env.py`
- **Returns the docker exec prefix if a supported container is running and we are…** (1 connections) — `src/pipeline/core/python_env.py`
- **Returns the appropriate Python interpreter command (possibly with docker exec).…** (1 connections) — `src/pipeline/core/python_env.py`
- **Generate current x4/HOMR/OMR support for one detector page. The current support…** (1 connections) — `src/pipeline/detection/current_support_worker.py`
- **Build the fresh current-runtime environment without local HOMR shadow paths.** (1 connections) — `src/pipeline/detection/current_support_worker.py`

## Relationships

- [test_issue274_two_homr_profile.py](test_issue274_two_homr_profile.py.md) (5 shared connections)
- [hybrid.py](hybrid.py.md) (3 shared connections)
- [pipeline/orchestrator.py](pipeline-orchestrator.py.md) (3 shared connections)
- [homr_profile.py](homr_profile.py.md) (3 shared connections)
- [current_homr_worker.py](current_homr_worker.py.md) (3 shared connections)
- [test_issue255_production_detector_restoration.py](test_issue255_production_detector_restoration.py.md) (2 shared connections)

## Source Files

- `src/pipeline/core/python_env.py`
- `src/pipeline/detection/current_support_worker.py`

## Audit Trail

- EXTRACTED: 54 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*