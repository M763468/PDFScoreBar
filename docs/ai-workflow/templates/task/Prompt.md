# Task: <task name>

## Context
Describe the current system component, history, and relevant constraints.

## Problem
Explain the current issue, bottleneck, or requirement.

## Goals
List measurable targets.
Example:
- Reduce latency by 30%
- Maintain output compatibility with OMR geometry.
- Add unit tests for `BARLINE_MATCHER`.

## Non‑Goals
Explicitly list what must **not** change.
- No changes to `pdf_to_images.py`.
- Do not introduce new third-party dependencies.

## Acceptance Criteria / Definition of Done
- All CI tests pass.
- Benchmarks recorded in `Benchmarks.md`.
- Documentation updated in `docs/`.
- No regression in barline detection accuracy.
