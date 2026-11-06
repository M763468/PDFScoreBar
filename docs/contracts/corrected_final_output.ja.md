# 補正済み最終出力ヘルパー

<!-- translation: {"original":"corrected_final_output.md","source":{"sha256":"319f574e5799806d2ad81d4378ce9c7bc853aa69f7f11e58e2d29ca769642ef5"},"state":"reviewed"} -->

[English / 原文](corrected_final_output.md)（英語正本）

翻訳元: same PR / SHA-256 `319f574e5799806d2ad81d4378ce9c7bc853aa69f7f11e58e2d29ca769642ef5`。状態: `reviewed`。原文との意味・制約・例外と日本語の可読性を確認済み。

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

## 出力名と保存済み attempt の互換性

`output_name` は任意の出力ファイル名メタデータです。ページの対応、検出結果、補正内容の意味を定義しません。この値がないジョブも有効で、生成時に既存の名前決定規則とフォールバックを適用し、指定された値はパスに使う前に正規化します。

操作ごとに検証する内容は異なります。

| 操作 | 必須 | 不要 |
| --- | --- | --- |
| レビューを開く | ファイルと構造を読み取れること | 保存済み attempt の検証。検証できない attempt は利用不可として一覧に表示 |
| チェックポイント導入前の attempt を取り込む | 記録された source identity と corrections identity を再現できること | ジョブの `output_name` との一致 |
| チェックポイントから再開する | チェックポイントと blob の整合性、依存入力、`resume.py` の PDF 対応検証 | 元の attempt の再検証 |

**取り込み。** これらの attempt は handoff ファイル全体のハッシュを記録しているため、identity は書き換えず、バイト列基準のまま扱います。ジョブの名前だけが異なる場合、`tools/review_correction/legacy.py` は attempt の保存コピーから記録時の handoff を組み立て、記録された source identity を再現できたときだけ受け入れます。対応する形式は1つだけで、キー順は attempt の保存時のもの、ジョブファイルのシリアライズは `prepare_local_review` のものです。それ以外は利用不可のままです。次の場合も同様です。

- ソース、manifest、補正内容が変更された場合
- 保存済み attempt が変更された場合（保存された `output_name` を含む）
- 保存された名前が適用時にのみ追加された attempt。記録時の handoff と変更されたコピーを区別できないため

取り込みで確認するのは保存入力だけです。以前の PDF 生成が成功したことは示しません。

**取り込み時の名前の優先順位:** attempt に保存された有効な名前、ジョブの現在の有効な名前、既存の名前決定規則の順です。有効な名前とは、正規化しても空にならない文字列です。取り込みは保存済み attempt、ジョブの handoff、既存のチェックポイントを変更しません。同じ attempt を再度取り込むと、ジョブの名前がその後変わっていても既存のチェックポイントを返します。セッションには名前を復元できる `final/` がないため、再開時の名前はチェックポイントの handoff から得ます。

チェックポイントの identity には引き続き handoff 全体が含まれます。ここから `output_name` を分離するには新しいスキーマと移行が必要で、この契約の対象外です。

## 非対象

このヘルパーは次を実装しません。

- 公開出力の完全な `OUTPUT_DIR/{final,review,debug}` マテリアライザー。
- 公開 `pdfscorebar run`／`pdfscorebar apply-corrections` CLI。
- GUI の起動ワークフロー。
- 実成果物を使った GUI リトライのワークフロー。
- detector／OCR／MMR の精度変更。
- 小節線または小節 override アルゴリズムの変更。
