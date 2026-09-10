# スクリプト管理とディレクトリ運用ルール

このドキュメントは、現在のリポジトリでスクリプトをどこに置き、いつ昇格・保持・削除するかを定義します。過去の個別ファイル移動一覧は Git history と Issue #45 / PR #184 に残し、ここでは現行ルールだけを扱います。

## 基本原則

スクリプトの配置は「今どこで使っているか」ではなく、**責務と寿命**で決めます。

| Location | Intended role | Production dependency |
| --- | --- | --- |
| `src/pipeline/` | 現行production pipelineの実装 | authoritative runtime code |
| `tools/` | 繰り返し利用する保守・評価・変換CLI/utility | hidden dependencyにしない |
| `experiments/` | 仮説検証、比較、reproduction、prototype | production runtimeから依存しない |
| `tmp/` | 一時確認、生成途中のscratch | Git管理しない |

### `src/pipeline/`

現行production behaviorはここに置きます。production codeは、便宜上の理由で `tools/` のCLIをimportしたり、`experiments/` の内容を探索してruntime入力を暗黙決定したりしてはいけません。

実験で採用が決まったロジックは、必要なtest/config/provenanceとともにproduction側へ明示的に昇格させます。

### `tools/`

複数Issueや日常運用で再利用するCLI/utilityを置きます。特定ページ・特定run・特定デバッグ局面にハードコードされたone-off scriptは原則ここへ残しません。

productionから必要な共通ロジックがある場合は、CLI script自体へ依存させず、適切なlibrary/module境界へ抽出します。

### `experiments/`

仮説検証、parameter sweep、比較、再現用のscript/configを置きます。実験終了後は次のいずれかにします。

- 再現性や比較価値が残る: provenanceを明確にして保持する。
- reusableな一般則が得られた: current source/test/generic docsへ移す。
- one-offで再利用価値がない: Git historyをarchiveとして削除する。

`experiments/` に存在すること自体をproduction runtimeのfallbackやmodel discovery契約にしてはいけません。

### `tmp/`

「まず動かして確認する」ためのscratchです。`.gitignore` 対象として扱い、有用性が確認できたものだけ `tools/` / `experiments/` / production moduleへ昇格させます。

## Lifecycle

新しいscriptを追加するときは次の順で判断します。

1. 既存のproduction module / toolで対応できないか確認する。
2. 一時確認なら `tmp/`、仮説検証なら `experiments/<topic>/`、反復利用するCLIなら `tools/` を選ぶ。
3. file名・README・configから目的と入力 provenance が分かるようにする。
4. 実験終了時に、採用・reproduction保持・削除のどれかを明示する。
5. 削除時は、重要な結果や採否理由がIssue/PR/commit/current docsから回収できることを確認する。

`temp.py`、`test.py`、`debug_page3_fix.py` のように用途や寿命が不明な名前を長期保持しないでください。

## Historical cleanup lineage

Issue #45 / PR #184 では、CNN関連の `tools/` / `experiments/` を棚卸しし、one-off scriptの削除、active-learning scriptの `experiments/` への移動、generic diagnostic toolの `tools/diagnostics/` への移動を行いました。個別ファイルの旧配置はそのIssue/PRとGit historyを参照してください。

Issue #185 / PR #188 では、production CNN model resolutionから `experiments/cnn_classifier/**/best_model.pth` の暗黙fallbackを削除しました。現在は設定されたmodel pathを明示的に解決することがproduction contractです。

## Recovering retired scripts

削除されたone-off scriptをarchaeologyのために確認する場合はGit historyを使います。

```bash
git log --follow -- <old-path>
git show <commit>:<old-path>
```

履歴上の存在を理由に、retired scriptをcurrent workflowへ無条件に復帰させないでください。現行source/config/testとの整合を先に確認します。
