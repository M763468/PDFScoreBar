# Plan: PIPELINE-OPTIMIZE-60

## M0 Baseline & Research (Completed)
- [x] 現状の `toy_symphony` を使用した実行時間を計測し、ベースラインを記録。
- [x] `src/pipeline/main.py` および各ステップの入出力（I/O）を分析。

## M1 MMR Batching & In-process execution (Completed)
- [x] MMR（RapidOCR, ResNet18）のモデル永続化（キャッシュ）を実装。
- [x] `tools/add_measure_numbers.py` の処理をインプロセス化し、プロセス起動オーバーヘッドを解消。

## M2 Dataflow Optimization & Debug Control (Completed)
- [x] `src/pipeline/main.py` に `--debug` フラグを導入し、不要な中間ファイルの出力を抑制。
- [x] 各ステップ間での不要なディスクへの書き込みを削減。

## M3 Validation & Hardening (In-progress)
- [x] `toy_symphony` の出力結果（JSON）がベースラインと一致することを検証。
- [x] `smoke_test.yaml` での回帰テスト。
- [ ] 他のデータセット（追加調査と統合）での精度検証。

## M4 Detailed Profiling & Resource Analysis (New)
- [ ] 複数のデータセット（ページ数や複雑さが異なるもの）で各ステップ（PDF, Detection, MMR, Numbering）の所要時間を詳細に計測。
- [ ] PCの負荷（VRAM/CPU/Memory）を監視し、システムが重くなる原因を特定。
- [ ] 大量の標準出力を `artifacts/` にリダイレクトし、コンテキスト使用量を最適化。
- [ ] プロファイリング結果を `Benchmarks.md` に集約。
