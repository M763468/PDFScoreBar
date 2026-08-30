# current_support_worker.py

> 20 nodes · cohesion 0.21

## Key Concepts

- **current_support_worker.py** (20 connections) — `src/pipeline/detection/current_support_worker.py`
- **get_pipeline_python()** (13 connections) — `src/pipeline/core/python_env.py`
- **run()** (13 connections) — `src/pipeline/detection/current_support_worker.py`
- **python_env.py** (8 connections) — `src/pipeline/core/python_env.py`
- **Path** (7 connections)
- **_require_precomputed_sr()** (7 connections) — `src/pipeline/detection/current_support_worker.py`
- **_build_worker_environment()** (6 connections) — `src/pipeline/detection/current_support_worker.py`
- **_run_child_worker()** (6 connections) — `src/pipeline/detection/current_support_worker.py`
- **Any** (5 connections)
- **get_docker_exec_prefix()** (4 connections) — `src/pipeline/core/python_env.py`
- **is_in_container()** (4 connections) — `src/pipeline/core/python_env.py`
- **_load_completed_result()** (4 connections) — `src/pipeline/detection/current_support_worker.py`
- **_load_request()** (4 connections) — `src/pipeline/detection/current_support_worker.py`
- **main()** (3 connections) — `src/pipeline/detection/current_support_worker.py`
- **Python interpreter selection for pipeline sub-processes.** (1 connections) — `src/pipeline/core/python_env.py`
- **Checks if the current process is running inside a Docker container.** (1 connections) — `src/pipeline/core/python_env.py`
- **Returns the docker exec prefix if a supported container is running and we are…** (1 connections) — `src/pipeline/core/python_env.py`
- **Returns the appropriate Python interpreter command (possibly with docker exec).…** (1 connections) — `src/pipeline/core/python_env.py`
- **Generate current x4/HOMR/OMR support for one detector page. The current support…** (1 connections) — `src/pipeline/detection/current_support_worker.py`
- **Build the fresh current-runtime environment without local HOMR shadow paths.** (1 connections) — `src/pipeline/detection/current_support_worker.py`

## Relationships

- [span](span.md) (8 shared connections)
- [test_issue274_two_homr_profile.py](test_issue274_two_homr_profile.py.md) (5 shared connections)
- [test_issue284_sr_batch_contract.py](test_issue284_sr_batch_contract.py.md) (4 shared connections)
- [hybrid.py](hybrid.py.md) (3 shared connections)
- [run_mmr_batch](run_mmr_batch.md) (3 shared connections)
- [homr_profile.py](homr_profile.py.md) (3 shared connections)
- [install_current_homr_consumer_compat](install_current_homr_consumer_compat.md) (3 shared connections)
- [restored_orchestrator.py](restored_orchestrator.py.md) (2 shared connections)
- [BatchSRVerifiedProfileHybridDetector](BatchSRVerifiedProfileHybridDetector.md) (1 shared connections)

## Source Files

- `src/pipeline/core/python_env.py`
- `src/pipeline/detection/current_support_worker.py`

## Audit Trail

- EXTRACTED: 71 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*