# 回帰テストのワークフロー

<!-- translation: {"original":"REGRESSION_TEST_WORKFLOW.md","source":{"sha256":"cd75541373915df4b4777fde51cf5fc187e0e3121f6e30d4f45520d6bc763b58"},"state":"reviewed"} -->

[English / 原文](REGRESSION_TEST_WORKFLOW.md)（英語正本）

翻訳元: same PR / SHA-256 `cd75541373915df4b4777fde51cf5fc187e0e3121f6e30d4f45520d6bc763b58`。状態: `reviewed`。原文との意味・制約・例外と日本語の可読性を確認済み。

## 目的
- コミット前・PR前の検証を標準化し、挙動の回帰を一貫して検出する。
- 実データのsmokeとparityチェックをセッション間で再現可能に保つ。

## 前提条件
- `docs/ENVIRONMENTS.md` を読み、適切な環境でコマンドを実行する。
- パイプラインの実データチェックでは、`docs/ENVIRONMENTS.md` と `docs/dev/LOCAL_VALIDATION.md` に従ってイメージ、コンテナ、マウント、アセットを選択・確認する。

## コミット・PR前のチェック選択

[検証方針](dev/VALIDATION_POLICY.md) に従い、変更した挙動に応じたチェックを選択して状態を報告する。このワークフローは方針を補足するものであり、すべての変更にすべてのチェックを要求しない。特に文書のみの変更に対しては、formatter、単体テスト、GPU smoke、全評価を一律には要求しない。`make format` はファイルを変更するため、使用前にその影響を確認する。PR CIはローカルの最小要件とは別に独自のチェックを実行する場合がある。

## テストの配置方針
- `tests/` は現行コードパスの保守中の軽量テストを置く正規の場所である。
- 新しい決定的な単体・契約テストは `tests/` に置く。
- 環境依存の統合チェックや実データチェックは `tools/verification/` のような明示的な検証ツールに置き、環境要件を文書化する。
- `tests_legacy/` を再作成しない。Issue #380では、細い小節線の挙動に関する残りの有用なテストカバレッジを `tests/` に移行した後、この第二のテスト領域を廃止した。

## テストを追加するとき
- まず決定的な単体テスト（`tests/`）を優先する。
- 変更が実データ上の挙動に関わる場合、`tools/verification/` に再現可能なparityまたはsmokeコマンドを追加・更新する。
- PRコメントで軽量テスト結果（`tests/` 内の対象テスト）と、該当する場合の実データ検証結果の両方を報告する。
- 古いテストを維持できない場合、該当IssueまたはPRに処置を記録し、依然として有用なアサーションを保守中のテストまたは検証領域に残す。

## 実データsmoke（検出パス）

以下はIssue #23の過去の例であり、現行の必須smokeテストではない。再現を試みる前にコンテナ、設定、アセットを確認する。利用できない場合もある。現在必要なチェックには検証方針と環境ガイドを使う。

1. 統合パイプラインを実行する（`pdfscore_pipeline_gpu` 内）
```bash
docker exec pdfscore_pipeline_gpu bash -lc "cd /workspace && \
  /opt/venv_pipeline/bin/python -m src.pipeline.main \
  --config logs/issue23_smoke/config_issue23_smoke_images.yaml"
```
2. 出力の存在を確認する
- `logs/full_pipeline_runs/<run_id>/intermediate/probe_scan/*/pipeline2_no_peak_candidates.json`
- `logs/full_pipeline_runs/<run_id>/intermediate/probe_scan/*/pipeline2_no_peak_filtered_cnn.json`

## 実データparityチェック（srcとtools）

このIssue #34の過去の例は、Issue固有の入出力を使ってparityスクリプトを実行する。再現前にパスとコンテナを確認する。利用可能とは限らない。一般的な受入ゲートではない。

```bash
docker exec pdfscore_pipeline_gpu bash -lc "cd /workspace && \
  /opt/venv_pipeline/bin/python tools/verification/run_probe_detector_parity_check.py \
  --image /workspace/data/evaluation2/images/Va_Prokofiev_Symphony1/page_001.png \
  --staff-mask /workspace/logs/issue23_smoke/runs/hybrid_issue23_smoke_images_20260207/sr/batch/page_001/page_001_proxy_debug_3_staff.png \
  --existing-boxes /workspace/logs/issue23_smoke/runs/hybrid_issue23_smoke_images_20260207/hybrid_results/page_001_hybrid.json \
  --output /workspace/logs/issue34_smoke/issue34_parity_latest/parity_summary.json"
```

確認事項:
- `logs/issue34_smoke/issue34_parity_latest/parity_summary.json`
- 全ケースで `exact_match: true`

参考例（2026-02-08、`issue34_parity_latest`）:
- `baseline_staffmask_dense`: `src_count=7700`, `tools_count=7700`
- `rescue_off_custom_width`: `src_count=2227`, `tools_count=2227`
- `row_stats_mode`: `src_count=440`, `tools_count=440`

## ログの規則
- Issue単位の作業では、新しい検証出力を `logs/issue<N>/<category-or-purpose>/<run-or-artifact>/` に保存する。それ以外は `logs/README.md` に従う。
- 上記の `logs/issue23_smoke` と `logs/issue34_smoke` は過去のパスであり、新たに `logs/issue<N>_smoke` のような別のルートを作成しない。
- 一つのIssueのログを複数のトップレベルの場所に分散させない。
- 実行場所が変わった場合、そのログフォルダーに正規パスを記載した短い `README.md` を追加する。

## 報告テンプレート（PRコメント）
- 検証したコミットまたは特定された差分
- 使用した環境（コンテナ・venv）
- 実行したコマンド
- 結果の要約（成功・失敗・実行できず・未実行）
- 実データparityの結果（該当する場合、`exact_match` と件数）
- ログの場所
