# PDFScoreBar

<!-- translation: {"original":"README.md","source":{"sha256":"08e908f6615a19437672954cedea438c049dc665afdcc10c902e3e9fca3c0636"},"state":"reviewed"} -->

[English / 原文](README.md)（英語正本）

翻訳元: same PR / SHA-256 `08e908f6615a19437672954cedea438c049dc665afdcc10c902e3e9fca3c0636`。状態: `reviewed`。原文との意味・制約・例外と日本語の可読性を確認済み。

PDFScoreBar は PDF 楽譜に小節番号を付け、検出結果の確認、修正の記録、修正済み最終 PDF の生成を行うブラウザーアプリケーションを提供します。

対応する実行環境は NVIDIA GPU を使用できる Linux と Docker です。インストール、モデル登録、PDF 処理、レビュー、トラブルシューティングは[ユーザーガイド](docs/USER_GUIDE.ja.md)から始めてください。初回はガイドに従い、安定版 `main` 配布物を入手してホストを準備し、イメージのビルド、preflight、PDF 処理の順に進めます。検証済みの展開済み配布物から直接始めることもできます。

`models/` の本番モデル manifest に、選択されたバージョン、SHA-256 による識別情報、管理主体が記録されています。運用者によるモデルのインポートは不要です。#522 以降、検出処理は外部の OMR-DLN 小節検出器を使用しません。

サポート対象の安定版配布物には `main`、進行中の統合には `develop` を使用します。リリース候補と配布物には、ソースコミットと配布された全ファイルのハッシュを記録した `DISTRIBUTION_PROVENANCE.json` が含まれます。コントリビューションの対象は `develop` です。候補を `main` に昇格する前にリリース受け入れを通す必要があります。このガイドを含む `develop` の変更は、別途昇格するまで `main` に反映されません。
