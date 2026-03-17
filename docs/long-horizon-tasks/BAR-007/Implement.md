# Implementation Notes: BAR-007 (Issue #7)

## Base Image Strategy
Standardize on `nvidia/cuda:12.3.2-cudnn9-runtime-ubuntu22.04` as used in `Dockerfile.sr_eval`. This image supports the current mainline requirement for CUDA 12.3 while providing a stable base for `homr` and `Real-ESRGAN`.

## Dependency Resolution
- Use `uv` for lightning-fast installs.
- Target Python 3.11 as the default version.
- Handle `ultralytics`, `basicsr`, and `homr` as editable installs or direct dependencies.

## Key Path Assumptions
- All source code is under `/workspace`.
- External libraries: `external/homr`, `external/realesrgan`, `external/grounding_dino`.
- Mount points: `data`, `logs`, `models`.

## Known Issues/Risks
- **Conflict between `ultralytics` and `homr`**: Verify if both can share the same `torch` version.
- **`basicsr` patch**: Keep the `sed` patch for `rgb_to_grayscale` as per `Dockerfile.sr_eval`.
- **`onnxruntime-gpu` vs `onnxruntime`**: Always prefer `onnxruntime-gpu` and uninstall the CPU version.

## Next Steps
1. Perform a detailed audit of `Dockerfile.homr` (Poetry) to ensure all system libs and Python packages are correctly transitioned to `uv` in the new image.
2. Check `Dockerfile.groundingdino` and decide if it can be integrated into the CUDA 12 environment.
