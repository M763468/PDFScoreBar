# ローカル検証環境

<!-- translation: {"original":"LOCAL_VALIDATION.md","source":{"sha256":"7299a9e13ca93ec681f565dd22193b52dd779258ff740b20d162ffe74ee97ae0"},"state":"reviewed"} -->

[English / 原文](LOCAL_VALIDATION.md)（英語正本）

翻訳元: same PR / SHA-256 `ec8d7387b0dd01e18a7d5ffa16d7b3fc8f9981716814d95a1abb42f573f04371`。状態: `reviewed`。原文との意味・制約・例外と日本語の可読性を確認済み。

アクティブな Issue ワークツリーに対して必要なチェックを実行できる環境を選択してください。
このガイドは [Validation Policy](VALIDATION_POLICY.md) の検証レベルと併せて使用します。以前に確認されたツールやコンテナは検証の手がかりにすぎず、現在も存在することや互換性があることを保証するものではありません。本番イメージや他のワークツリーで使用されているコンテナはそのまま維持してください。

## 環境の選択と事前確認（プリフライト）

| 環境 | 用途 | 使用前の確認事項 |
| --- | --- | --- |
| ホストシェル | Git プロベナンス（来歴）、Markdown/シェルのチェック、GitHub CLI、Docker の起動 | 必要なコマンドが存在すること。ホストの Python があるだけでは、pytest やプロジェクトの依存関係がインストールされていることの証明にはなりません。 |
| 永続 Python 検証コンテナ | リポジトリの pytest および Python チェック | 実行中のコンテナ、不変のイメージ ID、`/workspace` のバインド元、Issue ファイルが見えること、インタープリタおよび pytest が利用可能であること。 |
| 本番 GPU イメージ | リポジトリの Make ターゲットを通じた保守対象のパイプライン/GPU 検証 | `make verify-gpu-smoke` とそのソース/イメージ/アセットの事前確認を使用すること。このイメージには意図的に pytest やブラウザツールは含まれていません。 |
| ブラウザランナー | Node/Playwright/Chromium による受け入れチェック | ブラウザイメージ、Playwright モジュール、Chromium 実行ファイル、サーバーへのネットワーク経路、読み取り専用のソースマウントおよび書き込み可能なエビデンスマウント。 |

環境に依存するチェックでは、実行前に以下の事実を確認し、エビデンスに含めてください。

1. ホスト上のテスト対象ワークツリーのパス、ブランチ、コミット、および未コミットの差分（dirty diff）。
2. 選択した Python 実行ファイル、または不変の Docker イメージ ID とコンテナ。
3. コンテナ内の実際のバインドマウントとテスト対象ファイルへのパス。ホストの作業ディレクトリやコンテナ名からソースを推測しないでください。
4. 実行時の UID/GID、および各出力ディレクトリと既存ログへの書き込みアクセス権。
5. Docker、`gh`、およびコマンドが必要とするサンドボックス権限の利用可否。許可された経路が拒否された場合は、正確なコマンドとエラーを記録し、可能な場合は別の利用可能な環境を使用してください。

