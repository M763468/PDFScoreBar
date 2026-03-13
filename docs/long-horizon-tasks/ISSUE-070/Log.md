# Execution Log

## 2026-03-06 Initial Setup
- Issue #70 (パフォーマンス低下の原因調査と対策) のためのタスクディレクトリ `ISSUE-070` を作成。
- `Prompt.md` に課題の背景と目的、スコープを定義。
- `Plan.md` に調査・対策のマイルストーン (M0 ~ M3) を定義。
- ブランチ `chore/performance-investigation` の作成とチェックアウトを確認。

## 2026-03-06 Milestone M0: Baseline Measurement
- [x] パフォーマンス測定用のスクリプト `monitor.sh` を作成。
- [x] `make test` (pytest) および `main.py --dry-run` の実行時間を計測。
- [x] ベースラインとして `Benchmarks.md` に記録 (19.22s / 3.05s)。

## 2026-03-06 Milestone M1: Profiling and Bottleneck Identification
- [x] 実際のデータを用いた推論を含むパイプラインの実行とプロファイリング。
    - [x] `sr_eval_gpu` コンテナ内での実行により完走に成功。
    - [x] Peak VRAM: 7.85 GB (8GBの96%) を記録。
    - [x] Latency: 1ページあたり約8分。
- [x] ボトルネック箇所の特定。
    - **VRAM**: 超解像 (Real-ESRGAN) および Hybrid Detection (Segnet/OMR-DLN) が VRAM をほぼ使い切っている。
    - **Latency**: サブプロセス生成と大規模モデルのロード、タイル処理が支配的。

## 2026-03-06 Milestone M2: 対策の実施と検証
- [x] 対策の実施。
    - [x] `src/common/preprocessing.py`: Real-ESRGAN のデフォルトタイルサイズを 512 から 400 に縮小（VRAM節約）。
    - [x] `src/pipeline/main.py`: `OMP_NUM_THREADS`, `MKL_NUM_THREADS` を 4 に制限。
- [x] 検証。
    - [x] Peak VRAM: 7.62 GB (M1から約235MB削減)。
    - [x] Latency: 7分53秒 (M1から約5秒改善)。
    - [x] 8GBの制限内での安定動作を確認。

## 2026-03-06 Milestone M3: Hardening
- [x] 最終的な `make test` の実行。
    - [x] 10 tests passed in 15.12s。
- [x] 調査結果のまとめ。
    - [x] VRAM消費の主因はReal-ESRGANのタイル処理とHybrid Detectionのモデル群。
    - [x] タイルサイズを400に下げることで、8GB VRAM環境下で余裕（約500MB）を持って動作することを確認。
    - [x] スレッド制限によりCPU競合を抑えつつ、Latencyへの悪影響がないことを確認。

## 完了
- Issue #70 の全マイルストーンを完了。
