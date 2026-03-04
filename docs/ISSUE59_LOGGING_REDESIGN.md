# Issue #59: パイプライン全体のログ出力・監視性の再設計

## Goal
パイプライン（`main.py`）実行時のログ出力を整理・再設計し、監視性とデバッグのしやすさを向上させる。
- ログレベルとフォーマットの統一
- 進捗状況の可視化 (`tqdm` の導入)

## 方針と対応内容 (Plan & Implementation)

1. **進捗の可視化 (`tqdm` の導入):**
   - パイプラインのルートである `src/pipeline/main.py` にて、ページごとの処理ループを `tqdm` でラップし、全体の進捗が把握できるようにする。
   - 各サブステップ（`src/pipeline/detection.py` の Hybrid Consensus 生成、`src/pipeline/probe_scan.py`, `src/pipeline/cnn_scoring.py`）のループ処理にも `tqdm` を導入し、時間のかかる処理の進行状況を明確にする。

2. **`print()` から `logging` への移行:**
   - パイプライン関連ファイルやツールスクリプト（`tools/add_measure_numbers.py`, `tools/generate_numbering_overrides.py`）において、既存の `print()` 出力を `logger.info()`, `logger.debug()`, `logger.error()` などの適切なログレベルに置き換える。
   - ログ出力フォーマットを `%(asctime)s [%(levelname)s] %(name)s: %(message)s` に統一するための `logging.basicConfig` を各スクリプトのメインエントリポイントで設定する。

## 進捗 (Progress)
- [x] ブランチ `feat/pipeline-logging-redesign` を `feature/batch_orchestrator` から作成
- [x] 各処理ループへの `tqdm` の導入
- [x] `print` 文の `logger` への置き換えおよび `logging.basicConfig` の設定
- [x] 動作確認（テストおよびSmoke Testによる検証）
