# Issue #194 小節間隔構築（measure interval construction）ローカル調査報告書

## 概要
本報告書は、指定された 5 つの既知ケースについて、画像上の段・五線・小節構造と `numbering_base.json` の各 bbox との対応、およびエラー分類の整理結果をまとめたものです。
また、Issue #94 で整備された MMR overrides の正解データ（expected overrides）と現在の評価結果の整合性、および `page_033`, `page_035`, `page_037` の評価ステータスを確認しました。

---

## 評価結果と GT (expected overrides) の整合性確認
### 1. `page_033`, `page_035`, `page_037` の現在の評価ステータス
- **`page_035` (`Sibelius-Violin_Concerto-Viola_page_004.png`)**: 
  - 現在の評価結果 (`aggregated_eval_summary.json`): `unexpected: 1`
  - 内容: `system: 9, measure: 4` -> `detected_skip: 1` (OCR="2") が検出されているが、正解データ（GT）に登録されていなかったため unexpected 扱いとなっていた。
  - 解消状況: ローカルで `expected_overrides_page_035.json` に `{ "page": 34, "system": 9, "measure": 4, "skip": 1 }` が追加されており、**GT反映済みで解消可能（再評価により matched になる）**な状態である。
- **`page_037` (`Sibelius-Violin_Concerto-Viola_page_006.png`)**:
  - 現在の評価結果: `unexpected: 1`
  - 内容: `system: 11, measure: 3` -> `detected_skip: 5` (OCR="6") が unexpected となっていた。
  - 解消状況: ローカルで `expected_overrides_page_037.json` に `{ "page": 36, "system": 11, "measure": 3, "skip": 5 }` が追加されており、**GT反映済みで解消可能（再評価により matched になる）**な状態である。
- **`page_033` (`Sibelius-Violin_Concerto-Viola_page_002.png`)**:
  - 現在の評価結果: `unexpected: 1`
  - 内容: `system: 0, measure: 0` -> `detected_skip: 10` (OCR="11", CNN=0.54) が検出されている。
  - 解消状況: `expected_overrides_page_033.json` には本項目が追加されておらず、**現在の評価でも依然として unexpected（誤検出）扱い**のままである。ヘッダー部分などの誤検出（False Positive）と考えられる。

---

## 各ケースの調査結果

### 1. `page_021` (divisi 五線の独立段扱い)
- **page_id**: `page_021`
- **対象スコア / 画像 / ソースページ**: `Shostakovich-Sym5-Va` / `Shostakovich-Sym5-Va_page_013.png` / `page_013`
- **画像パス**: `logs/issue120_e2e_recovery/stage_e_full_pipeline/images/Shostakovich-Sym5-Va_page_013.png`
- **numbering_base.json パス**: `logs/issue120_e2e_recovery/stage_e_full_pipeline/intermediate/page_021/numbering_base.json`
- **overlay パス**:
  - `logs/issue194_measure_interval_construction/system_bbox_page_021.png`
  - `logs/issue194_measure_interval_construction/staff_bbox_page_021.png`
  - `logs/issue194_measure_interval_construction/measure_bbox_page_021.png`
  - `logs/issue194_measure_interval_construction/barline_candidates_page_021.png`
- **bbox 抜粋**:
  ```json
  "systems": [
    {
      "staves": [
        { "bbox": [231, 1135, 2760, 1286] } // Sys 1: 上五線
      ],
      "measures": [
        { "number": 7, "bbox": [232, 1135, 899, 1286] }
      ]
    },
    {
      "staves": [
        { "bbox": [234, 1519, 2760, 1653] } // Sys 2: 下五線
      ],
      "measures": [
        { "number": 13, "bbox": [235, 1519, 900, 1653] }
      ]
    }
  ]
  ```
- **分類**: `divisi merge miss`
- **原因層の仮説**:
  本来 divisi である上下2つの五線（Sys 1 と Sys 2）の縦方向の距離が離れている、または括弧（brace/bracket）が検出されなかったために、`system_grouping` 処理で同一システムとしてマージされず、別々の独立段として分割されてしまった。その結果、小節番号がシーケンシャル（7〜12、13〜18）に振られてしまっている。
