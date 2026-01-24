# Next Session Notes: Pipeline Optimization & Performance Tuning

**NOTE**: This file is a historical snapshot. The authoritative, reproducible record
is in `docs/DEVLOG_MEASURE_NUMBERING.md` (measure numbering/MMR) and
`docs/DEVLOG_CNN_TRAINING.md` (CNN training).

**Last Updated**: 2026-01-24
**Current Phase**: Pipeline Optimization - Ready for Integration

---

## 1. Current Status (2026-01-24)
- **Proxy Inference Strategy**: Implemented and verified (Phase 2).
    - **Performance Gain**: Segnet ~66x speedup, TrOmr ~6.5x speedup.
    - **Bottleneck Shift**: Inference is no longer the bottleneck. Real-ESRGAN generation (~120-180s/page) now dominates.
- **Real-ESRGAN Tuning (Phase 5A)**: Completed.
    - **Optimal Config**: `tile=512` (Auto) + `fp16` is the best balance for RTX 4060 (8GB).
    - **CLI Control**: Added `--sr-tile`, `--sr-tile-pad`, `--sr-fp32` to `homr_evaluator.py`.
- **SR Reuse Validation (Phase 4)**: Verified.
    - **Page 10 (Large)**: ~54s reduction (~20% total time). Reuse is highly effective for large images.
- **Documentation**: Benchmarks recorded in `docs/performance_comparison.md`.

## 2. Tasks & Strategy (Updated)

### Phase 5B: Batch Processing Architecture (Migrated)
**Decision (2026-01-24)**: This task is migrated to merge with the `plan/full_pipeline_workflow` initiative.
- **Reason**: The "Python Loop" optimization is functionally identical to the "End-to-End Orchestrator" planned in the full pipeline workflow. Developing them separately would cause redundancy.
- **Next Step**: Create a new integration branch based on `plan/full_pipeline_workflow` and incorporate the SR/Inference optimizations.

### Phase 5C: SR Decoupling & Caching (Pending)
*   Migration to the new orchestrator will naturally handle this via `generate_sr_image.py` or internal method calls.

## 3. Optimization Conclusion (2026-01-24)
- **Real-ESRGAN**: Tuning is considered complete. `tile=512` + `fp16` is the optimal configuration.
- **Inference**: Proxy Inference strategy effectively solved the bottleneck.
- **Pipeline**: The remaining overhead is purely "Cold Start" (Python startup & Model loading), which will be addressed by the Batch Processing Architecture / Orchestrator.

---

## 4. Reference Commands
```bash
# Full Benchmark Run (with SR generation)
bash tools/run_hybrid_pipeline.sh --image data/training/images/page_10.png --run-id page_10_bench_v3

# Benchmark with SR Reuse
bash tools/run_hybrid_pipeline.sh \
  --image data/training/images/page_10.png \
  --run-id page_10_reuse_test \
  --sr-image logs/hybrid_pipeline_bench/previous_run/sr/page_10/page_10/page_10.png

# Compare Results
python3 tools/compare_hybrid_results.py logs/bench/baseline_run.json logs/bench/optimized_run.json
```