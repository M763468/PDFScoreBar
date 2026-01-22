# Next Session Notes: Pipeline Optimization & Performance Tuning

**Target Branch**: `feature/pipeline_optimization`
**Objective**: Finalize verification of the Proxy Inference strategy and implement advanced optimizations (Caching, Batching) to minimize turnaround time.

---

## 1. Current Status (2026-01-23)
- **Proxy Inference Strategy**: Implemented and verified (Phase 2).
    - **Performance Gain**: Segnet ~66x speedup, TrOmr ~6.5x speedup.
    - **Bottleneck Shift**: Inference is no longer the bottleneck. Real-ESRGAN generation (~120-180s/page) now dominates.
- **SR Reuse Validation (Phase 4)**: Verified.
    - **Page 10 (Large)**: ~54s reduction (~20% total time). Reuse is highly effective for large images.
    - **Page 3 (Small)**: Negligible reduction.
- **Documentation**: Benchmarks recorded in `docs/performance_comparison.md`.

## 2. Tasks

### Phase 5: Advanced Optimization (Next)
#### A. Real-ESRGAN Tuning (Priority: High)
*   [ ] **Tile Size Experiment**: Benchmark `tile=1024` vs `tile=512` vs `no_tile` to see if SR generation itself can be faster.
*   [ ] **Padding Tuning**: Check if `tile_pad` reduction affects edge artifacts or speed.
*   [ ] **Precision**: Ensure `fp16` is strictly enabled.

#### B. Batch Processing Architecture (Priority: Medium)
*   [ ] **Python Loop Implementation**: Modify `homr_evaluator.py` to accept a directory or glob pattern.
*   [ ] **Memory Management**: Implement explicit `gc.collect()` and `torch.cuda.empty_cache()` calls between images to prevent OOM.

#### C. SR Decoupling (Priority: Medium)
*   [ ] **Extract SR Tool**: Create `tools/generate_sr_image.py`.
*   [ ] **Caching**: Implement opt-in hash-based caching (`--use-cache`) for development iteration.

### Completed Tasks (Phase 3 & 4)
#### Phase 3: End-to-End Verification (Done)
*   [x] **Full Benchmark Run**: Executed `tools/run_hybrid_pipeline.sh` on `page_10.png` with SR enabled.
*   [x] **Accuracy Check**: Compared `baseline` vs `optimized` output. Accuracy maintained.

#### Phase 4: Expansion & Tuning (Done)
*   [x] **Multi-page Validation**: Ran on `page_15`, `page_3`. Verified stability.
*   [x] **Parameter Tuning**: Verified `target_pixels = 3.5MP` threshold is effective.
*   [x] **SR Reuse Validation**: Quantified impact of caching SR images (Page 10: -54s).

---

## 3. Detailed Optimization Strategy (Reference)

This section details specific technical strategies to further reduce execution time and prepare for efficient batch processing of multiple images.

### A. Decoupling SR & Optional Caching
*   **Problem**: SR generation is expensive (~2 mins) and currently tightly coupled within `homr_evaluator.py`. Re-running inference logic triggers redundant SR calculation unless manually managed.
*   **Strategy 1: Decoupling (Architecture)**
    *   Extract SR logic into a standalone tool (e.g., `tools/generate_sr_image.py`).
    *   **Workflow**:
        1. Run `generate_sr_image.py` -> outputs high-res image.
        2. Run `homr_evaluator.py` taking the high-res image as input (bypass internal SR).
        3. Run `eval_omr_dln.py` taking the same high-res image.
    *   **Benefit**: Clearer data flow. The expensive step is performed exactly once, explicitly.
*   **Strategy 2: Hash-Based Caching (Dev Tool)**
    *   Implement caching strictly as an **opt-in developer feature** (`--use-cache`) for `generate_sr_image.py`.
    *   **Logic**: If enabled, check `data/cache/sr/<hash>_x4.png`. If hit, skip generation.
    *   **Impact**: drastically speeds up iterative experiments (parameter tuning) without adding complexity or "magic" behavior to the production pipeline.

### B. Real-ESRGAN Optimization
*   **Problem**: Default `tile=0` (auto) or conservative tiling might be suboptimal for RTX 4060 (8GB).
*   **Strategy**:
    *   Expose `tile` and `tile_pad` arguments in `src/common/preprocessing.py`.
    *   Benchmark `tile=1024` vs `tile=512` vs `no_tile`.
    *   Ensure `fp16` (half precision) is strictly enabled.

### C. Future Batch Processing Architecture
*   **Objective**: Efficiently process folders containing 10-100+ images.
*   **Current Limit**: `run_hybrid_pipeline.sh` invokes Python scripts per image. This incurs "Cold Start" penalties (Python startup + PyTorch/CUDA context init + Model Weights loading) for *every* image.
*   **Proposed Architecture**:
    1.  **Inversion of Control**: Instead of `Shell Loop -> Python`, use `Python Loop`.
        *   Modify `homr_evaluator.py` to accept a directory or glob pattern.
    2.  **Persistent Model Instance**:
        *   Load the SR Model and Homr Model **once** into VRAM.
        *   Iterate through images, processing them sequentially.
        *   **Benefit**: Saves ~5-10s overhead per image. On 100 images, this saves ~15 minutes.
    3.  **Memory Management**:
        *   Explicitly call `gc.collect()` and `torch.cuda.empty_cache()` after each image processing cycle to prevent VRAM fragmentation (OOM) on the 8GB card.
    4.  **Parallelism (CPU-bound tasks)**:
        *   While GPU inference must differ to sequential (on single GPU), CPU-bound tasks like "Heuristic filtering" or "XML Generation" can be offloaded to a `ProcessPoolExecutor` to run while the GPU processes the next image's SR.

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