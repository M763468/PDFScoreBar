# Refactoring Memo: Environment Unification & Subprocess Removal

Date: 2026-03-12

## Context
Currently, the pipeline (`src/pipeline/main.py`) relies on `docker exec` (via `src/pipeline/python_env.py`) to run "heavy" steps like `homr` and `omr_dln` because they require specific CUDA environments and dependencies (Real-ESRGAN, etc.) that are not present in the host `.venv_pdf`.

## Goal (Target of Issue #7)
Remove all `docker exec` calls and subprocess hops for environment management. Enable direct in-process execution (Import & Run) for all steps.

## Identified Technical Debt
1.  **Environment Fragmentation**: `sr_eval_gpu` (Docker) has Real-ESRGAN/ONNX, but the host environment does not.
2.  **Path Resolution**: `docker exec` maps host paths to `/workspace`, which creates complexity in log directory resolution.
3.  **In-Process Bottlenecks**: `homr` (TrOmr) currently runs as a standalone script. It needs to be refactored into a class/method that can be imported.
4.  **Makefile Complexity**: `make run-pipeline` is hardcoded to use `docker exec sr_eval_gpu`, making it brittle.

## Proposed Actions
1.  **Unified Docker Image**: Ensure the primary development image (`Dockerfile`) contains ALL dependencies for both `pipeline` and `homr/sr`.
2.  **PythonPath Consolidation**: Add `external/homr` and `external/oemer` to `PYTHONPATH` permanently within the unified environment.
3.  **API Refactoring**:
    -   `src/homr_eval_scripts/homr_evaluator.py` -> Refactor into `HomrProcessor` class.
    -   `src/pipeline/detection.py` -> Replace `run_with_logging(cmd)` with direct calls to `HomrProcessor.process()`.
4.  **Entry Point Standardization**:
    -   `make run-pipeline` should detect if it's already in the container and avoid `docker exec` if so.
    -   Host-side execution should only be for lightweight checks.

## Repetitive/Blocked Tasks Memo (For Future Skills)
- **Environment Verification**: Checking which `.venv` has which package (need a "env-doctor" skill).
- **PR Refinement Loop**: Fetching comments -> Analyzing -> Implementing -> Re-posting (need a "pr-refinement" skill, currently in progress).
- **Log Inspection**: Parsing `pipeline.log` to find specific step durations (need a "log-analyzer" skill).
