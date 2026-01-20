# Next Session Notes: Pipeline Optimization & Performance Tuning

**Target Branch**: `feature/pipeline_optimization`
**Objective**: Finalize verification of the Proxy Inference strategy and implement advanced optimizations (Caching, Batching) to minimize turnaround time.

---

## 1. Current Status (2026-01-17)
- **Proxy Inference Strategy**: Implemented in `src/homr_eval_scripts/homr_evaluator.py`.
- **Performance Gain**:
    - Segnet: ~66x speedup (Proxy used).
    - TrOmr: ~6.5x speedup (Proxy used).
- **Remaining Bottleneck**: Real-ESRGAN generation takes ~120-180s per page, dominating the pipeline.

## 2. Immediate Tasks (Phase 3 & 4)

### Phase 3: End-to-End Verification
*   [ ] **Full Benchmark Run**: Execute `tools/run_hybrid_pipeline.sh` on `page_10.png` with SR enabled.
*   [ ] **Accuracy Check**: Compare `baseline` vs `optimized` output using `tools/compare_hybrid_results.py`.

### Phase 4: Expansion & Tuning
*   [ ] **Multi-page Validation**: Run on `page_15`, `page_3`.
*   [ ] **Parameter Tuning**: Verify `target_pixels = 3.5MP` threshold.

---

## 3. Future Optimization Strategy (Phase 5)

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
# Full Benchmark Run
bash tools/run_hybrid_pipeline.sh --image data/training/images/page_10.png --run-id page_10_final_bench

# Compare Results
python3 tools/compare_hybrid_results.py logs/hybrid_pipeline_bench/baseline_run/sr/page_10/page_10_detections.json logs/hybrid_pipeline_bench/optimized_run/sr/page_10/page_10_detections.json
```