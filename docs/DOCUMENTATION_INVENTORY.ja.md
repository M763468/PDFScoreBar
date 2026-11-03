# 永続的なドキュメントの台帳

<!-- translation: {"original":"DOCUMENTATION_INVENTORY.md","source":{"sha256":"9cae8478d8d104853ddcf663f2dff24a5e87a134a2daf6be7d265f4ce0579cd2"},"state":"reviewed"} -->

[English / 原文](DOCUMENTATION_INVENTORY.md)（英語正本）

翻訳元: same PR / SHA-256 `9cae8478d8d104853ddcf663f2dff24a5e87a134a2daf6be7d265f4ce0579cd2`。状態: `reviewed`。原文との意味・制約・例外と日本語の可読性を確認済み。

Issue #280 は、受け入れ済みの #274 時点の本番状態に照らして、リポジトリのドキュメント監査を確立しました。このファイルは、ドキュメントの経緯と保守のルールを記録します。最小ランタイム選定の入口ではありません。その問いには `MINIMAL_MAINLINE_SURFACE.md`（[日本語](MINIMAL_MAINLINE_SURFACE.ja.md)）を使ってください。

## 分類のルール

- **canonical/current:** リポジトリを今どのように使うべきかを説明することを意図した文書。
- **current/reference:** より狭い領域の中では今も正確だが、全体のアーキテクチャの正本ではない文書。
- **future/roadmap:** 意図している永続的なアーキテクチャや責務の境界で、現在のランタイムの正本ではないことが明示されている文書。
- **historical:** 過去の Issue・実験から得た有用な証拠や根拠。それ自体で完結した Issue/PR/commit/source/test/ツールの記録からは回復できない、永続的な価値を加えている間だけ保持する。
- **retire:** 現在のガイダンスと重複または矛盾する、完了したタスク管理の状態が主な内容である、あるいは固有の永続的な内容がすでに別の場所へ移された文書。古い本文は Git 履歴に残る。
- **separate cleanup:** このドキュメント監査ではなく、既存の別トラックに属する実装・config の整理。

## 台帳

