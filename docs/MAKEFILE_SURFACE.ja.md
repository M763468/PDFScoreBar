# 保守対象のMakefile入口

<!-- translation: {"original":"MAKEFILE_SURFACE.md","source":{"sha256":"2b6cb7906b879c61d739e5569f821da7f706a70294e702b8d3cdab1ea17a4a25"},"state":"reviewed"} -->

[English / 原文](MAKEFILE_SURFACE.md)（英語正本）

翻訳元: same PR / SHA-256 `2b6cb7906b879c61d739e5569f821da7f706a70294e702b8d3cdab1ea17a4a25`。状態: `reviewed`。原文との意味・制約・例外と日本語の可読性を確認済み。

ルートの `Makefile` は、日常の開発、検証、正規のランタイム操作、および少数の保持された過去の再現手順について、サポートされるリポジトリの入口である。`make help` は各項目に役割を表示する。この一覧はルートの全ターゲットを分類する。Issue固有のターゲットは来歴のために保持されており、一般的なワークフローとして推奨するものではない。

## 保守対象のユーザー・開発者向け入口

| ターゲット | 分類 | 備考 |
| --- | --- | --- |
| `help` | 保守対象のユーザー向け入口 | 説明のあるルートターゲットを一覧表示する。 |
| `run-pipeline` | 保守対象のランタイム入口 | `ENVIRONMENTS.md` の正規イメージ、インタープリター、`/workspace` bind mountを使う。 |
| `docker-build` | 保守対象のランタイム入口 | 暗黙のクリーンアップなしに選択したイメージをビルドする。 |
| `docker-clean`, `docker-clean-full` | 保守対象のランタイム補助 | コンテナ削除と明示的なイメージ削除は分かれている。 |
| `setup-local-worktree-links` | 保守対象の開発補助 | `scripts/setup_local_worktree_links.sh` に処理を委ねる。 |
| `promote-log` | 保守対象の開発補助 | 実行結果を既存の保持ログカテゴリに昇格する。 |
| `repo-tree` | 保守対象の開発補助 | 任意の概要表示。外部の `tree` コマンドが必要。 |
| `issue-post-mortem` | 保守対象のIssue作業補助 | 完了したIssueの作業をレビューし、関連する処置・来歴を残す。 |
| `visual-diff` | OMR目視確認補助 | 最近のデバッグ画像を目視レビュー用に収集する。 |
| `clean-artifacts`, `clean-logs` | 保守対象のクリーンアップ補助 | `clean-logs` は文書化されたカテゴリルートに限定され、保持対象ディレクトリを保護する。 |
| `format` | 保守対象のコード補助 | Ruffによる整形と修正を適用する。 |

## 保守対象の検証と評価

| ターゲット | 分類 | 備考 |
| --- | --- | --- |
| `lint`, `test-fast`, `test` | 保守対象の検証 | `test-fast` は軽量。`test` は `tests/` の全テストを実行する。 |
| `run-smoke`, `verify-pipeline-smoke`, `verify-gpu-smoke` | 保守対象の検証 | 本番パイプラインのチェック。`ENVIRONMENTS.md` と `dev/VALIDATION_POLICY.md` を参照。 |
| `verify-service-readiness-smoke`, `verify-service-readiness-container` | 保守対象の検証 | 1ジョブのサービス準備状態を確認するコンテナチェック。 |
| `verify-full-eval` | 保守対象の任意評価 | 長時間の全評価ラッパー。 |
| `local-pr-validation` | 保守対象の検証補助 | `scripts/local_pr_validation.sh` に処理を委ねる。 |
| `check-makefile` | 保守対象の静的検証 | ルートMakefileのレシピにあるリポジトリパスへのリテラル参照を確認する。 |

## 保持されているIssue固有の再現ターゲット

これらは評価器、フィクスチャ、再生成手順がIssue #120の過去の契約を支えるため保持している。既定値の利用には、運用者が保持するデータ、モデル、Docker、GPUアセットが必要な場合がある。

| ターゲット | 分類 | 実装 |
| --- | --- | --- |
| `eval-issue120-full` | Issue #120の再現 | `tools/issue120/eval_full68_from_intermediates.py` と来歴ツール |
| `verify-issue120-stage-b`, `verify-issue120-stage-b-native` | Issue #120の再現 | Stage-Bスコアラー・評価器。DockerまたはホストPython経由 |
| `regen-issue120-stage-d-upstream`, `verify-issue120-stage-d` | Issue #120の再現 | Stage-D生成とStage-C検証器 |
| `summarize-issue120-stage-d`, `compare-issue120-stage-d-boxes` | Issue #120の再現 | ドリフトとボックス統計の分析ツール |

Stage-Eターゲットも利用できるが、その契約はIssue #120に限定されるため、ルートのhelp表示からは削除された。次のように明示的に呼び出す。

```bash
make -f tools/issue120/Makefile.stage_e.mk <target>
```

過去の `run-smoke-sr` エイリアスは非推奨の互換ターゲットとして保持され、`run-smoke` を指す。

## 削除された古いターゲット

- `check-consistency` は存在しない `tools/check_repo_consistency.py` を参照していた。現行のリポジトリ契約はそのマニフェスト・鮮度チェッカーを要求しない。代わりに `check-makefile` が、より限定された検証可能なMakefile契約を守る。
- `setup-worktree` は存在しない補助スクリプトを参照していた。worktreeはGitで作成でき、保守対象のワークフローが存在するまでは誤解を招くMakeターゲットを設けない。

## 参照チェックの契約

`make check-makefile` として公開される `tools/check_makefile_references.py` は、レシピ内のリポジトリのスクリプト、ソース、設定、テストに対するリテラル参照を走査する。ルートMakefileと独立したIssue #120 Stage-E Makefileを確認する。変数展開されるパスや、利用可否がローカル環境に依存する運用者のデータ・モデルのパスは意図的に無視する。PR検証ワークフローが自動実行する。ターゲットまたはその説明を変更する場合は、これと併せて `make help` を実行する。
