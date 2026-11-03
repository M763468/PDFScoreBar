# Codex 等のローカル自動化

<!-- translation: {"original":"codex_local_automation.md","source":{"sha256":"a0fa767bf60d200f639092adce4711a7e817efac55caf83f34b1f6400224582f"},"state":"reviewed"} -->

[English / 原文](codex_local_automation.md)（英語正本）

翻訳元: same PR / SHA-256 `a0fa767bf60d200f639092adce4711a7e817efac55caf83f34b1f6400224582f`。状態: `reviewed`。原文との意味・制約・例外と日本語の可読性を確認済み。

このリポジトリは、Codex app、Codex CLI、WSL、GitHub CLI での作業向けに、任意で使えるローカル自動化の入口を用意しています。これらのヘルパーは、通常の手作業による開発を置き換えずに、ローカルの検証を繰り返し実行できるようにするためのものです。

検証の強さは `docs/dev/VALIDATION_POLICY.md` で決まります。スクリプトはその方針を適用するための補助であり、必要なチェックを弱めたり、スコープの境界を無視したりする理由にはなりません。

## 役割

- Codex app: ローカルでの実装、ファイルの編集、軽いコマンドの実行、PR と Issue の文脈の把握。
- WSL/Linux シェル: Docker、GPU、データセット、長時間の検証を行う、正となるローカルの実行環境。
- Codex CLI: `codex exec` による、範囲を絞ったレビューや修正のループ（任意）。
- GitHub CLI: PR へのコメント、レビューの文脈の収集、認証が必要な GitHub の操作。
- GitHub/web の ChatGPT/Codex Cloud: 静的なレビューと GitHub 上の小さな編集。その結果は、GPU やパイプラインの挙動については最終的なものとして扱わないでください。
- 人: 結果の最終的な解釈と、正しい対象ブランチへのマージ。通常の Issue の作業は `develop` を対象にします。`main` はリリース・昇格の流れで使います。

## 基本の作業の流れ

1. 既存の管理用クローン（manager clone）は、今の作業のままにしておきます。すでに別の Issue に使っている場合は、そこでブランチを切り替えたりファイルを編集したりしないでください。
2. 管理用クローンで fetch してから、正しいベースブランチから Issue 専用の worktree を作ります。通常の Issue の作業では `develop` を使います。

   このブロックを実行する前に、シェルで `ISSUE_ID` に対象の Issue 番号（数値）を設定してください。

   ```bash
   if [[ "${ISSUE_ID:-}" =~ ^[0-9]+$ ]]; then
     cd /path/to/PDFScoreBar
     git fetch origin
     mkdir -p .worktrees
     git worktree add ".worktrees/issue${ISSUE_ID}" -b "fix/issue${ISSUE_ID}" origin/develop
     cd ".worktrees/issue${ISSUE_ID}"
   else
     printf 'Set ISSUE_ID to the active Issue number before running this block.\n' >&2
   fi
   ```

3. ローカル専用の資産が必要な場合は、worktree にリンクします。

   ```bash
   make setup-local-worktree-links LOCAL_DATA_ROOT=/path/to/pdfscore-local-assets
   ```

4. 通常のリポジトリのコマンドで変更を実装します。自動化のスクリプトは任意です。
5. [ローカル検証](LOCAL_VALIDATION.ja.md)を使ってランナーを選び、関連する最も軽い検証を実行します。ホストに pytest やブラウザのツールがあるとは仮定しないでください。

6. パイプラインや GPU に関わる変更では、次を実行します。

   ```bash
   make verify-gpu-smoke
   ```

7. 評価に関わる変更では、利用者、Issue、PR の文脈で認められている場合に、全体評価を実行します。

   ```bash
   make verify-full-eval
   ```

8. PR の検証と、任意のコメント投稿には次を使います。

   ```bash
   scripts/local_pr_validation.sh --pr 123 --with-gpu --with-full-eval --post-comment
   ```

## Codex app 向けのローカル操作

Codex app から公開・実行すると便利なコマンド:

- `make test-fast`
- `make verify-pipeline-smoke`
- `make verify-gpu-smoke`
- `make verify-full-eval`
- `scripts/gpu_smoke.sh --metadata-only`
- `scripts/local_pr_validation.sh --pr <number> --with-gpu --with-full-eval --post-comment`
- `scripts/respond_to_pr_review.sh --pr <number>`
- `scripts/setup_local_worktree_links.sh --source <path>`

Codex app のサンドボックスの承認は、セッション単位の挙動です。リポジトリから、特定のスクリプトだけにサンドボックス外での自動実行を許可することはできません。GPU、Docker、`gh`、ネットワークへのアクセスに承認が必要な場合は、アプリの通常の承認の流れでコマンドを実行し、コマンドとログのパスを記録してください。

## 検証のレベル

- Fast tests: `make test-fast`。通常のコードや文書に近い変更向けです。実データを使わない単体テストを実行し、実データを使う統合テストは意図的に除外しています。worktree では、ローカルの `.venv_pdf` があればそれを使い、なければ `PYTHON` を使います。
- パイプラインのスモーク: `make verify-pipeline-smoke`。既存の `make run-smoke` をラップします。
- GPU のスモーク: `make verify-gpu-smoke`。ブランチ、commit、Python のバージョン、GPU の情報、コマンド、終了コード、ログのパスを `logs/system/` の下に記録します。
- 全体評価: `make verify-full-eval` または `scripts/local_pr_validation.sh --with-full-eval` による長時間の実行。PR の既定の要件ではありませんが、評価に関わる変更では、結果か、`docs/dev/VALIDATION_POLICY.md` に基づく人による明示的なスキップ・延期の判断が必要です。

## GitHub CLI の要件

ローカル環境で一度だけ実行します。

```bash
gh auth login
gh auth status
```

コメントを投稿するスクリプトは `gh pr comment --body-file` を使います。`gh` がない、未認証、ネットワークやサンドボックスの制限でブロックされている場合、スクリプトはローカルに概要を残し、投稿をスキップした理由を報告するべきです。

## レビューコメントへの対応のループ

PR レビューの入口を使って文脈を集めます。

```bash
scripts/respond_to_pr_review.sh --pr <number>
```

これは `artifacts/` の下に成果物を書き出します。人または Codex app がその成果物を読み、対応すべき要求された修正だけを適用し、対象を絞った検証を実行して、概要を投稿できます。`--codex` は、`codex exec` がインストールされていて、チェックアウトがレビューの計画に十分クリーンな場合にだけ使ってください。

## Web の ChatGPT や GitHub での編集

Web からの編集は、小さな文書やコードの変更には問題ありませんが、ローカルのデータセット、Docker、GPU の文脈を持ちません。Web で編集した後は次を行います。

1. ブランチを専用のローカル worktree に取り込みます。
2. 差分をローカルで確認します。
3. [ローカル検証](LOCAL_VALIDATION.ja.md)で選んだ環境で、`docs/dev/VALIDATION_POLICY.md` が求めるチェックを実行します。
4. ローカルの検証結果を PR に投稿します。

## 安全の境界

- これらのスクリプトは `develop` や `main` にマージしません。
- 文書だけの変更や軽微な変更には GPU のスモークを要求しません。
- 評価値、閾値、フィルタ、シード、データセットの選択、指標を更新しません。
- ローカルのデータセット、ログ、モデル、キャッシュを移動・削除しません。
- これらのスクリプトを使わない、通常の手作業による開発も引き続き有効です。
