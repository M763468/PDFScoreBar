# PDFScoreBar

<!-- translation: {"original":"README.md","source":{"sha256":"f1fbf65a99adf13b0959a9d5276e804f6093fd21fcb8fa9e246fcb7f403fa2b8"},"state":"reviewed"} -->

[English / 原文](README.md)（英語正本）

翻訳元: same PR / SHA-256 `f1fbf65a99adf13b0959a9d5276e804f6093fd21fcb8fa9e246fcb7f403fa2b8`。状態: `reviewed`。原文との意味・制約・例外と日本語の可読性を確認済み。

PDFScoreBar は PDF 楽譜に小節番号を付け、検出結果の確認、修正の記録、修正済み最終 PDF の生成を行うブラウザーアプリケーションを提供します。

対応する実行環境は NVIDIA GPU を使用できる Linux と Docker です。インストール、モデル登録、PDF 処理、レビュー、トラブルシューティングは[ユーザーガイド](docs/USER_GUIDE.ja.md)から始めてください。初回はガイドに従い、安定版 `main` 配布物を入手してホストを準備し、イメージのビルド、preflight、PDF 処理の順に進めます。検証済みの展開済み配布物から直接始めることもできます。

`models/` の本番モデル manifest に、選択されたバージョン、SHA-256 による識別情報、管理主体が記録されています。運用者によるモデルのインポートは不要です。#522 以降、検出処理は外部の OMR-DLN 小節検出器を使用しません。

サポート対象の安定版配布物には `main`、進行中の統合には `develop` を使用します。リリース候補と配布物には、ソースコミットと配布された全ファイルのハッシュを記録した `DISTRIBUTION_PROVENANCE.json` が含まれます。コントリビューションの対象は `develop` です。候補を `main` に昇格する前にリリース受け入れを通す必要があります。このガイドを含む `develop` の変更は、別途昇格するまで `main` に反映されません。

## ライセンス

PDFScoreBar の first-party のコード、スクリプト、設定、補正 GUI、テスト、文書、`models/sr_x4/` の重み、および `models/mmr/mmr_classifier_best.pth` と barline CNN（`issue296-d27-v1`、`models/barline_cnn/manifest.json`）におけるオーナー保有権利部分は GNU Affero General Public License v3.0 以降（`AGPL-3.0-or-later`）で提供します。[LICENSE](LICENSE) と [NOTICE](NOTICE) を参照してください。商用利用やネットワークサービスとしての提供を含め、PDFScoreBar を利用・改変・実行できます。複製物を渡す場合、または改変版をネットワーク越しに利用者に操作させる場合、AGPL はその受領者・利用者に対応するソースを同じライセンスで提供することを求めます。変更を GitHub に公開することや、本プロジェクトに送ることまでは求めません。

第三者のコード、モデル重み、データ（初期化元重みや学習データにおける第三者の権利を含む）は再許諾しません。`src/third_party/realesrgan_sr/` 配下の vendored 推論コードは Apache-2.0 および BSD-3-Clause のまま維持され、ビルドされる実行環境には AGPL-3.0 の部品（HOMR、PyMuPDF）と、それぞれのライセンスに従うその他の部品が含まれます。[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) を参照してください。開発リポジトリにのみ含まれる評価・GT データや楽譜由来のテスト fixture はリポジトリのライセンスの対象外（`NotLicensed`）であり、最小配布物には含まれません。対象は [NOTICE](NOTICE) と `REUSE.toml` に記載しています。
