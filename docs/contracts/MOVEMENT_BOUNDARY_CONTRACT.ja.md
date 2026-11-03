# 確定済み楽章境界の利用契約

<!-- translation: {"original":"MOVEMENT_BOUNDARY_CONTRACT.md","source":{"sha256":"70b9fb4119bf296c698d45d9b2c7f22da86bc9ee1f371598f7ed0ed33d773f2c"},"state":"reviewed"} -->

[English / 原文](MOVEMENT_BOUNDARY_CONTRACT.md)（英語正本）

翻訳元: same PR / SHA-256 `70b9fb4119bf296c698d45d9b2c7f22da86bc9ee1f371598f7ed0ed33d773f2c`。状態: `reviewed`。原文との意味・制約・例外と日本語の可読性を確認済み。

番号付けパイプラインは、確定済みの楽章境界を利用します。楽章を検出したり推測したりはしません。候補の検出は、後述する別のレビュー専用の生成器が担い、確定は明示的な手動またはレビュー済みの判断で行います。

## 入力

`inputs.movement_boundaries` に、次の形のJSONパスまたはインラインのマッピングを設定します。

```json
{
  "schema_version": "issue268.movement_boundaries.v1",
  "boundaries": [
    {
      "page": 1,
      "system": 2,
      "reset_number": 1,
      "source": "manual",
      "provenance": {"kind": "fixture"}
    }
  ]
}
```

`page` と `system` は、パイプラインに入力した順序でのゼロ始まりのインデックスです。境界は、その段の直前で論理的な小節番号をリセットします。`page` はページ区切りを示すものではありません。境界を指定しなければ、通常どおりページからページへ番号が続きます。`reset_number`、`source`、`provenance` は明示的に指定し、最終成果物に保持されます。ページ/段の位置の重複や、範囲外のページは拒否されます。

## 番号付けと成果物

Phase A はページ単位のままです。その絶対的な小節番号と `[page, system, measure]` のインデックスがMMRの入力になるためです。MMRの認識とその `skip` 出力は変わりません。Phase C は、すでにマージ済みのMMR/手動の上書きを適用しながら、`next_number` をページからページへ引き継ぎます。境界のリセットは `set_number` より前に適用されます。その後、既存の明示的な `set_number` が、その小節に割り当てる番号を決めます。

各 `outputs/<page_id>/numbering_final.json` には、ページの開始/次の状態と境界の記録を含む、追加の `numbering_metadata` が入ります。まとめた `outputs/numbering_final.json` はそれらのページのペイロードを連結し、同じページのメタデータと確定済み境界の来歴を保持します。ページを独立に番号付けし直すことはしません。`skip_existing` は、このメタデータが現在の入力状態と境界に一致する場合だけページを再利用します。古いページ単位の成果物は、表示されている最大番号から推測せずに作り直します。推測するとMMRのskip状態が失われるためです。

最終レンダラーは、引き続き最終番号付けJSONから各段で最初に有効な小節番号を読み、段の先頭に1つのラベルを描画します。境界の来歴やデバッグ用データは最終PDFに描画しません。

## 確定の方針

上記の確定済みペイロードは、検出の根拠から意図的に分けています。本番の番号付けが境界を利用できるのは、次のいずれかの場合だけです。

- 明示的/手動/設定で指定されたもの。または
- 別途検証された生成方針のもとで確認された自動のもの。

あいまいな候補を `inputs.movement_boundaries` にコピーしてはいけません。候補がないことは `no_boundary` を意味しません。この状態を使えるのは、明示的にレビュー/却下された記録だけです（最初の入力段の記録を除く）。境界が確定していなければ番号は続きます。運用者は根拠を確認し、同じゼロ始まりのページ/段の位置を決定的に追加できます。現在、本番の既定として承認された自動生成器はありません。後述の幾何による生成器は、候補の提示とレビューの用途にだけ承認されており、既定のパイプラインの経路には組み込まれていません。

## 候補と根拠の成果物

楽章の開始を提案する生成器は、別の `issue333.movement_boundary_evidence.v1` 成果物を書き出す必要があります。これはレビューと来歴のための契約であり、番号付けの入力ではありません。最上位の形は次のとおりです。

