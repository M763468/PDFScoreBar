# 補正済み最終出力ヘルパー

<!-- translation: {"original":"corrected_final_output.md","source":{"sha256":"fd745dace46145dddbcf42d8d59f1586a82b91951d8b1770d098682889c62624"},"state":"reviewed"} -->

[English / 原文](corrected_final_output.md)（英語正本）

翻訳元: same PR / SHA-256 `fd745dace46145dddbcf42d8d59f1586a82b91951d8b1770d098682889c62624`。状態: `reviewed`。原文との意味・制約・例外と日本語の可読性を確認済み。

この内部ヘルパーのリファレンスは開発者・保守担当者向けです。手動補正の `apply_corrections` 再実行経路から、その補正済み実行のクリーンな最終 PDF 成果物への限定的な接続を説明します。サポート対象の利用者向け配布ワークフローは[ユーザーガイド](../USER_GUIDE.ja.md)を参照してください。

## 入口

`src.pipeline.review.apply_corrections.apply_corrections_and_rerun()` は次を受け取ります。

```python
generate_final_pdf = True
output_name = "optional-name"
```

最小 CLI ラッパーも次を受け付けます。

```bash
python -m src.pipeline.review.apply_corrections \
  path/to/review/manual_correction_input.json \
  --overwrite \
  --generate-final-pdf \
  --output-name optional-name
```

このフラグは明示的に指定した場合のみ有効です。既定では再実行時に最終 PDF を生成しません。

## 出力

dry run ではない補正済み再実行の後で有効にすると、ヘルパーは次を出力します。

```text
<corrected_run_dir>/
  final/
    <output-name>_score_numbered.pdf
  review/
    correction_summary.json
    corrected_final_summary.json
```

`final/` はクリーンな最終 PDF 成果物専用です。補正の来歴、行ラベルのメタデータ、警告は `review/` に書き込まれます。

## 描画契約

レンダラーは次を入力とします。

- 同じ手動補正レビューパッケージの座標空間にある元ページ画像。
- 補正済み再実行の `outputs/<page_id>/numbering_final.json` ファイル。

最終 PDF は最終番号付けの各行につき行頭の小節番号を一つ描画します。譜表の塗り分け、小節線の矩形、小節範囲の目盛り、MMR 証拠、補正の来歴、警告といったレビュー専用の情報は最終 PDF に描画しません。

## 非対象

このヘルパーは次を実装しません。

- 公開出力の完全な `OUTPUT_DIR/{final,review,debug}` マテリアライザー。
- 公開 `pdfscorebar run`／`pdfscorebar apply-corrections` CLI。
- GUI の起動ワークフロー。
- 実成果物を使った GUI リトライのワークフロー。
- detector／OCR／MMR の精度変更。
- 小節線または小節 override アルゴリズムの変更。
