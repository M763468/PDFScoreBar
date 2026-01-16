# Next Session Notes: Pipeline Optimization & Performance Tuning

**Target Branch**: `feature/pipeline_optimization`
**Objective**: Finalize verification of the Proxy Inference strategy and quantify end-to-end performance gains.

---

## 1. Current Status (2026-01-17)
- **Proxy Inference Strategy**: Implemented in `src/homr_eval_scripts/homr_evaluator.py`.
- **Performance Gain**:
    - Segnet: ~66x speedup.
    - TrOmr: ~6.5x speedup.
- **Infrastucture**: `sr_eval_gpu` container is now correctly configured for this workspace. `external/realesrgan` has been restored.

## 2. Next Session Tasks

### Phase 3: End-to-End Verification & Benchmarking
*   **Goal**: Confirm that the optimized pipeline produces accurate results and measure the final end-to-end execution time.
*   **Tasks**:
    *   [ ] **Full Benchmark Run**: Execute `tools/run_hybrid_pipeline.sh` on `page_10.png` with actual Real-ESRGAN upscaling enabled.
    *   [ ] **Accuracy Validation**: Use `tools/compare_hybrid_results.py` to compare the optimized output with the Phase 1 baseline.
    *   [ ] **Metric Logging**: Record the final "Total Time" and individual stage timings in `docs/performance_comparison.md`.

### Phase 4: Expansion & Refinement
*   **Goal**: Ensure the optimization is robust across different scores.
*   **Tasks**:
    *   [ ] **Multi-page Test**: Run the optimized pipeline on 3-5 additional pages (e.g., `page_15`, `page_3`).
    *   [ ] **Parameter Tuning**: Verify if the `target_pixels = 3.5MP` threshold is optimal for detection accuracy.

## 3. Reference Commands
```bash
# Full Benchmark Run
bash tools/run_hybrid_pipeline.sh --image data/training/images/page_10.png --run-id page_10_final_bench

# Result Comparison
python3 tools/compare_hybrid_results.py logs/hybrid_pipeline_bench/baseline_run/sr/page_10/page_10_detections.json logs/hybrid_pipeline_bench/optimized_run/sr/page_10/page_10_detections.json
```