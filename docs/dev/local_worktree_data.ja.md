# worktree へのローカルデータのリンク

<!-- translation: {"original":"local_worktree_data.md","source":{"sha256":"eaeb4b2f6671371dccb3b0c6746089f740d7d58ac4579440c597da2a5252e1ce"},"state":"reviewed"} -->

[English / 原文](local_worktree_data.md)（英語正本）

翻訳元: same PR / SHA-256 `eaeb4b2f6671371dccb3b0c6746089f740d7d58ac4579440c597da2a5252e1ce`。状態: `reviewed`。原文との意味・制約・例外と日本語の可読性を確認済み。

worktree では、意図的に git で追跡していないローカル専用のデータ（データセット、生成されたログ、モデル成果物、キャッシュ）が必要になることがよくあります。worktree を動かすためだけに、それらの資産をコピーしたりコミットしたりしないでください。

## 推奨する配置

Issue のソースは、[ローカル検証](LOCAL_VALIDATION.ja.md#ワークツリーとマウントの規約)で説明しているとおり `<manager-checkout>/.worktrees/issue<N>` に置きます。共有の Python コンテナからは `/workspace/.worktrees/issue<N>` として見えます。ローカル専用のデータはソースの worktree の外に置き、Docker で必要なときは明示的にマウントします。

ローカルの資産のルートは、Issue の worktree の外に置きます。例:

```bash
/path/to/pdfscore-local-assets/
  datasets/
  logs/models/
  cache/
```

そのうえで、選んだ項目を Issue の worktree にリンクします。

このブロックを実行する前に、シェルで `ISSUE_ID` に対象の Issue 番号（数値）を設定してください。

```bash
manager_root=/path/to/PDFScoreBar
if [[ "${ISSUE_ID:-}" =~ ^[0-9]+$ ]]; then
  cd "$manager_root/.worktrees/issue$ISSUE_ID"
  scripts/setup_local_worktree_links.sh --source /path/to/pdfscore-local-assets
else
  printf 'Set ISSUE_ID to the active Issue number before running this block.\n' >&2
fi
```

同等の Makefile のラッパー:

```bash
make setup-local-worktree-links LOCAL_DATA_ROOT=/path/to/pdfscore-local-assets
```

## 項目のカスタマイズ

既定では、ヘルパーは次をリンクしようとします。

- `datasets`
- `logs/models`
- `cache`

一覧は環境変数で上書きできます。

```bash
PDFSCORE_LINK_ITEMS="datasets logs/models external/homr external/omr_dln cache" \
  scripts/setup_local_worktree_links.sh --source /path/to/pdfscore-local-assets
```

スクリプトは、存在しないリンク元と、すでに存在するリンク先をスキップします。ファイルを上書き、移動、削除することはありません。

## Docker のマウント

worktree の外を指すシンボリックリンクは WSL のホスト上では便利ですが、Docker からはコンテナにマウントしたパスしか見えません。Docker 内で実行するパイプラインのコマンドが、`/home/...` などのホスト専用のパスへのシンボリックリンクをたどると、`/workspace` の中ではリンク先が存在しない場合があります。

Docker を使う検証では、シンボリックリンクだけに頼らず、明示的なバインドマウントを渡します。

```bash
DOCKER_EXTRA_ARGS="-v /path/to/PDFScoreBar/data/evaluation2/pdfs:/workspace/data/evaluation2/pdfs:ro" \
  make run-pipeline CONFIG=configs/evaluation2_e2e_verification_full.yaml
```

マシン固有のパスは、コミットする config ではなく、ローカルのコマンドや PR のコメントに書いてください。

## 注意事項

- 追跡しているプレースホルダやメタデータを隠さないと分かっている場合を除き、`data/` ディレクトリ全体をリンクしないでください。
- 秘密情報、個人のトークン、有料APIのキー、大きな生成ファイルは git に入れないでください。
- マシン固有のパスは、必要に応じて、ローカルのシェル履歴、git で無視される `.env` ファイル、PR のコメントに記録してください。それらのパスを再利用する config にコミットしないでください。