| 文書・領域 | 役割 | 分類 | 現在の扱い |
| --- | --- | --- | --- |
| `README.md` | リポジトリの入口 | current | 正規のアーキテクチャと永続的な文書を案内する |
| `AGENTS.md` | リポジトリのエージェント向け規約 | current | 保持 |
| `docs/README.md` | ドキュメントの索引 | canonical/current | 現行と履歴の案内を正確に保つ |
| `docs/REPOSITORY_SURFACE_INVENTORY.md` | #230 の開発リポジトリ監査であり #100 への入力 | historical/reference | 経緯のために保持する。古い現在形のパス表記は現在の抽出対象を定めない |
| `docs/MINIMAL_MAINLINE_SURFACE.md` / `.json` | Issue #100 の最小実行選定と、機械可読なずれの定義 | 抽出については canonical/current | 配布するランタイムのサブセットについての唯一の説明と正確なファイル一覧として使う。候補ごとの #409 の受入証拠は `docs/releases/issue409/ACCEPTANCE_HISTORY.md` に移した（#484） |
| `docs/HISTORY_INDEX.md` | 過去の経緯の案内 | current/reference | 重複させずに、Issue/PR/commit と保持している契約を指す |
| `docs/PIPELINE_ARCHITECTURE.md` / `.ja.md` | 読者向けの現在の本番アーキテクチャ | canonical/current（英語正本）、日本語は reviewed | パイプラインの構成要素、データフロー、実行順序、モジュールの責務。厳密な契約はリファレンスへ移した |
| `docs/PIPELINE_ARCHITECTURE_REFERENCE.md` / `.ja.md` | 本番実装のリファレンス | current/reference（英語正本）、日本語は reviewed | 検出器・番号付けの詳細な契約と、過去の互換性の根拠。アーキテクチャの概要から読む |
| `docs/FUTURE_SERVICE_ARCHITECTURE.md` | 将来のエンジン・サービスの責務境界 | future/roadmap | 現在のランタイムとは明示的に分けて保つ。長期的なエンジン・呼び出し元・補正・サービス境界の意図が大きく変わったときに更新する |
| `docs/ENGINE_JOB_CONTRACT.md` / `.ja.md` | バージョン付きの単一ジョブのエンジン呼び出し契約 | current/reference（英語正本）、日本語は reviewed | 規範となる v1 のシリアライズ境界と、互換性・補正の意味論。`PipelineJobExecutor` は参照アダプタであり、v1 の `CorrectionSet` の直接実行はそのアダプタの対象外のまま |
| `docs/ENGINE_JOB_LIFECYCLE.md` / `.ja.md` | #337 の単一ジョブのライフサイクル契約 | current/reference（英語正本）、日本語は reviewed | v1 のライフサイクル要件と再利用可能な制御ヘルパー。#337 の監査は履歴であり、キャンセルや期限の統合は未完了のまま |
| `docs/ENGINE_INPUT_SAFETY.md` / `.ja.md` | #338 の信頼できない PDF に対する安全性の契約 | current/reference（英語正本）、日本語は reviewed | 実装済みの上限付き preflight と安全なエラー。厳格なクォータ、プロセスツリー、ネットワーク隔離は将来の worker の要件のまま |
| `docs/ENGINE_TELEMETRY.md` / `.ja.md` | #339 の構造化された進捗・リソースのテレメトリー契約 | current/reference（英語正本）、日本語は reviewed | v1 のステージ・状態の語彙を保ったまま、追加的な経過時間・詳細のフィールド、ページの進捗、簡潔な要約、オプトインのプロセス・GPU のサンプリングを定める |
| `docs/ENGINE_SERVICE_READINESS.md` / `.ja.md` | #340 の参照 executor と互換性ゲート | current/reference（英語正本）、日本語は reviewed | サポート対象の succeeded/failed の公開境界。v1 の補正の直接実行、ライフサイクルの制御、公開サービスの隔離は現在のサポートの対象外のまま |
| `docs/history/TWO_HOMR_MILESTONE.md` | 受け入れ済みの #274 のアーキテクチャ・精度・性能の比較 | frozen milestone | #274 / PR #279 の再現記録として保持する。後の本番の変更に合わせて黙って書き換えない |
| `docs/ENVIRONMENTS.md` | 実行・ランタイムのガイダンス | current/reference | 保持 |
| `docs/BRANCH_POLICY.md` | ブランチ方針 | current/reference | 保持 |
| `docs/dev/VALIDATION_POLICY.md` | 検証方針 | current/reference | 保持 |
| `docs/REGRESSION_TEST_WORKFLOW.md` | 回帰ワークフロー | current/reference | 保持 |
| `docs/GT_PREPARATION_POLICY.md` | GT の方針 | current/reference | 保持 |
| `docs/BARLINE_MATCHER.md` | マッチング・評価のルール | current/reference | 保持 |
| `docs/SCRIPT_MANAGEMENT.md` | スクリプトの配置・ライフサイクルの方針 | current/reference | 簡潔に保つ。過去の移動・削除の記録は #45 / PR #184 に属する |
| `docs/manual_correction_review_package.md` | 内部のレビュー引き継ぎ | current/reference | 保持 |
| `docs/corrected_final_output.md` | 補正済み出力のワークフロー | scoped/reference | 保持する。出力のワークフローを変更するときはソースと照合する |
| `docs/ai-workflow/GRAPHIFY.md` | Graphify の運用 | current/reference | 保持 |
| `.agents/skills/graphify/**` | エージェントの Graphify スキル | current/reference | 保持 |
| `graphify-out/**` の永続的なセット | 生成されたナビゲーション用のグラフ・wiki・レポート・manifest | 来歴が新しいときだけ current | アーキテクチャの安定した変更の後に更新する |
| `docs/PIPELINE_DATAFLOW.md`、`docs/FULL_PIPELINE_README.md`、`docs/best_configuration_summary.md` | 古くなった現行ガイドの説明 | retired | 以前の整理で削除した。Git 履歴から回復する |
| `docs/CNN_RETRAINING_GUIDE.md` | #44 時点の FP 能動学習・ResNet18 の計画 | retired | 過去の要点は #44 へ移した。現在の検証済み CNN は #296 / PR #310 と source/config/tests |
| `docs/performance_comparison.md` | 日付付きの Phase 1–6 の性能の記述 | retired | ベンチマークの記録は #78 に要約した。その後の性能の経緯は #281–#294 にある |
| `docs/history/DEVELOPMENT_LOG.md` | プロジェクト発足時・Issue 運用前の履歴 | historical/reference | 短い旧マイルストーンの記録に圧縮した。古い実行日誌の正確な内容は Git 履歴にだけある |
| `docs/DEVLOG_CNN_TRAINING.md` | CNN 開発の日誌 | retired | 初期の実験の永続的な記録は Issue #44 へ移した。現在の検証済み CNN は #296 / PR #310 と source/config/tests |
| `docs/history/DEVLOG_MEASURE_NUMBERING.md` | 初期の番号付け・MMR の開発の経緯 | historical/reference | 短い旧マイルストーンの記録に圧縮した。現在の範囲限定の MMR の分析は `docs/refactors/issue94/MMR_CURRENT_STATE.md` と Issue #94 |
| `docs/` 直下の `ISSUE*.md` | Issue の調査・再現の記録 | historical | 固有の永続的な証拠か、有効な再現の契約が残っている間だけ保持する。そうでなければ要約して retire する |
| `docs/refactors/issue*/**` | 範囲限定の設計・経緯 | historical/scoped | 個別に監査する。現在の範囲限定の契約は保持し、一時的な引き継ぎ・タスク管理の束は要約した後に retire する |
| `docs/long-horizon-tasks/**` | 完了した Prompt/Plan/Log/Benchmarks のタスクの束 | retired | #25/#60/#70 の重要な結果はそれぞれの Issue のスレッドへ移した。有効に見えるタスク管理のコピーは削除した |
| `docs/notes/**`、`docs/future/**` | メモ・計画 | historical/planning | 置き換えられ、判断が他の場所から回復できるようになったら retire する |
| `docs/GOALS.md` | #446 以前のプロジェクトの目標と「現在の」方針 | retired | owner が #446 で、現在のプロジェクトの方針を示していないと判断した。翻訳せずに #488 で削除した。Git 履歴から回復する |
| `docs/model_experiments/*.md` | 古いモデルの調査・将来の計画 | 置き換えられたら retired | 有効に見える計画の文章は現在のモデルのロードマップではない。受け入れ済みの実験の証拠は別の場所に残る |
| `docs/model_experiments/*.pdf` | 実験前の文献・データセット・モデルの調査 | retired | #308 での内容レベルの監査で、プロジェクト固有の運用・再現の契約は見つからなかった。プロジェクト固有の実験の証拠は `experiments/models/` に残り、古い調査の文章そのものは Git 履歴に残る |
| `docs/fp_reduction/**` | 重複した 2025年12月の FP 削減の記述 | retired | 再利用できる安全上のガイダンスを `docs/ai-workflow/LESSONS.md` に移した後に削除した。ツールは `experiments/fp_reduction/` に残る |
| `configs/dense_full_pipeline.yaml` | 正規の dense の本番 config | 文章ではなく現在のランタイム入力 | 現在選ばれているモデル・閾値・ランタイムの値の正本 |
| `configs/detector_profiles/stage_e_verified_homr.json` | 固定した HOMR プロファイルの来歴 | 正規の機械可読なリファレンス | 保持 |

