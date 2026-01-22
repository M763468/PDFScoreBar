# Session Log

Last migrated: 2026-01-14

**Note**: The contents of this log have been migrated to `docs/DEVLOG_CNN_TRAINING.md` as part of the `experiment/cnn_classifier` branch closure.
Refer to that file for the complete history of the CNN training experiments.

New session entries should be appended below.

---

## Phase 1: Pipeline Analysis & Performance Benchmarking (2026-01-15)

### Objective
Establish a performance baseline for the current hybrid pipeline and identify major bottlenecks.

### Baseline Environment
- **Machine**: GeForce 4060 (8GB VRAM)
- **Container**: `sr_eval_gpu` (Docker)
- **Pipeline Script**: `tools/run_hybrid_pipeline.sh`
- **SR Model**: Real-ESRGAN x4 (`RealESRGAN_x4plus.pth`)

### Benchmarking Targets
- Page 10: `data/training/images/page_10.png`
- Page 15: `data/training/images/page_15.png`

### Initial Performance Measurements (Baseline)

| Page | Total Time | Homr Baseline | Homr SR | OMR-DLN SR | Hybrid Gen |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Page 10 | TBD | TBD | TBD | TBD | TBD |
| Page 15 | TBD | TBD | TBD | TBD | TBD |

### Interrupted Benchmark Analysis (2026-01-15)
- **Status**: The benchmark run for `page_10` was interrupted.
- **Progress**:
    - Step 1 (Homr Baseline): Completed.
    - Step 2 (Homr SR): Started but stalled/interrupted during inference.
    - Step 3 (OMR-DLN SR): Not started.
    - Step 4 (Hybrid Gen): Not started.
- **Log Analysis**: `logs/page_10_bench.log` shows the process hanging after "Running TrOmr inference on staff image 0" during the SR step. This confirms the SR/Inference stage is the major bottleneck or stability risk.

### Session Summary (2026-01-15) - Pipeline Optimization Phase 1
- **Achievements**:
    - Merged `experiment/cnn_classifier` into `main`.
    - Created `feature/pipeline_optimization` branch.
    - Updated `NEXT_SESSION_NOTES.md` with a 5-phase optimization plan.
    - Modified `tools/run_hybrid_pipeline.sh` to include automatic stage timing and summary reporting.
    - Identified Step 2 (Homr SR / Real-ESRGAN x4) as the primary bottleneck and a potential stability risk (hang during TrOmr inference).
- **Current Status**:
    - Initial benchmark for `page_10` stalled and was manually interrupted.
    - Cleanup attempt for `logs/hybrid_generalization/page_10_bench/` failed due to root-owned files from the Docker container.
- **Next Steps**:
    - **Cleanup**: (User Action) Remove `logs/hybrid_generalization/page_10_bench/` using `sudo` if possible.
    - **Benchmark**: Execute the timed pipeline with a fresh ID (e.g., `page_10_bench_v2`) to capture complete performance metrics.
    - **Optimization**: Focus on reducing SR overhead, possibly by caching SR results or optimizing inference (FP16/TensorRT).

