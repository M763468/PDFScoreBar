# Community 325

> 13 nodes · cohesion 0.24

## Key Concepts

- **get_pipeline_python()** (16 connections) — `src/pipeline/core/python_env.py`
- **python_env.py** (9 connections) — `src/pipeline/core/python_env.py`
- **get_docker_exec_prefix()** (6 connections) — `src/pipeline/core/python_env.py`
- **test_python_env.py** (5 connections) — `tests/test_python_env.py`
- **is_in_container()** (4 connections) — `src/pipeline/core/python_env.py`
- **test_get_docker_exec_prefix_does_not_probe_another_container()** (2 connections) — `tests/test_python_env.py`
- **test_get_docker_exec_prefix_uses_canonical_container()** (2 connections) — `tests/test_python_env.py`
- **test_get_pipeline_python_uses_explicit_override_without_managed_environment()** (2 connections) — `tests/test_python_env.py`
- **test_get_pipeline_python_uses_pipeline_venv_in_container()** (2 connections) — `tests/test_python_env.py`
- **Python interpreter selection for pipeline sub-processes.** (1 connections) — `src/pipeline/core/python_env.py`
- **Checks if the current process is running inside a project Docker container.** (1 connections) — `src/pipeline/core/python_env.py`
- **Returns the canonical pipeline docker exec prefix when available from the host.** (1 connections) — `src/pipeline/core/python_env.py`
- **Returns the appropriate Python interpreter command (possibly with docker exec).…** (1 connections) — `src/pipeline/core/python_env.py`

## Relationships

- [Community 46](Community_46.md) (4 shared connections)
- [Community 22](Community_22.md) (4 shared connections)
- [Community 91](Community_91.md) (3 shared connections)
- [Community 25](Community_25.md) (3 shared connections)

## Source Files

- `src/pipeline/core/python_env.py`
- `tests/test_python_env.py`

## Audit Trail

- EXTRACTED: 33 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*