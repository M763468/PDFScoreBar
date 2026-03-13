# docs/ ディレクトリ ドキュメント棚卸し (2026-03-14)

このドキュメントは、`docs/` 内の膨大な資料を「現行(Current)」「分析用(Analysis)」「レガシー(Legacy)」の3段階に分類し、どの資料を参照すべきかを整理したものです。

---

## 1. [Current] - 現行仕様・ガイドライン
現在の開発において遵守すべき最新のルール、仕様、または手順です。これらは「正解」として扱われます。

| ファイル / ディレクトリ | 概要 | 推奨アクション / 備考 |
| :--- | :--- | :--- |
| `README.md` (root) | プロジェクト全体のビジョンと構造。 | **必読。** 全体のエントリポイントです。 |
| `docs/README.md` | ドキュメント全体のインデックス。 | **必読。** このインベントリへの入り口です。 |
| `docs/MANIFEST.md` | 推奨モデル、データ、設定のレジストリ。 | **重要。** パスや資産の所在の「唯一の真実」です。 |
| `AGENTS.md` (root) | AIエージェント（Gemini/Codex）の憲法。 | **遵守。** エージェントの行動規範です。 |
| `docs/ENVIRONMENTS.md` | 実行環境（Docker, venv）の構築。 | **参照。** 環境構築・更新時に参照。 |
| `docs/GT_PREPARATION_POLICY.md` | 小節線GT作成ポリシー。 | **遵守。** ラベリング作業の基準です。 |
| `docs/BARLINE_MATCHER.md` | 小節線マッチングロジック詳細。 | **参照。** ロジック修正時のリファレンス。 |
| `docs/REGRESSION_TEST_WORKFLOW.md` | 検証ワークフロー（lint/test/smoke）。 | **遵守。** 変更適用前の必須手順です。 |
| `docs/PIPELINE_DATAFLOW.md` | 統合パイプラインのアーキテクチャ。 | **参照。** パイプライン構造の理解に。 |
| `docs/SCRIPT_MANAGEMENT.md` | スクリプト配置・運用ルール。 | **遵守。** 新規ツール追加時のルールです。 |
| `docs/ai-workflow/` | エージェント向け標準ワークフロー。 | **参照。** 各スキルの詳細。 |
| `docs/agent-skills/` | エージェントスキルの定義。 | **参照。** 各スキルの詳細。 |

---

## 2. [Analysis] - 分析結果・最新レポート
最近実施された実験の結果や、現在進行中の調査、設計検討資料、最新のロードマップです。

| ファイル / ディレクトリ | 概要 | 推奨アクション / 備考 |
| :--- | :--- | :--- |
| `docs/notes/ROADMAP_20260313.md` | 最新のロードマップ (2026-03-13)。 | **重要。** 今後の方向性を確認。 |
| `docs/ISSUE13_E2E_VERIFICATION_REPORT.md` | Issue #13 最終検証報告 (2026-03-13)。 | **参照。** パイプライン性能の最新エビデンス。 |
| `docs/notes/REFACTOR_PLAN_20260312.md` | 環境統合・Subprocess排除の計画。 | **参照。** 進行中のリファクタ設計。 |
| `docs/ISSUE44_ITER7_FINAL_REPORT.md` | CNNモデル救済 (Iter 7) の最終報告。 | **参照。** 現在の最高精度モデルの根拠。 |
| `docs/performance_comparison.md` | 各モデルの性能比較メトリクス。 | **参照。** モデル選定の判断材料。 |
| `docs/model_experiments/` | 各種モデル選定・調査の計画案。 | **参照。** モデル検討の背景。 |
| `docs/notes/technical_debt.md` | 認識されている技術的負債。 | **参照。** 優先すべき改善点の把握。 |

---

## 3. [Legacy] - 歴史的資料・過去の計画
完了したIssueの資料や、古い仕様、歴史的経緯を確認するためのアーカイブです。通常、これらに基づいて新規実装を行ってはいけません。

| ファイル / ディレクトリ | 概要 | 推奨アクション / 備考 |
| :--- | :--- | :--- |
| `docs/NEXT_SESSION_NOTES.md` | 以前のセッション引継ぎ資料。 | **参照不要。** 2026年1月で運用終了。 |
| `docs/future/roadmap.md` | 過去のロードマップ (2025-12)。 | **参照不要。** `ROADMAP_20260313.md` で上書き。 |
| `docs/DEVELOPMENT_LOG.md` | authoritative な歴史的事実の記録。 | **参照。** 過去の決定事項の「なぜ」を確認する際に。 |
| `docs/SESSION_LOG.md` | 短期的な作業メモのアーカイブ。 | **参照。** 過去のセッションの作業記録。 |
| `docs/FULL_PIPELINE_README.md` | 初期パイプライン (Phase 1) の説明。 | **レガシー。** 現在は `main.py` に統合。 |
| `docs/fp_reduction/` | 初期 FP 削減プロジェクトの記録。 | **歴史資料。** 現在の仕様の礎ですが、中身は古い。 |
| `docs/long-horizon-tasks/` | 完了済みの長期タスク履歴。 | **アーカイブ。** 各 Issue の過程記録。 |
| `docs/refactors/` | 完了済みのリファクタリング履歴。 | **アーカイブ。** 変更の意図の確認用。 |
| `docs/GOALS.md` | 初期のプロジェクト目標。 | **レガシー。** root README に最新版があります。 |
| `docs/CNN_RETRAINING_GUIDE.md` | 過去の学習手順書。 | **参照注意。** 最新の学習環境と差分がある可能性。 |
| `docs/best_configuration_summary.md` | 2026年1月時点の最適設定。 | **参照注意。** `MANIFEST.md` の方が新しい。 |
| `docs/ISSUE13_ACTION_PLAN.md` | Issue #13 実行計画（完了済み）。 | **アーカイブ。** |
| `docs/ISSUE44_*` (Iter 7以外) | Issue #44 の中間報告等。 | **アーカイブ。** |
| `docs/ISSUE46_*`, `ISSUE48_*`, `docs/ISSUE51_*` | 過去の個別バグ調査・分析。 | **アーカイブ。** |