- **修正候補 / 対処方針**:
  `system_grouping` のマージ閾値（縦方向間隔）の調整、または divisi 括弧検出ロジックの改善。実装修正で根本解決すべきだが、他ページへの副作用が大きい場合は manual correction に逃がすことも検討する。

---

### 2. `page_045` (本来別システムの二段のマージ)
- **page_id**: `page_045`
- **対象スコア / 画像 / ソースページ**: `Va_Prokofiev_Symphony1` / `Va_Prokofiev_Symphony1_page_004.png` / `page_004`
- **画像パス**: `logs/issue120_e2e_recovery/stage_e_full_pipeline/images/Va_Prokofiev_Symphony1_page_004.png`
- **numbering_base.json パス**: `logs/issue120_e2e_recovery/stage_e_full_pipeline/intermediate/page_045/numbering_base.json`
- **overlay パス**:
  - `logs/issue194_measure_interval_construction/system_bbox_page_045.png`
  - `logs/issue194_measure_interval_construction/staff_bbox_page_045.png`
  - `logs/issue194_measure_interval_construction/measure_bbox_page_045.png`
  - `logs/issue194_measure_interval_construction/barline_candidates_page_045.png`
- **bbox 抜粋**:
  ```json
  "systems": [
    {
      "staves": [
        { "bbox": [406, 3526, 3210, 3701] }, // Sys 9 の五線 1
        { "bbox": [405, 3794, 3210, 3952] }  // Sys 9 の五線 2
      ],
      "measures": [
        { "number": 72, "bbox": [406, 3526, 891, 3952] } // 縦方向に両五線を貫通
      ]
    }
  ]
  ```
- **分類**: `system merge`
- **原因層の仮説**:
  本来シーケンシャルに演奏される独立した 2 つの段（五線）の縦方向の間隔が狭すぎたために、`system_grouping` で誤って同一の system（divisi 扱い）としてマージされてしまった。そのため、本来別々の小節であるべき上下の領域が、1つの小節（M 72など）として結合してしまっている。
- **修正候補 / 対処方針**:
  `system_grouping` ロジックで、divisi 用の明示的な括弧や記号が存在しない場合に、単に距離が近いだけでマージする挙動を抑制する。

---

### 3. `page_053` (五線左端外側の小節化)
- **page_id**: `page_053`
- **対象スコア / 画像 / ソースページ**: `Va__Prokofiev_Symphony5` / `Va__Prokofiev_Symphony5_page_007.png` / `page_007`
- **画像パス**: `logs/issue120_e2e_recovery/stage_e_full_pipeline/images/Va__Prokofiev_Symphony5_page_007.png`
- **numbering_base.json パス**: `logs/issue120_e2e_recovery/stage_e_full_pipeline/intermediate/page_053/numbering_base.json`
- **overlay パス**:
  - `logs/issue194_measure_interval_construction/system_bbox_page_053.png`
  - `logs/issue194_measure_interval_construction/staff_bbox_page_053.png`
  - `logs/issue194_measure_interval_construction/measure_bbox_page_053.png`
  - `logs/issue194_measure_interval_construction/barline_candidates_page_053.png`
- **bbox 抜粋**:
  ```json
  "systems": [
    {
      "staves": [
        { "bbox": [485, 872, 3460, 1039] } // 五線の左端が 485 (他の段は 203)
      ],
      "measures": [
        { "number": 1, "bbox": [486, 872, 665, 1039] } // 非常に幅の狭い最初の小節
      ]
    }
  ]
  ```
- **分類**: `non-measure region` / `barline false positive`
- **原因層の仮説**:
  最初のシステム（Sys 1）がインデントされている、または五線の開始点（左端）の検出が誤って右にズレたために、五線開始前の余白・音部記号・調号の領域（またはその境界付近）に誤って小節線が検出され、そこが `measure 1` として過剰に切り出されてしまった。
