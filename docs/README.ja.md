# ドキュメントガイド

<!-- translation: {"original":"README.md","source":{"sha256":"7f66f6110df4c58e542d0c74a87dae0ae88b4588263af8f6759105f3aa1c2522"},"state":"reviewed"} -->

[English / 原文](README.md)（英語正本）

翻訳元: same PR / SHA-256 `7f66f6110df4c58e542d0c74a87dae0ae88b4588263af8f6759105f3aa1c2522`。状態: `reviewed`。原文との意味・制約・例外と日本語の可読性を確認済み。

知りたいことに答える文書から始めてください。開発リポジトリには過去の検証結果と検証ガイドが保持されていますが、それらの大半は最小配布物には含まれません。[ユーザーガイド](USER_GUIDE.ja.md)はサポート対象のインストールと操作の入口です。

| 知りたいこと | 最初に読む文書 |
| --- | --- |
| 実行に必要な最小サブセットは何か、抽出できる状態か | [最小 mainline サーフェス（英語）](MINIMAL_MAINLINE_SURFACE.md)とその[正確なファイル一覧](MINIMAL_MAINLINE_SURFACE.json) |
| 現在のパイプラインはどのように動作するか | [パイプラインアーキテクチャ（英語）](PIPELINE_ARCHITECTURE.md) / [日本語（reviewed）](PIPELINE_ARCHITECTURE.ja.md) |
| 検出／番号付けの厳密な実装契約はどこか | [実装リファレンス（英語）](PIPELINE_ARCHITECTURE_REFERENCE.md) / [日本語（reviewed）](PIPELINE_ARCHITECTURE_REFERENCE.ja.md) |
| 現在のリポジトリを実行するには | [環境ガイド（日本語）](ENVIRONMENTS.ja.md)、必要に応じて[手動補正ワークフロー（英語、未翻訳）](manual_correction_review_package.md) |
| 利用者の補正と GT／開発者向けツールはどう分離されているか | [利用者補正の境界（英語、未翻訳）](USER_CORRECTION_BOUNDARY.md) |
| エンジンの呼び出し元は何を送受信するか | [エンジンジョブ契約（英語）](ENGINE_JOB_CONTRACT.md) / [日本語（reviewed）](ENGINE_JOB_CONTRACT.ja.md) |
| このリポジトリを変更・検証するには | [ブランチ方針](BRANCH_POLICY.ja.md)、[検証方針](dev/VALIDATION_POLICY.ja.md)、[ローカル検証](dev/LOCAL_VALIDATION.ja.md) |
| 古いコードや検証結果が保持されている理由は | [リポジトリサーフェス台帳（英語、未翻訳）](REPOSITORY_SURFACE_INVENTORY.md)、[ドキュメント台帳（英語、未翻訳）](DOCUMENTATION_INVENTORY.md)、[履歴索引（英語、未翻訳）](HISTORY_INDEX.md) |

最小選択には説明文書と機械可読の一覧が一つずつあります。リポジトリとドキュメントの台帳は、より広範囲の過去の監査です。これらを実行時の第二のファイル一覧として使用してはいけません。`docs/**` の大半と `tests/**` の全体は develop 専用です。manifest はユーザーガイドと配布メタデータを明示的に選択しています。

## ドキュメントの言語

[カバレッジ台帳（英語、未翻訳）](DOCUMENTATION_INVENTORY.md#bilingual-coverage-and-translation-scope)には原文の言語、未作成の対訳、翻訳の優先順位が記録されています。翻訳を追加・更新するときは[言語・保守方針](DOCUMENTATION_LANGUAGE_POLICY.ja.md)に従ってください。完全な日本語版がないガイドは台帳で確認できます。日本語の UI 例があることは全文翻訳を意味しません。

## より具体的な契約

- [エンジンのライフサイクル](ENGINE_JOB_LIFECYCLE.ja.md)、[入力の安全性](ENGINE_INPUT_SAFETY.ja.md)、[テレメトリー](ENGINE_TELEMETRY.ja.md)は単一ジョブの契約を詳述します。[サービス準備ゲート](ENGINE_SERVICE_READINESS.ja.md)は、サポート対象の executor の振る舞いと互換性チェックを説明します。将来の worker 分離は別のものです。
- [最終出力](corrected_final_output.md)、[番号付けの幾何](NUMBERING_GEOMETRY_CONTRACT.md)、[GT 準備](GT_PREPARATION_POLICY.md)、[小節線マッチング](BARLINE_MATCHER.md)（いずれも英語、未翻訳）は、より限定された出力や検証の振る舞いを説明します。
- [モデル成果物契約](MODEL_ARTIFACT_CONTRACT.ja.md)は現在のモデル識別情報を定義し、[本番モデル成果物](MODEL_ARTIFACTS.ja.md)は公開とキャッシュのワークフローを扱います。[探索・比較用モデルの選択](dev/EXPERIMENT_MODEL_SELECTION.md)は、明示的な候補パス、固定比較、本番検証に関する日本語の開発者向けガイドです（#448 / PR #451）。
- [Makefile サーフェス](MAKEFILE_SURFACE.ja.md)、[回帰ワークフロー](REGRESSION_TEST_WORKFLOW.ja.md)、[スクリプト管理（英語、未翻訳）](SCRIPT_MANAGEMENT.md)はリポジトリ開発のガイドです。
- [将来のサービスアーキテクチャ（英語、未翻訳）](FUTURE_SERVICE_ARCHITECTURE.md)はロードマップであり、現在のランタイムの振る舞いではありません。[Two-HOMR マイルストーン（英語、未翻訳）](TWO_HOMR_MILESTONE.md)は固定された比較であり、現在の本番設定ではありません。

過去の調査には[履歴索引（英語、未翻訳）](HISTORY_INDEX.md)を使用し、該当する Issue または受け入れ済みの結果を探してください。現在の振る舞いはソース、テスト、使用中の設定、現在のアーキテクチャ文書で定義されます。振る舞いが変わった場合は該当する現在の契約を更新し、過去のメモを別の一般ガイドにコピーしないでください。
