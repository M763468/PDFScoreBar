# Execution Log: PIPELINE-OPTIMIZE-60

## 2026-03-12 Task Initialization
- Issue #60 および #24 の内容を反映した `Prompt.md` と `Plan.md` を作成。
- `long-horizon-task` スキルの `run.sh` にパスの修正（../../../）を適用。

## 2026-03-12 Milestone M0 & M1: Optimization Implementation
- **MMR Batching & Persistence**:
    - `src/measure_numbering/mmr.py` をリファクタリングし、`MMRClassifier` と `MMROCREngine` の外部注入（永続化）をサポート。
    - `src/pipeline/numbering.py` の `run_mmr_batch` を更新し、永続化されたエンジンを受け取れるように変更。
    - `src/pipeline/main.py` に `_MMR_PERSISTENCE` グローバルキャッシュを導入。
- **In-Process Measure Numbering**:
    - `src/pipeline/main.py` で `MeasureNumberingPipeline` を直接（インプロセスで）呼び出すように変更。
    - これにより、ページごとの `tools/add_measure_numbers.py` プロセス起動オーバーヘッドを解消。
- **Dataflow Optimization & Debug Control**:
    - `src/pipeline/main.py` に `--debug` フラグを導入。
    - デバッグフラグがオフの場合、`barlines_corrected.json` や中間オーバレイ等の出力を抑制。
    - `score_to_dict` ヘルパーを `src/pipeline/io.py` に移動し、共通化。
- **Environment Fixes**:
    - コンテナ内の依存関係（`pymupdf`）の不足を解消。
    - `src/pipeline/python_env.py` および `src/pipeline/detection.py` の `PYTHONPATH` 解決を修正（`external/homr` を追加）。

## 2026-03-12 Milestone M2 & M3: Verification & Bug Fixes
- `baseline_numbering.yaml` (4ページ) を用いた計測:
    - 改善前: 1分以上（プロセス起動オーバーヘッドあり、かつハングの可能性）
    - 改善後: **約9.5秒** (モデルキャッシュ有効時)
- 精度検証:
    - 改修前後で `numbering_final.json` の内容が完全一致することを確認。
- 回帰テストとバグ修正:
    - `resolve_paths_from_detection` が `*_staff_mask.png` パターンを認識するように修正。
    - `MMRClassifier` の ResNet18 ロード時の警告と、オフライン環境でのハング（ダウンロード試行）を抑制。

## 2026-03-12 Milestone M4: Detailed Profiling & Resource Analysis
- `evaluation2_e2e_subset.yaml` (3ページ) での詳細プロファイリング。
- **PC負荷調査**:
    - GPU Utilization が TrOmr 推論中に **92%** に達することを確認。これがシステム遅延の主な要因。
    - VRAM 使用量は **2.6 GB** 程度であり、8GB 環境では余裕がある。
- プロファイリング結果を `Benchmarks.md` に集約。
