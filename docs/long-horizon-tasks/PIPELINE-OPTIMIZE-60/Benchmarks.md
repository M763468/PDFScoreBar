# Benchmarks: PIPELINE-OPTIMIZE-60

## Test Case: Numbering-only (4 pages)
Input: Existing barlines and staff masks from `fix_verification_v8`.
Command: `python3 src/pipeline/main.py --config configs/baseline_numbering.yaml`

| Version | Duration (real) | Notes |
| :--- | :--- | :--- |
| Baseline (Issue #60 start) | ~1m 34s+ | Per-page subprocesses, redundant model loading. |
| **Optimized (Phase A/B/C In-process)** | **9.5s** | Models cached, No per-page overhead. |

## Test Case: Full Pipeline (smoke_test.yaml)
| Version | Duration (real) | Notes |
| :--- | :--- | :--- |
| Pre-optimization | ~5m 30s | (Est. based on previous sessions) |
| **Post-optimization** | **5m 30s** | Detection/Homr are still the primary bottlenecks, but MMR is now robust and persistent. |

## Impact
- **MMR Step (Batching)**: ページごとの RapidOCR/ResNet 起動を排除し、複数ページ処理時のスループットを大幅に改善。
- **Dataflow**: 不要な中間 JSON ファイルのディスク出力を抑制（通常実行時）。
- **Maintenance**: `MeasureNumberingPipeline` のインプロセス化により、ログの可読性が向上。
