# Task: BAR-007 (Issue #7)

## Context
Currently, the project has multiple overlapping Docker containers (`Dockerfile`, `Dockerfile.homr`, `Dockerfile.sr_eval`, `Dockerfile.groundingdino`) and specialized virtual environments (`.venv_pdf`, `.venv_cnn_classifier`, `.venv_yolo`, `.venv_omr_dln`). This fragmentation increases maintenance overhead and makes pipeline integration complex.

## Problem
Fragmented environments cause:
- Redundancy in dependency management.
- Complexity in cross-environment calls (e.g., `subprocess` to `docker exec`).
- Slow build times and large total disk footprint.

## Goals
- Consolidate multiple Docker containers into a unified, maintainable structure.
- Reduce redundancy and maintenance overhead.
- Ensure all pipeline steps (`homr`, `SR`, `OMR-DLN`, `CNN classifier`) work in a single environment.
- Clean up obsolete `Dockerfile`s and virtual environments.

## Non‑Goals
- No changes to the core logic of barline detection or super-resolution.
- No changes to the data directory layout.

## Acceptance Criteria / Definition of Done
- A single unified `Dockerfile` (or a clear, minimal set) is functional.
- The full pipeline (`src/pipeline/main.py`) runs end-to-end in the unified container.
- `docs/ENVIRONMENTS.md` is updated to reflect the new structure.
- Obsolete Dockerfiles are removed.
- All CI tests and `make check-consistency` pass.