```json
{
  "schema_version": "issue333.movement_boundary_evidence.v1",
  "source_document": {
    "sha256": "...",
    "page_order": "ordered_pipeline_input",
    "input_manifest": "runs/example/manifest.json",
    "input_manifest_sha256": "..."
  },
  "input_artifacts": {
    "numbering_base": {
      "path": "runs/example/intermediate/numbering_base.json",
      "sha256": "..."
    }
  },
  "producer": {
    "name": "...",
    "version": "...",
    "source_commit": "...",
    "parameters": {}
  },
  "candidates": [
    {
      "page": 3,
      "system": 8,
      "state": "ambiguous_review_required",
      "signals": [
        {
          "kind": "heading_ocr",
          "artifact": "heading_ocr.json",
          "raw": {"text": "IV", "box": [[0, 0], [1, 1]]}
        },
        {
          "kind": "system_layout",
          "artifact": "numbering_base.json",
          "raw": {"preceding_gap_px": 200, "left_x_px": 525}
        }
      ],
      "references": {
        "page_id": "page_004",
        "source_page": 3,
        "image": "runs/example/inputs/images/page_004.png"
      },
      "provenance": {"review": null}
    }
  ]
}
```

`page` と `system` は、確定済みの契約と同じ、入力順でのゼロ始まりの座標を使います。これらは実際の入力manifestから求める必要があります。`source_page` は別の来歴情報であり、ページが選択・省略・並べ替えされた場合は利用側の座標ではありません。検証済みの直接PDFレンダリングは、選択したページの一部であっても、物理的な元ページの明示的な対応を保持できます。外部の画像、事前にレンダリングした画像、並べ替えた入力は、独立に検証された対応がない限りこれを省略します。`state` は次のいずれかです。

- `confirmed_automatic` — 検証済みの方針が確定済み境界を出力してよいもの。
- `explicit_manual_configured` — 運用者または設定が確定を与えたもの。
- `ambiguous_review_required` — 候補にすぎず、決して黙ってリセットしないもの。
- `no_boundary` — 再提案を防ぐために保持する、レビュー済み/却下済みの根拠。

シグナルは、生の観測値とその元の成果物を保持します。根拠の成果物は、`input_artifacts.numbering_base.path` と `sha256` を通じて幾何の入力全体にも結び付けられます。これにより、元のファイルが後で上書きされたり根拠の成果物が移動されたりしても、候補の位置を監査できます。この最上位の幾何の識別情報は、レイアウトの候補が1つも出力されない場合でも保持します。数値の信頼度は任意であり、較正の根拠なしに出力してはいけません。生成器はパラメータとソース/ランタイムの来歴を保持する必要があります。閾値やレビューされていない根拠を、確定済みの利用側ペイロードに隠してはいけません。

レビューの後、確定した記録だけを含む新しい `issue268.movement_boundaries.v1` ペイロードを出力します。`source` には `manual`、`configured`、`reviewed_candidate`、または特定の検証済み自動生成器などを使い、`provenance` に根拠の成果物の識別情報を保持します。

### レビューパッケージでの作業の流れ

通常の補正画面では、検出器の根拠の成果物を添付しなくても、明示的な手動の境界を受け付けます。**Movement boundary** を選び、新しい楽章の最初の段を選んで境界を確定します。判断はすぐに保存され、パッケージ内の `corrections/movement_boundaries.json` に、`source: manual`、`reset_number: 1`、保存したレビュー成果物の SHA-256 とともに確定されます。補正済みPDFを生成すると、その確定内容がすべてのページに適用されます。記録済みの手動境界を削除すると、確定内容もすぐに更新されます。候補がないことは、境界なしの判断にはなりません。番号をリセットするのは明示的な境界の記録だけで、通常のページ区切りでは番号が続きます。

handoff 内のすべてのページは、同じ楽章レビューの出力パスを宣言する必要があります。他の補正出力がページ単位であっても、これは楽譜全体のレビュー成果物です。handoff の検証と適用では、楽章のパスが異なる場合、それを使う前に拒否します。

レビューの保存後に確定内容の保存が失敗した場合、レビューが正常に保存されるまで、適用はその古い組を拒否します。どちらのパスもレビューパッケージ内に限定されます。古い handoff も、読み込み時に同じ既定の確定出力先を受け取ります。合成した検出の根拠を添付する必要はありません。

候補のレビューは、別の楽章エディタを導入するのではなく、既存の手動補正レビューパッケージとGUIを拡張したものです。後述の幾何によるレビュー用生成器で根拠の成果物を作り、既存の `review/manual_correction_input.json` パッケージに添付します。

```bash
python -m tools.movement_boundary_review attach \
  --handoff <review_root>/manual_correction_input.json \
  --evidence <run>/movement_boundary_evidence.json
```

その handoff から、`python3 tools/review_correction/server.py --handoff <review_root>/manual_correction_input.json` で利用者向け補正アプリを起動します。**Movement boundary** の補正画面は、未確定の候補を生のシグナルと参照情報とともに表示します。レビュー担当者は次の操作ができます。