### Next Session Commands (Reference)
```bash
# 1. Cleanup root-owned files (Use sudo if necessary)
# sudo rm -rf logs/hybrid_generalization/page_10_bench/

# 2. Re-run timed benchmark with fresh ID
bash tools/run_hybrid_pipeline.sh --image data/training/images/page_10.png --run-id page_10_bench_v2

# 3. Monitor log (if backgrounded)
# tail -f logs/page_10_bench_v2.log

---

## Phase 1: Pipeline Analysis & Performance Benchmarking (2026-01-16 Update)

### 1. Performance Measurements (Baseline)
| Page | Total Time | Step 1 (Homr Baseline) | Step 2 (Homr SR) | Step 3 (OMR-DLN SR) | Step 4 (Hybrid Gen) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Page 10 | ~11 min | ~2 min | **~7 min** | ~1.5 min | <1s |

**Key Findings**:
- **Step 2 (Homr SR)** is the primary bottleneck. 解像度が4倍になったことで、Segnetが約47倍、TrOmrが約3.5倍低速化している。
- **Step 3 (OMR-DLN SR)** に冗長な超解像（SR）処理が含まれている（Step 2と同じ計算を繰り返している）。
- **検出精度の分析**: SR版は単なる高精細化ではなく、強力なノイズフィルタとして機能している（Baselineの237個からSRの160個へ絞り込み）。スキップは不可。

### 2. 実施した改善策
- **出力ディレクトリの整理**: `tools/run_hybrid_pipeline.sh` を改修し、`logs/hybrid_pipeline_bench/` 以下に実行日時（タイムスタンプ）付きで保存するように変更。
- **冗長処理の排除**:
    - `experiments/models/eval_omr_dln.py` に `--pre-computed-sr` オプションを追加。
    - `tools/run_hybrid_pipeline.sh` で Step 2 の生成画像を Step 3 へ直接渡すように変更。
    - **期待効果**: 実行時間を約1.5〜2分短縮。

### 3. 新規作成ツール
- **`tools/compare_hybrid_results.py`**: 2つの出力結果（JSON）を比較し、最適化によって精度が落ちていないか検証するツール。
  - **使い方**: `python3 tools/compare_hybrid_results.py <baseline_json> <target_json>`
- **`tools/temp_analyze_overlap.py`**: パイプライン各段階での検出結果の重複率を分析するためのスクリプト。

### 4. Step 2 (Homr SR) のボトルネック詳細分析 (2026-01-16)
Dockerコンテナ内のソースコード (`homr/main.py`, `inference_segnet.py`) を解析し、低速化の主原因を特定した。

#### A. Segnet (Semantic Segmentation) : ~80秒
*   **処理内容**: 画像全体をスライディングウィンドウ方式で走査し、各ピクセルのクラス（五線、音符など）を判定する。
*   **原因**: `inference_segnet.py` は固定の `step_size` (320px) を使用している。
    *   SRにより解像度が縦横4倍（面積16倍）になると、処理すべきパッチの数が **16倍** に増加する。
    *   計算量 $O(Width \times Height)$ に比例するため、処理時間が激増した。
*   **最適化案**: Segnet は「1x（元解像度）」で実行し、生成されたマスクを4倍に拡大する。マスク（領域情報）は高解像度である必要性は低い。これにより **80秒 → 2秒** 程度への短縮が見込める。

#### B. TrOmr (Note Recognition / Transformer) : ~190秒
*   **処理内容**: 切り出された五線譜（Staff）画像から、音符や記号を認識する。
*   **原因**: SRにより各五線譜の画像サイズも4倍になっている。
    *   Transformerモデルはシーケンス長（画像パッチ数）に対して計算量が $O(N^2)$ で増加する傾向がある。
    *   元の学習データ（1x）よりも遥かに大きな画像を処理させているため、極めて非効率。
*   **最適化案**: TrOmr に入力する前に、切り出した五線譜画像を「標準サイズ（高さ128px等）」にリサイズ（ダウンサンプル）する。TrOmrの認識結果（XML）は座標変換で4xに戻すか、そもそもSRの恩恵を受けにくい工程として割り切る。

---

## Phase 2: Implementation of Proxy Inference Optimization (2026-01-17)

### Objective
Implement the "Proxy Inference" strategy to eliminate the performance bottleneck in Step 2 (Homr SR) without modifying external repositories.

### Changes
- **Modified**: `src/homr_eval_scripts/homr_evaluator.py`
    - Added logic to check if the input image (SR or large original) exceeds 5.25MP.
    - If exceeded, creates a temporary downscaled proxy image (~3.5MP).
    - Executes Homr inference on the proxy image.
    - Maps detected bounding box coordinates back to the high-resolution coordinate system.
    - Ensures segmentation masks are resized to full resolution for downstream heuristics.
- **Infrastucture**: Re-created `sr_eval_gpu` container with correct workspace mount point (`/home/masaki_muramatsu/ws_PDFScoreBar`).
- **Data Migration**: Copied `external/realesrgan` from the legacy workspace to ensure SR functionality.

### Verification Results (Page 10)
- **Segnet Speedup**: ~80s → **1.2s (~66x improvement)**.
- **TrOmr Speedup**: ~15s/staff → **2.3s/staff (~6.5x improvement)**.
- **Total Pipeline Impact**: Step 2 Homr processing time (excluding SR generation) reduced from ~4.5 min to **< 40s**.

### Status
- **Proxy Inference**: Successfully implemented and verified for performance.
- **Documentation**: Updated `docs/performance_comparison.md` with Phase 2 results.
- **Remaining Task**: Perform a full end-to-end benchmark with Real-ESRGAN enabled to confirm accuracy parity and final timing.

TODO: この方式によって検出される小節線などの結果が既存方式から劣化していないことを確認する必要がある。

---

## Phase 3: End-to-End Verification & Dependency Repair (2026-01-17)

### Status Update
- **OMR-DLN repo restored**: Cloned `external/omr_dln` from upstream (`dmgonzalez8/OMR`).
- **Model weights downloaded**: Pulled Google Drive model pack and placed into `external/omr_dln/models/public_models/` without overwriting existing files.
- **Real-ESRGAN import fixed**: Installed `external/realesrgan` into `/opt/venv_sr` inside `sr_eval_gpu`.
- **Pipeline re-run (no GT)**:
  - Run ID: `page_10_opt_final_bench_v2`
  - Output: `logs/hybrid_pipeline_bench/page_10_opt_final_bench_v2_20260117_143744`
  - Summary: Step1 88s / Step2 380s / Step3 12s / Step4 0s / Total 480s
  - Counts: Baseline 233, SR 156, OMR-DLN 320 (measures->barlines), Hybrid 152

### Follow-up
- Run the full pipeline **with GT** to record accuracy metrics.
- Investigate why Step 2 Segnet time is ~75s during SR (proxy inference expected to be ~1–2s).

### GT Benchmark Results (2026-01-17)
- **Run ID**: `page_10_opt_final_bench_v2_gt`
- **Output**: `logs/hybrid_pipeline_bench/page_10_opt_final_bench_v2_gt_20260117_145206`
- **OMR-DLN Metrics**:
  - TP 121 / FP 62 / FN 38
  - Precision 0.6612 / Recall 0.7610 / F1 0.7076
- **Hybrid Metrics**:
  - TP 149 / FP 1 / FN 10 / Soft Matches 2
  - Precision 0.9933 / Recall 0.9371 / F1 0.9644
- **Performance Summary**:
  - Step1 86s / Step2 399s / Step3 6s / Step4 0s / Total 491s
- **Open Issue**: SR Step2 Segnet still ~75s even when proxy image (1620x2160) is used; likely GPU/CPU fallback or unexpected path usage.

### Diagnostics (2026-01-17)
- Added Segnet ONNXRuntime provider logging to confirm CUDA vs CPU path:
  - `external/homr/homr/segmentation/inference_segnet.py` now logs available/selected ORT providers at model init.

### Provider Check Run (2026-01-17)
- **Run ID**: `page_10_opt_final_bench_v2_gt_providers`
- **Output**: `logs/hybrid_pipeline_bench/page_10_opt_final_bench_v2_gt_providers_20260117_150628`
- **Segnet ORT providers**:
  - Available: `['TensorrtExecutionProvider', 'CUDAExecutionProvider', 'CPUExecutionProvider']`
  - Selected: `['CUDAExecutionProvider', 'CPUExecutionProvider']`
- **Observation**: SR Step2 Segnet still ~75s despite CUDA provider selected, so slowdown is not a CPU fallback.

### Segnet Slowdown Root Cause (2026-01-17)
- **Repro**: Running Real-ESRGAN in-process causes subsequent Segnet inference to take ~75s.
- **Fix**: `torch.cuda.empty_cache()` restores Segnet time to <1s in the same process.
- **Change**: Added CUDA cache clear after SR in `src/homr_eval_scripts/homr_evaluator.py`.

### Cache Fix Verification (2026-01-17)
- **Run ID**: `page_10_opt_final_bench_v2_gt_cachefix`
- **Output**: `logs/hybrid_pipeline_bench/page_10_opt_final_bench_v2_gt_cachefix_20260117_152207`
- **Result**: SR Step2 Segnet back to ~1.2s; total time dropped to 259s.
- **Performance Summary**:
  - Step1 86s / Step2 167s / Step3 6s / Step4 0s / Total 259s

### Multi-page Verification (2026-01-17)
- **Run ID**: `page_15_opt_cachefix`
- **Output**: `logs/hybrid_pipeline_bench/page_15_opt_cachefix_20260117_160346`
- **OMR-DLN Metrics**:
  - TP 84 / FP 53 / FN 35
  - Precision 0.6131 / Recall 0.7059 / F1 0.6563
- **Hybrid Metrics**:
  - TP 106 / FP 2 / FN 13
  - Precision 0.9815 / Recall 0.8908 / F1 0.9339
- **Performance Summary**:
  - Step1 107s / Step2 206s / Step3 8s / Step4 0s / Total 321s

### Multi-page Verification (2026-01-17) - page_3
- **Run ID**: `page_3_opt_cachefix`
- **Output**: `logs/hybrid_pipeline_bench/page_3_opt_cachefix_20260117_161347`
- **OMR-DLN Metrics**:
  - TP 138 / FP 16 / FN 16
  - Precision 0.8961 / Recall 0.8961 / F1 0.8961
- **Hybrid Metrics**:
  - TP 152 / FP 9 / FN 2 / Soft Matches 18
  - Precision 0.9441 / Recall 0.9870 / F1 0.9651
- **Performance Summary**:
  - Step1 130s / Step2 167s / Step3 5s / Step4 0s / Total 302s

### SR Reuse Validation (2026-01-17) - page_3
- **Run ID**: `page_3_opt_reuse_sr`
- **Output**: `logs/hybrid_pipeline_bench/page_3_opt_reuse_sr_20260117_162654`
- **Command (SR step)**:
  - `/workspace/src/homr_eval_scripts/homr_evaluator.py --images /workspace/data/evaluation/images/page_3.png --output-root /workspace/logs/hybrid_pipeline_bench/page_3_opt_reuse_sr_20260117_162654/sr --force-run-id page_3 --enable-sr --ground-truth page_3:/workspace/data/evaluation/annotations/page_003/boxes_sorted.json --pre-computed-sr /workspace/logs/hybrid_pipeline_bench/page_3_opt_cachefix_20260117_161347/sr/page_3/page_3/page_3.png`
- **Accuracy (baseline homr)**:
  - TP 154 / FP 30 / FN 0
  - Precision 0.8370 / Recall 1.0000 / F1 0.9112
- **Accuracy (SR homr)**:
  - TP 144 / FP 24 / FN 10
  - Precision 0.8571 / Recall 0.9351 / F1 0.8944
- **Accuracy (OMR-DLN)**:
  - TP 138 / FP 16 / FN 16
  - Precision 0.8961 / Recall 0.8961 / F1 0.8961
- **Timing**:
  - No stage timing artifacts were generated for this run; `tools/run_hybrid_pipeline.sh` output needs to be captured (e.g., `tee logs/opt_reuse_sr.log`) to confirm the time saved by reusing SR.
- **Hybrid Metrics**:
  - `hybrid_predictions.json` exists, but no hybrid metrics file was generated; if needed, run a metrics step against GT.
- **Dependency Note**:
  - `external/omr_dln/README.md` points to a Google Drive link for model downloads. The current files in `external/omr_dln/models/public_models/` were preserved; their original source remains unverified, so do not delete them.
- **Serena Code Structure Scan**:
  - `src/homr_eval_scripts/homr_evaluator.py` contains core pipeline functions (`parse_args`, `run_homr_on_image`, `compute_metrics`, `aggregate_metrics`, `write_*`) and helper classes (`TransformInfo`, `BarlinePrediction`, `ImageMetrics`, `AggregateMetrics`).

### End-of-Session Checklist (2026-01-17)
- **Debug logging**: Keep Segnet provider diagnostics available via `HOMR_DEBUG_PROVIDERS=1`; do not remove debug mode support.
- **Timing capture needed**: Re-run the SR reuse test with `tools/run_hybrid_pipeline.sh | tee logs/opt_reuse_sr.log` to record stage timings.
- **Hybrid metrics**: If needed, compute metrics for `logs/hybrid_pipeline_bench/page_3_opt_reuse_sr_20260117_162654/hybrid_predictions.json`.
- **Next experiments (order)**:
  - SR reuse timing confirmation (page_3 or page_10).
  - x2 or lighter SR model experiment.
  - ESRGAN tile-size tuning.

---

## Phase 4: SR Cache Reuse Validation (2026-01-23)

### Objective
Quantify the potential time savings of "caching" or reusing pre-computed SR images (skipping Real-ESRGAN generation) in the pipeline.

### Benchmark Result: `page_3.png` (Small Image: 0.47 MP)
- **Run ID**: `page_3_reuse_sr_timed_v2`
- **Output**: `logs/hybrid_pipeline_bench/page_3_reuse_sr_timed_v2_20260122_235056`
- **Performance Summary**:
  - Step 2 (Homr SR) Time: **161s** (vs 167s with SR gen)
  - Impact: **-6s** (Negligible)
  - Conclusion: For small images, the overhead of Python startup and model loading dominates; SR generation itself is fast enough that caching yields little wall-clock benefit for single runs.

### Benchmark Result: `page_10.png` (Large Image: 9.72 MP)
- **Run ID**: `page_10_reuse_sr_timed_v1`
- **Output**: `logs/hybrid_pipeline_bench/page_10_reuse_sr_timed_v1_20260123_001424`
- **Performance Summary**:
  - Step 2 (Homr SR) Time: **113s** (vs 167s with SR gen)
  - Impact: **-54s** (~20% improvement in total pipeline time)
  - Conclusion: For standard/large scores, avoiding redundant SR generation saves significant time (~1 min per page).

### Outcome
- The value of SR caching is confirmed for full-page score processing.
- Results documented in `docs/performance_comparison.md`.