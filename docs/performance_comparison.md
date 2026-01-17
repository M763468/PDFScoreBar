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

## Phase 2: Proxy Inference Optimization (2026-01-17)

**Optimization Strategy**:
SR処理後の巨大な画像（155MP相当）を直接Homrに渡すのではなく、推論用に適正解像度（~3.5MP）のプロキシ画像を生成して実行。検出結果（座標）をSR座標系に逆写像することで、精度を維持しつつ計算量を劇的に削減。

**Benchmark Result**: `page_10.png`
**Run ID**: `page_10_opt_final_20260117_035102`

| Metric | Baseline (Before Opt) | Optimized (Proxy) | Improvement |
| :--- | :--- | :--- | :--- |
| **Segnet Inference** | ~80.0 s | **~1.2 s** | **~66x Faster** |
| **TrOmr (Per Staff)** | ~15.0 s | **~2.3 s** | **~6.5x Faster** |
| **TrOmr Inference (Total)** | ~190.0 s | **~30.0 s** | **~6.3x Faster** |

### Conclusion
推論部分のボトルネックは完全に解消されました。今後の処理時間は、主にReal-ESRGANによる画像拡大処理（約3分）に依存することになります。
座標変換およびマスクのリサイズ処理（SR解像度への復元）も正常に動作し、後続のヒューリスティック処理への影響がないことを確認しました。

---

## Phase 3: Cache Cleanup Fix (2026-01-17)

**Issue**: After running Real-ESRGAN in-process, Segnet inference on the proxy image slowed to ~75s despite CUDA being selected.  
**Fix**: Call `torch.cuda.empty_cache()` immediately after SR to release large allocations.

### Benchmark Result: `page_10.png` (GT)
**Run ID**: `page_10_opt_final_bench_v2_gt_cachefix_20260117_152207`

| Stage | Duration | Notes |
| :--- | :--- | :--- |
| **Step 1: Homr Baseline** | **86 s** | Segnet ~1.2s, TrOmr ~2–3s per staff |
| **Step 2: Homr SR (x4)** | **167 s** | SR tiling + Segnet ~1.2s + TrOmr ~2–3s per staff |
| **Step 3: OMR-DLN SR** | **6 s** | Pre-computed SR input |
| **Step 4: Hybrid Gen** | **0 s** | |
| **Total** | **259 s** | |

### Benchmark Result: `page_15.png` (GT)
**Run ID**: `page_15_opt_cachefix_20260117_160346`

| Stage | Duration | Notes |
| :--- | :--- | :--- |
| **Step 1: Homr Baseline** | **107 s** | Segnet ~1.7s, TrOmr ~2–4s per staff |
| **Step 2: Homr SR (x4)** | **206 s** | SR tiling + Segnet ~1.3s + TrOmr ~2–4s per staff |
| **Step 3: OMR-DLN SR** | **8 s** | Pre-computed SR input |
| **Step 4: Hybrid Gen** | **0 s** | |
| **Total** | **321 s** | |

### Benchmark Result: `page_3.png` (GT)
**Run ID**: `page_3_opt_cachefix_20260117_161347`

| Stage | Duration | Notes |
| :--- | :--- | :--- |
| **Step 1: Homr Baseline** | **130 s** | Segnet ~1.2s, TrOmr ~2–4s per staff |
| **Step 2: Homr SR (x4)** | **167 s** | SR tiling + Segnet ~0.8s + TrOmr ~2–4s per staff |
| **Step 3: OMR-DLN SR** | **5 s** | Pre-computed SR input |
| **Step 4: Hybrid Gen** | **0 s** | |
| **Total** | **302 s** | |
