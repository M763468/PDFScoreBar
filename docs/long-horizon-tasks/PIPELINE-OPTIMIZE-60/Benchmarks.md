# Benchmarks: PIPELINE-OPTIMIZE-60

## Test Case: Numbering-only (4 pages)
Input: Existing barlines and staff masks from `fix_verification_v8`.
Command: `python3 src/pipeline/main.py --config configs/baseline_numbering.yaml`

| Version | Duration (real) | Notes |
| :--- | :--- | :--- |
| Baseline (Issue #60 start) | ~1m 34s+ | Per-page subprocesses, redundant model loading. |
| **Optimized (Phase A/B/C In-process)** | **9.5s** | Models cached, No per-page overhead. |

## Test Case: Full Pipeline (eval2_e2e_subset.yaml - 3 pages)
Command: `python3 src/pipeline/main.py --config configs/evaluation2_e2e_subset.yaml` (SR=False)

| Step | Total Duration | Per Page | Notes |
| :--- | :--- | :--- | :--- |
| PDF to Images | ~3s | 1s | |
| **Detection (Homr)** | **3m 32s** | **70.7s** | **Major Bottleneck.** TrOmr inference on staves. |
| Hybrid Consensus | <1s | <0.1s | |
| Probe Scan | ~1s | 0.3s | |
| CNN Scoring | ~3s | 1s | |
| **Numbering (Phase A)** | **<1s** | **<0.1s** | **Optimized (In-process)** |
| **MMR Batch (Phase B)** | **~6s** | **2s** | **Optimized (Persistent models)** |
| **Final Numbering (Phase C)** | **~1s** | **0.3s** | **Optimized (In-process)** |

### Resource Analysis (RTX 4060 8GB)
- **VRAM Usage**: Peak **2.6 GB** (During Homr/TrOmr). 8GB context is safe.
- **GPU Utilization**: Peak **92%**. これが実験中にPCが重くなる主な原因（TrOmr推論時）。
- **I/O**: `--debug` オフ時は中間ファイルの書き出しが大幅に削減されていることを確認。

## Impact Summary
- **MMR Step**: ページごとのモデルロードを排除し、処理時間を大幅に短縮。
- **Numbering Step**: プロセス起動オーバーヘッドを排除し、ミリ秒単位まで高速化。
- **Bottleneck**: 現在のパイプラインの支配的なボトルネックは `Homr (TrOmr)` ステップであり、ここが全実行時間の 95% 以上を占めている。
