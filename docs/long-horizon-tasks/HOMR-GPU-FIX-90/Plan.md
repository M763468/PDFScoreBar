# Plan

## M0 Baseline
- [x] Reproduce the issue: Confirmed `CUDAExecutionProvider` is missing and both `onnxruntime` and `onnxruntime-gpu` are mixed in `sr_eval_gpu`.
- [x] Confirmed GPU inference falls back to CPU.

## M1 Immediate Fix & Verification (Container)
- [x] Manually uninstall `onnxruntime` and `onnxruntime-gpu`.
- [x] Reinstall only `onnxruntime-gpu==1.24.3`.
- [x] Verify `CUDAExecutionProvider` is present.
- [x] Verify `HomrPredictor` works without warnings in a test run. (Confirmed Tromr inference used CUDA).

## M2 Dockerfile Hardening
- [x] Modify `Dockerfile.sr_eval` to ensure `onnxruntime` (CPU) is correctly replaced by the GPU version.
- [x] Updated `onnxruntime-gpu` version to `1.24.3` to match `homr` requirements (`^1.22.1`).

## M3 Verification
- [x] Verified `make lint` and `make format`.
- [x] Confirmed inference speed improvement.
