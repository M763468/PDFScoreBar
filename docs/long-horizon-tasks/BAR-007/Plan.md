# Milestone Plan: BAR-007 (Issue #7)

## Phase 1: Setup & Initial Audit
- [x] Create working branch `task/env-consolidation`. (Done)
- [x] Initialize `long-horizon-task` `BAR-007`. (Done)
- [x] Audit requirements from all current `Dockerfile`s and `.venv_*` environments (including `/opt/venv_sr` in `sr_eval_gpu`).
- [ ] Create a "Consolidated Requirements Matrix".
- [ ] Record audit findings in `Log.md`.

## Phase 2: Unified Dockerfile Implementation
- [x] Select `nvidia/cuda:12.3.2-cudnn9-runtime-ubuntu22.04` as the base image.
- [x] Integrate dependencies from `Dockerfile.sr_eval` (the most consolidated version).
- [x] Incorporate missing dependencies from `Dockerfile.homr` (Poetry-based) and base `Dockerfile` (Pip-based).
- [x] Archive `Dockerfile.groundingdino` as it is not part of the main pipeline (`src/pipeline`).
- [x] Implement the new unified `Dockerfile.unified`.

## Phase 3: Unified Requirements Management
- [x] Consolidate requirements into a single `requirements.txt` or `pyproject.toml` managed via `uv`.
- [x] Ensure the container's virtual environment (e.g., `/opt/venv_sr` from `sr_eval_gpu`) is mapped correctly to a unified structure.
- [x] Handle potential dependency conflicts.

## Phase 4: Verification & Integration
- [ ] Build the new `Dockerfile.unified`.
- [ ] Run end-to-end pipeline (`src/pipeline/main.py`) in the new container.
- [ ] Verify GPU usage and correctness in all modules (Homr, SR, MMR, etc.).

## Phase 5: Documentation & Cleanup
- [ ] Update `docs/ENVIRONMENTS.md`.
- [ ] Remove obsolete `Dockerfile.homr`, `Dockerfile.sr_eval`, and `Dockerfile.groundingdino`.
- [ ] Rename `Dockerfile.unified` to `Dockerfile`.
- [ ] Prepare instructions for cleaning up host `.venv_*` environments.

## Milestones
- **M1: Audit Complete**: Consolidated requirements matrix created.
- **M2: Unified Image Built**: New Dockerfile successfully built and runs basic tasks.
- **M3: Pipeline Verified**: Full pipeline runs correctly in the new environment.
- **M4: Task Complete**: Documentation updated and obsolete files removed.
