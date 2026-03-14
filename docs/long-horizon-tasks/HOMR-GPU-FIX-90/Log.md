# Execution Log

## 2026-03-14 Initial Setup
- Created task directory.
- Defined `Prompt.md` and updated it with Issue #90 specifics.

## 2026-03-14 Milestone M0: Baseline Reproduction
- Confirmed `sr_eval_gpu` container had both `onnxruntime` (CPU) and `onnxruntime-gpu` (GPU) installed (v1.24.3).
- Verified `CUDAExecutionProvider` was missing inside the container's `/opt/venv_sr` environment.
- Verified pipeline run on host fell back to CPU (using host's `.venv_pdf`).
- Verified pipeline run inside container also fell back to CPU due to package conflict.

## 2026-03-14 Milestone M1: Manual Fix & Verification
- Manually uninstalled both `onnxruntime` and `onnxruntime-gpu` in the container.
- Reinstalled only `onnxruntime-gpu==1.24.3`.
- Confirmed `CUDAExecutionProvider` appeared in `onnxruntime.get_available_providers()`.
- Ran a subset pipeline test (`Prokofiev Page 1`) inside the container and confirmed `CUDAExecutionProvider` was successfully used (Memcpy warnings from ONNX Runtime confirmed CUDA execution).
- Observed significant speed improvement (Inference time for Tromr was ~2-6s per staff).

## 2026-03-14 Milestone M2: Dockerfile Hardening
- Updated `Dockerfile.sr_eval` to resolve the conflict during build time.
- Implementation: `uv pip uninstall onnxruntime onnxruntime-gpu && uv pip install onnxruntime-gpu==1.24.3`.
- This ensures that even if `uv` re-installs the CPU version as a dependency of `homr`, it is explicitly cleaned up and replaced by the GPU version.
- Upgraded version to `1.24.3` to match `homr`'s `^1.22.1` requirement and prevent future re-installation.
