# ドキュメントガイド

<!-- translation: {"original":"README.md","source":{"sha256":"f85f1c31bc3224ee427d78f2f48c100842267dbdf69d297389215db96f7fc1c4"},"state":"reviewed"} -->

[English / 原文](README.md)（英語正本）

翻訳元: same PR / SHA-256 `f85f1c31bc3224ee427d78f2f48c100842267dbdf69d297389215db96f7fc1c4`。状態: `reviewed`。原文との意味・制約・例外と日本語の可読性を確認済み。

知りたいことに答える文書から始めてください。開発リポジトリには過去の検証結果と検証ガイドが保持されていますが、それらの大半は最小配布物には含まれません。[ユーザーガイド](USER_GUIDE.ja.md)はサポート対象のインストールと操作の入口です。

| 知りたいこと | 最初に読む文書 |
| --- | --- |
| 実行に必要な最小サブセットは何か、抽出できる状態か | [最小配布面](MINIMAL_MAINLINE_SURFACE.ja.md)とその[正確なファイル一覧](MINIMAL_MAINLINE_SURFACE.json) |
| 現在のパイプラインはどのように動作するか | [パイプラインアーキテクチャ（英語）](architecture/PIPELINE_ARCHITECTURE.md) / [日本語（reviewed）](architecture/PIPELINE_ARCHITECTURE.ja.md) |
| 検出／番号付けの厳密な実装契約はどこか | [実装リファレンス（英語）](architecture/PIPELINE_ARCHITECTURE_REFERENCE.md) / [日本語（reviewed）](architecture/PIPELINE_ARCHITECTURE_REFERENCE.ja.md) |
| 現在のリポジトリを実行するには | [環境ガイド（日本語）](dev/ENVIRONMENTS.ja.md)、必要に応じて[手動補正ワークフロー](dev/manual_correction_review_package.ja.md) |
| 利用者の補正と GT／開発者向けツールはどう分離されているか | [利用者補正の境界](contracts/USER_CORRECTION_BOUNDARY.ja.md) |
| エンジンの呼び出し元は何を送受信するか | [エンジンジョブ契約（英語）](contracts/ENGINE_JOB_CONTRACT.md) / [日本語（reviewed）](contracts/ENGINE_JOB_CONTRACT.ja.md) |
| このリポジトリを変更・検証するには | [ブランチ方針](dev/BRANCH_POLICY.ja.md)、[検証方針](dev/VALIDATION_POLICY.ja.md)、[ローカル検証](dev/LOCAL_VALIDATION.ja.md)、[設定と実行入口](dev/CONFIGURATION_REFERENCE.ja.md) |
| 古いコードや検証結果が保持されている理由は | [リポジトリサーフェス台帳（英語、未翻訳）](REPOSITORY_SURFACE_INVENTORY.md)、[ドキュメント台帳](DOCUMENTATION_INVENTORY.ja.md)、[履歴索引](HISTORY_INDEX.ja.md) |

最小選択には説明文書と機械可読の一覧が一つずつあります。リポジトリとドキュメントの台帳は、より広範囲の過去の監査です。これらを実行時の第二のファイル一覧として使用してはいけません。`docs/**` の大半と `tests/**` の全体は develop 専用です。manifest はユーザーガイドと配布メタデータを明示的に選択しています。

## ディレクトリ構成

| 場所 | 内容 |
| --- | --- |
| `docs/` 直下 | このガイド、ユーザーガイド、最小配布の契約、台帳、言語方針、履歴索引 |
| [`architecture/`](architecture/) | 現在のパイプラインのアーキテクチャと実装リファレンス、明示的に将来のものとしたサービスアーキテクチャ |
| [`contracts/`](contracts/) | 現在のエンジンジョブ、モデル成果物、出力、番号付け、楽章、補正の境界、matcher の契約 |
| [`dev/`](dev/) | ブランチ、環境、検証、設定、Makefile、スクリプト、モデル公開の手順 |
| [`history/`](history/)、[`refactors/`](refactors/)、[`releases/`](releases/)、[`performance/`](performance/) | 凍結された Issue の記録、マイルストーンの台帳、リファクタリング・リリースの証拠、性能の結果 |
| [`ai-workflow/`](ai-workflow/)、[`agent-skills/`](agent-skills/)、[`archive/`](archive/) | 任意のエージェント作業ガイド、Skill の評価、アーカイブした案内 |
| [`licensing/`](licensing/) | 第三者ライセンス監査（#504）と、オーナー決定待ちのリポジトリライセンス選択肢（#505）。日本語が原文 |