パイプラインを使用する場合は、さらにアクティブなワークツリーに対してイメージを解決し、[Environment & Tooling](ENVIRONMENTS.md) に記載されている本番用の事前確認を実行してください。ツールの利用可否プローブは、アプリケーション受け入れテストの合格とはみなされません。実際のチェック結果は、[エビデンス規則](VALIDATION_POLICY.md#validation-status-and-evidence)に従って Passed、Failed、Blocked、または Not run として報告してください。

## ワークツリーとマウントの規約

マネージャーチェックアウトは現在のタスクのまま維持してください。通常の Issue ワークツリーは、現在の `origin/develop` からマネージャーチェックアウトの `.worktrees/` ディレクトリ配下に作成します。コマンドを実行する前に、シェルで `ISSUE_ID` に対象の数値の Issue 番号を設定してください（以下の例では入力を求めるプロンプトは表示されません）。

```bash
# Run from the manager checkout.
if [[ "${ISSUE_ID:-}" =~ ^[0-9]+$ ]]; then
  manager_root="$(git rev-parse --show-toplevel)"
  git fetch origin develop
  mkdir -p "$manager_root/.worktrees"
  git -C "$manager_root" worktree add \
    -b "fix/issue${ISSUE_ID}" \
    "$manager_root/.worktrees/issue${ISSUE_ID}" origin/develop
else
  printf 'Set ISSUE_ID to the active Issue number before running this block.\n' >&2
fi
```

未使用のパスとブランチを使用してください。既存のワークツリーがある場合は、再作成せずに再開してください。1 つの Issue に対して同時に複数のワークツリーが必要な場合にのみ、用途を表すサフィックスを追加してください。既存のワークツリー、進行中の実験、または凍結されたリリース候補（release candidate）を機械的に移動しないでください。候補を `/workspace` に直接マウントする専用の候補コンテナは、引き続き明示的な例外となります。

標準の共有 Python コンテナはマネージャーチェックアウトを `/workspace` にマウントするため、`<manager-checkout>/.worktrees/issue<issue-id>` は `/workspace/.worktrees/issue<issue-id>` として表示されます。使用前に実際のソースとネストされたパスを確認してください。

```bash
if [[ "${ISSUE_ID:-}" =~ ^[0-9]+$ ]]; then
  manager_root="$(git rev-parse --show-toplevel)"
  issue_root="$manager_root/.worktrees/issue${ISSUE_ID}"
  container_issue="/workspace/.worktrees/issue${ISSUE_ID}"
  docker inspect pdfscore_pipeline_pytest_dev \
    --format '{{.Image}} {{json .Mounts}}'
  docker exec pdfscore_pipeline_pytest_dev \
    test -f "$container_issue/AGENTS.md"
else
  printf 'Set ISSUE_ID to the active Issue number before running this block.\n' >&2
fi
```

[`scripts/docker_container_preflight.sh`](../../scripts/docker_container_preflight.sh) は、アクティブなチェックアウトが `/workspace` に直接マウントされている専用コンテナ向けに意図して作られています。そのため、ネストされた Issue ワークツリーは拒否されます。共有レイアウトの場合は、上記のコマンドでマネージャーのバインド元、ネストされたファイル、およびインポートパスを確認してください。スクリプトの直接マウントチェックを弱めないでください。リンクされたワークツリーの `.git` ファイルにはホストの絶対パスが含まれているため、コンテナ内で Git コマンドを実行するには、マネージャーチェックアウトの `/workspace/.git` 配下にあるワークツリーの管理ディレクトリへの明示的なマッピングが必要です。ブランチとコミットはホスト側で記録し、ホストの `.git` ポインタを書き換えないでください。

`.worktrees/` は Git によって無視され、Docker ビルドコンテキストからも除外されます。これらの追跡対象の無視ルールがまだ含まれていない古いマネージャーチェックアウトでは、ルールが利用可能になるまでローカルの `.git/info/exclude` を使用してください。ネストされた Issue のソースをイメージビルドに含めないでください。

## Python と pytest

永続 Python 検証コンテナが利用可能であり、マネージャーチェックアウトにマウントされている場合は、pytest にそのコンテナを使用してください。生成されたファイルをホストユーザーが編集できるようにするため、ホストの UID/GID でチェックを実行します。上記のネストされたレイアウトに対しては `scripts/docker_container_preflight.sh` を使用しないでください。

ホスト上の Issue ワークツリーから以下を実行します。

```bash
git_common_dir="$(git rev-parse --path-format=absolute --git-common-dir)"
manager_root="$(dirname "$git_common_dir")"
issue_root="$PWD"
issue_relative="$(realpath --relative-to="$manager_root" "$issue_root")"
container_issue="/workspace/$issue_relative"
git rev-parse HEAD
docker inspect pdfscore_pipeline_pytest_dev --format '{{.Image}} {{json .Mounts}}'
docker exec --user "$(id -u):$(id -g)" \
  -w "$container_issue" -e PYTHONPATH="$container_issue" \
  pdfscore_pipeline_pytest_dev \
  /opt/venv_pipeline/bin/python -m pytest --version
```

### Git に依存する pytest スイート

ネストされたワークツリーの `.git` ポインタはホスト上のパスであるため、共有コンテナ内からは辿ることができません。Git を呼び出すスイートは、独自の `.git` ディレクトリを持つ使い捨て clone から実行してください。clone は `/workspace` マウント経由で見えるよう、Issue のログルート配下に置きます。

```bash
git_common_dir="$(git rev-parse --path-format=absolute --git-common-dir)"
manager_root="$(dirname "$git_common_dir")"
clone="logs/issue${ISSUE_ID}/pytest-clone/$(git rev-parse --short HEAD)"
git clone -q --no-hardlinks . "$clone"
container_clone="/workspace/$(realpath --relative-to="$manager_root" "$PWD/$clone")"
docker exec --user "$(id -u):$(id -g)" \
  -w "$container_clone" -e PYTHONPATH="$container_clone" -e HOME=/tmp \
  pdfscore_pipeline_pytest_dev \
  /opt/venv_pipeline/bin/python -m pytest \
  tests/test_docker_runtime_contract.py tests/test_distribution_surface.py \
  tests/test_release_candidate.py tests/test_doc_translations.py
```

パスが既に存在する場合 `git clone` は停止します。以前の clone を削除するのは、それが使い捨ての clone であることを確認してからにしてください。clone にはコミット済みの `HEAD` の内容しか含まれないため、検証対象の変更を先にコミット（または一時的な WIP コミット）し、検証したコミットを報告してください。実行後は clone を削除してください。

`GIT_DIR` や `GIT_WORK_TREE` を pytest に渡さないでください。これらの変数は `git -C <dir>` より優先され、すべてのサブプロセスに継承されます。そのため、一時ディレクトリで `git init`、`git config`、`git add -f -A`、`git commit` を実行する fixture が、マッピング先のワークツリーへ書き込みます。そのブランチには未追跡ファイルや ignored ファイルを含むコミットが追加され、共有 `.git/config` には `core.worktree` とテスト用の `[user]` が書き込まれます（#513）。このため `tests/conftest.py` と `tools/release_candidate.py` は `git rev-parse --local-env-vars` が返す変数を除去します。これらの変数に依存する実行は Issue ワークツリーを解決できず、失敗します。検査した `/workspace` マウント配下にマネージャーの `.git` ディレクトリが見えない場合は、必要な依存関係を備えたホストランナーを使用してください。`pytest --version` のみ、あるいは Git アクセスなしでのテスト実行のみに基づいて、Git に依存するスイートを合格（Passed）として報告しないでください。

#### fixture の書き込み混入の検出と復旧

以前の `GIT_DIR`/`GIT_WORK_TREE` 手順に従った実行は、チェックアウトを変更している可能性があります。共有設定と、影響を受けた各ブランチの最近のコミットを確認してください。

```bash
git_common_dir="$(git rev-parse --path-format=absolute --git-common-dir)"
common_config="$git_common_dir/config"
git config --file "$common_config" --get-all core.worktree
git config --file "$common_config" --get-regexp '^user\.'
git log -5 --format='%h %an <%ae> %s' <branch>
git -C "$(dirname "$git_common_dir")" rev-parse --show-toplevel
```

混入の兆候は、共有設定の `core.worktree`（このときマネージャーチェックアウトの `--show-toplevel` は別のワークツリーを指します）、`Distribution test` / `distribution-test@example.invalid` や `Release tests` / `release-tests@example.invalid` などの `[user]`、およびそれらの identity による `fixture candidate` などのコミットです。各値が意図的に設定されたものでないことを確認してから復旧してください（fixture は既存のリポジトリ単位の `[user]` を上書きするため、元の値があった場合は削除せずその値に戻してください）。

```bash
git config --file "$common_config" --unset-all core.worktree
git config --file "$common_config" --unset user.name
git config --file "$common_config" --unset user.email
# 影響を受けたブランチで、fixture のコミットが未 push かつ HEAD の場合のみ:
git reset --mixed HEAD~1
```

`git reset --mixed` はコミットを取り除き、そのファイルを作業ツリーに残します。そのため、実行前に未追跡または ignored だったファイルは、再び未追跡または ignored に戻ります。コミットが既に push されている場合は、共有履歴を書き換えずに revert してください。

Issue ワークツリーの Makefile から保守対象の `FAST_TESTS` リストを読み取り、コンテナのインタープリタで直接 pytest を呼び出します。

```bash
mapfile -t fast_tests < <(
  sed -n 's/^FAST_TESTS ?= //p' Makefile | tr ' ' '\n'
)
fast_tests_valid=1
if ((${#fast_tests[@]} == 0)); then
  printf 'FAST_TESTS was not found or is empty; stopping before pytest.\n' >&2
  fast_tests_valid=0
fi
for test_path in "${fast_tests[@]}"; do
  if [[ ! -f "$test_path" ]]; then
    printf 'FAST_TESTS entry is not a file: %s; stopping before pytest.\n' "$test_path" >&2
    fast_tests_valid=0
  fi
done
if ((fast_tests_valid)); then
  docker exec --user "$(id -u):$(id -g)" \
    -w "$container_issue" -e PYTHONPATH="$container_issue" \
    pdfscore_pipeline_pytest_dev \
    /opt/venv_pipeline/bin/python -m pytest "${fast_tests[@]}"
fi
```

特定のスイートに絞って実行する場合は、テスト配列を選択したパスやオプションに置き換えてください。`make test-fast` は、`PYTHON` が設定されていても `.venv_pdf/bin/python` が存在すればそちらを優先します。コンテナのインタープリタを直接呼び出すことで、ホストやワークツリーのインタープリタが暗黙のうちに選択されるのを防げます。pytest が存在しないことを確認するためだけにホストで `make test-fast` を実行しないでください。出力ディレクトリは実行ユーザーとして作成し、リダイレクトを行うコマンドを実行する前に既存ログの所有者を確認してください。

## ブラウザ検証

Python コンテナにブラウザツールがない場合は、用意されている Node/Playwright/Chromium ランナーを使用してください。サーバーを起動し、書き込み可能な新しいレビューパッケージを準備するには、[利用者補正の受入検証](REVIEW_ACCEPTANCE.ja.md#browser-workflow) に従ってください。以下の例では、ブラウザランナーがサーバーコンテナのネットワーク名前空間を共有していることを前提としています。共有していない場合は、明示的な経路を選択して確認してください。ランナーはソースを読み取り専用でマウントし、エビデンスを別のディレクトリに書き込みます。

```bash
if [[ "${ISSUE_ID:-}" =~ ^[0-9]+$ ]]; then
  issue_root="$PWD"
  browser_evidence="$issue_root/logs/issue${ISSUE_ID}/validation/browser"
  mkdir -p "$browser_evidence"
  browser_image="$(docker image inspect mcp/playwright:latest --format '{{.Id}}')"
  chromium_path="$(docker run --rm --entrypoint node "$browser_image" \
    -p 'require("/app/node_modules/playwright").chromium.executablePath()')"
  docker run --rm --network container:pdfscore_pipeline_pytest_dev \
    --user "$(id -u):$(id -g)" \
    -v "$issue_root:/workspace:ro" \
    -v "$browser_evidence:/evidence" \
    -w /workspace \
    -e PLAYWRIGHT_MODULE=/app/node_modules/playwright \
    -e CHROMIUM_PATH="$chromium_path" \
    --entrypoint node "$browser_image" \
    tools/review_correction/browser_acceptance.cjs \
    http://127.0.0.1:8010 /evidence
else
  printf 'Set ISSUE_ID to the active Issue number before running this block.\n' >&2
fi
```

Playwright/Chromium イメージはブラウザランナーであり、本番イメージの依存関係ではありません。バージョン確認、インポートプローブ、空白ページの起動、または HTTP プローブは環境の準備状況を確認するものであり、ブラウザ受け入れテストに合格したことを意味するものではありません。アプリケーションの受け入れ結果は、これらのプローブとは区別して扱ってください。

## ローカルデータとナビゲーション

データセット、ログ、モデル、およびキャッシュは、実用上可能な限り Issue ソースワークツリーの外に保持してください。シンボリックリンクと明示的な Docker マウントのルールについては、[`local_worktree_data.ja.md`](local_worktree_data.ja.md) を参照してください（リンク先がコンテナ内にマウントされていない限り、Docker はホスト専用のシンボリックリンクを辿ることができません）。保守対象のイメージ、アセットの所有権、およびランタイムの互換性については、[Environment & Tooling](ENVIRONMENTS.md) を参照してください。ワークツリーおよび検証コマンドは本ファイルが管轄します。リンク先のドキュメントではこれらの手順を重複して記載せず、ここを参照するようにしてください。
