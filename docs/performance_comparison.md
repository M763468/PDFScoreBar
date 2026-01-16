# Performance Comparison: Hybrid Pipeline Optimization

## Phase 1: Baseline Establishment (2026-01-16)

**Benchmark Target**: `page_10.png` (2700x3600)
**Hardware**: GeForce 4060 (8GB VRAM)
**Run ID**: `page_10_bench_20260116_213356`

| Stage | Duration (Approx) | Notes |
| :--- | :--- | :--- |
| **Step 1: Homr Baseline** | **~2 min** | Segnet: ~1.7s, TrOmr: ~52s (Total). Includes initialization overhead. |
| **Step 2: Homr SR (x4)** | **~7 min** | **Bottleneck**. Segnet: ~80s, TrOmr: ~180s. SR Tiling overhead included. |
| **Step 3: OMR-DLN SR** | **~1-2 min** | **Redundancy**. Re-runs SR (Tiling) on the same image. Inference is fast. |
| **Step 4: Hybrid Gen** | **< 1s** | Negligible. |
| **Total** | **~10-11 min** | |

### Identified Bottlenecks
1.  **SR Calculation Redundancy**: SR is calculated independently in Step 2 and Step 3.
2.  **Homr SR Inference**:
    *   **Segnet**: Jumped from ~1.7s to ~80s (47x slower) on 4x image.
    *   **TrOmr**: Jumped from ~52s to ~180s (3.5x slower).

### Optimization Plan
1.  **Eliminate Redundancy**: Pass the SR image generated in Step 2 to Step 3.
2.  **Optimize Homr SR**: Investigate why Segnet is scaling so poorly.
    *   Can we run Segnet on the original image (or x2) and map coordinates to x4?
    *   Does TrOmr really need x4?

---
