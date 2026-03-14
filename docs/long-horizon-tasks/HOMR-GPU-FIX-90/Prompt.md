# Task: HOMR-GPU-FIX-90 (Issue #90)

## Context
- Container: `sr_eval_gpu`
- Virtualenv: `/opt/venv_sr`
- Model: Homr (Segnet inference)
- Problem: ONNX Runtime falls back to CPU due to package conflict.

## Problem
In the `sr_eval_gpu` container, Homr inference is significantly slower because it runs on the CPU. The logs indicate that `CUDAExecutionProvider` is not available, and both `onnxruntime` and `onnxruntime-gpu` are present in the environment, causing a conflict.

## Goals
- Resolve the `onnxruntime` vs `onnxruntime-gpu` conflict in the `/opt/venv_sr` environment.
- Ensure `HomrPredictor` successfully uses `CUDAExecutionProvider`.
- Restore inference speed to GPU levels (a few seconds per page).
- Reflect the fix in `Dockerfile.sr_eval` or the relevant package management configuration.

## Non‑Goals
- Changing the Homr model architecture.
- Modifying the pipeline logic outside of environment/dependency configuration.

## Acceptance Criteria / Definition of Done
- [ ] No `UserWarning` about `CUDAExecutionProvider` missing in `sr_eval_gpu`.
- [ ] Homr inference completes in seconds rather than minutes.
- [ ] `onnxruntime` (CPU-only) is uninstalled if `onnxruntime-gpu` is intended for use.
- [ ] `Dockerfile.sr_eval` is updated to prevent future regressions.