<a id="bilingual-coverage-and-translation-scope"></a>

## 日英の対訳範囲と翻訳の対象

この台帳は、文書の意図と観測した言語を分類するものです。すべての記述が現在の source/tests と一致することを**保証するものではありません**。翻訳の配置、翻訳元のリビジョン、レビュー、ずれの扱いについては、[言語方針](DOCUMENTATION_LANGUAGE_POLICY.ja.md)（[English](DOCUMENTATION_LANGUAGE_POLICY.md)）を使ってください。これは既存の監査を拡張するもので、その経緯を置き換えたり、競合するランタイム・配布の manifest を作ったりするものではありません。

言語のラベルは説明の文章の言語を表します。**EN** = 英語、**JA** = 日本語、**mixed** = 両方の言語でまとまった文章があるもの。コード、識別子、日本語の UI の例、翻訳された状態ラベルだけでは、完全な対訳とはみなしません。
#452 の最初の監査の時点では、下の表のどの文書にも、別ファイルのレビュー済みの完全な対訳はありませんでした。これは過去の監査結果であり、現在の対訳状況ではありません。
現在の対訳の状態は、下の各行に記録しています。**JA needed** と **EN needed** は未翻訳を意味します。**split/review** は、mixed の原文をまず全体としてレビューする必要があることを意味します。draft の対訳は、reviewed や技術的に同期済みとは認定されません。