- **修正候補 / 対処方針**:
  五線の左端（開始位置）検出および最初の小節線の位置フィルタリングの強化。特に、五線開始から一定の閾値（例えば `unit_size` の数倍）未満の非常に狭い領域を独立した小節とみなさないガードロジックの導入。

---

### 4. `page_060` (小節の過剰分割 R37/R38)
- **page_id**: `page_060`
- **対象スコア / 画像 / ソースページ**: `Va__Prokofiev_Symphony5` / `Va__Prokofiev_Symphony5_page_015.png` / `page_015`
- **画像パス**: `logs/issue120_e2e_recovery/stage_e_full_pipeline/images/Va__Prokofiev_Symphony5_page_015.png`
- **numbering_base.json パス**: `logs/issue120_e2e_recovery/stage_e_full_pipeline/intermediate/page_060/numbering_base.json`
- **overlay パス**:
  - `logs/issue194_measure_interval_construction/system_bbox_page_060.png`
  - `logs/issue194_measure_interval_construction/staff_bbox_page_060.png`
  - `logs/issue194_measure_interval_construction/measure_bbox_page_060.png`
  - `logs/issue194_measure_interval_construction/barline_candidates_page_060.png`
- **bbox 抜粋**:
  ```json
  "systems": [
    {
      "staves": [
        { "bbox": [215, 3955, 3479, 4135] }
      ],
      "measures": [
        { "number": 37, "bbox": [216, 3955, 580, 4135] },
        { "number": 38, "bbox": [584, 3955, 1028, 4135] }
      ]
    }
  ]
  ```
- **分類**: `measure over-split`
- **原因層の仮説**:
  本来は 1 つの小節（R37 から R38 にまたがる領域）であるはずが、その中間位置（x=580付近）に False Positive の小節線（barline）が誤検出されたため、小節が過剰に分割されてしまった。
- **修正候補 / 対処方針**:
  小節線（barline）検出モデルのノイズ抑制、または `barline_matcher` 層における不要な小節線のデデュプリケーション閾値の調整。

---

### 5. `Shostakovich-Sym5-Va_page_014` (divisi 五線の独立段扱い)
- **page_id**: `page_022` (対応する page_id)
- **対象スコア / 画像 / ソースページ**: `Shostakovich-Sym5-Va` / `Shostakovich-Sym5-Va_page_014.png` / `page_014`
- **画像パス**: `logs/issue120_e2e_recovery/stage_e_full_pipeline/images/Shostakovich-Sym5-Va_page_014.png`
- **numbering_base.json パス**: `logs/issue120_e2e_recovery/stage_e_full_pipeline/intermediate/page_022/numbering_base.json`
- **overlay パス**:
  - `logs/issue194_measure_interval_construction/system_bbox_page_022.png`
  - `logs/issue194_measure_interval_construction/staff_bbox_page_022.png`
  - `logs/issue194_measure_interval_construction/measure_bbox_page_022.png`
  - `logs/issue194_measure_interval_construction/barline_candidates_page_022.png`
- **bbox 抜粋**:
  ```json
  "systems": [
    {
      "staves": [
        { "bbox": [202, 377, 2726, 524] } // Sys 0: R1〜R4
      ],
      "measures": [
        { "number": 1, "bbox": [203, 377, 1114, 524] }
      ]
    },
    {
      "staves": [
        { "bbox": [228, 759, 279, 889] } // Sys 1: R5〜R8
      ],
      "measures": [
        { "number": 5, "bbox": [229, 759, 1116, 889] }
      ]
    }
  ]
  ```
- **分類**: `divisi merge miss`
- **原因層の仮説**:
  `page_021` と同様、本来 divisi であるはずの二段（Sys 0: R1〜R4 と Sys 1: R5〜R8）が `system_grouping` でマージされず、別々の独立した system として扱われてしまった。これにより、小節番号がシーケンシャル（1〜4、5〜8）にナンバリングされている。
- **修正候補 / 対処方針**:
  `system_grouping` のマージ閾値の調整、または divisi 括弧検出ロジックの改善。
