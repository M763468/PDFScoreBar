# PR単位の軽量検証の手順

<!-- translation: {"original":"PR_SLICE_VALIDATION.md","source":{"sha256":"a8bdb852ed5c76ca20f4b5741bcad88ea167b531c1880afb52471d211cb8bd44"},"state":"reviewed"} -->

[English / 原文](PR_SLICE_VALIDATION.md)（英語正本）

翻訳元: same PR / SHA-256 `a8bdb852ed5c76ca20f4b5741bcad88ea167b531c1880afb52471d211cb8bd44`。状態: `reviewed`。原文との意味・制約・例外と日本語の可読性を確認済み。

この文書は、範囲を絞ったPRのための、ローカルでの軽量な検証の手順を定めます。フォーマッタだけの追加コミットを防ぎ、範囲を絞った pytest のセットをレビューの繰り返しで再利用できるようにすることが目的です。

## 範囲を絞ったPRをpushする前に

リポジトリのルートで、スライス検証コマンドを実行します。

```bash
bash scripts/check_pr_slice.sh issue236-apply-corrections
```

このコマンドは次を実行します。

1. `make lint`
2. `scripts/pr_validation_profiles/issue236-apply-corrections.txt` に列挙された pytest の項目

実行の概要とログは `artifacts/pr_slice_validation/` に書き出されます。

## フォーマッタだけのコミットを避ける

コミットする前、またはレビュー対応の更新をpushする前に、次を実行します。

```bash
make format
bash scripts/check_pr_slice.sh issue236-apply-corrections
```

または、ランナーの変更を伴う便利なオプションを使います。

```bash
bash scripts/check_pr_slice.sh issue236-apply-corrections --fix
```

`--fix` は検証の前に `make format` を実行します。ファイルが変更される場合があるため、コミットの前に `git diff` を確認してください。

lintだけを確認するには、次を使います。

```bash
bash scripts/check_pr_slice.sh issue236-apply-corrections --lint-only
```

lintが合格済みであると分かっている状態で、範囲を絞った pytest だけを再実行するには、次を使います。

```bash
bash scripts/check_pr_slice.sh issue236-apply-corrections --pytest-only
```

## 範囲を絞ったテストのプロファイルを追加する

`scripts/pr_validation_profiles/` の下に新しいテキストファイルを作ります。

```text
scripts/pr_validation_profiles/<profile-name>.txt
```

規則:

- 1行に pytest の引数を1つ書きます。
- 空行と `#` で始まる行は無視されます。
- プロファイル名はIssueや機能の範囲に結び付けます。例: `issue236-apply-corrections`、`issue267-numbering-geometry`。
- GPU、Docker、モデル成果物、全体評価のデータを必要としない、安定した軽量なテストを優先します。
- スライスにもっと重い検証が必要な場合は、その要件を軽量プロファイルの中に隠さず、PR本文に `docs/dev/VALIDATION_POLICY.md` の用語で記載します。

利用できるプロファイルは次で一覧できます。

```bash
bash scripts/check_pr_slice.sh --list-profiles
```

## ローカルのフック（任意）

フックは任意で導入します。`.git/hooks/` のファイルはコミットしないでください。

ローカルの pre-push フックで、lintだけの確認を実行できます。

```bash
cat > .git/hooks/pre-push <<'HOOK'
#!/usr/bin/env bash
set -euo pipefail
bash scripts/check_pr_slice.sh issue236-apply-corrections --lint-only
HOOK
chmod +x .git/hooks/pre-push
```

プロファイル全体を実行するフックは、範囲を絞った pytest のセットが通常のpushに十分なほど速い場合にだけ使ってください。

## GitHub Actions での対象範囲

`.github/workflows/pr-validation.yml` のPR検証ワークフローは、`develop` と `main` へのプルリクエストと、手動実行で動きます。その `make lint` ジョブは、文書の翻訳来歴（`tools/verification/check_doc_translations.py` とそのテスト）、Makefile のリポジトリ参照（`make check-makefile`）、`make lint` を確認します。`engine contract compatibility` ジョブは、少数の依存パッケージをインストールし、固定したエンジン契約の pytest ファイル一覧を実行します。

`scripts/pr_validation_profiles/` にあるプロファイル単位の限定 pytest は、GitHub Actions では実行されません。選んだテストによっては、PyMuPDF、OpenCV、torch 関連のパッケージ、OCR のバックエンド、Docker、GPU、モデル成果物などの任意または重い依存関係が必要になります。プロファイルについて安定したCIの依存関係の層が定まるまでは、ローカルでの確認のままとします。

プロファイルについてCIの依存関係の準備が安定したら、次のようなプロファイルのコマンドでワークフローを拡張します。

```bash
bash scripts/check_pr_slice.sh issue236-apply-corrections --pytest-only
```

選んだプロファイルと依存関係の前提は、同じPRに記載してください。