優先度は読む順序の依存関係を表すもので、すべての行を1つの PR で終える必要があるという意味ではありません。
**P1** = 入口と、中核のアーキテクチャ・エンジン・モデル・運用・検証。
**P2** = 補助的な契約と、開発者・エージェント向けのガイダンス。
**P3** = 将来の方針や任意のリファレンスで、必要になったときに翻訳する。
`current/reference` は意図している範囲を表し、技術的な現行性は翻訳時に確認します。履歴と範囲限定の記録は、下の除外事項に従います。

表のラベル（役割・言語・対訳の扱い・優先度）は、上で定義した記号として原文のまま記載します。

| 文書 | 意図した役割・権威 | 言語 | 対訳の扱い | 優先度 |
| --- | --- | --- | --- | --- |
| [../README.md](../README.md) | canonical/current | EN | [JA reviewed](../README.ja.md) | P1 |
| [../AGENTS.md](../AGENTS.md) | canonical/current; agent instructions | EN | not required (agent-only) | N/A |
| [README.md](README.md) | canonical/current | EN | [JA reviewed](README.ja.md) | P1 |
| [DOCUMENTATION_INVENTORY.md](DOCUMENTATION_INVENTORY.md) | canonical/current | EN | [JA reviewed](DOCUMENTATION_INVENTORY.ja.md); #488 | P1 |
| [DOCUMENTATION_LANGUAGE_POLICY.md](DOCUMENTATION_LANGUAGE_POLICY.md) | current/reference; translation and documentation maintenance rules | EN | [JA reviewed](DOCUMENTATION_LANGUAGE_POLICY.ja.md); #489 | P1 |
| [PIPELINE_ARCHITECTURE.md](PIPELINE_ARCHITECTURE.md) | canonical/current overview | EN | [JA full reviewed](PIPELINE_ARCHITECTURE.ja.md); #456 review completed | P1 |
| [PIPELINE_ARCHITECTURE_REFERENCE.md](PIPELINE_ARCHITECTURE_REFERENCE.md) | current implementation-level reference | EN | [JA full reviewed](PIPELINE_ARCHITECTURE_REFERENCE.ja.md); #456 review completed | P1 |
| [ENGINE_JOB_CONTRACT.md](ENGINE_JOB_CONTRACT.md) | current/reference | EN / [JA](ENGINE_JOB_CONTRACT.ja.md) | reviewed; #463 implementation/meaning review | P1 |
| [ENGINE_JOB_LIFECYCLE.md](ENGINE_JOB_LIFECYCLE.md) | current/reference | EN / [JA](ENGINE_JOB_LIFECYCLE.ja.md) | reviewed; #463 implementation/meaning review | P1 |
| [ENGINE_INPUT_SAFETY.md](ENGINE_INPUT_SAFETY.md) | current/reference | EN / [JA](ENGINE_INPUT_SAFETY.ja.md) | reviewed; #463 implementation/meaning review | P1 |
| [ENGINE_TELEMETRY.md](ENGINE_TELEMETRY.md) | current/reference | EN / [JA](ENGINE_TELEMETRY.ja.md) | reviewed; #463 implementation/meaning review | P1 |
| [ENGINE_SERVICE_READINESS.md](ENGINE_SERVICE_READINESS.md) | current/reference | EN / [JA](ENGINE_SERVICE_READINESS.ja.md) | reviewed; #463 implementation/meaning review | P1 |
| [MODEL_ARTIFACT_CONTRACT.md](MODEL_ARTIFACT_CONTRACT.md) | current/reference | EN / [JA](MODEL_ARTIFACT_CONTRACT.ja.md) | reviewed | P1 |
| [MODEL_ARTIFACTS.md](MODEL_ARTIFACTS.md) | current/reference | EN / [JA](MODEL_ARTIFACTS.ja.md) | reviewed | P1 |
| [ENVIRONMENTS.md](ENVIRONMENTS.md) | current/reference | EN / [JA](ENVIRONMENTS.ja.md) | reviewed; #465 translation and meaning review | P1 |
| [USER_GUIDE.md](USER_GUIDE.md) | current/reference | EN | [JA reviewed](USER_GUIDE.ja.md) | P1 |
| [manual_correction_review_package.md](manual_correction_review_package.md) | current/reference | EN | [JA reviewed](manual_correction_review_package.ja.md) | P1 |
| [BRANCH_POLICY.md](BRANCH_POLICY.md) | current/reference | EN / [JA](BRANCH_POLICY.ja.md) | reviewed; #465 translation and meaning review | P1 |
| [dev/VALIDATION_POLICY.md](dev/VALIDATION_POLICY.md) | current/reference | EN / [JA](dev/VALIDATION_POLICY.ja.md) | reviewed; #465 translation and meaning review | P1 |
| [dev/LOCAL_VALIDATION.md](dev/LOCAL_VALIDATION.md) | current/reference | EN / [JA](dev/LOCAL_VALIDATION.ja.md) | reviewed; #465 translation and meaning review | P1 |
| [USER_CORRECTION_BOUNDARY.md](USER_CORRECTION_BOUNDARY.md) | current/reference | EN | [JA reviewed](USER_CORRECTION_BOUNDARY.ja.md) | P2 |
| [corrected_final_output.md](corrected_final_output.md) | current/reference | EN | [JA reviewed](corrected_final_output.ja.md) | P2 |
| [MOVEMENT_BOUNDARY_CONTRACT.md](MOVEMENT_BOUNDARY_CONTRACT.md) | current/reference | EN | [JA reviewed](MOVEMENT_BOUNDARY_CONTRACT.ja.md); #477 currency review | P2 |
| [NUMBERING_GEOMETRY_CONTRACT.md](NUMBERING_GEOMETRY_CONTRACT.md) | current/reference | EN | [JA reviewed](NUMBERING_GEOMETRY_CONTRACT.ja.md); #477 currency review | P2 |
| [GT_PREPARATION_POLICY.md](GT_PREPARATION_POLICY.md) | current/reference | EN | [JA reviewed](GT_PREPARATION_POLICY.ja.md); #475 currency review | P2 |
| [BARLINE_MATCHER.md](BARLINE_MATCHER.md) | current/reference | EN | [JA reviewed](BARLINE_MATCHER.ja.md); #475 currency review | P2 |
| [MAKEFILE_SURFACE.md](MAKEFILE_SURFACE.md) | current/reference | EN / [JA](MAKEFILE_SURFACE.ja.md) | reviewed; #465 translation and meaning review | P2 |
| [REGRESSION_TEST_WORKFLOW.md](REGRESSION_TEST_WORKFLOW.md) | current/reference | EN / [JA](REGRESSION_TEST_WORKFLOW.ja.md) | reviewed; #465 translation and meaning review | P2 |
| [dev/MMR_RAPIDOCR_PROVIDER.md](dev/MMR_RAPIDOCR_PROVIDER.md) | current/reference | EN | [JA reviewed](dev/MMR_RAPIDOCR_PROVIDER.ja.md); #477 currency review | P2 |
| [dev/REVIEW_ACCEPTANCE.md](dev/REVIEW_ACCEPTANCE.md) | current/reference | EN | [JA reviewed](dev/REVIEW_ACCEPTANCE.ja.md); #480 currency review | P2 |
| [dev/PR_SLICE_VALIDATION.md](dev/PR_SLICE_VALIDATION.md) | current/reference | EN | [JA reviewed](dev/PR_SLICE_VALIDATION.ja.md); #480 currency review | P2 |
| [dev/codex_local_automation.md](dev/codex_local_automation.md) | current/reference | EN | [JA reviewed](dev/codex_local_automation.ja.md); #480 currency review | P2 |
| [dev/local_worktree_data.md](dev/local_worktree_data.md) | current/reference | EN | [JA reviewed](dev/local_worktree_data.ja.md); #480 currency review | P2 |
| [agent-skills/EVAL.md](agent-skills/EVAL.md) | current/reference | EN | [JA reviewed](agent-skills/EVAL.ja.md); #482 | P2 |
| [dev/CONFIGURATION_REFERENCE.md](dev/CONFIGURATION_REFERENCE.md) | current/reference; canonical config keys and values guarded in PR CI by `tests/test_configuration_reference.py` | EN | [JA reviewed](dev/CONFIGURATION_REFERENCE.ja.md); #486 | P2 |
| [dev/EXPERIMENT_MODEL_SELECTION.md](dev/EXPERIMENT_MODEL_SELECTION.md) | current/reference | JA | [EN reviewed](dev/EXPERIMENT_MODEL_SELECTION.en.md); #475 | P1 |
| [SCRIPT_MANAGEMENT.md](SCRIPT_MANAGEMENT.md) | current/reference | JA (designated original, #480) | [EN reviewed](SCRIPT_MANAGEMENT.en.md) | P2 |
| [ai-workflow/README.md](ai-workflow/README.md) | current/reference | EN | [JA reviewed](ai-workflow/README.ja.md); #482 | P2 |
| [ai-workflow/WORKFLOW.md](ai-workflow/WORKFLOW.md) | current/reference | EN | [JA reviewed](ai-workflow/WORKFLOW.ja.md); #482 | P2 |
| [ai-workflow/GRAPHIFY.md](ai-workflow/GRAPHIFY.md) | current/reference | EN | [JA reviewed](ai-workflow/GRAPHIFY.ja.md); #482 | P2 |
| [ai-workflow/CODEX_GEMINI_COLLAB.md](ai-workflow/CODEX_GEMINI_COLLAB.md) | current/reference | EN | [JA reviewed](ai-workflow/CODEX_GEMINI_COLLAB.ja.md); #482 | P2 |
| [ai-workflow/LABELS.md](ai-workflow/LABELS.md) | current/reference | EN | [JA reviewed](ai-workflow/LABELS.ja.md); #482 | P2 |
| [ai-workflow/PROMPTS.md](ai-workflow/PROMPTS.md) | optional/reference | JA | EN needed | P3 |
| [FUTURE_SERVICE_ARCHITECTURE.md](FUTURE_SERVICE_ARCHITECTURE.md) | future/roadmap | EN | JA needed; deferred until #449 resumes (#484) | P3 |
| [MINIMAL_MAINLINE_SURFACE.md](MINIMAL_MAINLINE_SURFACE.md) | current extraction reference; frozen evidence moved to `releases/issue409/` | EN | [JA reviewed](MINIMAL_MAINLINE_SURFACE.ja.md); #484 | P2 |
| [HISTORY_INDEX.md](HISTORY_INDEX.md) | history navigation / retention rules | EN | [JA reviewed](HISTORY_INDEX.ja.md); #484 | P2 |
| [ai-workflow/LESSONS.md](ai-workflow/LESSONS.md) | historical heuristics; revalidate before use | EN | selective; no bulk translation | P3 |
| [ai-workflow/RUNNER_DESIGN.md](ai-workflow/RUNNER_DESIGN.md) | deprecated runner proposal (#482) | EN | not translated (deprecated) | N/A |

### 範囲の境界とレビュー待ちの項目

- **エージェント向けの指示:** `AGENTS.md` は、英語で書かれた運用上の指示の唯一の正本として保ちます。翻訳の残件からは除外します。人が読むための補助は、将来具体的な必要が生じた場合にだけ再検討します。利用者・開発者向けガイドの翻訳は引き続き対象です。

- **範囲限定の契約は自動的に古くなるわけではありません。** `ISSUE120_EVALUATION_CONTRACT.md`、`ISSUE120_ARTIFACT_RETENTION.md`、`ISSUE158_DENSE_ROUTE_NAMING.md`、`ISSUE162_PIPELINE_LOGGING_TAXONOMY.md` は、英語の Issue 限定のリファレンスです。現在の利用者を確認し、必要な契約を範囲を保ったまま選んで翻訳してください。
- **凍結された履歴:** `TWO_HOMR_MILESTONE.md`、`REPOSITORY_SURFACE_INVENTORY.md`、`DEVELOPMENT_LOG.md`、`DEVLOG_MEASURE_NUMBERING.md`、`ISSUE333_MOVEMENT_BOUNDARY_INVESTIGATION.md`、`ISSUE363_RUNTIME_DEPENDENCY_REVIEW.md` は英語の履歴・参照の記録です。`ISSUE44_ITER7_FINAL_REPORT.md` は日本語です。一括の翻訳は必要ありません。
- **Issue の設計と実験:** `refactors/**`、`dev/ISSUE441_*.md`、`releases/issue410/**` は、個別に権威とライフサイクルをレビューする必要があり、自動的に現在の設計へ昇格するものではありません。#441 と #410 の記録は日本語が中心です。`refactors/**` は主に英語で、日本語の混在した記録（特に #94 と rebuild plan）を含みます。作業中のタスクがその証拠を必要とする場合にだけ、履歴索引を通じて読んでください。
  これらの記録の一部、特に `dev/ISSUE441_*.md` は、記録したコマンドの一部としてマシン固有の絶対パスを含みます。これらは過去の証拠であり、再利用する手順ではありません。#488 では証拠を書き換えず、そのまま残しました。
- **把握しているレビューの必要:** #226–#229 の文書は、自らが最終的に常設の利用者・運用文書へ移行することを記述しています。retire する前に、残っている固有の契約を確認してください。`ai-workflow/RUNNER_DESIGN.md` は `docs/refactors/` の下にタスクの束を必須としており、現在の `AGENTS.md` / `ai-workflow/WORKFLOW.md` と矛盾します。#482 で非推奨とし、翻訳していません。これらはレビュー項目であり、ランタイムの修正ではありません。
- **アーカイブ・非推奨:** `archive/**`、`ai-workflow/AI_AGENT_STRATEGY_2026.md`、`ai-workflow/LONG_HORIZON_WORKFLOW.md` は過去の案内として残すもので、翻訳の前提条件ではありません。`ai-workflow/templates/task/**` は任意の英語のテンプレートで、必須のタスク準備ではありません。
- **機械可読なものと生成物:** JSON/YAML の契約、例、モデルの manifest、config、`graphify-out/**` は、文章の翻訳の対象ではありません。キー、パス、ハッシュ、スキーマの値を保ってください。それらの説明の文書は翻訳します。ローカライズした機械向けの契約を作ったり、配布の選定を黙って広げたりしないでください。
- **隣接する文書:** `docs/` の外にある data、tools、experiments、skills、モデル固有の README は、ここで網羅的には台帳化していません。選んだ現行のガイドから辿られるものは、そのガイドを翻訳するときに監査してください。ここに載っていないことは、それが古い、あるいは日英対訳済みであるという主張ではありません。

#446 では、翻訳の作業単位 #452–#486 が、上の P1 の行と reviewed と記した P2 の行を、小さく独立してレビューした単位で扱いました。まだ **JA needed**、**EN needed**、延期、翻訳しない、と記した行は意図的なものです。具体的な必要が生じたときに翻訳してください。#488 では、文書を新しいディレクトリへ移動しないと決めました。英語と日本語の索引からすべての現行文書に到達でき、一方でファイルを移動すると、読者にとっての利点が示されないまま、既存のリンク、ツールの参照、配布の manifest が変わるためです。新しい設計の層が必要かどうかは別にレビューします（#489）。

## 履歴の案内と retire のルール

過去の記録は証拠として残りますが、エージェントはそれらを無差別に走査したり事前に読み込んだりするべきではありません。`docs/HISTORY_INDEX.md`（[日本語](HISTORY_INDEX.ja.md)）を使って作業中の Issue/PR に関係する経緯を選び、そのタスクに必要な受け入れ済みのマイルストーンや調査の記録だけを開いてください。

過去の一時的な状態は、再検証しない限り正本ではありません。例としては、ブランチや `develop` の HEAD、worktree やコンテナの状態、ローカルの成果物のパス、当時のブロッカー、未完了の PASS/FAIL の状態、`next step` の指示があります。

過去の文書は、次のすべてを満たすときに、現行のツリーから retire できます。

1. 採用・不採用の判断と重要な実験の来歴が、関連する Issue/PR/commit/source/test または保持している実験ツールから回復できる。
2. Issue をまたいで再利用できるルールが、現在の一般的なガイドかアーキテクチャの契約へ移されている。
3. そのファイルが、現在の運用・再現の唯一の契約ではない。
4. 残っているリポジトリ内のリンクを、同じ整理の変更で更新する。

完了した `Prompt.md`、`Plan.md`、引き継ぎ、実行日誌のファイルは、この条件を満たした時点で通常は retire します。ファイル名が過去の案内としてまだ役立つ場合は、古い実行ごとの状態を残すよりも、大きな日誌を明示的に過去のものとした簡潔な記録に置き換えることを優先します。

重要な実験については、チャットの記録を残したり同じ結果を別の要約文書に写したりするよりも、次のように回復できるつながりを優先します。

`hypothesis -> script/command -> commit -> fixed provenance -> result -> disposition`

無効になった結果や置き換えられた結果は、そのことが分かるラベルを付けたままにしてください。

## 凍結された #274 のマイルストーンと現在の本番

`docs/history/TWO_HOMR_MILESTONE.md` は、受け入れ済みの #274 / PR #279 の比較の契約を意図的に保存しています。その比較では、次にある Issue #44 / PR #57 の Iter 7 final-rescue の CNN 成果物を使いました。

```text
logs/cnn_barline_classification/issue44_iter7_final_rescue_v1/cnn_classifier_best.pth
```

`docs/history/ISSUE44_ITER7_FINAL_REPORT.md` は、**その過去の比較のチェックポイント**を再構成する手順として残っています。これは Iter 7 が現在の本番の CNN であることを意味しません。

検証済みの dense の本番ルートは、その後 Issue #296 / PR #310 で、current-producer の候補に整合した EfficientNet-B0 D27 のチェックポイントと、検証で選んだ閾値に更新されました。現在のモデルの契約については、現在の source/tests と `configs/dense_full_pipeline.yaml` が正本です。

この2つの層を区別しておくことで、凍結したマイルストーンを競合する現行のガイダンスにすることなく、受け入れ済みの #274 の比較を再現できます。

## 整理の経緯

ドキュメント整理の経緯では、冗長な説明を削除・圧縮する前に、永続的な情報を段階的に移してきました。

- #300 / PR #301: 履歴の案内と、作業中の文脈の保持に関するガイダンスを追加した。
- #302 / PR #305: 冗長な過去の文書の最初のまとまりを retire し、再実行の CSV を config が所有するフィクスチャの場所へ移した。
- #306 / PR #307: #19/#46/FP 削減の結論と、再利用できる安全上のガイダンスを要約した。
- #308 / PR #309: 現在の検出器の入力の来歴と NMS の契約を正規のアーキテクチャへ移し、重複した #120/#163/#245 の説明を retire した。
- #308 / PR #314: Issue 側で要約した後に、完了したタスク管理の束、古い CNN・経緯のガイド、重複した過去の説明を retire した。
- #308 / PR #316: 残っていた全体と番号付けの実行日誌を、簡潔な過去のマイルストーンの記録に圧縮した。
- その後の #308 の整理では、別の Issue を作らずに、監査したモデル調査の成果物に同じ retire の条件を適用した。

## 別の実装の整理

ドキュメントの整理で、本番のランタイムや config の意味を黙って変えてはいけません。古い環境変数のキー、互換性のためのフォールバック、モデルの挙動、マッチャーの意味論などの実装上の懸念は、コードの変更が必要な場合、それぞれの既存の実装の Issue に属します。

Graphify の更新には、`graphifyy` をインストールしたローカル環境が必要です。その運用上の前提条件は、現行のドキュメントのツリーに古い文章を残す理由にはなりません。

## 今後の監査のルール

永続的な文書は、次の4つの問いのどれか1つに明確に答えるべきです。**システムが今どう動くか**、**今どう運用するか**、**明示的に将来のものとして意図しているアーキテクチャや責務の境界は何か**、**過去の調査から得た永続的な証拠のうち、まだリポジトリ内の契約が必要なものは何か**。役割が混在している場合は、分割、要約、またはラベル付けをしてください。将来・ロードマップの文書は、自らが現行ではないことを示し、現在の正本を指さなければなりません。

過去の調査については、完全な説明の2つ目のコピーよりも、簡潔な案内・索引の層と、元の Issue/PR/commit の証拠を優先してください。これにより、すべての過去の調査を作業中の文脈にすることなく、過去の知識を回復できる状態に保てます。
