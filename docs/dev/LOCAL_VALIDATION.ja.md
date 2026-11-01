# ローカル検証環境

<!-- translation: {"original":"LOCAL_VALIDATION.md","source":{"sha256":"19d9e14ccec3da0c890971efbb608ac17a1338354d0a49aa74e92cceed82144c"},"state":"reviewed"} -->

[English / 原文](LOCAL_VALIDATION.md)（英語正本）

翻訳元: same PR / SHA-256 `19d9e14ccec3da0c890971efbb608ac17a1338354d0a49aa74e92cceed82144c`。状態: `reviewed`。原文との意味・制約・例外と日本語の可読性を確認済み。

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

パイプラインを使用する場合は、さらにアクティブなワークツリーに対してイメージを解決し、[Environment & Tooling](../ENVIRONMENTS.md) に記載されている本番用の事前確認を実行してください。ツールの利用可否プローブは、アプリケーション受け入れテストの合格とはみなされません。実際のチェック結果は、[エビデンス規則](VALIDATION_POLICY.md#validation-status-and-evidence)に従って Passed、Failed、Blocked、または Not run として報告してください。

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

ネストされたワークツリーの `.git` ポインタはホスト上のパスであるため、共有コンテナ内からは辿ることができません。Git を呼び出すテストでは、マネージャーチェックアウトのバインドマウントを介してワークツリーの管理ディレクトリをマッピングし、明示的に渡してください。ワークツリーのディレクトリ名を決め打ちせず、パスを動的に導出してください。

```bash
git_common_dir="$(git rev-parse --path-format=absolute --git-common-dir)"
git_dir="$(git rev-parse --path-format=absolute --git-dir)"
git_dir_relative="$(realpath --relative-to="$git_common_dir" "$git_dir")"
container_git_dir="/workspace/.git/$git_dir_relative"
container_issue="/workspace/$(realpath --relative-to="$(dirname "$git_common_dir")" "$PWD")"
docker exec --user "$(id -u):$(id -g)" \
  -w "$container_issue" \
  pdfscore_pipeline_pytest_dev \
  git --git-dir="$container_git_dir" --work-tree="$container_issue" \
  rev-parse --absolute-git-dir
```

この事前確認でコンテナ内のパスが解決された場合は、同じ `GIT_DIR` と `GIT_WORK_TREE` を pytest に渡し、Git のサブプロセスがそのマッピングを継承するようにします。これらの変数は Git に依存するスイートに限定してください（通常のテストでは不要です）。検査した `/workspace` マウント配下にマネージャーの `.git` ディレクトリが見えない場合は、必要な依存関係を備えたホストランナー、または Git を認識できるチェックアウトを代わりに使用してください。`pytest --version` のみ、あるいは Git アクセスなしでのテスト実行のみに基づいて、Git に依存するスイートを合格（Passed）として報告しないでください。

たとえば、`git rev-parse` を呼び出す Docker ランタイム契約テストは、マッピングされたメタデータを使用して次のように実行できます（必要に応じて対象のテストパスに置き換えてください）。

```bash
git_common_dir="$(git rev-parse --path-format=absolute --git-common-dir)"
git_dir="$(git rev-parse --path-format=absolute --git-dir)"
git_dir_relative="$(realpath --relative-to="$git_common_dir" "$git_dir")"
container_git_dir="/workspace/.git/$git_dir_relative"
container_issue="/workspace/$(realpath --relative-to="$(dirname "$git_common_dir")" "$PWD")"
docker exec --user "$(id -u):$(id -g)" \
  -w "$container_issue" \
  -e PYTHONPATH="$container_issue" \
  -e GIT_DIR="$container_git_dir" \
  -e GIT_WORK_TREE="$container_issue" \
  pdfscore_pipeline_pytest_dev \
  /opt/venv_pipeline/bin/python -m pytest \
  tests/test_docker_runtime_contract.py::test_direct_build_creates_artifact_directory_before_tempfile
```

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

Python コンテナにブラウザツールがない場合は、用意されている Node/Playwright/Chromium ランナーを使用してください。サーバーを起動し、書き込み可能な新しいレビューパッケージを準備するには、[Review Acceptance](REVIEW_ACCEPTANCE.md#browser-workflow) に従ってください。以下の例では、ブラウザランナーがサーバーコンテナのネットワーク名前空間を共有していることを前提としています。共有していない場合は、明示的な経路を選択して確認してください。ランナーはソースを読み取り専用でマウントし、エビデンスを別のディレクトリに書き込みます。

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

データセット、ログ、モデル、およびキャッシュは、実用上可能な限り Issue ソースワークツリーの外に保持してください。シンボリックリンクと明示的な Docker マウントのルールについては、[`local_worktree_data.md`](local_worktree_data.md) を参照してください（リンク先がコンテナ内にマウントされていない限り、Docker はホスト専用のシンボリックリンクを辿ることができません）。保守対象のイメージ、アセットの所有権、およびランタイムの互換性については、[Environment & Tooling](../ENVIRONMENTS.md) を参照してください。ワークツリーおよび検証コマンドは本ファイルが管轄します。リンク先のドキュメントではこれらの手順を重複して記載せず、ここを参照するようにしてください。