言語の対応訳は原文の隣にあります。#492 ではこれらのファイルを直下から移動しました。古い Issue や PR のリンクを解決するには、その[旧パスと新パスの対応表](DOCUMENTATION_INVENTORY.ja.md#directory-layout-and-492-reorganization)を使ってください。

## ドキュメントの言語

[カバレッジ台帳](DOCUMENTATION_INVENTORY.ja.md#bilingual-coverage-and-translation-scope)には原文の言語、未作成の対訳、翻訳の優先順位が記録されています。翻訳を追加・更新するときは[言語・保守方針](DOCUMENTATION_LANGUAGE_POLICY.ja.md)に従ってください。完全な日本語版がないガイドは台帳で確認できます。日本語の UI 例があることは全文翻訳を意味しません。

## より具体的な契約

- [エンジンのライフサイクル](contracts/ENGINE_JOB_LIFECYCLE.ja.md)、[入力の安全性](contracts/ENGINE_INPUT_SAFETY.ja.md)、[テレメトリー](contracts/ENGINE_TELEMETRY.ja.md)は単一ジョブの契約を詳述します。[サービス準備ゲート](contracts/ENGINE_SERVICE_READINESS.ja.md)は、サポート対象の executor の振る舞いと互換性チェックを説明します。将来の worker 分離は別のものです。
- [最終出力](contracts/corrected_final_output.ja.md)、[番号付けの幾何](contracts/NUMBERING_GEOMETRY_CONTRACT.ja.md)、[楽章境界](contracts/MOVEMENT_BOUNDARY_CONTRACT.ja.md)、[GT 準備](dev/GT_PREPARATION_POLICY.ja.md)、[小節線マッチング](contracts/BARLINE_MATCHER.ja.md)は、より限定された出力や検証の振る舞いを説明します。
- [モデル成果物契約](contracts/MODEL_ARTIFACT_CONTRACT.ja.md)は現在のモデル識別情報を定義し、[本番モデル成果物](dev/MODEL_ARTIFACTS.ja.md)は公開とキャッシュのワークフローを扱います。[探索・比較用モデルの選択](dev/EXPERIMENT_MODEL_SELECTION.md)（日本語正本、[English](dev/EXPERIMENT_MODEL_SELECTION.en.md)）は、明示的な候補パス、固定比較、本番検証に関する開発者向けガイドです。
- [Makefile サーフェス](dev/MAKEFILE_SURFACE.ja.md)、[回帰ワークフロー](dev/REGRESSION_TEST_WORKFLOW.ja.md)、[スクリプト管理](dev/SCRIPT_MANAGEMENT.md)（日本語正本、[English](dev/SCRIPT_MANAGEMENT.en.md)）はリポジトリ開発のガイドです。
- [将来のサービスアーキテクチャ（英語、未翻訳）](architecture/FUTURE_SERVICE_ARCHITECTURE.md)はロードマップであり、現在のランタイムの振る舞いではありません。[Two-HOMR マイルストーン（英語、未翻訳）](history/TWO_HOMR_MILESTONE.md)は固定された比較であり、現在の本番設定ではありません。

過去の調査には[履歴索引](HISTORY_INDEX.ja.md)を使用し、該当する Issue または受け入れ済みの結果を探してください。現在の振る舞いはソース、テスト、使用中の設定、現在のアーキテクチャ文書で定義されます。振る舞いが変わった場合は該当する現在の契約を更新し、過去のメモを別の一般ガイドにコピーしないでください。
