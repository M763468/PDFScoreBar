# Next Session Notes: Pipeline Optimization & Performance Tuning

**Target Branch**: `feature/pipeline_optimization`
**Worktree**: `ws_PDFScoreBar_training` (Reused)
**Objective**: Drastically reduce the execution time of the candidate generation pipeline (specifically Super-Resolution overhead) while maintaining detection accuracy parity with the current baseline.

---

### Operational Rules
- **Do not overwrite** `docs/SESSION_LOG.md`. Append new findings.
- **Reproducibility**: Record commit hash + command + output path for all major results.

---

## 1. Project Goal & Current Status
**Goal**: Optimize the candidate generation pipeline to reduce execution time (SR bottleneck) without compromising accuracy.

**Current Phase**: Phase 1 - Analysis & Benchmarking

**Status Update (2026-01-15)**:
- **Worktree**: `ws_PDFScoreBar_training` (Reused).
- **Branch**: `feature/pipeline_optimization`.
- **Infrastructure**: `tools/run_hybrid_pipeline.sh` now includes performance timing.
- **Identified Blocker**: Step 2 (Homr SR) is the primary bottleneck and caused a hang during the initial benchmark on `page_10`.
- **Cleanup Required**: `logs/hybrid_generalization/page_10_bench/` contains root-owned files. Use `sudo rm -rf` to clear it before reuse.

## 2. Planned Tasks (Pipeline Optimization)

### A. Pipeline Analysis & Baseline Establishment
*   **Goal**: Quantify current performance and freeze expected outputs for regression testing.
*   **Tasks**:
    *   [ ] **Select Benchmark Set**: Choose 5-10 representative pages (varying density, noise, resolution).
    *   [ ] **Generate Baseline Artifacts**: Run the current full pipeline (Homr + OMR-DLN + SR x4) on the benchmark set. Save the `candidates.json` and execution logs.
    *   [ ] **Measure Execution Time**: Record precise timings for each stage (PDF->Img, Homr, SR, OMR-DLN, Merging).

### B. Bottleneck Identification
*   **Goal**: Pinpoint the exact cause of slowness in the SR stage.
*   **Tasks**:
    *   [ ] **Profiling**: Use `cProfile` or detailed logging to analyze the `RealESRGAN` inference step.
    *   [ ] **Resource Monitoring**: Check GPU/CPU utilization and VRAM transfer overhead during SR.
    *   [ ] **Hypothesis Testing**: Is it the model size? The input image resolution? The tiling strategy?

### C. Optimization Implementation
*   **Goal**: Implement efficiency improvements targeting the identified bottlenecks.
*   **Strategies to Explore**:
    *   **Inference Optimization**:
        *   Enable **FP16 (Half-Precision)** inference for Real-ESRGAN (if supported by hardware/library).
        *   Investigate **TensorRT** or **ONNX Runtime** optimization for the SR model.
    *   **Algorithmic Optimization**:
        *   **Selective SR**: Only apply SR to specific regions of interest (ROIs) instead of the full page.
        *   **Resolution Tuning**: Does OMR-DLN *really* need x4 scaling? Test x2 or x3 scaling to see if accuracy degrades.
        *   **Tiling Strategy**: Optimize tile size and overlap to maximize GPU parallelism.

### D. Result Verification (Regression Testing)
*   **Goal**: Ensure the optimized pipeline produces results equivalent to the baseline.
*   **Tasks**:
    *   [ ] **Comparison Script**: Create a tool to compare `optimized_candidates.json` vs `baseline_candidates.json`.
    *   [ ] **Metric Definition**:
        *   **Speedup**: Target > 2x improvement.
        *   **Accuracy**: IoU > 0.98 or F1-score retention (allow minor pixel-level shifts, but no lost barlines).
    *   [ ] **Visual Validation**: Generate overlays for any discrepancies.

### E. Documentation
*   **Goal**: Record findings and usage instructions.
*   **Tasks**:
    *   [ ] Update `docs/performance_comparison.md` with Before/After metrics.
    *   [ ] Document new library requirements (e.g., TensorRT) if applicable.

## 3. Reference Configs & Artifacts
*   **Baseline Pipeline Script**: `run_batch_candidates.sh` (Primary entry point to be optimized).
*   **SR Model**: `RealESRGAN_x4plus`.
