# 補正済み最終出力ヘルパー

<!-- translation: {"original":"corrected_final_output.md","source":{"sha256":"6eb0c481612583b779d4ede8e77bc222a38ff80c9ae0ac68c30ad704af375d45"},"state":"reviewed"} -->

[English / 原文](corrected_final_output.md)（英語正本）

翻訳元: same PR / SHA-256 `6eb0c481612583b779d4ede8e77bc222a38ff80c9ae0ac68c30ad704af375d45`。状態: `reviewed`。原文との意味・制約・例外と日本語の可読性を確認済み。

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

## バージョン付き identity

レビューパッケージの identity には3つの規則があります。`tools/review_correction/state.py` がすべてを計算し、保存済みの記録は常にその記録自身の規則で比較します。

| | Identity v1 | Identity v2 | Identity v3 |
| --- | --- | --- | --- |
| 記録元 | チェックポイント schema 1、以前の結果、チェックポイント導入前の attempt | チェックポイント schema 2、#543 以前の結果 | チェックポイント schema 3、新しい結果 |
| 目印 | `identity_version` なし | `identity_version: 2` | `identity_version: 3` |
| handoff の入力 | ファイル全体の SHA-256 | 最上位の `output_name` を除いて解析した JSON オブジェクトのダイジェスト | v2 と同じ |
| ソース manifest | バイト列の SHA-256 | バイト列の SHA-256 | 保存場所に依存しないダイジェスト |

それ以外の入力はすべての規則で共通です。宣言されたソースファイル、再開用 PDF、補正内容が該当します。v2 と v3 でも、ページ順や `resume` ブロックなどの handoff の内容が変われば identity は変わります。JSON の書式やキー順では変わりません。JSON オブジェクトでない handoff は、そのバイト列でハッシュします。`corrections_identity` はすべての規則で同じ値です。

**保存場所に依存しないソース manifest（v3）。** 準備済みのローカルレビューは、ソース manifest を `<job>/.engine-retained/runs/<job-id>/local_manifest.json` に結び付けます。この manifest にはジョブフォルダ配下の絶対パスが記録されます。ジョブを移動すると（別の保存ルート、マウントポイント、Windows portable フォルダ）、次にレビューを準備したときにそれらのパスが書き換わります。manifest の `run_dir` がこの retained レイアウトを宣言している場合、v3 は宣言されたジョブルート自身とその配下を指す文字列をジョブ相対パスに置き換えたうえで、解析済み manifest をハッシュします。ジョブ ID、数値・設定・モデル／来歴の値、ジョブ外のパスはすべて記録どおりにハッシュします。それ以外の manifest、不正な manifest、ジョブルート配下に `.` や `..` の要素を含む manifest は、そのバイト列でハッシュします。したがって意味を失うのは保存場所だけです。入力、認識結果、設定、モデル参照、ジョブが異なれば identity は変わります。

**一括移行なし。** schema 1／2 のチェックポイント、その blob、`cp_...` ID、保存済みの結果は書き換えず、引き続き一覧表示、マテリアライズ、再開ができます。未知の schema／identity バージョンや、バージョンやダイジェストに矛盾がある記録は拒否します。identity v3 より前のコードは schema 3 のチェックポイントを読み取れません。

**移動後の v1／v2 の記録。** v1／v2 の記録は、以前のジョブの場所を含む manifest のバイト列をハッシュしています。各チェックポイントは、保存時の manifest のバイト列をそのまま保持します。チェックポイント ID と blob のハッシュで検証した保持済みバイト列が、現在の manifest と同じ保存場所非依存ダイジェストを持ち、さらにそのダイジェストに置き換えると記録の identity 全体を再現できる場合に限り、v1／v2 の記録は移動後のパッケージと一致します。そのようなチェックポイントがない場合や、保存場所以外にも変更がある場合、記録は stale のままです。照合で記録を書き換えることはありません。

**再利用と状態表示:**

- 保存時は、その記録自身の規則で identity が一致する最新のチェックポイントを再利用します。このため `output_name` だけの変更やジョブの移動だけでは、チェックポイントは増えず、v2／v3 の結果も stale になりません。
- v1 の記録はダイジェストしか持たないため変換できません。一致するのは handoff のバイト列が変わっていない間だけです。名前の変更後は次の保存で v3 のチェックポイントが1つ作られ、v1 の結果は次の適用が成功するまで stale と表示されます。
- 状態レスポンスの `current_identity` は常に v3 です。一致した v1／v2 の結果は、記録時のダイジェストのまま `current_result` に入ります。

**移動後のパス。** チェックポイントは、保存時点のジョブの絶対パスを保持します。保持済みの依存ファイルと復元する manifest では、記録されたジョブルート配下の参照を、同じ retained run ID を現在保持しているジョブの中で解決し、その外へは解決しません（ジョブ外を指すシンボリックリンクは拒否します）。SHA-256 も引き続き一致する必要があります。ジョブ外の参照は記録どおりに使います。結果には `final_pdf_package_path`、`corrected_run_package_path`、存在する場合は `number_layer_sidecar_package_path` も記録します。ダウンロード、番号付き結果からの再開、中断した適用の回復では、これらのパス、または以前の絶対パスの `application_runs/...` 部分を現在のパッケージ内で解決し、記録された SHA-256 を検証します。絶対パスは来歴として記録に残ります。ジョブが移動したチェックポイント導入前の attempt は、正確なソース manifest のバイト列が保持されていないため取り込めません。

**整合性検証は別に行います。** チェックポイントは `output_name` を含む完全な handoff を、内容アドレス方式の blob として保持します。そのバイト列は blob のハッシュと `cp_...` manifest のハッシュで保護され、handoff の blob がない schema 2／3 のチェックポイントは拒否します。

**再利用後の名前:**

- 補正結果の生成では、別の名前のチェックポイントを再利用した場合でも、ジョブの現在の `output_name` を使います。ジョブに名前がなければ既存の名前決定規則に従います。
- 再開では、選択したチェックポイントに保持された名前を使います。変更後の名前で再開するには、先にチェックポイントを明示的に保存してください。明示的な保存では既存のチェックポイントを再利用しません。

identity は[出力名と保存済み attempt の互換性](#出力名と保存済み-attempt-の互換性)に示した操作ごとの検証を置き換えません。チェックポイント導入前の attempt の取り込みでは引き続き記録時の v1 identity を再現し、再開では PDF、ページ、画像、注釈の検証を維持します。

## 非対象

このヘルパーは次を実装しません。

- 公開出力の完全な `OUTPUT_DIR/{final,review,debug}` マテリアライザー。
- 公開 `pdfscorebar run`／`pdfscorebar apply-corrections` CLI。
- GUI の起動ワークフロー。
- 実成果物を使った GUI リトライのワークフロー。
- detector／OCR／MMR の精度変更。
- 小節線または小節 override アルゴリズムの変更。