- 明示的な候補を楽章境界としてマークする。
- 明示的な候補をレビュー済みの境界なしとしてマークする。
- 生成器が候補を出していない位置でも、サポートされる任意のページ/段の位置に楽章境界を追加する。

3つ目の操作が必要なのは、幾何によるレビュー用生成器が実際の楽章の開始を見逃すことがあるためです。候補がないことは決して `no_boundary` に変換されません。`no_boundary` のレビュー操作は、明示的な未確定の候補に対してだけ有効です。

保存すると、パッケージ内の `corrections/movement_boundaries_review.json` に書き込まれます。GUIの **Finish movement review** 操作（未確定の候補が残っている間は拒否されます）、または同等のCLIコマンド

```bash
python -m tools.movement_boundary_review export \
  --handoff <review_root>/manual_correction_input.json
```

は、変更されていない `issue268.movement_boundaries.v1` スキーマで `corrections/movement_boundaries.json` を書き出します。却下した候補はレビューの記録には残りますが、確定済みのペイロードからは除かれます。採用した候補は `source: reviewed_candidate`、候補以外で手動追加した境界は `source: manual` を使います。出力される各記録は、根拠の成果物の正確な SHA-256 とレビュー操作を来歴に結び付けます。


## 幾何によるレビュー用生成器

`src.pipeline.movement_boundary_candidates.build_movement_boundary_evidence` と `tools/generate_movement_boundary_candidates.py` は、検証済みのレビュー専用の生成器（バージョン2）を実装しています。説明可能な候補の規則は、すべての五線のbboxを再構成した和集合を使います。その開始位置がページの中央値よりページ幅の2%以上右にあるか、直前の隙間がページの隙間の中央値の1.75倍以上ある場合に候補とします。最初の五線だけの幾何は、複数の五線での監査の後に却下しました。空白や字下げの誤ったシグナルを生むためです。最初の空でない入力段は、最初のリセットは不要なため `no_boundary` として保持します。それ以外に一致した位置は常に `ambiguous_review_required` です。生成器は数値の信頼度も確定済みのリセットも出力しません。

リポジトリのルートから実行します。

```bash
python -m tools.generate_movement_boundary_candidates \
  --numbering-base runs/example/intermediate/numbering_base.json \
  --manifest runs/example/manifest.json \
  --source-pdf-sha256 <sha256> \
  --producer-source-commit <commit> \
  --output runs/example/movement_boundary_evidence.json
```

manifest と番号付けの成果物は、順序付けられたページ数が同じである必要があります。CLIは `numbering_base.json` の正確なバイト列のハッシュを求め、その SHA-256 を根拠の最上位に成果物のパスと並べて記録します。正規化した生のレイアウト値、一致した規則、画像の参照、元のハッシュ、manifest のハッシュ、番号付け成果物のハッシュ、パラメータ、生成器のcommitは、GUIまたは手動のレビューのために保持されます。`issue268.movement_boundaries.v1` への出力は、引き続き別の明示的なレビュー/設定の操作です。

代表的なfixtureは `tests/fixtures/movement_boundaries/issue333_representative.json` です。7つの元資料全体の一覧と文書全体の正解データは `experiments/issue333/phase25_ground_truth.json` に保持しています。どちらも、著作権のあるPDFや画像のバイト列を保持せずに、元PDFのハッシュとゼロ始まりの正確なページ/段の位置を固定しています。

`source_page` は、manifest に、元の digest と物理ページを持つ検証済みの直接PDFレンダリングの参照が含まれる場合にだけ出力されます。そのため、選択した直接PDFレンダリングは、物理的な対応を明示的に保持できます。外部の画像、事前にレンダリングした画像、並べ替えた画像の入力は、順序付けられた `page` と `page_id` を保持しますが、独立に検証された対応がない限り `source_page` を省略します。`page_NNN` というファイル名の部分を物理的なPDFのページと解釈することは決してありません。根拠のコアAPIも同じ規則を適用します。直接PDFの参照は、有効な0以上の `source_page`、有効な元文書の SHA-256、最上位の `source_document.sha256` と一致する digest を持つ必要があり、矛盾する検証済みの参照はすぐに失敗します。

この生成器は補助にすぎません。記録済みの Issue #333 の監査（過去の根拠であり、現在の保証ではありません）では、Phase 2.5 の全五線の和集合による再生で、16件の切り替わりのうち14件を見つけ、誤った候補は1件でした。917段中15件という候補の割合は生成の負担を示すもので、正しさを確認するレビュー全体の負担ではありません。候補がないことは決して `no_boundary` を意味しません。
